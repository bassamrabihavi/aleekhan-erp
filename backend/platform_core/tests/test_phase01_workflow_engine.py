"""WorkTask machine (STATE_TRANSITIONS 4.3) and workflow-instance cancellation (4.5) at service level."""

from __future__ import annotations

import pytest

from platform_core.authz.policy import Caller
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import (
    AccessDenied,
    MfaRequired,
    NotFound,
    SelfApprovalForbidden,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.org.models import OrgUnit
from platform_core.workflow import instances, tasks
from platform_core.workflow.models import ApprovalRequest, WorkflowDefinition, WorkflowStepEvent, WorkTask

from .engine_fixtures import caller, give_role, person
from .phase01_factories import approval, org_unit, position, position_assignment

pytestmark = pytest.mark.django_db

EXPECTED_TASK_EDGES = {
    ("OPEN", "ASSIGNED"), ("OPEN", "IN_PROGRESS"), ("OPEN", "CANCELLED"),
    ("ASSIGNED", "ASSIGNED"), ("ASSIGNED", "IN_PROGRESS"), ("ASSIGNED", "CANCELLED"),
    ("IN_PROGRESS", "ASSIGNED"), ("IN_PROGRESS", "BLOCKED"),
    ("IN_PROGRESS", "DONE"), ("IN_PROGRESS", "CANCELLED"),
    ("BLOCKED", "ASSIGNED"), ("BLOCKED", "IN_PROGRESS"), ("BLOCKED", "CANCELLED"),
    ("DONE", "CLOSED"), ("DONE", "CANCELLED"),
}  # fmt: skip


def test_task_machine_every_pair() -> None:
    m = tasks.TASK_MACHINE
    for a in sorted(m.states):
        for b in sorted(m.states):
            assert m.can(a, b) is ((a, b) in EXPECTED_TASK_EDGES), (a, b)
    assert m.terminal_states == {"CLOSED", "CANCELLED"}


def _team() -> tuple[OrgUnit, Caller, Caller, Caller]:
    unit = org_unit()
    mgr, emp, other = person(), person(), person()
    give_role(mgr, "unit_manager", scope_kind="ORG_UNIT_SUBTREE", scope_unit=unit)
    give_role(emp, "employee")
    give_role(other, "employee")
    pos = position(unit, primary_capacity=3)
    position_assignment(pos, emp)
    position_assignment(pos, mgr)
    return unit, caller(mgr), caller(emp), caller(other)


def test_full_task_lifecycle_and_maker_checker() -> None:
    _unit, mgr, emp, _other = _team()
    t = tasks.create_task(mgr, subject="بررسی ساختگی", assignee_kind="USER", assignee_user_id=emp.user_id)
    assert t.status == "ASSIGNED"
    t = tasks.start(emp, t.pk)
    with pytest.raises(ValidationFailed):
        tasks.block(emp, t.pk, reason="")
    t = tasks.block(emp, t.pk, reason="waiting for drawing")
    with pytest.raises(StateTransitionNotAllowed):  # start is not unblock
        tasks.start(emp, t.pk)
    t = tasks.unblock(emp, t.pk)
    t = tasks.complete(emp, t.pk)
    assert t.status == "DONE" and t.completed_by_id == emp.user_id
    with pytest.raises(AccessDenied):  # employees cannot verify at all
        tasks.verify_close(emp, t.pk)
    t = tasks.verify_close(mgr, t.pk)
    assert t.status == "CLOSED"
    with pytest.raises(StateTransitionNotAllowed):
        tasks.cancel(mgr, t.pk, reason="too late")


def test_verifier_must_differ_from_completer() -> None:
    _unit, mgr, _emp, _other = _team()
    t = tasks.create_task(mgr, subject="کار ساختگی", assignee_kind="USER", assignee_user_id=mgr.user_id)
    tasks.start(mgr, t.pk)
    tasks.complete(mgr, t.pk)
    with pytest.raises(SelfApprovalForbidden):
        tasks.verify_close(mgr, t.pk)


def test_out_of_scope_task_is_not_found_for_a_stranger() -> None:
    _unit, mgr, emp, other = _team()
    t = tasks.create_task(mgr, subject="کار ساختگی", assignee_kind="USER", assignee_user_id=emp.user_id)
    with pytest.raises(NotFound):  # SEC-01: another employee, not in the unit, not an owner
        tasks.start(other, t.pk)


def test_employee_creates_only_in_own_unit_and_cancels_only_own() -> None:
    unit, _mgr, emp, other = _team()
    elsewhere = org_unit()
    t = tasks.create_task(emp, subject="درخواست ساختگی", assignee_kind="ORG_UNIT", assignee_unit_id=unit.pk)
    assert t.status == "OPEN"
    with pytest.raises(NotFound):
        tasks.create_task(
            emp, subject="خارج از واحد", assignee_kind="ORG_UNIT", assignee_unit_id=elsewhere.pk
        )
    with pytest.raises(NotFound):  # cancel ○ = created by me
        tasks.cancel(other, t.pk, reason="not mine")
    tasks.cancel(emp, t.pk, reason="duplicate request")
    assert WorkTask.objects.get(pk=t.pk).status == "CANCELLED"


def test_reassign_needs_assign_permission_and_reason() -> None:
    _unit, mgr, emp, other = _team()
    t = tasks.create_task(mgr, subject="کار ساختگی", assignee_kind="USER", assignee_user_id=emp.user_id)
    with pytest.raises(AccessDenied):
        tasks.reassign(emp, t.pk, user_id=other.user_id, reason="handover")
    with pytest.raises(ValidationFailed):
        tasks.reassign(mgr, t.pk, user_id=emp.user_id, reason="")
    assert tasks.reassign(mgr, t.pk, user_id=emp.user_id, reason="handover").status == "ASSIGNED"


# ---------------------------------------------------------------------------------- workflow instance
def _definition(steps: list[dict[str, str]]) -> WorkflowDefinition:
    """TEST-ONLY synthetic definition (definitions are shipped by reviewed migrations of their phases)."""
    d = WorkflowDefinition.objects.create(
        key="syn_flow", version=1, name_fa="گردش ساختگی", steps=steps, status="DRAFT"
    )
    WorkflowDefinition.objects.filter(pk=d.pk).update(status="ACTIVE")
    return d


def test_instance_machine_edges() -> None:
    m = instances.INSTANCE_MACHINE
    assert m.can("RUNNING", "CANCEL_REQUESTED") and m.can("CANCEL_REQUESTED", "COMPENSATING")
    assert m.can("COMPENSATING", "CANCELLED") and not m.can("CANCELLED", "RUNNING")
    assert not m.can("COMPLETED", "CANCEL_REQUESTED") and m.terminal_states == {
        "COMPLETED",
        "CANCELLED",
        "FAILED",
    }


def test_cancel_with_compensation_withdraws_approvals_and_cancels_tasks() -> None:
    _definition([{"key": "draft", "compensation": "void_draft"}, {"key": "review"}])
    starter = person()
    ctx = RequestContext(Actor.user(starter.pk))
    inst = instances.start_instance(
        ctx, definition_key="syn_flow", subject_type="syn_subject", subject_id="1", first_step="draft"
    )
    inst = instances.complete_step(ctx, inst.pk, step="draft", next_step="review")
    req = approval(starter, workflow_instance=inst, resource_type="syn_resource")
    task = WorkTask.objects.create(
        subject="کار گردش",
        assignee_kind="USER",
        assignee_user=starter,
        status="ASSIGNED",
        workflow_instance=inst,
    )
    mgr = person()
    give_role(mgr, "unit_manager")
    with pytest.raises(StateTransitionNotAllowed):  # instance-owned tasks are cancelled through the instance
        tasks.cancel(caller(mgr), task.pk, reason="direct cancel")
    with pytest.raises(MfaRequired):
        instances.request_cancel(caller(mgr, mfa=False), inst.pk, reason="customer withdrew")
    with pytest.raises(ValidationFailed):
        instances.request_cancel(caller(mgr), inst.pk, reason="")
    inst = instances.request_cancel(caller(mgr), inst.pk, reason="customer withdrew")
    assert inst.status == "COMPENSATING" and inst.cancel_reason == "customer withdrew"
    assert ApprovalRequest.objects.get(pk=req.pk).status == "WITHDRAWN"
    assert WorkTask.objects.get(pk=task.pk).status == "CANCELLED"
    inst = instances.record_compensated(ctx, inst.pk, step="draft")
    assert inst.status == "CANCELLED" and inst.ended_at is not None
    kinds = list(
        WorkflowStepEvent.objects.filter(instance=inst).order_by("seq").values_list("event", flat=True)
    )
    assert kinds == ["ENTERED", "COMPLETED", "ENTERED", "COMPENSATION_STARTED", "COMPENSATED"]


def test_cancel_without_compensation_and_fail_with_code() -> None:
    _definition([{"key": "only"}])
    ctx = RequestContext(Actor.system())
    mgr = person()
    give_role(mgr, "unit_manager")
    a = instances.start_instance(ctx, definition_key="syn_flow", subject_type="syn_subject", subject_id="a")
    assert instances.request_cancel(caller(mgr), a.pk, reason="not needed").status == "CANCELLED"
    b = instances.start_instance(ctx, definition_key="syn_flow", subject_type="syn_subject", subject_id="b")
    with pytest.raises(ValidationFailed):
        instances.fail(ctx, b.pk, failure_code="not a code")
    assert instances.fail(ctx, b.pk, failure_code="SYNTHETIC_FAILURE").status == "FAILED"
    with pytest.raises(StateTransitionNotAllowed):
        instances.request_cancel(caller(mgr), b.pk, reason="too late")
