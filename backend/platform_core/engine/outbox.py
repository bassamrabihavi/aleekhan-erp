"""Outbox dispatcher: delivery state machine, deterministic backoff, SKIP LOCKED claim, pluggable publisher.

State machine (docs/discovery/STATE_TRANSITIONS.md 1.1)::

    PENDING -> DISPATCHED -> ACKED
    PENDING | DISPATCHED -> FAILED (attempt counted, next_attempt_at = now + backoff) -> PENDING
    FAILED -> DEAD_LETTER (attempts >= max_attempts; visible to Admin)
    DEAD_LETTER -> PENDING (authorised admin replay only, audited)

Composite moves are validated step by step against the machine and written in one UPDATE: a retry claim
is ``FAILED -> PENDING -> DISPATCHED``; a final failure is ``DISPATCHED -> FAILED -> DEAD_LETTER``.

Delivery is *at least once*: a crash after ``publish`` and before the ACK leaves the row DISPATCHED; after the
lease, :func:`recover_stale` counts it as a failed attempt and it is published again. Consumers dedupe by
``event_id`` (contract: "Handlers idempotent").

No broker is wired in PHASE_00: callers pass an :class:`OutboxPublisher`. The only implementation shipped is
the test double in ``platform_core.engine.testing`` (refused outside dev/test). Retry/backoff numbers in
:class:`OutboxPolicy` are technical defaults, not business rules; integration tuning is step 00.6.
"""

from __future__ import annotations

import hashlib
import itertools
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from django.db import transaction
from django.db.models import DateTimeField, DurationField, ExpressionWrapper, F, Value
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
        S.DEAD_LETTER: frozenset({S.PENDING}),
        S.ACKED: frozenset(),
    },
)

MAX_ERROR_LEN = 500


def _assert_path(*states: str) -> None:
    for src, dst in itertools.pairwise(states):
        OUTBOX_DELIVERY_MACHINE.assert_transition(src, dst)


# ---------------------------------------------------------------------------------------------- backoff
def backoff_delay(
    attempt: int,
    *,
    base: timedelta,
    factor: int,
    cap: timedelta,
    jitter_permille: int = 0,
    jitter_key: str = "",
) -> timedelta:
    """Deterministic exponential backoff after ``attempt`` failed attempts (attempt >= 1).

    ``delay = min(cap, base * factor ** (attempt - 1))`` in integer microseconds, then an optional
    *deterministic* jitter that shortens the delay by up to ``jitter_permille``/1000, derived from
    ``sha256(jitter_key:attempt)`` (same inputs -> same delay; different events spread out).
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
        h = int.from_bytes(hashlib.sha256(f"{jitter_key}:{attempt}".encode()).digest()[:8], "big")
        delay_us -= (delay_us * jitter_permille * h) // (1000 * 2**64)
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


class OutboxPublisher(Protocol):
    def publish(self, envelope: EventEnvelope) -> None:
        """Deliver or raise. Must be safe to call again for the same ``event_id``."""


class PublishError(Exception):
    """Publisher failure with a *safe* machine code (stored in ``last_error``; no message text is stored)."""

    def __init__(self, safe_code: str) -> None:
        super().__init__(safe_code)
        self.safe_code = safe_code


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
    )


def claim_batch(policy: OutboxPolicy, *, using: str = "default") -> list[ClaimedEvent]:
    """Claim due PENDING/FAILED rows with ``FOR UPDATE SKIP LOCKED`` and mark them DISPATCHED.

    Concurrent dispatchers never claim the same row (each locked row is skipped by the others).
    """
    with transaction.atomic(using=using):
        now = db_now(using)
        rows = list(
            OutboxEvent.objects.using(using)
            .select_for_update(skip_locked=True)
            .filter(delivery_status__in=[S.PENDING, S.FAILED], next_attempt_at__lte=now)
            .order_by("next_attempt_at", "id")[: policy.batch_size]
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
    claimed: ClaimedEvent, error: str, policy: OutboxPolicy, *, using: str = "default"
) -> str | None:
    """DISPATCHED -> FAILED (backoff) or -> FAILED -> DEAD_LETTER. Returns the new status, None if lost."""
    attempt = claimed.envelope.attempt
    if attempt >= policy.max_attempts:
        _assert_path(S.DISPATCHED, S.FAILED, S.DEAD_LETTER)
        new_status: str = S.DEAD_LETTER
        delay = timedelta(0)
    else:
        _assert_path(S.DISPATCHED, S.FAILED)
        new_status = S.FAILED
        delay = policy.delay_after(attempt, claimed.envelope.event_id)
    # next_attempt_at = statement_timestamp() + delay: same clock and instant as the trigger's updated_at
    next_at = ExpressionWrapper(
        Now() + Value(delay, output_field=DurationField()), output_field=DateTimeField()
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
    errors: list[str] = field(default_factory=list)


def dispatch_once(
    publisher: OutboxPublisher, policy: OutboxPolicy, *, using: str = "default"
) -> DispatchStats:
    """One pass: claim a batch, publish each event outside the claim transaction, record the outcome."""
    stats = DispatchStats()
    for claimed in claim_batch(policy, using=using):
        stats.claimed += 1
        try:
            publisher.publish(claimed.envelope)
        except Exception as exc:
            error = _safe_error(exc)
            stats.errors.append(error)
            status = mark_failed(claimed, error, policy, using=using)
            if status == S.DEAD_LETTER:
                stats.dead_lettered += 1
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


def recover_stale(policy: OutboxPolicy, *, using: str = "default") -> int:
    """DISPATCHED rows older than the lease (dispatcher crashed) count as a failed attempt."""
    with transaction.atomic(using=using):
        cutoff = db_now(using) - policy.lease
        rows = list(
            OutboxEvent.objects.using(using)
            .select_for_update(skip_locked=True)
            .filter(delivery_status=S.DISPATCHED, dispatched_at__lte=cutoff)
            .order_by("dispatched_at", "id")[: policy.batch_size]
        )
        recovered = 0
        for row in rows:
            claimed = ClaimedEvent(row.pk, row.row_version, _envelope(row, row.attempts))
            if mark_failed(claimed, "LEASE_EXPIRED", policy, using=using) is not None:
                recovered += 1
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
