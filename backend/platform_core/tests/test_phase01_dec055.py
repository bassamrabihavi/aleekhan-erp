"""DEC-055 (option B): the owner's one-time bootstrap self-approval of the first holder of a business-approval
role - service rules, DB guard (raw SQL bypass refused) and the race "two bootstrap approvals, one role"."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from platform_core.authz.policy import Caller
from platform_core.engine.errors import MfaRequired, SelfApprovalForbidden, ValidationFailed
from platform_core.identity import roles
from platform_core.identity.models import Role, RoleAssignment, User
from platform_core.models import AuditEvent
from platform_core.workflow import approvals
from platform_core.workflow.models import ApprovalRequest

from .engine_fixtures import caller, ensure_catalogue, give_role, person, with_role
from .phase01_factories import db_refuses
from .threads import run_concurrently


def _rid(ra: RoleAssignment) -> uuid.UUID:
    assert ra.approval_request_id is not None
    return ra.approval_request_id


def _pending(owner: Caller, role: str = "document_approver", who: User | None = None) -> RoleAssignment:
    target = who or person()
    return roles.grant_role(owner, user_id=target.pk, role_code=role, reason="first approver")


@pytest.mark.django_db
def test_owner_bootstraps_the_first_holder_once_per_role() -> None:
    _o, owner = with_role("owner_admin")
    ra = _pending(owner)
    out = approvals.bootstrap_self_approve(owner, _rid(ra), reason="DEC-055 first document approver")
    assert out.request.status == "APPROVED" and out.request.bootstrap_self_approval
    assert out.request.decided_by_id == out.request.requested_by_id
    ra.refresh_from_db()
    assert ra.status == "ACTIVE"
    audit = AuditEvent.objects.get(
        action="platform.workflow.approval.approve", resource_id=str(out.request.pk)
    )
    assert audit.scope == {"bootstrap_self_approval": True} and audit.reason
    # second holder of the same role: DEC-032 unchanged
    second = _pending(owner)
    with pytest.raises(SelfApprovalForbidden):
        approvals.bootstrap_self_approve(owner, _rid(second), reason="second approver")
    # still once per role even after the first holder is gone
    roles.revoke_assignment(owner, ra.pk, reason="left the company")
    with pytest.raises(SelfApprovalForbidden):
        approvals.bootstrap_self_approve(owner, _rid(second), reason="again")
    # the normal path still works: a third person (holder of approval.decide) decides
    decider = person()
    give_role(decider, "workflow_approver")
    assert approvals.approve(caller(decider), _rid(second)).request.status == "APPROVED"


@pytest.mark.django_db
def test_owner_may_bootstrap_his_own_first_business_role() -> None:
    o, owner = with_role("owner_admin")
    ra = roles.grant_role(
        owner, user_id=o.pk, role_code="workflow_approver", reason="self, first", allow_self=True
    )
    approvals.bootstrap_self_approve(owner, _rid(ra), reason="DEC-055 owner as first workflow approver")
    ra.refresh_from_db()
    assert ra.status == "ACTIVE" and ra.self_assignment


@pytest.mark.django_db
def test_bootstrap_needs_owner_step_up_and_reason() -> None:
    o, owner = with_role("owner_admin")
    ra = _pending(owner)
    with pytest.raises(ValidationFailed):
        approvals.bootstrap_self_approve(owner, _rid(ra), reason=" ")
    with pytest.raises(MfaRequired):
        approvals.bootstrap_self_approve(caller(o, mfa=False), _rid(ra), reason="no step-up")
    # a non-owner who made a request (synthetic setup) can never self-approve
    grantor = person()
    give_role(grantor, "employee")
    target = person()
    ra2 = RoleAssignment.objects.create(
        user=target,
        role=Role.objects.get(code="config_approver"),
        scope_kind="GLOBAL",
        status="PENDING_APPROVAL",
        granted_by=grantor,
        reason="synthetic grant",
    )
    now = timezone.now()
    req = ApprovalRequest.objects.create(
        action_id="platform.identity.assignment.grant",
        resource_type="role_assignment",
        resource_id=str(ra2.pk),
        resource_revision=1,
        requested_by=grantor,
        requested_at=now,
        expires_at=now + timedelta(days=30),
    )
    with pytest.raises(SelfApprovalForbidden):
        approvals.bootstrap_self_approve(caller(grantor), req.pk, reason="not an owner")
    assert ApprovalRequest.objects.get(pk=req.pk).status == "PENDING"


# --------------------------------------------------------------------------------------------- DB guard
def _raw_self_approve(req_id: uuid.UUID, *, flag: bool, note: str = "raw bypass") -> None:
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE platform_approval_request SET status = 'APPROVED', decided_by_id = requested_by_id, "
            "closed_at = now(), decision_note = %s, bootstrap_self_approval = %s WHERE id = %s",
            [note, flag, str(req_id)],
        )


@pytest.mark.django_db
def test_raw_sql_bypass_is_refused_by_the_database() -> None:
    _o, owner = with_role("owner_admin")
    ra = _pending(owner)
    with db_refuses("ck_approval_request_maker_checker"):  # self-approval without the bootstrap flag
        _raw_self_approve(_rid(ra), flag=False)
    with db_refuses("ck_approval_request_bootstrap_self_approval"):  # reason missing
        _raw_self_approve(_rid(ra), flag=True, note="")
    approvals.bootstrap_self_approve(owner, _rid(ra), reason="first holder")
    second = _pending(owner)
    with db_refuses("ck_approval_request_bootstrap_self_approval"):  # not the first holder any more
        _raw_self_approve(_rid(second), flag=True)
    # the flag alone (without the PENDING -> APPROVED decision) is refused too
    with db_refuses("ck_approval_request_bootstrap_self_approval"):
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE platform_approval_request SET bootstrap_self_approval = true WHERE id = %s",
                [str(_rid(second))],
            )


@pytest.mark.django_db
def test_db_refuses_bootstrap_by_a_non_owner() -> None:
    grantor = person()
    target = person()
    ra = RoleAssignment.objects.create(
        user=target,
        role=Role.objects.get(code="document_approver"),
        scope_kind="GLOBAL",
        status="PENDING_APPROVAL",
        granted_by=grantor,
        reason="synthetic grant",
    )
    now = timezone.now()
    req = ApprovalRequest.objects.create(
        action_id="platform.identity.assignment.grant",
        resource_type="role_assignment",
        resource_id=str(ra.pk),
        resource_revision=1,
        requested_by=grantor,
        requested_at=now,
        expires_at=now + timedelta(days=30),
    )
    with db_refuses("ck_approval_request_bootstrap_self_approval"):
        _raw_self_approve(req.pk, flag=True)


# ------------------------------------------------------------------------------------------------ race
@pytest.mark.django_db(transaction=True)
def test_concurrent_bootstrap_approvals_of_one_role_exactly_one_wins(audit_cleanup: None) -> None:
    ensure_catalogue()
    _o, owner = with_role("owner_admin")
    pending = [_pending(owner) for _ in range(4)]

    def boot(i: int) -> str:
        return approvals.bootstrap_self_approve(owner, _rid(pending[i]), reason="race").request.status

    results = run_concurrently(boot, 4)
    ok = [r for r in results if isinstance(r, str)]
    errors = [r for r in results if isinstance(r, BaseException)]
    assert ok == ["APPROVED"] and len(errors) == 3, results
    assert all(isinstance(e, SelfApprovalForbidden) for e in errors), errors
    role = Role.objects.get(code="document_approver")
    assert RoleAssignment.objects.filter(role=role, status="ACTIVE").count() == 1
    assert ApprovalRequest.objects.filter(bootstrap_self_approval=True).count() == 1
