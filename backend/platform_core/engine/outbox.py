"""Outbox dispatcher: delivery state machine, deterministic backoff, SKIP LOCKED claim, pluggable publisher.

State machine (docs/discovery/STATE_TRANSITIONS.md 1.1)::

    PENDING -> DISPATCHED -> ACKED
    PENDING | DISPATCHED -> FAILED (attempt counted, next_attempt_at = now + backoff) -> PENDING
    FAILED -> DEAD_LETTER (attempts >= max_attempts; visible to Admin)
    DEAD_LETTER -> PENDING (authorised admin replay only, audited)
    DEAD_LETTER -> DISCARDED (terminal; the owner only, from the server console, reason required, audited -
                              PHASE_01 / 01.7, REV-0129: a poison head no longer blocks its aggregate forever)

Composite moves are validated step by step against the machine and written in one UPDATE: a retry claim
is ``FAILED -> PENDING -> DISPATCHED``; a final failure is ``DISPATCHED -> FAILED -> DEAD_LETTER``.

Delivery is *at least once*: a crash after ``publish`` and before the ACK leaves the row DISPATCHED; after the
lease, :func:`recover_stale` counts it as a failed attempt and it is published again. Consumers dedupe by
``event_id`` (contract: "Handlers idempotent").

No broker is wired in PHASE_00: callers pass an :class:`OutboxPublisher`. Shipped implementations: the
in-process consumer registry ``platform_core.engine.consumers.RegistryPublisher`` (step 00.6: handlers + inbox
dedupe + compensation hook) and the test double in ``platform_core.engine.testing`` (refused outside
dev/test). Retry/backoff numbers in :class:`OutboxPolicy` are technical defaults, not business rules
(``INTEGRATION_POLICY`` below = 00.6 defaults, docs/integration/README.md section 3).

Determinism for tests (00.6): the jitter source is injectable (``OutboxPolicy.jitter_source``) and every
dispatcher entry point accepts ``now=`` (an explicit clock instead of the database clock).
"""

from __future__ import annotations

import hashlib
import itertools
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from django.db import transaction
from django.db.models import DateTimeField, DurationField, Exists, ExpressionWrapper, F, OuterRef, Value
from django.db.models.functions import Now

from platform_core.models import ActorType, AuditOutcome, DeliveryStatus, OutboxEvent

from .context import RequestContext, db_now
from .errors import EngineContractError, NotFound, StateTransitionNotAllowed
from .state import StateMachine
from .uow import unit_of_work

S = DeliveryStatus
OUTBOX_DELIVERY_MACHINE = StateMachine(
    name="platform.outbox.delivery",
    states=frozenset(S.values),
    transitions={
        S.PENDING: frozenset({S.DISPATCHED, S.FAILED}),
        S.DISPATCHED: frozenset({S.ACKED, S.FAILED}),
        S.FAILED: frozenset({S.PENDING, S.DEAD_LETTER}),
        S.DEAD_LETTER: frozenset({S.PENDING, S.DISCARDED}),
        S.ACKED: frozenset(),
        S.DISCARDED: frozenset(),
    },
)

MAX_ERROR_LEN = 500


def _assert_path(*states: str) -> None:
    for src, dst in itertools.pairwise(states):
        OUTBOX_DELIVERY_MACHINE.assert_transition(src, dst)


# ---------------------------------------------------------------------------------------------- backoff
JitterSource = Callable[[str, int], int]
"""``(jitter_key, attempt) -> int in [0, 2**64)``; the default is :func:`sha256_jitter` (deterministic)."""

JITTER_SPACE = 2**64


def sha256_jitter(jitter_key: str, attempt: int) -> int:
    return int.from_bytes(hashlib.sha256(f"{jitter_key}:{attempt}".encode()).digest()[:8], "big")


def backoff_delay(
    attempt: int,
    *,
    base: timedelta,
    factor: int,
    cap: timedelta,
    jitter_permille: int = 0,
    jitter_key: str = "",
    jitter_source: JitterSource | None = None,
) -> timedelta:
    """Deterministic exponential backoff after ``attempt`` failed attempts (attempt >= 1).

    ``delay = min(cap, base * factor ** (attempt - 1))`` in integer microseconds, then an optional
    jitter that shortens the delay by up to ``jitter_permille``/1000. The jitter sample comes from
    ``jitter_source(jitter_key, attempt)`` (default ``sha256(jitter_key:attempt)``: same inputs -> same delay,
    different events spread out); tests may inject a fixed source.
    """
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    if factor < 1:
        raise ValueError("factor must be >= 1")
    if not 0 <= jitter_permille <= 1000:
        raise ValueError("jitter_permille must be within 0..1000")
    base_us = _us(base)
    cap_us = _us(cap)
    if base_us <= 0 or cap_us < base_us:
        raise ValueError("require 0 < base <= cap")
    delay_us = base_us
    for _ in range(attempt - 1):
        if delay_us >= cap_us:
            break
        delay_us *= factor
    delay_us = min(delay_us, cap_us)
    if jitter_permille:
        h = (jitter_source or sha256_jitter)(jitter_key, attempt)
        if not 0 <= h < JITTER_SPACE:
            raise ValueError("jitter_source must return an int in [0, 2**64)")
        delay_us -= (delay_us * jitter_permille * h) // (1000 * JITTER_SPACE)
    return timedelta(microseconds=delay_us)


def _us(td: timedelta) -> int:
    return (td.days * 86_400 + td.seconds) * 1_000_000 + td.microseconds


@dataclass(frozen=True)
class OutboxPolicy:
    max_attempts: int = 10
    base_delay: timedelta = timedelta(seconds=2)
    factor: int = 2
    max_delay: timedelta = timedelta(hours=1)
    jitter_permille: int = 0
    lease: timedelta = timedelta(minutes=5)
    batch_size: int = 100
    jitter_source: JitterSource | None = field(default=None, compare=False, repr=False)
    # 01.6: deliver the events of one aggregate in order (see claim_batch)
    per_aggregate_order: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.batch_size < 1:
            raise ValueError("max_attempts and batch_size must be >= 1")
        if self.lease <= timedelta(0):
            raise ValueError("lease must be positive")
        backoff_delay(1, base=self.base_delay, factor=self.factor, cap=self.max_delay)  # validates params

    def delay_after(self, attempt: int, event_id: uuid.UUID) -> timedelta:
        return backoff_delay(
            attempt,
            base=self.base_delay,
            factor=self.factor,
            cap=self.max_delay,
            jitter_permille=self.jitter_permille,
            jitter_key=str(event_id),
            jitter_source=self.jitter_source,
        )


# TECHNICAL DEFAULT retry policy for integration consumers (00.6; not a business rule, ops to confirm in
# 00.7):
# 8 attempts, 5 s * 2^(n-1) capped at 30 min, up to 25 % deterministic jitter, 5 min lease, batches of 50.
# Back-off before DEAD_LETTER (no jitter): 5+10+20+40+80+160+320 s = 635 s (~10.6 min) plus processing time.
INTEGRATION_POLICY = OutboxPolicy(
    max_attempts=8,
    base_delay=timedelta(seconds=5),
    factor=2,
    max_delay=timedelta(minutes=30),
    jitter_permille=250,
    lease=timedelta(minutes=5),
    batch_size=50,
)


# ---------------------------------------------------------------------------------------------- publisher
@dataclass(frozen=True)
class EventEnvelope:
    """What a publisher receives. ``event_id`` is the consumer dedupe key."""

    event_id: uuid.UUID
    event_type: str
    schema_version: int
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    occurred_at: datetime
    actor_type: str
    actor_id: uuid.UUID | None
    request_id: uuid.UUID | None
    correlation_id: uuid.UUID | None
    causation_id: uuid.UUID | None
    payload: Mapping[str, Any]
    attempt: int
    # 01.6 provenance of the producing code: producer module, build commit, schema migration ('' = unknown)
    provenance: Mapping[str, str] = field(default_factory=dict)


class OutboxPublisher(Protocol):
    def publish(self, envelope: EventEnvelope) -> None:
        """Deliver or raise. Must be safe to call again for the same ``event_id``."""


class PublishError(Exception):
    """Publisher failure with a *safe* machine code (stored in ``last_error``; no message text is stored).

    ``permanent=True`` (01.6): retrying cannot help (e.g. an incompatible schema version) - the event goes to
    DEAD_LETTER at once instead of after ``max_attempts`` (poison message; compensation hook runs)."""

    def __init__(self, safe_code: str, *, permanent: bool = False) -> None:
        super().__init__(safe_code)
        self.safe_code = safe_code
        self.permanent = permanent


def _safe_error(exc: BaseException) -> str:
    # Never persist str(exc): it may contain hosts, credentials or payload data.
    code = exc.safe_code if isinstance(exc, PublishError) else type(exc).__name__
    return code[:MAX_ERROR_LEN]


# ---------------------------------------------------------------------------------------------- dispatch
@dataclass(frozen=True)
class ClaimedEvent:
    pk: int
    row_version: int
    envelope: EventEnvelope


def _envelope(row: OutboxEvent, attempt: int) -> EventEnvelope:
    return EventEnvelope(
        event_id=row.event_id,
        event_type=row.event_type,
        schema_version=row.schema_version,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        aggregate_version=row.aggregate_version,
        occurred_at=row.occurred_at,
        actor_type=row.actor_type,
        actor_id=row.actor_id,
        request_id=row.request_id,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
        payload=dict(row.payload),
        attempt=attempt,
        provenance={
            "producer": row.producer,
            "build_commit": row.build_commit,
            "schema_migration": row.schema_migration,
        },
    )


SETTLED = (S.ACKED, S.DISCARDED)
"""States that no longer hold later events of the same aggregate back (01.7: DISCARDED counts as settled)."""


def _earlier_open_event() -> Exists:
    """An earlier (lower ``id``) not yet settled (ACKED / DISCARDED) event of the same aggregate exists."""
    return Exists(
        OutboxEvent.objects.filter(
            aggregate_type=OuterRef("aggregate_type"),
            aggregate_id=OuterRef("aggregate_id"),
            id__lt=OuterRef("id"),
        ).exclude(delivery_status__in=SETTLED)
    )


def claim_batch(
    policy: OutboxPolicy, *, using: str = "default", now: datetime | None = None
) -> list[ClaimedEvent]:
    """Claim due PENDING/FAILED rows with ``FOR UPDATE SKIP LOCKED`` and mark them DISPATCHED.

    Concurrent dispatchers never claim the same row (each locked row is skipped by the others). ``now``
    overrides the database clock (tests / deterministic simulations).

    Per-aggregate ordering (01.6, ``policy.per_aggregate_order``): a row is claimed only if no earlier row of
    the same aggregate is still undelivered (PENDING / FAILED / DISPATCHED / DEAD_LETTER). So the events of
    one aggregate are delivered one after the other in ``id`` order (= commit order: every unit of work holds
    the audit chain lock from its start to its commit, so outbox ids are allocated in commit order); a failing
    event holds back the later events of *its* aggregate only, and a DEAD_LETTER head blocks its aggregate
    until it is replayed or discarded by the owner (:func:`discard_dead_letter`, 01.7) - visible as
    ``blocked_aggregates`` in the health snapshot. Other aggregates are not affected.
    """
    with transaction.atomic(using=using):
        now = now if now is not None else db_now(using)
        qs = OutboxEvent.objects.using(using).filter(
            delivery_status__in=[S.PENDING, S.FAILED], next_attempt_at__lte=now
        )
        if policy.per_aggregate_order:
            qs = qs.exclude(_earlier_open_event())
        rows = list(
            qs.select_for_update(skip_locked=True).order_by("next_attempt_at", "id")[: policy.batch_size]
        )
        claimed: list[ClaimedEvent] = []
        for row in rows:
            if row.delivery_status == S.FAILED:
                _assert_path(S.FAILED, S.PENDING, S.DISPATCHED)
            else:
                _assert_path(S.PENDING, S.DISPATCHED)
            claimed.append(ClaimedEvent(row.pk, row.row_version + 1, _envelope(row, row.attempts + 1)))
        if rows:
            OutboxEvent.objects.using(using).filter(pk__in=[r.pk for r in rows]).update(
                delivery_status=S.DISPATCHED, dispatched_at=now, attempts=F("attempts") + 1
            )
    return claimed


def mark_delivered(claimed: ClaimedEvent, *, using: str = "default") -> bool:
    _assert_path(S.DISPATCHED, S.ACKED)
    updated = (
        OutboxEvent.objects.using(using)
        .filter(pk=claimed.pk, delivery_status=S.DISPATCHED, row_version=claimed.row_version)
        .update(delivery_status=S.ACKED, acked_at=Now())
    )
    return updated == 1


def mark_failed(
    claimed: ClaimedEvent,
    error: str,
    policy: OutboxPolicy,
    *,
    using: str = "default",
    now: datetime | None = None,
    permanent: bool = False,
) -> str | None:
    """DISPATCHED -> FAILED (backoff) or -> FAILED -> DEAD_LETTER. Returns the new status, None if lost.

    ``next_attempt_at = now + backoff``; ``now`` defaults to the statement clock of the UPDATE itself.
    ``permanent`` (a :class:`PublishError` with ``permanent=True``) dead-letters at once.
    """
    attempt = claimed.envelope.attempt
    if permanent or attempt >= policy.max_attempts:
        _assert_path(S.DISPATCHED, S.FAILED, S.DEAD_LETTER)
        new_status: str = S.DEAD_LETTER
        delay = timedelta(0)
    else:
        _assert_path(S.DISPATCHED, S.FAILED)
        new_status = S.FAILED
        delay = policy.delay_after(attempt, claimed.envelope.event_id)
    # next_attempt_at = statement_timestamp() + delay: same clock and instant as the trigger's updated_at
    next_at: Any = (
        now + delay
        if now is not None
        else ExpressionWrapper(
            Now() + Value(delay, output_field=DurationField()), output_field=DateTimeField()
        )
    )
    updated = (
        OutboxEvent.objects.using(using)
        .filter(pk=claimed.pk, delivery_status=S.DISPATCHED, row_version=claimed.row_version)
        .update(delivery_status=new_status, next_attempt_at=next_at, last_error=error[:MAX_ERROR_LEN])
    )
    return new_status if updated == 1 else None


@dataclass
class DispatchStats:
    claimed: int = 0
    delivered: int = 0
    failed: int = 0
    dead_lettered: int = 0
    lost: int = 0
    compensation_errors: int = 0
    errors: list[str] = field(default_factory=list)


DeadLetterHook = Callable[[EventEnvelope, str], object]
"""Called after an event became DEAD_LETTER (``envelope``, safe failure code). See ``engine.consumers``."""


def _after_dead_letter(
    hook: DeadLetterHook | None, envelope: EventEnvelope, error: str, stats: DispatchStats
) -> None:
    if hook is None:
        return
    try:
        hook(envelope, error)
    except Exception as exc:  # never crash the dispatcher; consumers.sweep_dead_letters() retries later
        stats.compensation_errors += 1
        stats.errors.append(f"COMPENSATION_FAILED:{type(exc).__name__}")


def dispatch_once(
    publisher: OutboxPublisher,
    policy: OutboxPolicy,
    *,
    using: str = "default",
    now: datetime | None = None,
    on_dead_letter: DeadLetterHook | None = None,
) -> DispatchStats:
    """One pass: claim a batch, publish each event outside the claim transaction, record the outcome.

    ``on_dead_letter`` runs after an event reached DEAD_LETTER (compensation hook, step 00.6).
    """
    stats = DispatchStats()
    for claimed in claim_batch(policy, using=using, now=now):
        stats.claimed += 1
        try:
            publisher.publish(claimed.envelope)
        except Exception as exc:
            error = _safe_error(exc)
            stats.errors.append(error)
            permanent = isinstance(exc, PublishError) and exc.permanent
            status = mark_failed(claimed, error, policy, using=using, now=now, permanent=permanent)
            if status == S.DEAD_LETTER:
                stats.dead_lettered += 1
                _after_dead_letter(on_dead_letter, claimed.envelope, error, stats)
            elif status == S.FAILED:
                stats.failed += 1
            else:
                stats.lost += 1
            continue
        if mark_delivered(claimed, using=using):
            stats.delivered += 1
        else:
            stats.lost += 1
    return stats


def recover_stale(
    policy: OutboxPolicy,
    *,
    using: str = "default",
    now: datetime | None = None,
    on_dead_letter: DeadLetterHook | None = None,
) -> int:
    """DISPATCHED rows older than the lease (dispatcher crashed) count as a failed attempt.

    A recovered row that reaches ``max_attempts`` becomes DEAD_LETTER; ``on_dead_letter`` then runs after the
    recovery transaction committed.
    """
    dead: list[EventEnvelope] = []
    with transaction.atomic(using=using):
        cutoff = (now if now is not None else db_now(using)) - policy.lease
        rows = list(
            OutboxEvent.objects.using(using)
            .select_for_update(skip_locked=True)
            .filter(delivery_status=S.DISPATCHED, dispatched_at__lte=cutoff)
            .order_by("dispatched_at", "id")[: policy.batch_size]
        )
        recovered = 0
        for row in rows:
            claimed = ClaimedEvent(row.pk, row.row_version, _envelope(row, row.attempts))
            status = mark_failed(claimed, "LEASE_EXPIRED", policy, using=using, now=now)
            if status is not None:
                recovered += 1
            if status == S.DEAD_LETTER:
                dead.append(claimed.envelope)
    stats = DispatchStats()
    for envelope in dead:
        _after_dead_letter(on_dead_letter, envelope, "LEASE_EXPIRED", stats)
    return recovered


def replay_dead_letter(
    ctx: RequestContext, event_id: uuid.UUID, *, reason: str, using: str = "default"
) -> None:
    """DEAD_LETTER -> PENDING by an admin (audited). RBAC for this action is enforced by the API layer."""
    if ctx.actor.actor_type != ActorType.USER:
        raise EngineContractError("dead-letter replay must be performed by an identified user")
    if not reason.strip():
        raise EngineContractError("dead-letter replay requires a reason")
    with unit_of_work(ctx, require_event=False, using=using) as uow:
        row = OutboxEvent.objects.using(using).select_for_update().filter(event_id=event_id).first()
        if row is None:
            raise NotFound()
        if row.delivery_status != S.DEAD_LETTER:  # FAILED -> PENDING is the dispatcher's move, not admin's
            raise StateTransitionNotAllowed(f"replay needs DEAD_LETTER, row is {row.delivery_status}")
        OUTBOX_DELIVERY_MACHINE.assert_transition(row.delivery_status, S.PENDING)
        OutboxEvent.objects.using(using).filter(pk=row.pk).update(
            delivery_status=S.PENDING, attempts=0, next_attempt_at=db_now(using), last_error=""
        )
        uow.audit(
            action="platform.outbox.replay",
            resource_type="platform.outbox_event",
            resource_id=str(row.event_id),
            resource_version=row.row_version + 1,
            outcome=AuditOutcome.SUCCESS,
            before={"delivery_status": row.delivery_status, "attempts": row.attempts},
            after={"delivery_status": S.PENDING, "attempts": 0},
            reason=reason,
        )


def discard_dead_letter(
    ctx: RequestContext, event_id: uuid.UUID, *, reason: str, using: str = "default"
) -> None:
    """DEAD_LETTER -> DISCARDED (terminal), audited with the reason (PHASE_01 / 01.7, REV-0129).

    The event is never delivered; later events of the same aggregate are released (``SETTLED``). Who may do
    this (the owner only, from the server console) is enforced by the caller layer in the same transaction
    (``platform_core.ops.dead_letters``); there is no HTTP operation for it in the contract. A compensation
    record of the dead letter (if any) is left as it is: a human still owns the business consequence.
    """
    if ctx.actor.actor_type != ActorType.USER:
        raise EngineContractError("dead-letter discard must be performed by an identified user")
    text = reason.strip()
    if len(text) < 3:
        raise EngineContractError("dead-letter discard requires a reason")
    with unit_of_work(ctx, require_event=False, using=using) as uow:
        row = OutboxEvent.objects.using(using).select_for_update().filter(event_id=event_id).first()
        if row is None:
            raise NotFound()
        if row.delivery_status != S.DEAD_LETTER:
            raise StateTransitionNotAllowed(f"discard needs DEAD_LETTER, row is {row.delivery_status}")
        OUTBOX_DELIVERY_MACHINE.assert_transition(row.delivery_status, S.DISCARDED)
        OutboxEvent.objects.using(using).filter(pk=row.pk).update(
            delivery_status=S.DISCARDED, discarded_at=db_now(using)
        )
        uow.audit(
            action="platform.outbox.discard",
            resource_type="platform.outbox_event",
            resource_id=str(row.event_id),
            resource_version=row.row_version + 1,
            outcome=AuditOutcome.SUCCESS,
            before={"delivery_status": row.delivery_status, "attempts": row.attempts},
            after={"delivery_status": S.DISCARDED},
            scope={"event_type": row.event_type, "aggregate_type": row.aggregate_type},
            reason=text[:500],
        )
