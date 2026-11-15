"""Outbox / background-job monitoring snapshot (PHASE_00 / 00.7). Read-only: plain SELECTs, no locks.

Used by ``manage.py outbox_status`` (text or JSON, exit code for cron/monitoring) - see
docs/ops/JOB_MONITORING.md. There is no public HTTP endpoint for this on purpose: queue depth and error
codes are operational information; an authenticated ops page arrives with PHASE_01 roles.

Verdict thresholds are TECHNICAL DEFAULTS (not business rules; ops to confirm on staging):

* ``critical`` - at least one DEAD_LETTER event (needs a human: replay, discard (owner, 01.7) or compensate);
* ``warn``     - a DISPATCHED event older than the lease (dispatcher crashed; ``recover_stale`` needed), or
  the oldest due PENDING/FAILED event has waited longer than :data:`DUE_BACKLOG_WARN`;
* ``ok``       - otherwise.

01.6 (integration freshness, page 36): :func:`integration_health` - delivery lag (age of the oldest event not
yet delivered and not dead), a ``stale`` flag (lag > :data:`DELIVERY_STALE_AFTER`), aggregates whose events
wait behind a dead-letter head (per-aggregate ordering, ``outbox.claim_batch``; REV-0130: an aggregate with a
dead letter and nothing behind it is not counted) and the events held behind them, open
conflicts and compensation records that still need a human (``MANUAL_REQUIRED`` / ``HOOK_FAILED``).
Exposed in ``GET /admin/health`` (``integration``) and in ``outbox_snapshot`` (reasons ``DELIVERY_STALE`` /
``ORDERING_BLOCKED``).

02.7 (PHASE_02 Security & Ops), command output only (``/admin/health`` is unchanged):

* :func:`import_health` - import batches of the sources an owning module APPLIES
  (``imports.SOURCE_APPLY_POLICIES``): batches whose apply FAILED and that are still not APPLIED (an audit row
  ``platform.integration.batch.apply_failed`` exists; event ``platform.integration.batch_apply_failed``),
  batches VALIDATED and waiting for the operator's apply, open conflict items per source. Reason
  ``IMPORT_APPLY_FAILED`` (``warn``) in ``outbox_status`` and ``job_status``.
* :func:`event_families` - undelivered / dead-letter counts per event family (``identity``, ``commercial``,
  ``platform.integration``, ...), every family of the event catalogue listed (zero when idle), so the PHASE_02
  events are visible next to the PHASE_00/01 ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final

from django.db import models
from django.db.models import Count, Exists, Max, Min, OuterRef, Q
from django.db.models.functions import Cast

from platform_core.engine.context import db_now
from platform_core.engine.outbox import INTEGRATION_POLICY, OutboxPolicy
from platform_core.integration.models import BatchStatus, ConflictItem, ConflictStatus, ImportBatch
from platform_core.models import (
    AuditEvent,
    CompensationOutcome,
    CompensationRecord,
    DeliveryStatus,
    OutboxEvent,
)

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
    held_qs = qs.filter(delivery_status__in=UNDELIVERED).filter(
        Exists(
            OutboxEvent.objects.using(using).filter(
                aggregate_type=OuterRef("aggregate_type"),
                aggregate_id=OuterRef("aggregate_id"),
                id__lt=OuterRef("id"),
                delivery_status=DeliveryStatus.DEAD_LETTER,
            )
        )
    )
    held = held_qs.count()
    # REV-0130: only aggregates that really have events waiting behind a dead letter (= the OpenAPI text); a
    # dead letter with nothing behind it is counted in ``dead_letters`` / DEAD_LETTER_PRESENT, not here.
    blocked = held_qs.values("aggregate_type", "aggregate_id").distinct().count() if held else 0
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


# ------------------------------------------------------------------------------------ imports (02.7)
APPLY_FAILED_AUDIT: Final = "platform.integration.batch.apply_failed"


@dataclass(frozen=True)
class SourceImportHealth:
    source_code: str
    apply_failed: int
    awaiting_apply: int
    open_conflicts: int
    last_apply_failed_at: datetime | None
    last_applied_at: datetime | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_code": self.source_code,
            "apply_failed": self.apply_failed,
            "awaiting_apply": self.awaiting_apply,
            "open_conflicts": self.open_conflicts,
            "last_apply_failed_at": _ts(self.last_apply_failed_at),
            "last_applied_at": _ts(self.last_applied_at),
        }


def import_health(*, using: str = "default") -> list[SourceImportHealth]:
    """Per source of ``imports.SOURCE_APPLY_POLICIES`` (plain SELECTs; counts and times only, never a value).

    ``apply_failed``: batches not APPLIED whose apply failed (``batch_apply_failed`` recorded) - a re-run of
    the import resumes them (compensation = rollback, staging kept). ``awaiting_apply``: VALIDATED batches
    without a recorded failure (the operator's apply has not run yet). Once a batch is APPLIED it no longer
    counts as failed, whatever happened before."""
    from platform_core.integration.imports import SOURCE_APPLY_POLICIES

    out: list[SourceImportHealth] = []
    audits = AuditEvent.objects.using(using).filter(
        action=APPLY_FAILED_AUDIT, resource_type="platform.import_batch"
    )
    for code in sorted(SOURCE_APPLY_POLICIES):
        batches = ImportBatch.objects.using(using).filter(source__code=code)
        # a failed apply leaves the batch VALIDATED (rollback); APPLIED / REJECTED batches are settled
        validated = batches.filter(status=BatchStatus.VALIDATED).annotate(rid=Cast("id", models.CharField()))
        waiting = set(validated.values_list("rid", flat=True))
        failures = audits.filter(resource_id__in=validated.values("rid"))
        failed = set(failures.values_list("resource_id", flat=True))
        out.append(
            SourceImportHealth(
                source_code=code,
                apply_failed=len(failed),
                awaiting_apply=len(waiting - failed),
                open_conflicts=ConflictItem.objects.using(using)
                .filter(source__code=code, status=ConflictStatus.OPEN)
                .count(),
                last_apply_failed_at=failures.aggregate(t=Max("occurred_at"))["t"],
                last_applied_at=batches.filter(status=BatchStatus.APPLIED).aggregate(t=Max("closed_at"))["t"],
            )
        )
    return out


def import_verdict(sources: list[SourceImportHealth]) -> list[str]:
    """Reasons: ``IMPORT_APPLY_FAILED`` when any source has a failed, not yet applied batch."""
    return ["IMPORT_APPLY_FAILED"] if any(s.apply_failed for s in sources) else []


def event_families(*, using: str = "default") -> dict[str, dict[str, int]]:
    """``family -> {"undelivered": n, "dead_letter": n}`` for every family of the event catalogue; events of a
    type outside the catalogue (synthetic test / drill types) are counted under ``other`` (no free text from
    the table is printed). Family = first segment of the event type, two segments for ``platform.*``
    (``platform.integration``, ``platform.workflow``, ...)."""
    from platform_core.engine.events import CATALOGUE

    out: dict[str, dict[str, int]] = {
        event_family(t): {"undelivered": 0, "dead_letter": 0} for t in CATALOGUE.event_types
    }
    out[OTHER_FAMILY] = {"undelivered": 0, "dead_letter": 0}
    rows = (
        OutboxEvent.objects.using(using)
        .filter(delivery_status__in=[*UNDELIVERED, DeliveryStatus.DEAD_LETTER])
        .values("event_type", "delivery_status")
        .annotate(n=Count("id"))
    )
    for row in rows:
        known = row["event_type"] in CATALOGUE
        slot = out[event_family(row["event_type"]) if known else OTHER_FAMILY]
        key = "dead_letter" if row["delivery_status"] == DeliveryStatus.DEAD_LETTER else "undelivered"
        slot[key] += row["n"]
    return dict(sorted(out.items()))


OTHER_FAMILY: Final = "other"


def event_family(event_type: str) -> str:
    parts = event_type.split(".")
    return ".".join(parts[:2]) if parts[0] == "platform" and len(parts) > 2 else parts[0]


def _ts(v: datetime | None) -> str | None:
    return v.isoformat() if v is not None else None


# ------------------------------------------------------------------------------- housekeeping jobs (01.7)
# TECHNICAL DEFAULT (01.7): a housekeeping job type without a SUCCEEDED run in this window is "overdue". The
# intended schedule is daily (docs/ops/JOB_MONITORING.md); 26 h leaves 2 h slack. Ops confirm on staging.
HOUSEKEEPING_MAX_AGE: Final = timedelta(hours=26)


@dataclass(frozen=True)
class HousekeepingJob:
    job_type: str
    last_state: str | None
    last_succeeded_at: datetime | None
    last_failed_at: datetime | None
    last_error_code: str | None
    max_age_seconds: int
    overdue: bool
    failing: bool

    def as_dict(self) -> dict[str, Any]:
        def ts(v: datetime | None) -> str | None:
            return v.isoformat() if v is not None else None

        return {
            "job_type": self.job_type,
            "last_state": self.last_state,
            "last_succeeded_at": ts(self.last_succeeded_at),
            "last_failed_at": ts(self.last_failed_at),
            "last_error_code": self.last_error_code,
            "max_age_seconds": self.max_age_seconds,
            "overdue": self.overdue,
            "failing": self.failing,
        }


def housekeeping_health(*, using: str = "default", now: datetime | None = None) -> list[HousekeepingJob]:
    """Per housekeeping job type (``jobs.service.HOUSEKEEPING_TYPES`` that have a seeded definition): newest
    run state, last success / failure, ``overdue`` (no success within :data:`HOUSEKEEPING_MAX_AGE` - also when
    it never ran: PHASE_01 has no scheduler, the honest answer is "overdue") and ``failing`` (newest finished
    run FAILED). Plain SELECTs; machine error codes only."""
    from platform_core.jobs.models import JobDefinition, JobRun, JobState
    from platform_core.jobs.service import HOUSEKEEPING_TYPES

    now = now if now is not None else db_now(using)
    seeded = set(
        JobDefinition.objects.using(using)
        .filter(job_type__in=HOUSEKEEPING_TYPES)
        .values_list("job_type", flat=True)
    )
    runs = JobRun.objects.using(using)
    out: list[HousekeepingJob] = []
    for job_type in HOUSEKEEPING_TYPES:
        if job_type not in seeded:
            continue
        mine = runs.filter(job_type_id=job_type)
        newest = mine.order_by("-queued_at", "-id").values_list("state", flat=True).first()
        ok_at = mine.filter(state=JobState.SUCCEEDED).aggregate(t=Max("finished_at"))["t"]
        last_finished = (
            mine.filter(finished_at__isnull=False)
            .order_by("-finished_at")
            .values("state", "error_code")
            .first()
        )
        failed_at = mine.filter(state=JobState.FAILED).aggregate(t=Max("finished_at"))["t"]
        failing = bool(last_finished and last_finished["state"] == JobState.FAILED)
        out.append(
            HousekeepingJob(
                job_type=job_type,
                last_state=newest,
                last_succeeded_at=ok_at,
                last_failed_at=failed_at,
                last_error_code=(last_finished["error_code"] or None) if failing and last_finished else None,
                max_age_seconds=int(HOUSEKEEPING_MAX_AGE.total_seconds()),
                overdue=ok_at is None or now - ok_at > HOUSEKEEPING_MAX_AGE,
                failing=failing,
            )
        )
    return out


def housekeeping_verdict(jobs: list[HousekeepingJob]) -> tuple[str, list[str]]:
    """``warn`` with reasons ``HOUSEKEEPING_FAILING`` / ``HOUSEKEEPING_OVERDUE``, else ``ok``."""
    reasons: list[str] = []
    if any(j.failing for j in jobs):
        reasons.append("HOUSEKEEPING_FAILING")
    if any(j.overdue for j in jobs):
        reasons.append("HOUSEKEEPING_OVERDUE")
    return ("warn" if reasons else "ok"), reasons


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
    imports: list[SourceImportHealth] = field(default_factory=list)
    families: dict[str, dict[str, int]] = field(default_factory=dict)

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
            "imports": [i.as_dict() for i in self.imports],
            "event_families": {k: dict(v) for k, v in self.families.items()},
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
    imports = import_health(using=using)
    reasons.extend(import_verdict(imports))
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
        imports=imports,
        families=event_families(using=using),
    )
