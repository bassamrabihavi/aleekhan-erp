"""Job runs (page 36; STATE_TRANSITIONS 4.7) and the housekeeping job functions of PHASE_01.

* enqueue: ``task_key`` unique -> enqueueing the same key twice returns the existing run (idempotent).
* worker side: start (QUEUED -> RUNNING), :func:`checkpoint` (a requested cancel stops the job safely there),
  finish (SUCCEEDED / FAILED with a machine ``error_code``, never exception text; a cancel that came too late
  is recorded as ``cancel_too_late``).
* :func:`request_cancel` (``platform.ops.job.cancel``, MFA step-up, reason >= 3): protected or non-cancellable
  job types -> 409 ``JOB_PROTECTED`` (the DB trigger refuses too); QUEUED -> CANCELLED at once, RUNNING ->
  CANCEL_REQUESTED. **Force kill does not exist**: :func:`force_kill` always answers ``RULE_NOT_APPROVED``
  (DEC-024, SEC-02 is PHASE_11).
* :data:`HOUSEKEEPING` maps the job types seeded by migration 0011 to their functions; :func:`run_job` runs
  one
  under the job-run lifecycle with a checkpoint after each batch.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Final

from django.db import IntegrityError, transaction

from platform_core.authz.policy import Caller, require_permission, require_step_up
from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.engine.errors import (
    FieldError,
    JobProtected,
    NotFound,
    RuleNotApproved,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import UnitOfWork, unit_of_work
from platform_core.schema_common import ERROR_CODE_PATTERN

from .models import JobDefinition, JobRun, JobState

CANCEL: Final = "platform.ops.job.cancel"
J = JobState
JOB_MACHINE: Final = StateMachine(
    name="job_run",
    states=frozenset(JobState.values),
    transitions={
        J.QUEUED: frozenset({J.RUNNING, J.CANCELLED}),
        J.RUNNING: frozenset({J.SUCCEEDED, J.FAILED, J.CANCEL_REQUESTED}),
        J.CANCEL_REQUESTED: frozenset({J.CANCELLED, J.SUCCEEDED, J.FAILED}),
        J.CANCELLED: frozenset(),
        J.SUCCEEDED: frozenset(),
        J.FAILED: frozenset(),
    },
)


def _system(request_id: uuid.UUID | None = None) -> RequestContext:
    return RequestContext(Actor.system(), request_id=request_id)


def _view(run: JobRun) -> dict[str, object]:
    return {
        "job_type": run.job_type_id,
        "state": run.state,
        "cancel_too_late": run.cancel_too_late,
        "error_code": run.error_code,
    }


def _audit(
    uow: UnitOfWork, verb: str, run: JobRun, *, before: dict[str, object] | None, reason: str = ""
) -> None:
    uow.audit(
        action=f"platform.ops.job.{verb}",
        resource_type="platform.job_run",
        resource_id=str(run.pk),
        resource_version=run.row_version,
        before=before,
        after=_view(run),
        reason=reason,
    )
    uow.emit(
        event_type="platform.ops.job.changed",
        aggregate_type="platform.job_run",
        aggregate_id=str(run.pk),
        aggregate_version=run.row_version,
        payload={"id": str(run.pk), "job_type": run.job_type_id, "state": run.state},
    )


def _lock(run_id: uuid.UUID) -> JobRun:
    run = JobRun.objects.select_for_update().select_related("job_type").filter(pk=run_id).first()
    if run is None:
        raise NotFound()
    return run


def _set(
    uow: UnitOfWork, run: JobRun, state: JobState, verb: str, *, reason: str = "", **values: object
) -> None:
    JOB_MACHINE.assert_transition(run.state, state)
    before = _view(run)
    if state in (J.CANCELLED, J.SUCCEEDED, J.FAILED):
        values["finished_at"] = db_now()
    JobRun.objects.filter(pk=run.pk).update(state=state, **values)
    run.refresh_from_db()
    _audit(uow, verb, run, before=before, reason=reason)


# ------------------------------------------------------------------------------------------ lifecycle
def enqueue(ctx: RequestContext, *, job_type: str, task_key: str) -> JobRun:
    if not JobDefinition.objects.filter(job_type=job_type).exists():
        raise NotFound()
    existing = JobRun.objects.filter(task_key=task_key).first()
    if existing is not None:
        return existing
    try:
        with unit_of_work(ctx) as uow:
            run = JobRun.objects.create(
                job_type_id=job_type, task_key=task_key, requested_by_id=ctx.actor.actor_id
            )
            run.refresh_from_db()
            _audit(uow, "enqueue", run, before=None)
        return run
    except IntegrityError:  # concurrent enqueue of the same task key: the other one won
        return JobRun.objects.get(task_key=task_key)


def start(run_id: uuid.UUID, *, worker_task_id: str = "") -> JobRun:
    with unit_of_work(_system()) as uow:
        run = _lock(run_id)
        _set(uow, run, J.RUNNING, "start", started_at=db_now(), worker_task_id=worker_task_id[:64])
    return run


def checkpoint(run_id: uuid.UUID, *, progress: int | None = None) -> bool:
    """Safe stop point. Returns False if the job must stop now (a cancel was requested -> CANCELLED)."""
    with transaction.atomic():
        state = JobRun.objects.filter(pk=run_id).values_list("state", flat=True).first()
    if state == J.CANCEL_REQUESTED:
        with unit_of_work(_system()) as uow:
            run = _lock(run_id)
            if run.state == J.CANCEL_REQUESTED:
                _set(uow, run, J.CANCELLED, "cancelled_at_checkpoint", progress=progress)
                return False
    if state != J.RUNNING:
        return False
    values: dict[str, object] = {"last_checkpoint_at": db_now()}
    if progress is not None:
        values["progress"] = max(0, min(100, progress))
    JobRun.objects.filter(pk=run_id, state=J.RUNNING).update(**values)  # technical progress, no audit row
    return True


def finish(run_id: uuid.UUID, *, ok: bool, error_code: str = "") -> JobRun:
    import re

    if not ok and not re.fullmatch(ERROR_CODE_PATTERN, error_code):
        raise ValidationFailed(errors=[FieldError("error_code", "INVALID")])
    with unit_of_work(_system()) as uow:
        run = _lock(run_id)
        too_late = run.state == J.CANCEL_REQUESTED
        _set(
            uow,
            run,
            J.SUCCEEDED if ok else J.FAILED,
            "finish",
            error_code="" if ok else error_code,
            cancel_too_late=too_late,
            progress=100 if ok and run.progress is not None else run.progress,
        )
    return run


def request_cancel(
    caller: Caller, run_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> JobRun:
    """Safe cancel only (Gate-1 "Job kill under permission and reason"; force kill = DEC-024)."""
    require_permission(caller, CANCEL)
    require_step_up(caller, CANCEL)
    text = reason.strip()
    if len(text) < 3:
        raise ValidationFailed("a reason is required", errors=[FieldError("reason", "REQUIRED")])
    with unit_of_work(caller.context(request_id)) as uow:
        run = _lock(run_id)
        if run.job_type.protected or not run.job_type.cancellable:
            raise JobProtected()
        values = {
            "cancel_requested_by_id": caller.user_id,
            "cancel_requested_at": db_now(),
            "cancel_reason": text[:500],
        }
        if run.state == J.QUEUED:
            _set(uow, run, J.CANCELLED, "cancel", reason=text, **values)
        elif run.state == J.RUNNING:
            _set(uow, run, J.CANCEL_REQUESTED, "cancel_request", reason=text, **values)
        else:
            raise StateTransitionNotAllowed(f"job_run: cancel is not possible in {run.state}")
    return run


def force_kill(caller: Caller, run_id: uuid.UUID, *, reason: str) -> None:
    """Not available in PHASE_01 (SEC-02 / DEC-024, PHASE_11)."""
    raise RuleNotApproved("DEC-024", "force kill of a job is not approved")


# --------------------------------------------------------------------------------------- housekeeping
def _housekeeping() -> dict[str, Callable[[], int]]:
    from platform_core.documents.service import purge_rejected, scan_pending
    from platform_core.identity.roles import expire_due_assignments
    from platform_core.identity.sessions import expire_due_sessions
    from platform_core.workflow.approvals import expire_due

    from .retention import purge_login_events, run_audit_integrity

    return {
        "approval_expiry_sweep": expire_due,
        "role_assignment_expiry_sweep": expire_due_assignments,
        "session_expiry_sweep": expire_due_sessions,
        "document_scan": lambda: sum(scan_pending().values()),
        "document_rejected_purge": purge_rejected,
        "login_event_retention_purge": purge_login_events,
        "audit_integrity_check": run_audit_integrity,
    }


HOUSEKEEPING_TYPES: Final = (
    "approval_expiry_sweep",
    "role_assignment_expiry_sweep",
    "session_expiry_sweep",
    "document_scan",
    "document_rejected_purge",
    "login_event_retention_purge",
    "audit_integrity_check",
)


def run_job(job_type: str, *, task_key: str | None = None, max_batches: int = 100) -> JobRun:
    """Run one housekeeping job under the job-run lifecycle; a checkpoint after each batch."""
    fn = _housekeeping().get(job_type)
    if fn is None:
        raise NotFound()
    run = enqueue(_system(), job_type=job_type, task_key=task_key or f"{job_type}:{uuid.uuid4()}")
    if run.state != J.QUEUED:
        return run
    start(run.pk)
    try:
        for _ in range(max_batches):
            if not checkpoint(run.pk):
                return JobRun.objects.get(pk=run.pk)
            if fn() == 0:
                break
    except Exception:
        return finish(run.pk, ok=False, error_code="JOB_FAILED")
    return finish(run.pk, ok=True)
