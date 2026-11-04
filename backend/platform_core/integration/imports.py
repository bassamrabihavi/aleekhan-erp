"""Import batches + staging (PHASE_00 / 00.6). Platform mechanics only: nothing is applied to business data.

Batch state machine (``IMPORT_BATCH_MACHINE``, docs/integration/README.md section 2)::

    RECEIVED -> STAGED -> VALIDATED -> APPLIED -> COMPENSATED
    RECEIVED | STAGED | VALIDATED -> REJECTED
    VALIDATED -> SUPERSEDED

``VALIDATED -> APPLIED``, ``VALIDATED -> SUPERSEDED`` and ``APPLIED -> COMPENSATED`` are business decisions
per source: the service always calls ``require_approved_rule(source.policy_decision_id)`` first, so in
PHASE_00 they raise 409 ``RULE_NOT_APPROVED`` (e.g. DEC-016 for Rahkaran snapshot validity / re-import
policy).

* :func:`receive_file` - provenance only (source, SHA-256, size, basename, actor, request). The bytes are
  hashed while streaming and then discarded: raw content is never stored in the DB or the repository (object
  storage wiring is a later phase). Same source + same SHA-256 => the SAME batch (idempotent, race safe via
  ``uq_import_batch_source_sha256``): ``created=False`` and an audit row ``...batch.receive_duplicate``; no
  second batch, no second event, freshness not refreshed (framework for WH-01 "single accounted snapshot").
* :func:`stage_rows` - RECEIVED -> STAGED: stores rows (sheet, row number, JSON payload, payload SHA-256).
  Rows with sensitive keys (password/salary/...) are refused before anything is stored (DEC-028).
* :func:`validate_batch` - STAGED -> VALIDATED: structural checks (``EMPTY_ROW``, ``DUPLICATE_PAYLOAD``) plus
  optional per-source validators (none is approved in PHASE_00). Updates source freshness.
* :func:`reject_batch` - by an identified user with a reason.

Every transition = one unit of work (state + audit + outbox event).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, BinaryIO, Final, NoReturn

from django.db import IntegrityError, transaction
from django.db.models.functions import Now

from platform_core.engine.context import RequestContext, db_now
from platform_core.engine.errors import (
    EngineContractError,
    FieldError,
    NotFound,
    PayloadTooLarge,
    ValidationFailed,
    VersionConflict,
)
from platform_core.engine.redaction import sensitive_paths
from platform_core.engine.rules import require_approved_rule
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import unit_of_work
from platform_core.models import ActorType

from .models import BatchStatus, ImportBatch, IntegrationSource, RowStatus, StagingRow
from .sources import get_source, require_enabled

B = BatchStatus
IMPORT_BATCH_MACHINE: Final = StateMachine(
    name="platform.integration.import_batch",
    states=frozenset(B.values),
    transitions={
        B.RECEIVED: frozenset({B.STAGED, B.REJECTED}),
        B.STAGED: frozenset({B.VALIDATED, B.REJECTED}),
        B.VALIDATED: frozenset({B.APPLIED, B.REJECTED, B.SUPERSEDED}),
        B.APPLIED: frozenset({B.COMPENSATED}),
        B.REJECTED: frozenset(),
        B.SUPERSEDED: frozenset(),
        B.COMPENSATED: frozenset(),
    },
)
# Edges that need the source's owner decision (checked per source by the service, see module docstring).
SOURCE_POLICY_GATED: Final = frozenset(
    {(B.VALIDATED, B.APPLIED), (B.VALIDATED, B.SUPERSEDED), (B.APPLIED, B.COMPENSATED)}
)

# TECHNICAL DEFAULT limits (not business rules; ops to confirm in 00.7).
MAX_FILE_BYTES: Final = 50 * 1024 * 1024
MAX_ROWS_PER_BATCH: Final = 200_000
MAX_ROW_PAYLOAD_BYTES: Final = 16 * 1024
MAX_SHEET_NAME_LEN: Final = 100
MAX_REASON_LEN: Final = 500
BULK_CHUNK: Final = 1000
HASH_CHUNK: Final = 1024 * 1024
UNIQUE_BATCH: Final = "uq_import_batch_source_sha256"

ROW_ERROR_CODE_RE: Final = re.compile(r"[A-Z][A-Z0-9_]{2,63}")
ROW_EMPTY: Final = "EMPTY_ROW"
ROW_DUPLICATE_PAYLOAD: Final = "DUPLICATE_PAYLOAD"

# Bidi controls are removed from names (they can disguise an extension, e.g. "x‮gpj.exe"); ZWNJ (U+200C),
# which Persian file names use legitimately, is kept.
_BIDI_CONTROLS: Final = frozenset(
    chr(c) for c in [*range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x200E, 0x200F]
)

RowValidator = Callable[[Mapping[str, Any]], Sequence[str]]


# ---------------------------------------------------------------------------------------------- helpers
def safe_basename(name: str) -> str:
    """Basename only (no client directory), NFC, without control/bidi characters, at most 255 characters."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = unicodedata.normalize("NFC", base)
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Cc" and ch not in _BIDI_CONTROLS)
    base = base.strip().strip(".").strip()
    return base[:255] or "unnamed"


def canonical_payload(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


@dataclass(frozen=True)
class FileDigest:
    sha256: str
    byte_size: int


def digest_content(content: bytes | BinaryIO, *, max_bytes: int = MAX_FILE_BYTES) -> FileDigest:
    """SHA-256 + size while streaming; refuses empty files and files above ``max_bytes`` (nothing is kept)."""
    h = hashlib.sha256()
    size = 0
    if isinstance(content, bytes | bytearray | memoryview):
        data = bytes(content)
        size = len(data)
        if size > max_bytes:
            raise PayloadTooLarge("file exceeds the import size limit")
        h.update(data)
    else:
        while True:
            chunk = content.read(HASH_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise PayloadTooLarge("file exceeds the import size limit")
            h.update(chunk)
    if size == 0:
        raise ValidationFailed("empty file", errors=[FieldError(field="file", code="EMPTY_FILE")])
    return FileDigest(h.hexdigest(), size)


def _is_unique_violation(exc: IntegrityError, name: str) -> bool:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None) == name


def _lock_batch(batch_id: Any, using: str, expected_version: int | None = None) -> ImportBatch:
    batch = (
        ImportBatch.objects.using(using)
        .select_for_update()
        .select_related("source")
        .filter(pk=batch_id)
        .first()
    )
    if batch is None:
        raise NotFound()
    if expected_version is not None and batch.row_version != expected_version:
        raise VersionConflict("row_version does not match the current version")
    return batch


def _event_payload(batch: ImportBatch, **extra: Any) -> dict[str, Any]:
    return {"batch_id": str(batch.id), "source_code": batch.source.code, **extra}


# ---------------------------------------------------------------------------------------------- receive
@dataclass(frozen=True)
class ReceiveResult:
    batch: ImportBatch
    created: bool


def receive_file(
    ctx: RequestContext,
    *,
    source_code: str,
    content: bytes | BinaryIO,
    original_name: str,
    source_as_of: datetime | None = None,
    max_bytes: int = MAX_FILE_BYTES,
    using: str = "default",
) -> ReceiveResult:
    if source_as_of is not None and source_as_of.tzinfo is None:
        raise ValidationFailed(errors=[FieldError(field="source_as_of", code="TIMEZONE_REQUIRED")])
    source = get_source(source_code, using=using)
    require_enabled(source)
    digest = digest_content(content, max_bytes=max_bytes)
    name = safe_basename(original_name)
    try:
        with unit_of_work(ctx, using=using) as uow:
            batch = ImportBatch(
                source=source,
                file_sha256=digest.sha256,
                byte_size=digest.byte_size,
                original_name=name,
                actor_type=ctx.actor.actor_type,
                actor_id=ctx.actor.actor_id,
                request_id=ctx.request_id,
                correlation_id=ctx.effective_correlation_id,
                source_as_of=source_as_of,
            )
            batch.save(using=using, force_insert=True)
            batch.refresh_from_db(using=using)
            uow.audit(
                action="platform.integration.batch.receive",
                resource_type="platform.import_batch",
                resource_id=str(batch.id),
                resource_version=batch.row_version,
                after={"status": batch.status, "sha256": digest.sha256, "byte_size": digest.byte_size},
                scope={"source_code": source.code},
            )
            uow.emit(
                event_type="platform.integration.batch_received",
                aggregate_type="platform.import_batch",
                aggregate_id=str(batch.id),
                aggregate_version=batch.row_version,
                payload=_event_payload(batch, sha256=digest.sha256, byte_size=digest.byte_size),
            )
        return ReceiveResult(batch, created=True)
    except IntegrityError as exc:
        if not _is_unique_violation(exc, UNIQUE_BATCH):
            raise
    existing = (
        ImportBatch.objects.using(using)
        .select_related("source")
        .get(source=source, file_sha256=digest.sha256)
    )
    with unit_of_work(ctx, require_event=False, using=using) as uow:
        uow.audit(
            action="platform.integration.batch.receive_duplicate",
            resource_type="platform.import_batch",
            resource_id=str(existing.id),
            resource_version=existing.row_version,
            scope={"source_code": source.code},
        )
    return ReceiveResult(existing, created=False)


# ---------------------------------------------------------------------------------------------- stage
@dataclass(frozen=True)
class StagingInput:
    row_number: int
    payload: Mapping[str, Any]
    sheet_name: str = ""


def _check_rows(rows: Iterable[StagingInput]) -> list[tuple[StagingInput, bytes]]:
    out: list[tuple[StagingInput, bytes]] = []
    errors: list[FieldError] = []
    seen: set[tuple[str, int]] = set()
    for i, row in enumerate(rows):
        if len(out) + 1 > MAX_ROWS_PER_BATCH:
            raise PayloadTooLarge("too many rows for one batch")
        where = f"rows[{i}]"
        if not isinstance(row.payload, Mapping):
            errors.append(FieldError(field=f"{where}.payload", code="NOT_AN_OBJECT"))
            continue
        if not isinstance(row.row_number, int) or isinstance(row.row_number, bool) or row.row_number < 1:
            errors.append(FieldError(field=f"{where}.row_number", code="OUT_OF_RANGE"))
            continue
        if not isinstance(row.sheet_name, str) or len(row.sheet_name) > MAX_SHEET_NAME_LEN:
            errors.append(FieldError(field=f"{where}.sheet_name", code="INVALID"))
            continue
        position = (row.sheet_name, row.row_number)
        if position in seen:
            errors.append(FieldError(field=f"{where}.row_number", code="DUPLICATE_POSITION"))
            continue
        seen.add(position)
        leaked = list(sensitive_paths(dict(row.payload)))
        if leaked:  # paths only, never values
            errors.append(FieldError(field=f"{where}.payload.{leaked[0]}", code="SENSITIVE_FIELD"))
            continue
        try:
            raw = canonical_payload(row.payload)
        except (TypeError, ValueError):
            errors.append(FieldError(field=f"{where}.payload", code="NOT_JSON"))
            continue
        if len(raw) > MAX_ROW_PAYLOAD_BYTES:
            errors.append(FieldError(field=f"{where}.payload", code="TOO_LARGE"))
            continue
        out.append((row, raw))
    if errors:
        raise ValidationFailed("rows refused; nothing was staged", errors=errors)
    return out


def stage_rows(
    ctx: RequestContext,
    batch_id: Any,
    rows: Iterable[StagingInput],
    *,
    expected_version: int | None = None,
    using: str = "default",
) -> ImportBatch:
    checked = _check_rows(rows)
    with unit_of_work(ctx, using=using) as uow:
        batch = _lock_batch(batch_id, using, expected_version)
        IMPORT_BATCH_MACHINE.assert_transition(batch.status, B.STAGED)
        objs = [
            StagingRow(
                batch=batch,
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                payload=json.loads(raw),
                payload_sha256=hashlib.sha256(raw).hexdigest(),
            )
            for row, raw in checked
        ]
        for start in range(0, len(objs), BULK_CHUNK):
            StagingRow.objects.using(using).bulk_create(objs[start : start + BULK_CHUNK])
        ImportBatch.objects.using(using).filter(pk=batch.pk).update(
            status=B.STAGED, staged_at=Now(), row_count=len(objs)
        )
        batch.refresh_from_db(using=using)
        uow.audit(
            action="platform.integration.batch.stage",
            resource_type="platform.import_batch",
            resource_id=str(batch.id),
            resource_version=batch.row_version,
            before={"status": B.RECEIVED},
            after={"status": B.STAGED, "row_count": len(objs)},
            scope={"source_code": batch.source.code},
        )
        uow.emit(
            event_type="platform.integration.batch_staged",
            aggregate_type="platform.import_batch",
            aggregate_id=str(batch.id),
            aggregate_version=batch.row_version,
            payload=_event_payload(batch, row_count=len(objs)),
        )
    return batch


# ---------------------------------------------------------------------------------------------- validate
def _is_empty(payload: Mapping[str, Any]) -> bool:
    return all(v is None or (isinstance(v, str) and not v.strip()) for v in payload.values())


def _row_errors(row: StagingRow, seen_hashes: set[str], validators: Sequence[RowValidator]) -> list[str]:
    codes: list[str] = []
    if _is_empty(row.payload):
        codes.append(ROW_EMPTY)
    if row.payload_sha256 in seen_hashes:
        codes.append(ROW_DUPLICATE_PAYLOAD)
    seen_hashes.add(row.payload_sha256)
    for validator in validators:
        for code in validator(row.payload):
            if not isinstance(code, str) or not ROW_ERROR_CODE_RE.fullmatch(code):
                raise EngineContractError("row validators must return UPPER_SNAKE error codes")
            if code not in codes:
                codes.append(code)
    return codes


def validate_batch(
    ctx: RequestContext,
    batch_id: Any,
    *,
    validators: Sequence[RowValidator] = (),
    expected_version: int | None = None,
    using: str = "default",
) -> ImportBatch:
    with unit_of_work(ctx, using=using) as uow:
        batch = _lock_batch(batch_id, using, expected_version)
        IMPORT_BATCH_MACHINE.assert_transition(batch.status, B.VALIDATED)
        seen: set[str] = set()
        error_rows = 0
        pending: list[StagingRow] = []
        qs = StagingRow.objects.using(using).filter(batch=batch).order_by("sheet_name", "row_number", "id")
        for row in qs.iterator(chunk_size=BULK_CHUNK):
            codes = _row_errors(row, seen, validators)
            row.error_codes = codes
            row.validation_status = RowStatus.ERROR if codes else RowStatus.PENDING_REVIEW
            error_rows += bool(codes)
            pending.append(row)
            if len(pending) >= BULK_CHUNK:
                StagingRow.objects.using(using).bulk_update(pending, ["validation_status", "error_codes"])
                pending = []
        if pending:
            StagingRow.objects.using(using).bulk_update(pending, ["validation_status", "error_codes"])
        now = db_now(using)
        ImportBatch.objects.using(using).filter(pk=batch.pk).update(
            status=B.VALIDATED, validated_at=now, error_row_count=error_rows
        )
        batch.refresh_from_db(using=using)
        valid_rows = batch.row_count - error_rows
        if valid_rows > 0:
            IntegrationSource.objects.using(using).filter(pk=batch.source_id).update(
                last_success_at=now, last_success_batch=batch, last_as_of=batch.source_as_of
            )
        uow.audit(
            action="platform.integration.batch.validate",
            resource_type="platform.import_batch",
            resource_id=str(batch.id),
            resource_version=batch.row_version,
            before={"status": B.STAGED},
            after={"status": B.VALIDATED, "row_count": batch.row_count, "error_row_count": error_rows},
            scope={"source_code": batch.source.code},
        )
        uow.emit(
            event_type="platform.integration.batch_validated",
            aggregate_type="platform.import_batch",
            aggregate_id=str(batch.id),
            aggregate_version=batch.row_version,
            payload=_event_payload(batch, row_count=batch.row_count, error_row_count=error_rows),
        )
    return batch


# ---------------------------------------------------------------------------------------- reject / gated
def reject_batch(
    ctx: RequestContext,
    batch_id: Any,
    *,
    reason: str,
    expected_version: int | None = None,
    using: str = "default",
) -> ImportBatch:
    if ctx.actor.actor_type != ActorType.USER:
        raise EngineContractError("rejecting a batch must be performed by an identified user")
    note = (reason or "").strip()
    if not note or len(note) > MAX_REASON_LEN:
        raise ValidationFailed(
            errors=[FieldError(field="reason", code="REQUIRED" if not note else "TOO_LONG")]
        )
    with unit_of_work(ctx, using=using) as uow:
        batch = _lock_batch(batch_id, using, expected_version)
        before = batch.status
        IMPORT_BATCH_MACHINE.assert_transition(before, B.REJECTED)
        ImportBatch.objects.using(using).filter(pk=batch.pk).update(
            status=B.REJECTED, closed_at=Now(), close_reason=note
        )
        batch.refresh_from_db(using=using)
        uow.audit(
            action="platform.integration.batch.reject",
            resource_type="platform.import_batch",
            resource_id=str(batch.id),
            resource_version=batch.row_version,
            before={"status": before},
            after={"status": B.REJECTED},
            reason=note,
            scope={"source_code": batch.source.code},
        )
        uow.emit(
            event_type="platform.integration.batch_rejected",
            aggregate_type="platform.import_batch",
            aggregate_id=str(batch.id),
            aggregate_version=batch.row_version,
            payload=_event_payload(batch),
        )
    return batch


def _gated(batch_id: Any, target: str, using: str) -> NoReturn:
    with transaction.atomic(using=using):
        batch = _lock_batch(batch_id, using)
        IMPORT_BATCH_MACHINE.assert_transition(batch.status, target)
        require_approved_rule(
            batch.source.policy_decision_id, rule=f"platform.integration.{target.lower()}:{batch.source.code}"
        )
    # Unreachable in PHASE_00 (no rule is approved). A later phase implements the owning module's apply step.
    raise EngineContractError(f"no {target} implementation exists for source {batch.source.code}")


def apply_batch(ctx: RequestContext, batch_id: Any, *, using: str = "default") -> ImportBatch:
    """VALIDATED -> APPLIED: blocked (RULE_NOT_APPROVED with the source's policy decision)."""
    _gated(batch_id, B.APPLIED, using)


def supersede_batch(ctx: RequestContext, batch_id: Any, *, using: str = "default") -> ImportBatch:
    """VALIDATED -> SUPERSEDED (re-import policy): blocked (RULE_NOT_APPROVED)."""
    _gated(batch_id, B.SUPERSEDED, using)


def compensate_batch(ctx: RequestContext, batch_id: Any, *, using: str = "default") -> ImportBatch:
    """APPLIED -> COMPENSATED (rollback-with-compensation): blocked (RULE_NOT_APPROVED)."""
    _gated(batch_id, B.COMPENSATED, using)
