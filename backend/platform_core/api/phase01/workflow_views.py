"""``workflow`` endpoints: tasks, approvals (maker-checker DEC-032, bootstrap DEC-055), definitions,
instances.

* Tasks: record scope = ``workflow.tasks.record_scope`` (units through the assignee, owners = creator /
  assignee / holders of the assigned position or unit). Holders change over time, so the list uses the SAME
  per-record check as ``getTask`` (:func:`paginate_filtered`, list == object check).
* Approvals: read scope = route unit + requester (``workflow.approvals.record_scope``); deciding needs the
  decider permission of the request (``authz.policy.decider_permission``: document approve / parameter publish
  / ``platform.workflow.approval.decide``), BUSINESS roles only, maker != checker, fresh MFA step-up.
* ``bootstrapSelfApproveRequest`` (DEC-055 option B, contract item of 01.4): the owner approves his own
  request for the FIRST holder of a business-approval role - a separate operation (never a flag on
  ``approveRequest``), so ``approveRequest`` keeps DEC-032 unchanged and the exception is visible in audit and
  contract.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from django.db.models import Q
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.authz import policy as P
from platform_core.authz.policy import Caller, RecordScope
from platform_core.engine.context import db_now
from platform_core.engine.errors import NotFound
from platform_core.engine.idempotency import StoredResponse
from platform_core.org.models import PositionAssignment
from platform_core.workflow import approvals, instances, tasks
from platform_core.workflow.models import (
    ApprovalRequest,
    WorkflowDefinition,
    WorkflowInstance,
    WorkTask,
)

from . import serializers as S
from .common import (
    Phase01View,
    body_of,
    etag_response,
    if_match,
    in_scope,
    lock_checked,
    not_supported,
    paginate,
    paginate_filtered,
    query_choice,
    stored,
    write,
)

TASK_READ: Final = "platform.workflow.task.read"
TASK_CREATE: Final = "platform.workflow.task.create"
TASK_WORK: Final = "platform.workflow.task.work"
TASK_ASSIGN: Final = "platform.workflow.task.assign"
TASK_VERIFY: Final = "platform.workflow.task.verify"
TASK_CANCEL: Final = "platform.workflow.task.cancel"
APPROVAL_READ: Final = "platform.workflow.approval.read"
APPROVAL_REQUEST: Final = "platform.workflow.approval.request"
APPROVAL_DECIDE: Final = "platform.workflow.approval.decide"
BOOTSTRAP: Final = "platform.identity.assignment.grant"
DEFINITION_READ: Final = "platform.workflow.definition.read"
INSTANCE_CANCEL: Final = "platform.workflow.instance.cancel"
TASK_STATUSES: Final = ("OPEN", "ASSIGNED", "IN_PROGRESS", "BLOCKED", "DONE", "CLOSED", "CANCELLED")
APPROVAL_STATUSES: Final = ("PENDING", "APPROVED", "REJECTED", "WITHDRAWN", "EXPIRED", "SUPERSEDED")


# ----------------------------------------------------------------------------------------------- tasks
def _holders(t: WorkTask) -> frozenset[uuid.UUID]:
    now = db_now()
    qs = PositionAssignment.objects.filter(valid_from__lte=now).exclude(valid_to__lte=now)
    if t.assignee_kind == "POSITION" and t.assignee_position_id:
        return frozenset(qs.filter(position_id=t.assignee_position_id).values_list("user_id", flat=True))
    if t.assignee_kind == "ORG_UNIT" and t.assignee_unit_id:
        return frozenset(qs.filter(position__unit_id=t.assignee_unit_id).values_list("user_id", flat=True))
    return frozenset()


def _task_visible(caller: Caller, t: WorkTask, inbox: str | None, own_units: frozenset[uuid.UUID]) -> bool:
    if not P.can(caller, TASK_READ, tasks.record_scope(t, TASK_READ)):
        return False
    if inbox == "mine":
        return t.assignee_user_id == caller.user_id or caller.user_id in _holders(t)
    if inbox == "my_units":
        return bool(tasks.task_units(t) & own_units)
    if inbox == "created_by_me":
        return t.created_by_id == caller.user_id
    return True


class TasksView(Phase01View):
    required_action = TASK_READ
    write_action = TASK_CREATE

    def get(self, request: Request) -> Response:
        caller = self.caller()
        inbox = query_choice(request, "inbox", ("mine", "my_units", "created_by_me"))
        status = query_choice(request, "status", TASK_STATUSES)
        qs = WorkTask.objects.all()
        if status:
            qs = qs.filter(status=status)
        if inbox == "created_by_me":
            qs = qs.filter(created_by_id=caller.user_id)
        own = P.own_units(caller.user_id) if inbox == "my_units" else frozenset()
        return paginate_filtered(request, qs, lambda t: _task_visible(caller, t, inbox, own), S.task)

    def post(self, request: Request) -> Response:
        data = body_of(request, "TaskCreateRequest")
        assignee = data["assignee"]
        related = data.get("related") or {}

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            ref = assignee["ref_id"]
            t = tasks.create_task(
                caller,
                subject=data["subject"],
                assignee_kind=assignee["kind"],
                assignee_user_id=ref if assignee["kind"] == "USER" else None,
                assignee_unit_id=ref if assignee["kind"] == "ORG_UNIT" else None,
                assignee_position_id=ref if assignee["kind"] == "POSITION" else None,
                related_type=related.get("entity_type", ""),
                related_id=related.get("entity_id", ""),
                related_revision=related.get("revision"),
                due_at=data.get("due_at"),
                note=data.get("note", ""),
                request_id=rid,
            )
            return stored(201, S.task(t), etag_version=t.row_version)

        return write(self, run)


class TaskView(Phase01View):
    required_action = TASK_READ

    def get(self, request: Request, task_id: uuid.UUID) -> Response:
        caller = self.caller()
        t = WorkTask.objects.filter(pk=task_id).first()
        if t is None:
            raise NotFound()
        in_scope(caller, TASK_READ, tasks.record_scope(t, TASK_READ))
        return etag_response(S.task(t), t.row_version)


def _task_scope(caller: Caller, action: str) -> Any:
    return lambda t: in_scope(caller, action, tasks.record_scope(t, action))


def _task_action(action: str, schema: str, call: Any) -> type[Phase01View]:
    class _View(Phase01View):
        required_action = action

        def post(self, request: Request, task_id: uuid.UUID) -> Response:
            expected = if_match(self)
            data = body_of(request, schema)

            def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
                lock_checked(WorkTask, task_id, scope=_task_scope(caller, action), expected=expected)
                t = call(caller, task_id, data, rid)
                return stored(200, S.task(t), etag_version=t.row_version)

            return write(self, run)

    return _View


def _note(data: dict[str, Any]) -> str:
    return str(data.get("note") or "")


def _reassign(caller: Caller, task_id: uuid.UUID, data: dict[str, Any], rid: uuid.UUID) -> WorkTask:
    if data["assignee"]["kind"] != "USER":
        raise not_supported("assignee.kind")  # 01.3 engine reassigns to a user only
    return tasks.reassign(
        caller, task_id, user_id=data["assignee"]["ref_id"], reason=data["reason"], request_id=rid
    )


def _block(caller: Caller, task_id: uuid.UUID, data: dict[str, Any], rid: uuid.UUID) -> WorkTask:
    ref = data.get("blocked_by") or {}
    blocked_by = f"{ref['entity_type']}:{ref['entity_id']}" if ref else ""
    return tasks.block(caller, task_id, reason=data["reason"], blocked_by_ref=blocked_by, request_id=rid)


StartTaskView = _task_action(
    TASK_WORK, "OptionalNoteRequest", lambda c, i, d, r: tasks.start(c, i, note=_note(d), request_id=r)
)
CompleteTaskView = _task_action(
    TASK_WORK, "OptionalNoteRequest", lambda c, i, d, r: tasks.complete(c, i, note=_note(d), request_id=r)
)
BlockTaskView = _task_action(TASK_WORK, "TaskBlockRequest", _block)
UnblockTaskView = _task_action(
    TASK_WORK, "OptionalNoteRequest", lambda c, i, d, r: tasks.unblock(c, i, note=_note(d), request_id=r)
)
ReassignTaskView = _task_action(TASK_ASSIGN, "TaskReassignRequest", _reassign)
VerifyCloseTaskView = _task_action(
    TASK_VERIFY,
    "OptionalNoteRequest",
    lambda c, i, d, r: tasks.verify_close(c, i, note=_note(d), request_id=r),
)
CancelTaskView = _task_action(
    TASK_CANCEL, "ReasonRequest", lambda c, i, d, r: tasks.cancel(c, i, reason=d["reason"], request_id=r)
)


# ------------------------------------------------------------------------------------------- approvals
def _approval_q(caller: Caller) -> Q:
    return P.scope_q(
        caller, APPROVAL_READ, unit_field="route_scope_unit_id", owner_fields=("requested_by_id",)
    )


class ApprovalsView(Phase01View):
    required_action = APPROVAL_READ

    def get(self, request: Request) -> Response:
        caller = self.caller()
        inbox = query_choice(request, "inbox", ("to_decide", "requested_by_me"))
        status = query_choice(request, "status", APPROVAL_STATUSES)
        qs = ApprovalRequest.objects.filter(_approval_q(caller))
        if status:
            qs = qs.filter(status=status)
        if inbox == "requested_by_me":
            qs = qs.filter(requested_by_id=caller.user_id)
        if inbox == "to_decide":
            pending = qs.filter(status="PENDING")
            return paginate_filtered(request, pending, lambda r: approvals.can_decide(caller, r), S.approval)
        return paginate(request, self, qs, S.approval)


class ApprovalView(Phase01View):
    required_action = APPROVAL_READ

    def get(self, request: Request, approval_id: uuid.UUID) -> Response:
        caller = self.caller()
        r = ApprovalRequest.objects.filter(pk=approval_id).first()
        if r is None:
            raise NotFound()
        in_scope(caller, APPROVAL_READ, approvals.record_scope(r))
        return etag_response(S.approval(r), r.row_version)


def _decider_scope(caller: Caller) -> Any:
    def check(r: ApprovalRequest) -> None:
        perm = P.decider_permission(r.action_id)
        if not P.can(caller, perm, approvals.record_scope(r)):
            raise NotFound()  # SEC-01: a request the caller cannot decide is not disclosed by the decide path

    return check


class ApproveRequestView(Phase01View):
    required_action = APPROVAL_DECIDE

    def post(self, request: Request, approval_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "ApprovalDecisionRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(ApprovalRequest, approval_id, scope=_decider_scope(caller), expected=expected)
            out = approvals.approve(
                caller,
                approval_id,
                note=data["note"],
                expected_revision=data["resource_revision"],
                request_ctx_id=rid,
            )
            return stored(200, S.approval(out.request), etag_version=out.request.row_version)

        return write(self, run)


class RejectRequestView(Phase01View):
    required_action = APPROVAL_DECIDE

    def post(self, request: Request, approval_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "ApprovalDecisionRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(ApprovalRequest, approval_id, scope=_decider_scope(caller), expected=expected)
            out = approvals.reject(
                caller,
                approval_id,
                note=data["note"],
                expected_revision=data["resource_revision"],
                request_ctx_id=rid,
            )
            return stored(200, S.approval(out.request), etag_version=out.request.row_version)

        return write(self, run)


def _own_request(caller: Caller) -> Any:
    def check(r: ApprovalRequest) -> None:
        if r.requested_by_id != caller.user_id:
            raise NotFound()  # only the requester's own requests (○)

    return check


class BootstrapApproveRequestView(Phase01View):
    """DEC-055: ``POST /workflow/approvals/{approval_id}/bootstrap-approve`` (owner, first holder only)."""

    required_action = BOOTSTRAP

    def post(self, request: Request, approval_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "ReasonRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(ApprovalRequest, approval_id, scope=_own_request(caller), expected=expected)
            out = approvals.bootstrap_self_approve(
                caller, approval_id, reason=data["reason"], request_ctx_id=rid
            )
            return stored(200, S.approval(out.request), etag_version=out.request.row_version)

        return write(self, run)


class WithdrawRequestView(Phase01View):
    required_action = APPROVAL_REQUEST

    def post(self, request: Request, approval_id: uuid.UUID) -> Response:
        expected = if_match(self)
        body_of(request, "ReasonRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(ApprovalRequest, approval_id, scope=_own_request(caller), expected=expected)
            r = approvals.withdraw(caller, approval_id, request_ctx_id=rid)
            r.refresh_from_db()
            return stored(200, S.approval(r), etag_version=r.row_version)

        return write(self, run)


# ----------------------------------------------------------------------------- definitions / instances
class DefinitionsView(Phase01View):
    required_action = DEFINITION_READ

    def get(self, request: Request) -> Response:
        q = P.scope_q(self.caller(), DEFINITION_READ, unit_field=None, owner_fields=())
        return paginate(request, self, WorkflowDefinition.objects.filter(q), S.workflow_definition)


class DefinitionView(Phase01View):
    required_action = DEFINITION_READ

    def get(self, request: Request, definition_id: uuid.UUID) -> Response:
        caller = self.caller()
        d = WorkflowDefinition.objects.filter(pk=definition_id).first()
        if d is None:
            raise NotFound()
        in_scope(caller, DEFINITION_READ, RecordScope())
        return etag_response(S.workflow_definition(d), d.row_version)


class InstanceView(Phase01View):
    required_action = APPROVAL_READ

    def get(self, request: Request, instance_id: uuid.UUID) -> Response:
        caller = self.caller()
        i = WorkflowInstance.objects.filter(pk=instance_id).first()
        if i is None:
            raise NotFound()
        in_scope(caller, APPROVAL_READ, instances.instance_scope(i))
        return etag_response(S.workflow_instance(i), i.row_version)


class CancelInstanceView(Phase01View):
    required_action = INSTANCE_CANCEL

    def post(self, request: Request, instance_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "ReasonRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(
                WorkflowInstance,
                instance_id,
                scope=lambda i: in_scope(caller, INSTANCE_CANCEL, instances.instance_scope(i)),
                expected=expected,
            )
            i = instances.request_cancel(caller, instance_id, reason=data["reason"], request_id=rid)
            i.refresh_from_db()
            return stored(200, S.workflow_instance(i), etag_version=i.row_version)

        return write(self, run)
