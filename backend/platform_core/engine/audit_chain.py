"""Tamper-evident audit hash chain (PHASE_01 / 01.3; columns added by migration 0007).

Every audit row written through :class:`~platform_core.engine.uow.UnitOfWork` is chained::

    chain_seq  = previous chain_seq + 1                  (1 for the first chained row)
    prev_hash  = event_hash of the previous row          (GENESIS_HASH for the first)
    event_hash = sha256( prev_hash || "\\n" || canonical_json(event) )

``canonical_json`` = the hashed fields of :data:`HASHED_FIELDS` as JSON with sorted keys, no whitespace,
UTF-8, NaN/Infinity refused; timestamps are RFC 3339 UTC with microseconds; UUIDs as lower-case strings.

Serialisation: the next sequence number needs the previous hash, so chain appends are serialised by a
transaction-scoped advisory lock (:data:`CHAIN_LOCK`). The outermost unit of work takes it **first**, before
any
business row lock, so all writers lock in the same order (no lock cycle). A rolled-back transaction or
savepoint
never leaves a sequence number behind (the next writer reads the last row visible under the lock: committed
rows
plus its own live rows), so committed sequences have no gaps.

Verification (:func:`verify_chain`) recomputes every hash in sequence order and records the result as an
append-only :class:`~platform_core.jobs.models.AuditIntegrityRun`. It reports BROKEN for: a changed field
(hash
mismatch), a broken link (prev_hash), a missing sequence number (deleted row) and an unchained row written
after
the chain started (insert that bypassed the engine). Rows written before the chain existed (PHASE_00, NULL
chain columns) are legacy and are counted but not verifiable.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, Final

from django.db import connections

from platform_core.models import AuditEvent

from .errors import EngineContractError

GENESIS_HASH: Final = "0" * 64
CHAIN_LOCK: Final = "platform_audit_chain"
HASHED_FIELDS: Final = (
    "id",
    "occurred_at",
    "actor_type",
    "actor_id",
    "request_id",
    "correlation_id",
    "session_id",
    "network_zone",
    "action",
    "outcome",
    "resource_type",
    "resource_id",
    "resource_version",
    "scope",
    "reason",
    "before",
    "after",
    "chain_seq",
    "prev_hash",
)


def _ts(value: datetime) -> str:
    if value.tzinfo is None:
        raise EngineContractError("audit timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return _ts(value)
    return value


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def jsonb_normalised(cur: Any, *values: Any) -> list[Any]:
    """The values exactly as PostgreSQL ``jsonb`` will return them (key order, numeric normalisation such as
    ``1e16`` -> ``10000000000000000``): the hash is computed over what will be read back."""
    cur.execute("SELECT " + ", ".join(["%s::jsonb::text"] * len(values)), [_dumps(v) for v in values])
    row = cur.fetchone()
    assert row is not None
    return [None if text is None else json.loads(text) for text in row]


def canonical_bytes(fields: Mapping[str, Any]) -> bytes:
    body = {name: _plain(fields.get(name)) for name in HASHED_FIELDS}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return text.encode("utf-8")


def compute_hash(prev_hash: str, fields: Mapping[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(prev_hash.encode("ascii"))
    digest.update(b"\n")
    digest.update(canonical_bytes(fields))
    return digest.hexdigest()


def _fields_of(event: AuditEvent) -> dict[str, Any]:
    return {name: getattr(event, name) for name in HASHED_FIELDS}


def acquire_chain_lock(using: str = "default") -> None:
    """Take the transaction-scoped chain lock (re-entrant within the transaction)."""
    conn = connections[using]
    if not conn.in_atomic_block:
        raise EngineContractError("the audit chain lock is transaction-scoped")
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [CHAIN_LOCK])


def append_chained(events: Iterable[AuditEvent], *, using: str = "default") -> None:
    """Insert ``events`` as the next links of the chain (must run inside the writing transaction)."""
    pending = list(events)
    if not pending:
        return
    conn = connections[using]
    if not conn.in_atomic_block:
        raise EngineContractError("audit chain appends must run inside a transaction")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0)), statement_timestamp()", [CHAIN_LOCK]
        )
        row = cur.fetchone()
        assert row is not None
        now: datetime = row[1]
        cur.execute(
            "SELECT chain_seq, event_hash FROM platform_audit_event WHERE chain_seq IS NOT NULL "
            "ORDER BY chain_seq DESC LIMIT 1"
        )
        last = cur.fetchone()
        normalised = [jsonb_normalised(cur, e.scope or {}, e.before, e.after) for e in pending]
    seq, prev = (int(last[0]), str(last[1])) if last else (0, GENESIS_HASH)
    for event, (scope, before, after) in zip(pending, normalised, strict=True):
        seq += 1
        event.occurred_at = now
        event.scope, event.before, event.after = scope, before, after
        event.chain_seq = seq
        event.prev_hash = prev
        event.event_hash = compute_hash(prev, _fields_of(event))
        event.save(using=using)
        prev = event.event_hash


# ------------------------------------------------------------------------------------------ verification
class ChainResult:
    __slots__ = ("checked", "first_broken", "last_seq", "legacy")

    def __init__(self) -> None:
        self.checked = 0
        self.legacy = 0
        self.last_seq: int | None = None
        self.first_broken: uuid.UUID | None = None


def check_chain(*, using: str = "default", batch: int = 1000) -> ChainResult:
    """Recompute the chain (read-only). Stops at the first broken row."""
    result = ChainResult()
    qs = AuditEvent.objects.using(using)
    first = qs.filter(chain_seq__isnull=False).order_by("chain_seq").first()
    if first is None:
        result.legacy = qs.filter(chain_seq__isnull=True).count()
        return result
    result.legacy = qs.filter(chain_seq__isnull=True, occurred_at__lt=first.occurred_at).count()
    # an unchained row written after the chain started bypassed the engine (raw INSERT)
    bypass = (
        qs.filter(chain_seq__isnull=True, occurred_at__gte=first.occurred_at).order_by("occurred_at").first()
    )
    expected_seq, prev = 1, GENESIS_HASH
    last_seq = 0
    while True:
        rows = list(qs.filter(chain_seq__gt=last_seq).order_by("chain_seq")[:batch])
        if not rows:
            break
        for event in rows:
            ok = (
                event.chain_seq == expected_seq
                and event.prev_hash == prev
                and event.event_hash == compute_hash(prev, _fields_of(event))
            )
            if not ok:
                result.first_broken = event.id
                return result
            result.checked += 1
            result.last_seq = expected_seq
            prev = event.event_hash
            expected_seq += 1
        last_seq = int(rows[-1].chain_seq or 0)
    if bypass is not None:
        result.first_broken = bypass.id
    return result


def verify_chain(*, using: str = "default", job_run_id: uuid.UUID | None = None) -> Any:
    """Run :func:`check_chain` and record the outcome in ``platform_audit_integrity_run`` (append-only)."""
    from platform_core.jobs.models import AuditIntegrityRun, IntegrityStatus

    from .context import db_now

    started = db_now(using)
    try:
        result = check_chain(using=using)
    except Exception:  # recorded as ERROR with a safe code, never exception text
        return AuditIntegrityRun.objects.using(using).create(
            started_at=started,
            finished_at=db_now(using),
            status=IntegrityStatus.ERROR,
            events_checked=0,
            error_code="CHECK_FAILED",
            job_run_id=job_run_id,
        )
    return AuditIntegrityRun.objects.using(using).create(
        started_at=started,
        finished_at=db_now(using),
        status=IntegrityStatus.BROKEN if result.first_broken else IntegrityStatus.OK,
        events_checked=result.checked,
        checked_up_to_seq=result.last_seq,
        first_broken_event_id=result.first_broken,
        job_run_id=job_run_id,
    )
