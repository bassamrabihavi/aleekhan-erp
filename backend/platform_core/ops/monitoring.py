"""Outbox / background-job monitoring snapshot (PHASE_00 / 00.7). Read-only: plain SELECTs, no locks.

Used by ``manage.py outbox_status`` (text or JSON, exit code for cron/monitoring) - see
docs/ops/JOB_MONITORING.md. There is no public HTTP endpoint for this on purpose: queue depth and error
codes are operational information; an authenticated ops page arrives with PHASE_01 roles.

Verdict thresholds are TECHNICAL DEFAULTS (not business rules; ops to confirm on staging):

* ``critical`` - at least one DEAD_LETTER event (needs a human: replay or compensate);
* ``warn``     - a DISPATCHED event older than the lease (dispatcher crashed; ``recover_stale`` needed), or
  the oldest due PENDING/FAILED event has waited longer than :data:`DUE_BACKLOG_WARN`;
* ``ok``       - otherwise.

01.6 (integration freshness, page 36): :func:`integration_health` - delivery lag (age of the oldest event not
yet delivered and not dead), a ``stale`` flag (lag > :data:`DELIVERY_STALE_AFTER`), aggregates blocked by a
dead-letter head (per-aggregate ordering, ``outbox.claim_batch``) and the events held behind them, open
conflicts and compensation records that still need a human (``MANUAL_REQUIRED`` / ``HOOK_FAILED``).
Exposed in ``GET /admin/health`` (``integration``) and in ``outbox_snapshot`` (reasons ``DELIVERY_STALE`` /
``ORDERING_BLOCKED``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final

from django.db.models import Count, Exists, Max, Min, OuterRef, Q

from platform_core.engine.context import db_now
from platform_core.engine.outbox import INTEGRATION_POLICY, OutboxPolicy
from platform_core.integration.models import ConflictItem, ConflictStatus
from platform_core.models import CompensationOutcome, CompensationRecord, DeliveryStatus, OutboxEvent

# TECHNICAL DEFAULT: a due event waiting longer than this = the dispatcher is not keeping up / not running.
DUE_BACKLOG_WARN: Final = timedelta(minutes=15)
# TECHNICAL DEFAULT (01.6): consumers are "stale" when the oldest undelivered event is older than this.
DELIVERY_STALE_AFTER: Final = timedelta(minutes=15)
VERDICTS: Final = ("ok", "warn", "critical")
UNDELIVERED: Final = (DeliveryStatus.PENDING, DeliveryStatus.FAILED, DeliveryStatus.DISPATCHED)


@dataclass(frozen=True)
class IntegrationHealth:
    lag_seconds: int | None
    stale: bool
    stale_after_seconds: int
    blocked_aggregates: int
    held_events: int
    open_conflicts: int
    compensation_open: int
    last_acked_at: datetime | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "lag_seconds": self.lag_seconds,
            "stale": self.stale,
            "stale_after_seconds": self.stale_after_seconds,
            "blocked_aggregates": self.blocked_aggregates,
            "held_events": self.held_events,
            "open_conflicts": self.open_conflicts,
            "compensation_open": self.compensation_open,
            "last_acked_at": self.last_acked_at.isoformat() if self.last_acked_at else None,
        }


def integration_health(*, using: str = "default", now: datetime | None = None) -> IntegrationHealth:
    """Read-only freshness / ordering / compensation view of the event pipeline (plain SELECTs)."""
    now = now if now is not None else db_now(using)
    qs = OutboxEvent.objects.using(using)
    oldest = qs.filter(delivery_status__in=UNDELIVERED).aggregate(o=Min("created_at"))["o"]
    lag = _age(now, oldest)
    dead = qs.filter(delivery_status=DeliveryStatus.DEAD_LETTER)
    blocked = dead.values("aggregate_type", "aggregate_id").distinct().count()
    held = (
        qs.filter(delivery_status__in=UNDELIVERED)
        .filter(
            Exists(
                OutboxEvent.objects.using(using).filter(
                    aggregate_type=OuterRef("aggregate_type"),
                    aggregate_id=OuterRef("aggregate_id"),
                    id__lt=OuterRef("id"),
                    delivery_status=DeliveryStatus.DEAD_LETTER,
                )
            )
        )
        .count()
    )
    return IntegrationHealth(
        lag_seconds=lag,
        stale=lag is not None and lag > DELIVERY_STALE_AFTER.total_seconds(),
        stale_after_seconds=int(DELIVERY_STALE_AFTER.total_seconds()),
        blocked_aggregates=blocked,
        held_events=held,
        open_conflicts=ConflictItem.objects.using(using).filter(status=ConflictStatus.OPEN).count(),
        compensation_open=CompensationRecord.objects.using(using)
        .filter(outcome__in=[CompensationOutcome.MANUAL_REQUIRED, CompensationOutcome.HOOK_FAILED])
        .count(),
        last_acked_at=qs.aggregate(a=Max("acked_at"))["a"],
    )


@dataclass(frozen=True)
class OutboxSnapshot:
    checked_at: datetime
    counts: dict[str, int]
    due_now: int
    oldest_due_age_seconds: int | None
    oldest_pending_age_seconds: int | None
    stale_dispatched: int
    dead_letters: int
    oldest_dead_letter_at: datetime | None
    last_dispatched_at: datetime | None
    last_acked_at: datetime | None
    open_conflicts: int
    lease_seconds: int
    verdict: str
    reasons: list[str] = field(default_factory=list)
    integration: IntegrationHealth | None = None

    def as_dict(self) -> dict[str, Any]:
        def ts(v: datetime | None) -> str | None:
            return v.isoformat() if v is not None else None

        return {
            "checked_at": ts(self.checked_at),
            "counts": dict(self.counts),
            "due_now": self.due_now,
            "oldest_due_age_seconds": self.oldest_due_age_seconds,
            "oldest_pending_age_seconds": self.oldest_pending_age_seconds,
            "stale_dispatched": self.stale_dispatched,
            "dead_letters": self.dead_letters,
            "oldest_dead_letter_at": ts(self.oldest_dead_letter_at),
            "last_dispatched_at": ts(self.last_dispatched_at),
            "last_acked_at": ts(self.last_acked_at),
            "open_conflicts": self.open_conflicts,
            "lease_seconds": self.lease_seconds,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "integration": self.integration.as_dict() if self.integration is not None else None,
        }


def _age(now: datetime, then: datetime | None) -> int | None:
    return None if then is None else max(0, int((now - then).total_seconds()))


def outbox_snapshot(
    *, policy: OutboxPolicy = INTEGRATION_POLICY, using: str = "default", now: datetime | None = None
) -> OutboxSnapshot:
    now = now if now is not None else db_now(using)
    qs = OutboxEvent.objects.using(using)
    counts = {s: 0 for s in DeliveryStatus.values}
    for row in qs.values("delivery_status").annotate(n=Count("id")):
        counts[row["delivery_status"]] = row["n"]
    waiting = Q(delivery_status__in=[DeliveryStatus.PENDING, DeliveryStatus.FAILED])
    due = qs.filter(waiting, next_attempt_at__lte=now)
    agg_due = due.aggregate(n=Count("id"), oldest=Min("next_attempt_at"))
    oldest_pending = qs.filter(waiting).aggregate(oldest=Min("created_at"))["oldest"]
    stale = qs.filter(
        delivery_status=DeliveryStatus.DISPATCHED, dispatched_at__lte=now - policy.lease
    ).count()
    oldest_dead = qs.filter(delivery_status=DeliveryStatus.DEAD_LETTER).aggregate(o=Min("occurred_at"))["o"]
    last = qs.aggregate(dispatched=Max("dispatched_at"), acked=Max("acked_at"))
    open_conflicts = ConflictItem.objects.using(using).filter(status=ConflictStatus.OPEN).count()

    dead = counts[DeliveryStatus.DEAD_LETTER]
    oldest_due_age = _age(now, agg_due["oldest"])
    reasons: list[str] = []
    if dead:
        reasons.append("DEAD_LETTER_PRESENT")
    if stale:
        reasons.append("STALE_DISPATCHED")
    if oldest_due_age is not None and oldest_due_age > DUE_BACKLOG_WARN.total_seconds():
        reasons.append("DUE_BACKLOG")
    health = integration_health(using=using, now=now)
    if health.stale:
        reasons.append("DELIVERY_STALE")
    if health.held_events:
        reasons.append("ORDERING_BLOCKED")
    verdict = "critical" if dead else ("warn" if reasons else "ok")
    return OutboxSnapshot(
        checked_at=now,
        counts=counts,
        due_now=agg_due["n"],
        oldest_due_age_seconds=oldest_due_age,
        oldest_pending_age_seconds=_age(now, oldest_pending),
        stale_dispatched=stale,
        dead_letters=dead,
        oldest_dead_letter_at=oldest_dead,
        last_dispatched_at=last["dispatched"],
        last_acked_at=last["acked"],
        open_conflicts=open_conflicts,
        lease_seconds=int(policy.lease.total_seconds()),
        verdict=verdict,
        reasons=reasons,
        integration=health,
    )
