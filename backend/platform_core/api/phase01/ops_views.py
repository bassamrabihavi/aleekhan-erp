"""``jobs`` + ``audit`` endpoints: detailed health (page 36), job runs, SAFE cancel, audit query + integrity.

* Audit is read-only for everyone (append-only, DB triggers since 00.2); there is no API to change or delete
  an audit event. ``listAuditEvents`` / ``getAuditEvent`` need a fresh MFA step-up (matrix v1.0) and a time
  window (``occurred_from`` / ``occurred_to``, both required). Before/after were redacted at write time.
* ``requestJobCancel``: QUEUED -> CANCELLED at once, RUNNING -> CANCEL_REQUESTED (stops at the next safe
  checkpoint) - STATE_TRANSITIONS 4.7 (engine reading E-7); protected types -> 409 ``JOB_PROTECTED``; force
  kill is not part of the contract (DEC-024).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Final

from django.db.models import Count, Min
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.authz import policy as P
from platform_core.authz.policy import Caller, RecordScope
from platform_core.engine.context import db_now
from platform_core.engine.errors import FieldError, NotFound, ValidationFailed
from platform_core.engine.idempotency import StoredResponse
from platform_core.identity.models import LoginAttempt, User
from platform_core.jobs import service as jobs
from platform_core.jobs.models import AuditIntegrityRun, JobDefinition, JobRun
from platform_core.models import AuditEvent, OutboxEvent
from platform_core.ops.monitoring import housekeeping_health, integration_health

from .. import views as probes
from . import serializers as S
from .common import (
    NO_STORE,
    Phase01View,
    body_of,
    etag_response,
    if_match,
    in_scope,
    lock_checked,
    paginate,
    parse_ts,
    query_choice,
    query_pattern,
    query_uuid,
    stored,
    utc,
    utc_req,
    write,
)

HEALTH: Final = "platform.ops.health.read"
JOB_READ: Final = "platform.ops.job.read"
JOB_CANCEL: Final = "platform.ops.job.cancel"
AUDIT_READ: Final = "platform.audit.read"
INTEGRITY_READ: Final = "platform.audit.integrity.read"
NO_UNIT: Final = RecordScope()
JOB_STATES: Final = ("QUEUED", "RUNNING", "CANCEL_REQUESTED", "CANCELLED", "SUCCEEDED", "FAILED")
FAILED_LOGIN_OUTCOMES: Final = ("INVALID_CREDENTIALS", "MFA_FAILED")


def _q(caller: Caller, action: str) -> Any:
    return P.scope_q(caller, action, unit_field=None, owner_fields=())


class HealthDetailView(Phase01View):
    required_action = HEALTH

    def get(self, request: Request) -> Response:
        in_scope(self.caller(), HEALTH, NO_UNIT)
        now = db_now()
        database = probes._safe("database", probes._check_database)
        components = [
            {"name": "database", "status": database},
            {
                "name": "migrations",
                "status": probes._safe("migrations", probes._check_migrations)
                if database == "up"
                else "unknown",
            },
            {"name": "cache", "status": probes._safe("cache", probes._check_cache)},
            {"name": "worker", "status": "unknown"},  # no worker heartbeat in PHASE_01 (honest: unknown)
        ]
        counts = dict(
            OutboxEvent.objects.values_list("delivery_status")
            .annotate(n=Count("id"))
            .values_list("delivery_status", "n")
        )
        oldest = OutboxEvent.objects.filter(delivery_status="PENDING").aggregate(t=Min("occurred_at"))["t"]
        jobs_counts = dict(
            JobRun.objects.values_list("state").annotate(n=Count("id")).values_list("state", "n")
        )
        housekeeping = housekeeping_health(now=now)  # 01.7 (contract 0.6.3-draft, additive)
        body = {
            "checked_at": utc_req(now.replace(microsecond=0)),
            "components": components,
            "outbox": {
                "pending": int(counts.get("PENDING", 0)),
                "failed": int(counts.get("FAILED", 0)),
                "dead_letter": int(counts.get("DEAD_LETTER", 0)),
                "oldest_pending_at": utc(oldest),
            },
            "jobs": {
                "running": int(jobs_counts.get("RUNNING", 0)) + int(jobs_counts.get("CANCEL_REQUESTED", 0)),
                "queued": int(jobs_counts.get("QUEUED", 0)),
                "failed_24h": JobRun.objects.filter(
                    state="FAILED", finished_at__gte=now - timedelta(hours=24)
                ).count(),
                "housekeeping_alerts": sum(1 for j in housekeeping if j.overdue or j.failing),
                "housekeeping": [_housekeeping(j) for j in housekeeping],
            },
            # 01.6: event delivery freshness / ordering / compensation (counts only, no payloads or ids)
            "integration": _integration(now),
            "security": {
                "failed_logins_24h": LoginAttempt.objects.filter(
                    outcome__in=FAILED_LOGIN_OUTCOMES, occurred_at__gte=now - timedelta(hours=24)
                ).count(),
                "locked_users": User.objects.filter(status="LOCKED").count(),
            },
        }
        return Response(body, headers=NO_STORE)


def _housekeeping(j: Any) -> dict[str, Any]:
    return {
        "job_type": j.job_type,
        "last_state": j.last_state,
        "last_succeeded_at": utc(j.last_succeeded_at),
        "last_failed_at": utc(j.last_failed_at),
        "last_error_code": j.last_error_code,
        "max_age_seconds": j.max_age_seconds,
        "overdue": j.overdue,
        "failing": j.failing,
    }


def _integration(now: Any) -> dict[str, Any]:
    h = integration_health(now=now)
    return {
        "lag_seconds": h.lag_seconds,
        "stale": h.stale,
        "stale_after_seconds": h.stale_after_seconds,
        "blocked_aggregates": h.blocked_aggregates,
        "held_events": h.held_events,
        "open_conflicts": h.open_conflicts,
        "compensation_open": h.compensation_open,
        "last_acked_at": utc(h.last_acked_at),
    }


class JobDefinitionsView(Phase01View):
    required_action = JOB_READ

    def get(self, request: Request) -> Response:
        qs = JobDefinition.objects.filter(_q(self.caller(), JOB_READ))
        return paginate(request, self, qs, S.job_definition, ordering="job_type")


class JobsView(Phase01View):
    required_action = JOB_READ

    def get(self, request: Request) -> Response:
        qs = JobRun.objects.filter(_q(self.caller(), JOB_READ))
        state = query_choice(request, "state", JOB_STATES)
        job_type = query_pattern(request, "job_type", r"^[a-z][a-z0-9_]{2,63}$", 64)
        if state:
            qs = qs.filter(state=state)
        if job_type:
            qs = qs.filter(job_type_id=job_type)
        return paginate(request, self, qs, S.job, ordering="-queued_at")


class JobView(Phase01View):
    required_action = JOB_READ

    def get(self, request: Request, job_id: uuid.UUID) -> Response:
        caller = self.caller()
        run = JobRun.objects.filter(pk=job_id).first()
        if run is None:
            raise NotFound()
        in_scope(caller, JOB_READ, NO_UNIT)
        return etag_response(S.job(run), run.row_version)


class RequestJobCancelView(Phase01View):
    required_action = JOB_CANCEL

    def post(self, request: Request, job_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "JobCancelRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(
                JobRun, job_id, scope=lambda _r: in_scope(caller, JOB_CANCEL, NO_UNIT), expected=expected
            )
            jobs.request_cancel(caller, job_id, reason=data["reason"], request_id=rid)
            r = JobRun.objects.get(pk=job_id)
            return stored(200, S.job(r), etag_version=r.row_version)

        return write(self, run)


# ----------------------------------------------------------------------------------------------- audit
class AuditEventsView(Phase01View):
    required_action = AUDIT_READ

    def get(self, request: Request) -> Response:
        caller = self.caller()
        params = request.query_params
        errors = [
            FieldError(n, "REQUIRED") for n in ("occurred_from", "occurred_to") if params.get(n) is None
        ]
        if errors:
            raise ValidationFailed(errors=errors)
        start = parse_ts(params.get("occurred_from"), "occurred_from")
        end = parse_ts(params.get("occurred_to"), "occurred_to")
        if end < start:
            raise ValidationFailed(errors=[FieldError("occurred_to", "BEFORE_OCCURRED_FROM")])
        qs = AuditEvent.objects.filter(_q(caller, AUDIT_READ), occurred_at__gte=start, occurred_at__lte=end)
        actor = query_uuid(request, "actor_id")
        rtype = query_pattern(request, "resource_type", r"^[a-z][a-z0-9_.]{0,63}$", 64)
        action = query_pattern(request, "action", r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$", 120)
        rid = params.get("resource_id")
        if rid is not None and not 1 <= len(rid) <= 64:
            raise ValidationFailed(errors=[FieldError("resource_id", "OUT_OF_RANGE")])
        if actor:
            qs = qs.filter(actor_id=actor)
        if rtype:
            qs = qs.filter(resource_type=rtype)
        if action:
            qs = qs.filter(action=action)
        if rid:
            qs = qs.filter(resource_id=rid)
        return paginate(request, self, qs, S.audit_event, ordering="-occurred_at")


class AuditEventView(Phase01View):
    required_action = AUDIT_READ

    def get(self, request: Request, audit_event_id: uuid.UUID) -> Response:
        caller = self.caller()
        e = AuditEvent.objects.filter(pk=audit_event_id).first()
        if e is None:
            raise NotFound()
        in_scope(caller, AUDIT_READ, NO_UNIT)
        return Response(S.audit_event(e), headers=NO_STORE)


class AuditIntegrityView(Phase01View):
    required_action = INTEGRITY_READ

    def get(self, request: Request) -> Response:
        in_scope(self.caller(), INTEGRITY_READ, NO_UNIT)
        last = AuditIntegrityRun.objects.order_by("-finished_at", "-started_at").first()
        if last is None:
            body: dict[str, Any] = {"checked_at": None, "status": "NEVER_RUN", "events_checked": 0}
        else:
            body = {
                "checked_at": utc(last.finished_at),
                "status": last.status,
                "events_checked": int(last.events_checked),
                "first_broken_event_id": str(last.first_broken_event_id)
                if last.first_broken_event_id
                else None,
            }
        return Response(body, headers=NO_STORE)
