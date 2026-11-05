"""PHASE_01 / 01.2: roles, grants and assignments - DEC-003 (admin != business approval), DEC-032 (second
person for business-approval roles, never self-approval), DEC-049 (matrix v1.0; owner starts as owner_admin).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from platform_core.identity.models import Permission, Role, RoleAssignment, RolePermission
from platform_core.workflow.models import ApprovalRequest

from .phase01_factories import approval, assignment, db_refuses, org_unit, role, user

pytestmark = pytest.mark.django_db
BA_PERMISSIONS = (
    "platform.workflow.approval.decide",
    "platform.document.approve",
    "platform.config.parameter.publish",
)


def _draft_role(kind: str, code: str = "syn_role") -> Role:
    return Role.objects.create(code=code, name_fa="نقش ساختگی", kind=kind, status="DRAFT")


@pytest.mark.parametrize("action", BA_PERMISSIONS)
def test_technical_role_can_never_hold_business_approval(action: str) -> None:
    tech = _draft_role("TECHNICAL")
    with db_refuses("ck_role_technical_no_business_approval"):
        RolePermission.objects.create(role=tech, permission_id=action, grant_mode="SCOPE")


def test_business_role_with_ba_cannot_be_turned_technical() -> None:
    biz = _draft_role("BUSINESS")
    RolePermission.objects.create(role=biz, permission_id="platform.document.approve", grant_mode="SCOPE")
    with db_refuses("ck_role_technical_no_business_approval"):
        Role.objects.filter(pk=biz.pk).update(kind="TECHNICAL")


def test_permission_held_by_technical_role_cannot_become_business_approval() -> None:
    with db_refuses("ck_role_technical_no_business_approval"):
        Permission.objects.filter(action="platform.identity.user.read").update(
            business_approval=True, maker_checker=True, mfa_step_up=True
        )


def test_business_approval_permissions_are_maker_checker_and_mfa() -> None:
    with db_refuses("ck_permission_ba_is_sod_and_mfa"):
        Permission.objects.filter(action="platform.document.approve").update(maker_checker=False)


def test_grants_change_only_while_role_is_draft() -> None:
    oa = role("owner_admin")
    assert oa.status == "ACTIVE"
    with db_refuses("ck_role_permission_draft_only"):
        RolePermission.objects.create(role=oa, permission_id="platform.document.read", grant_mode="SCOPE")
    with db_refuses("ck_role_permission_draft_only"):
        RolePermission.objects.filter(role=oa).delete()


def test_active_role_names_its_matrix_version() -> None:
    r = _draft_role("BUSINESS")
    with db_refuses("ck_role_active_has_matrix"):
        Role.objects.filter(pk=r.pk).update(status="ACTIVE")


def test_assignment_of_draft_role_refused_and_scope_ref_consistent() -> None:
    owner = user()
    target = user()
    draft = _draft_role("BUSINESS")
    with db_refuses("ck_role_assignment_role_active"):
        RoleAssignment.objects.create(
            user=target, role=draft, scope_kind="GLOBAL", status="ACTIVE", granted_by=owner, reason="test"
        )
    with db_refuses("ck_role_assignment_scope_ref"):
        assignment(target, "employee", owner, scope_kind="ORG_UNIT")
    with db_refuses("ck_role_assignment_scope_ref"):
        assignment(target, "employee", owner, scope_unit=org_unit())
    with db_refuses("ck_role_assignment_reason"):
        assignment(target, "employee", owner, reason="x")


def test_console_bootstrap_only_for_technical_roles() -> None:
    """DEC-049 item 4: the owner starts with owner_admin only (console bootstrap = TECHNICAL roles)."""
    owner = user()
    a = assignment(owner, "owner_admin", None)
    assert a.granted_via == "CONSOLE_BOOTSTRAP"
    with db_refuses("ck_role_assignment_bootstrap_technical"):
        assignment(owner, "employee", None)
    with db_refuses("ck_role_assignment_granted_by"):
        assignment(owner, "it_ops", None, granted_via="ADMIN")


def test_self_assignment_is_generated_and_visible() -> None:
    owner = user()
    a = assignment(owner, "employee", owner)
    a.refresh_from_db()
    assert a.self_assignment is True
    b = assignment(user(), "employee", owner)
    b.refresh_from_db()
    assert b.self_assignment is False


def test_business_approval_role_waits_for_a_second_person() -> None:
    """DEC-032: assigning a role holding a BA permission stays PENDING until someone else approves."""
    owner = user()
    target = user()
    a = assignment(target, "workflow_approver", owner, status="PENDING_APPROVAL")
    assert a.requires_second_approval is True
    with db_refuses("ck_role_assignment_second_approval"):
        RoleAssignment.objects.filter(pk=a.pk).update(status="ACTIVE")
    # forcing the flag off is impossible (trigger recomputes it)
    RoleAssignment.objects.filter(pk=a.pk).update(requires_second_approval=False)
    a.refresh_from_db()
    assert a.requires_second_approval is True
    # direct ACTIVE insert without approval is refused
    with db_refuses("ck_role_assignment_second_approval"):
        assignment(user(), "document_approver", owner)


def _grant_request(assign: RoleAssignment, requester, decider, status: str = "APPROVED") -> ApprovalRequest:
    req = approval(
        requester,
        action_id="platform.identity.assignment.grant",
        resource_type="role_assignment",
        resource_id=str(assign.pk),
    )
    ApprovalRequest.objects.filter(pk=req.pk).update(
        status=status, decided_by=decider, closed_at=timezone.now()
    )
    return ApprovalRequest.objects.get(pk=req.pk)


def test_second_approval_must_be_by_someone_else() -> None:
    owner = user()
    target = user()
    second = user()
    a = assignment(target, "workflow_approver", owner, status="PENDING_APPROVAL")
    # the grantor deciding his own request is refused already at the approval row (maker != checker)
    with db_refuses("ck_approval_request_maker_checker"):
        _grant_request(a, owner, owner)
    # the assignee approving his own role is refused at activation
    by_target = _grant_request(a, owner, target)
    with db_refuses("ck_role_assignment_second_approval"):
        RoleAssignment.objects.filter(pk=a.pk).update(status="ACTIVE", approval_request=by_target)
    assert second != owner


def test_second_approval_activation_happy_path() -> None:
    owner, target, second = user(), user(), user()
    a = assignment(target, "workflow_approver", owner, status="PENDING_APPROVAL")
    req = _grant_request(a, owner, second)
    RoleAssignment.objects.filter(pk=a.pk).update(status="ACTIVE", approval_request=req)
    a.refresh_from_db()
    assert a.status == "ACTIVE"


def test_roles_without_ba_activate_directly() -> None:
    owner = user()
    a = assignment(user(), "employee", owner)
    assert a.requires_second_approval is False and a.status == "ACTIVE"


def test_no_overlapping_live_assignment_for_same_user_role_scope() -> None:
    owner, target = user(), user()
    unit = org_unit()
    assignment(target, "employee", owner)
    with db_refuses("ex_role_assignment_no_overlap"):
        assignment(target, "employee", owner)
    # different scope is a different grant
    assignment(target, "employee", owner, scope_kind="ORG_UNIT", scope_unit=unit)
    # a later, non-overlapping window is fine
    later = timezone.now() + timedelta(days=400)
    assignment(target, "unit_manager", owner, valid_from=later, valid_to=later + timedelta(days=1))


def test_assignment_identity_immutable_and_revoked_terminal() -> None:
    owner = user()
    a = assignment(user(), "employee", owner)
    with db_refuses("immutable_column"):
        RoleAssignment.objects.filter(pk=a.pk).update(role=role("unit_manager"))
    with db_refuses("ck_role_assignment_revoked_reason"):
        RoleAssignment.objects.filter(pk=a.pk).update(status="REVOKED")
    RoleAssignment.objects.filter(pk=a.pk).update(
        status="REVOKED", revoked_at=timezone.now(), revoked_by=owner, revoke_reason="synthetic revoke"
    )
    with db_refuses("terminal_immutable"):
        RoleAssignment.objects.filter(pk=a.pk).update(status="ACTIVE")


def test_role_code_immutable() -> None:
    with db_refuses("immutable_column"):
        Role.objects.filter(code="employee").update(code="staff")
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM platform_role WHERE code = 'employee'")
        assert cur.fetchone()[0] == 1
