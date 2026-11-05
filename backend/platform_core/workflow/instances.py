"""Workflow instances and the cancellation state machine (STATE_TRANSITIONS 4.5).

PHASE_01 ships no business workflow definition (definitions are reviewed migrations of their own phases); the
machine is exercised with a synthetic, test-only definition. Definition steps (JSON array) may name a
compensation per step: ``{"key": "<step>", "compensation": "<compensation key>"}``.

* start: definition ACTIVE (DB) -> RUNNING; the instance pins the definition version.
* RUNNING <-> WAITING; RUNNING/WAITING -> COMPLETED.
* cancel (``platform.workflow.instance.cancel``, MFA step-up, mandatory reason): RUNNING/WAITING ->
  CANCEL_REQUESTED, and in the same transaction its PENDING approvals -> WITHDRAWN and open tasks ->
  CANCELLED.
  Then COMPENSATING if completed steps have a compensation (each recorded as COMPENSATION_STARTED; completed
  by
  :func:`record_compensated` as new records, never deletes), otherwise CANCELLED.
* fail: RUNNING/WAITING/COMPENSATING -> FAILED with a machine ``failure_code`` (no exception text).
Every step is an append-only ``platform_workflow_step_event``.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from platform_core.authz.policy import Caller, RecordScope, require_record, require_step_up
from platform_core.engine.context import RequestContext, db_now
from platform_core.engine.errors import FieldError, NotFound, StateTransitionNotAllowed, ValidationFailed
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import UnitOfWork, unit_of_work
from platform_core.schema_common import ERROR_CODE_PATTERN

from . import approvals, tasks
from .models import (
    ApprovalRequest,
    ApprovalStatus,
    DefinitionStatus,
    InstanceStatus,
    StepEventKind,
    TaskStatus,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStepEvent,
    WorkTask,
)

CANCEL: Final = "platform.workflow.instance.cancel"
IS = InstanceStatus
INSTANCE_MACHINE: Final = StateMachine(
    name="workflow_instance",
    states=frozenset(InstanceStatus.values),
    transitions={
        IS.RUNNING: frozenset({IS.WAITING, IS.COMPLETED, IS.CANCEL_REQUESTED, IS.FAILED}),
        IS.WAITING: frozenset({IS.RUNNING, IS.COMPLETED, IS.CANCEL_REQUESTED, IS.FAILED}),
        IS.CANCEL_REQUESTED: frozenset({IS.COMPENSATING, IS.CANCELLED}),
        IS.COMPENSATING: frozenset({IS.CANCELLED, IS.FAILED}),
        IS.COMPLETED: frozenset(),
        IS.CANCELLED: frozenset(),
        IS.FAILED: frozenset(),
    },
)


def _next_seq(instance: WorkflowInstance) -> int:
    last = (
        WorkflowStepEvent.objects.filter(instance=instance)
        .order_by("-seq")
        .values_list("seq", flat=True)
        .first()
    )
    return (last or 0) + 1


def _event(
    instance: WorkflowInstance,
    step: str,
    kind: StepEventKind,
    actor: uuid.UUID | None,
    detail: dict[str, Any] | None = None,
) -> None:
    WorkflowStepEvent.objects.create(
        instance=instance,
        seq=_next_seq(instance),
        step_key=step or "instance",
        event=kind,
        actor_id=actor,
        detail=detail or {},
    )


def _audit(
    uow: UnitOfWork, verb: str, inst: WorkflowInstance, *, before: str | None, reason: str = ""
) -> None:
    uow.audit(
        action=f"platform.workflow.instance.{verb}",
        resource_type="platform.workflow_instance",
        resource_id=str(inst.pk),
        resource_version=inst.row_version,
        before={"status": before} if before else None,
        after={"status": inst.status, "current_step": inst.current_step},
        reason=reason,
    )
    uow.emit(
        event_type="platform.workflow.instance.changed",
        aggregate_type="platform.workflow_instance",
        aggregate_id=str(inst.pk),
        aggregate_version=inst.row_version,
        payload={"id": str(inst.pk), "status": inst.status},
    )


def _set(
    uow: UnitOfWork,
    inst: WorkflowInstance,
    status: InstanceStatus,
    verb: str,
    *,
    reason: str = "",
    **values: Any,
) -> None:
    INSTANCE_MACHINE.assert_transition(inst.status, status)
    before = inst.status
    if status in (IS.COMPLETED, IS.CANCELLED, IS.FAILED):
        values["ended_at"] = db_now()
    WorkflowInstance.objects.filter(pk=inst.pk).update(status=status, **values)
    inst.refresh_from_db()
    _audit(uow, verb, inst, before=before, reason=reason)


def _lock(instance_id: uuid.UUID) -> WorkflowInstance:
    inst = (
        WorkflowInstance.objects.select_for_update()
        .select_related("definition")
        .filter(pk=instance_id)
        .first()
    )
    if inst is None:
        raise NotFound()
    return inst


def start_instance(
    ctx: RequestContext, *, definition_key: str, subject_type: str, subject_id: str, first_step: str = ""
) -> WorkflowInstance:
    """Called by the owning use case (no own permission: the use case is authorised)."""
    with unit_of_work(ctx) as uow:
        definition = WorkflowDefinition.objects.filter(
            key=definition_key, status=DefinitionStatus.ACTIVE
        ).first()
        if definition is None:
            raise NotFound()
        inst = WorkflowInstance.objects.create(
            definition=definition,
            subject_type=subject_type,
            subject_id=subject_id,
            current_step=first_step,
            started_by_id=ctx.actor.actor_id,
        )
        inst.refresh_from_db()
        _event(inst, first_step, StepEventKind.ENTERED, ctx.actor.actor_id)
        _audit(uow, "start", inst, before=None)
    return inst


def complete_step(
    ctx: RequestContext, instance_id: uuid.UUID, *, step: str, next_step: str | None
) -> WorkflowInstance:
    """Record a completed step; ``next_step=None`` completes the instance."""
    with unit_of_work(ctx) as uow:
        inst = _lock(instance_id)
        if inst.status not in (IS.RUNNING, IS.WAITING):
            raise StateTransitionNotAllowed(
                f"workflow_instance: step completion not allowed in {inst.status}"
            )
        _event(inst, step, StepEventKind.COMPLETED, ctx.actor.actor_id)
        if next_step is None:
            _set(uow, inst, IS.COMPLETED, "complete")
        else:
            _event(inst, next_step, StepEventKind.ENTERED, ctx.actor.actor_id)
            WorkflowInstance.objects.filter(pk=inst.pk).update(current_step=next_step)
            inst.refresh_from_db()
            _audit(uow, "advance", inst, before=inst.status)
    return inst


def wait(ctx: RequestContext, instance_id: uuid.UUID) -> WorkflowInstance:
    with unit_of_work(ctx) as uow:
        inst = _lock(instance_id)
        _set(uow, inst, IS.WAITING, "wait")
    return inst


def resume(ctx: RequestContext, instance_id: uuid.UUID) -> WorkflowInstance:
    with unit_of_work(ctx) as uow:
        inst = _lock(instance_id)
        _set(uow, inst, IS.RUNNING, "resume")
    return inst


def _compensations(inst: WorkflowInstance) -> list[tuple[str, str]]:
    done = set(
        WorkflowStepEvent.objects.filter(instance=inst, event=StepEventKind.COMPLETED).values_list(
            "step_key", flat=True
        )
    )
    out: list[tuple[str, str]] = []
    for step in inst.definition.steps or []:
        if isinstance(step, dict) and step.get("key") in done and step.get("compensation"):
            out.append((str(step["key"]), str(step["compensation"])))
    return out


def instance_scope(inst: WorkflowInstance) -> RecordScope:
    # PHASE_01: instances carry no org unit; ``instance.cancel`` is a ● grant (unit_manager) -> GLOBAL scope
    # needed
    return RecordScope(owners=frozenset({inst.started_by_id}) if inst.started_by_id else frozenset())


def request_cancel(
    caller: Caller, instance_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> WorkflowInstance:
    text = reason.strip()
    if len(text) < 3:
        raise ValidationFailed("a reason is required", errors=[FieldError("reason", "REQUIRED")])
    with unit_of_work(caller.context(request_id)) as uow:
        inst = _lock(instance_id)
        require_record(caller, CANCEL, instance_scope(inst))
        require_step_up(caller, CANCEL)
        _set(
            uow,
            inst,
            IS.CANCEL_REQUESTED,
            "cancel_request",
            reason=text,
            cancel_requested_by_id=caller.user_id,
            cancel_requested_at=db_now(),
            cancel_reason=text,
        )
        for req in ApprovalRequest.objects.select_for_update().filter(
            workflow_instance=inst, status=ApprovalStatus.PENDING
        ):
            approvals.close(
                uow, req, ApprovalStatus.WITHDRAWN, by=caller.user_id, note="workflow instance cancelled"
            )
        for t in (
            WorkTask.objects.select_for_update()
            .filter(workflow_instance=inst)
            .exclude(status__in=[TaskStatus.CLOSED, TaskStatus.CANCELLED])
        ):
            tasks.system_cancel(uow, t, reason=f"workflow instance cancelled: {text}", by=caller.user_id)
        pending = _compensations(inst)
        if pending:
            _set(uow, inst, IS.COMPENSATING, "compensate", reason=text)
            for step, comp in pending:
                _event(inst, step, StepEventKind.COMPENSATION_STARTED, caller.user_id, {"compensation": comp})
        else:
            _set(uow, inst, IS.CANCELLED, "cancel", reason=text)
    return inst


def record_compensated(ctx: RequestContext, instance_id: uuid.UUID, *, step: str) -> WorkflowInstance:
    """A compensation step finished (its effect = new records written by the owning module)."""
    with unit_of_work(ctx) as uow:
        inst = _lock(instance_id)
        if inst.status != IS.COMPENSATING:
            raise StateTransitionNotAllowed("the instance is not compensating")
        started = set(
            WorkflowStepEvent.objects.filter(
                instance=inst, event=StepEventKind.COMPENSATION_STARTED
            ).values_list("step_key", flat=True)
        )
        done = set(
            WorkflowStepEvent.objects.filter(instance=inst, event=StepEventKind.COMPENSATED).values_list(
                "step_key", flat=True
            )
        )
        if step not in started or step in done:
            raise StateTransitionNotAllowed("no running compensation for this step")
        _event(inst, step, StepEventKind.COMPENSATED, ctx.actor.actor_id)
        if started <= done | {step}:
            _set(uow, inst, IS.CANCELLED, "cancel", reason="compensation completed")
        else:
            _audit(uow, "compensated_step", inst, before=inst.status)
    return inst


def fail(
    ctx: RequestContext, instance_id: uuid.UUID, *, failure_code: str, step: str = ""
) -> WorkflowInstance:
    import re

    if not re.fullmatch(ERROR_CODE_PATTERN, failure_code):
        raise ValidationFailed(errors=[FieldError("failure_code", "INVALID")])
    with unit_of_work(ctx) as uow:
        inst = _lock(instance_id)
        _event(
            inst,
            step or inst.current_step,
            StepEventKind.FAILED,
            ctx.actor.actor_id,
            {"failure_code": failure_code},
        )
        _set(uow, inst, IS.FAILED, "fail", failure_code=failure_code)
    return inst
