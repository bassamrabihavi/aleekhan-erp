"""Outbox / background-job monitoring snapshot (PHASE_00 / 00.7). Read-only: plain SELECTs, no locks.

Used by ``manage.py outbox_status`` (text or JSON, exit code for cron/monitoring) - see
docs/ops/JOB_MONITORING.md. There is no public HTTP endpoint for this on purpose: queue depth and error
codes are operational information; an authenticated ops page arrives with PHASE_01 roles.

Verdict thresholds are TECHNICAL DEFAULTS (not business rules; ops to confirm on staging):

* ``critical`` - at least one DEAD_LETTER event (needs a human: replay or compensate);
* ``warn``     - a DISPATCHED event older than the lease (dispatcher crashed; ``recover_stale`` needed), or
  the oldest due PENDING/FAILED event has waited longer than :data:`DUE_BACKLOG_WARN`;
* ``ok``       - otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final

from django.db.models import Count, Max, Min, Q

from platform_core.engine.context import db_now
from platform_core.engine.outbox import INTEGRATION_POLICY, OutboxPolicy
from platform_core.integration.models import ConflictItem, ConflictStatus
from platform_core.models import DeliveryStatus, OutboxEvent

# TECHNICAL DEFAULT: a due event waiting longer than this = the dispatcher is not keeping up / not running.
DUE_BACKLOG_WARN: Final = timedelta(minutes=15)
VERDICTS: Final = ("ok", "warn", "critical")


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
    )
