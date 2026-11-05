"""Operational tasks (page 39; STATE_TRANSITIONS 4.3).

Machine: OPEN/ASSIGNED -> IN_PROGRESS <-> BLOCKED -> DONE -> CLOSED; any non-terminal -> CANCELLED (reason).
DONE != CLOSED; the verifier must differ from the completer (403 ``SELF_APPROVAL_FORBIDDEN``; DB CHECK
``ck_work_task_verifier``). Reopen, SLA clocks and SLA pause have no approved rule (STATE_TRANSITIONS 4.11)
and
are not implemented; ``due_at`` is informational. A task owned by a workflow instance is cancelled only
through
the instance's cancellation (``instances.request_cancel``).

Record scope (authz): units = assignee unit / the unit of the assignee position / the units where the assignee
user holds a position; owners = creator, assignee user, completer and the current holders of an assignee
position (or of positions in an assignee unit). ``platform.workflow.task.cancel`` ○ means "created by me"
(PERMISSION_MATRIX section 3), so its owners are the creator only.
"""

from __future__ import annotations

import uuid
from typing import Final

from django.db.models import Q

from platform_core.authz.policy import (
    Caller,
    RecordScope,
    require_permission,
    require_record,
    require_step_up,
)
from platform_core.engine.context import db_now
from platform_core.engine.errors import (
    FieldError,
    NotFound,
    SelfApprovalForbidden,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import UnitOfWork, unit_of_work

from .models import AssigneeKind, TaskStatus, WorkTask

TASK_MACHINE: Final = StateMachine(
    name="work_task",
    states=frozenset(TaskStatus.values),
    transitions={
        TaskStatus.OPEN: frozenset({TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
        TaskStatus.ASSIGNED: frozenset({TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
        TaskStatus.IN_PROGRESS: frozenset(
            {TaskStatus.ASSIGNED, TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.CANCELLED}
        ),
        TaskStatus.BLOCKED: frozenset({TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
        TaskStatus.DONE: frozenset({TaskStatus.CLOSED, TaskStatus.CANCELLED}),
        TaskStatus.CLOSED: frozenset(),
        TaskStatus.CANCELLED: frozenset(),
    },
)


def _current_holders(
    *, position_id: uuid.UUID | None = None, unit_id: uuid.UUID | None = None
) -> frozenset[uuid.UUID]:
    from platform_core.org.models import PositionAssignment

    now = db_now()
    qs = PositionAssignment.objects.filter(valid_from__lte=now).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gt=now)
    )
    if position_id is not None:
        qs = qs.filter(position_id=position_id)
    elif unit_id is not None:
        qs = qs.filter(position__unit_id=unit_id)
    else:
        return frozenset()
    return frozenset(qs.values_list("user_id", flat=True))


def _units_of_user(user_id: uuid.UUID) -> frozenset[uuid.UUID]:
    from platform_core.authz.policy import own_units

    return own_units(user_id)


def task_units(t: WorkTask) -> frozenset[uuid.UUID]:
    from platform_core.org.models import Position

    if t.assignee_kind == AssigneeKind.ORG_UNIT and t.assignee_unit_id:
        return frozenset({t.assignee_unit_id})
    if t.assignee_kind == AssigneeKind.POSITION and t.assignee_position_id:
        unit = Position.objects.filter(pk=t.assignee_position_id).values_list("unit_id", flat=True).first()
        return frozenset({unit}) if unit else frozenset()
    if t.assignee_user_id:
        return _units_of_user(t.assignee_user_id)
    return frozenset()


def record_scope(t: WorkTask, action: str) -> RecordScope:
    units = task_units(t)
    owners: set[uuid.UUID | None]
    if action == "platform.workflow.task.cancel":
        owners = {t.created_by_id}
    else:
        owners = {t.created_by_id, t.assignee_user_id, t.completed_by_id}
        if t.assignee_kind == AssigneeKind.POSITION:
            owners |= _current_holders(position_id=t.assignee_position_id)
        elif t.assignee_kind == AssigneeKind.ORG_UNIT:
            owners |= _current_holders(unit_id=t.assignee_unit_id)
    return RecordScope(units=units, owners=frozenset(o for o in owners if o is not None))


def _assignee_scope(
    kind: str, user_id: uuid.UUID | None, unit_id: uuid.UUID | None, position_id: uuid.UUID | None
) -> RecordScope:
    probe = WorkTask(
        assignee_kind=kind,
        assignee_user_id=user_id,
        assignee_unit_id=unit_id,
        assignee_position_id=position_id,
    )
    return RecordScope(units=task_units(probe))


def _reason(text: str, field: str = "reason") -> str:
    value = text.strip()
    if len(value) < 3:
        raise ValidationFailed("a reason is required", errors=[FieldError(field, "REQUIRED")])
    return value[:500]


def _view(t: WorkTask) -> dict[str, object]:
    return {
        "status": t.status,
        "assignee_kind": t.assignee_kind,
        "assignee_user_id": str(t.assignee_user_id) if t.assignee_user_id else None,
        "assignee_unit_id": str(t.assignee_unit_id) if t.assignee_unit_id else None,
        "assignee_position_id": str(t.assignee_position_id) if t.assignee_position_id else None,
    }


def _audit(
    uow: UnitOfWork,
    verb: str,
    t: WorkTask,
    *,
    before: dict[str, object] | None,
    reason: str = "",
    scope: dict[str, object] | None = None,
) -> None:
    uow.audit(
        action=f"platform.workflow.task.{verb}",
        resource_type="platform.work_task",
        resource_id=str(t.pk),
        resource_version=t.row_version,
        before=before,
        after=_view(t),
        reason=reason,
        scope=scope or {},
    )
    uow.emit(
        event_type="platform.workflow.task.changed",
        aggregate_type="platform.work_task",
        aggregate_id=str(t.pk),
        aggregate_version=t.row_version,
        payload={"id": str(t.pk), "status": t.status, "verb": verb},
    )


def _lock(task_id: uuid.UUID) -> WorkTask:
    t = WorkTask.objects.select_for_update().filter(pk=task_id).first()
    if t is None:
        raise NotFound()
    return t


def _assignee_fields(
    kind: str, user_id: uuid.UUID | None, unit_id: uuid.UUID | None, position_id: uuid.UUID | None
) -> dict[str, object]:
    if kind not in AssigneeKind.values:
        raise ValidationFailed(errors=[FieldError("assignee_kind", "INVALID")])
    refs = {AssigneeKind.USER: user_id, AssigneeKind.ORG_UNIT: unit_id, AssigneeKind.POSITION: position_id}
    if refs[AssigneeKind(kind)] is None or sum(v is not None for v in refs.values()) != 1:
        raise ValidationFailed(errors=[FieldError("assignee", "INVALID")])
    return {
        "assignee_kind": kind,
        "assignee_user_id": user_id,
        "assignee_unit_id": unit_id,
        "assignee_position_id": position_id,
    }


# --------------------------------------------------------------------------------------------- commands
def create_task(
    caller: Caller,
    *,
    subject: str,
    assignee_kind: str,
    assignee_user_id: uuid.UUID | None = None,
    assignee_unit_id: uuid.UUID | None = None,
    assignee_position_id: uuid.UUID | None = None,
    related_type: str = "",
    related_id: str = "",
    related_revision: int | None = None,
    request_id: uuid.UUID | None = None,
) -> WorkTask:
    action = "platform.workflow.task.create"
    fields = _assignee_fields(assignee_kind, assignee_user_id, assignee_unit_id, assignee_position_id)
    if not subject.strip():
        raise ValidationFailed(errors=[FieldError("subject", "REQUIRED")])
    require_record(
        caller,
        action,
        _assignee_scope(assignee_kind, assignee_user_id, assignee_unit_id, assignee_position_id),
    )
    with unit_of_work(caller.context(request_id)) as uow:
        t = WorkTask.objects.create(
            subject=subject.strip()[:300],
            related_type=related_type,
            related_id=related_id,
            related_revision=related_revision,
            status=TaskStatus.ASSIGNED if assignee_kind == AssigneeKind.USER else TaskStatus.OPEN,
            created_by_id=caller.user_id,
            updated_by_id=caller.user_id,
            **fields,
        )
        t.refresh_from_db()
        _audit(uow, "create", t, before=None)
    return t


def _transition(
    caller: Caller,
    task_id: uuid.UUID,
    action: str,
    target: TaskStatus,
    verb: str,
    *,
    request_id: uuid.UUID | None,
    reason: str = "",
    from_states: frozenset[str] | None = None,
    not_in_instance: bool = False,
    **values: object,
) -> WorkTask:
    require_permission(caller, action)
    with unit_of_work(caller.context(request_id)) as uow:
        t = _lock(task_id)
        require_record(caller, action, record_scope(t, action))
        require_step_up(caller, action)
        if from_states is not None and t.status not in from_states:
            raise StateTransitionNotAllowed(f"work_task: {verb} is not allowed from {t.status}")
        if not_in_instance and t.workflow_instance_id is not None:
            raise StateTransitionNotAllowed("cancel the workflow instance instead (STATE_TRANSITIONS 4.5)")
        TASK_MACHINE.assert_transition(t.status, target)
        before = _view(t)
        WorkTask.objects.filter(pk=t.pk).update(status=target, updated_by_id=caller.user_id, **values)
        t.refresh_from_db()
        _audit(uow, verb, t, before=before, reason=reason)
    return t


def reassign(
    caller: Caller,
    task_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> WorkTask:
    """-> ASSIGNED to a user (``platform.workflow.task.assign``); the new assignee must be in scope too."""
    action = "platform.workflow.task.assign"
    text = _reason(reason)
    require_record(caller, action, _assignee_scope(AssigneeKind.USER, user_id, None, None))
    return _transition(
        caller,
        task_id,
        action,
        TaskStatus.ASSIGNED,
        "reassign",
        request_id=request_id,
        reason=text,
        assignee_kind=AssigneeKind.USER,
        assignee_user_id=user_id,
        assignee_unit_id=None,
        assignee_position_id=None,
        blocked_reason="",
    )


def start(caller: Caller, task_id: uuid.UUID, *, request_id: uuid.UUID | None = None) -> WorkTask:
    return _transition(
        caller,
        task_id,
        "platform.workflow.task.work",
        TaskStatus.IN_PROGRESS,
        "start",
        request_id=request_id,
        from_states=frozenset({TaskStatus.OPEN, TaskStatus.ASSIGNED}),
    )


def block(
    caller: Caller,
    task_id: uuid.UUID,
    *,
    reason: str,
    blocked_by_ref: str = "",
    request_id: uuid.UUID | None = None,
) -> WorkTask:
    text = _reason(reason)
    return _transition(
        caller,
        task_id,
        "platform.workflow.task.work",
        TaskStatus.BLOCKED,
        "block",
        request_id=request_id,
        reason=text,
        blocked_reason=text,
        blocked_by_ref=blocked_by_ref[:200],
    )


def unblock(caller: Caller, task_id: uuid.UUID, *, request_id: uuid.UUID | None = None) -> WorkTask:
    return _transition(
        caller,
        task_id,
        "platform.workflow.task.work",
        TaskStatus.IN_PROGRESS,
        "unblock",
        request_id=request_id,
        from_states=frozenset({TaskStatus.BLOCKED}),
        blocked_reason="",
        blocked_by_ref="",
    )


def complete(caller: Caller, task_id: uuid.UUID, *, request_id: uuid.UUID | None = None) -> WorkTask:
    return _transition(
        caller,
        task_id,
        "platform.workflow.task.work",
        TaskStatus.DONE,
        "complete",
        request_id=request_id,
        completed_by_id=caller.user_id,
        completed_at=db_now(),
    )


def verify_close(caller: Caller, task_id: uuid.UUID, *, request_id: uuid.UUID | None = None) -> WorkTask:
    action = "platform.workflow.task.verify"
    require_permission(caller, action)
    with unit_of_work(caller.context(request_id)) as uow:
        t = _lock(task_id)
        require_record(caller, action, record_scope(t, action))
        if t.completed_by_id == caller.user_id:
            raise SelfApprovalForbidden("the completer cannot verify his own task")
        TASK_MACHINE.assert_transition(t.status, TaskStatus.CLOSED)
        before = _view(t)
        WorkTask.objects.filter(pk=t.pk).update(
            status=TaskStatus.CLOSED,
            closed_by_id=caller.user_id,
            closed_at=db_now(),
            updated_by_id=caller.user_id,
        )
        t.refresh_from_db()
        _audit(uow, "verify_close", t, before=before)
    return t


def cancel(
    caller: Caller, task_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> WorkTask:
    text = _reason(reason)
    return _transition(
        caller,
        task_id,
        "platform.workflow.task.cancel",
        TaskStatus.CANCELLED,
        "cancel",
        request_id=request_id,
        reason=text,
        not_in_instance=True,
        cancelled_by_id=caller.user_id,
        cancelled_at=db_now(),
        cancel_reason=text,
    )


def system_cancel(uow: UnitOfWork, t: WorkTask, *, reason: str, by: uuid.UUID | None) -> None:
    """Cancellation as an effect of a workflow-instance cancel (caller holds the lock, same transaction)."""
    if t.status in (TaskStatus.CLOSED, TaskStatus.CANCELLED):
        return
    before = _view(t)
    WorkTask.objects.filter(pk=t.pk).update(
        status=TaskStatus.CANCELLED,
        cancelled_by_id=by,
        cancelled_at=db_now(),
        cancel_reason=reason[:500],
        updated_by_id=by,
    )
    t.refresh_from_db()
    _audit(uow, "cancel", t, before=before, reason=reason)
