"""Roles, assignments and maker-checker approvals (DEC-003 / DEC-032 / DEC-049) at service level, the
approval state machine, idempotent commands and the race "two deciders, one request"."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from platform_core.authz.policy import Caller
from platform_core.engine import commands
from platform_core.engine.errors import (
    AccessDenied,
    IdempotencyKeyReused,
    MfaRequired,
    NotFound,
    RuleNotApproved,
    SelfApprovalForbidden,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.identity import roles
from platform_core.identity.models import RoleAssignment, User
from platform_core.models import AuditEvent
from platform_core.workflow import approvals
from platform_core.workflow.models import ApprovalRequest

from .engine_fixtures import caller, ensure_catalogue, give_role, person, with_role
from .phase01_factories import org_unit
from .threads import run_concurrently


def _rid(ra: RoleAssignment) -> uuid.UUID:
    assert ra.approval_request_id is not None
    return ra.approval_request_id


def _age_request(request_id: uuid.UUID) -> None:
    """TEST-ONLY: make a request 31 days old (expires_at is immutable for the runtime; DB owner here)."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute("ALTER TABLE platform_approval_request DISABLE TRIGGER trg_approval_request_immutable")
        try:
            cur.execute(
                "UPDATE platform_approval_request SET requested_at = now() - interval '31 days', "
                "expires_at = now() - interval '1 day' WHERE id = %s",
                [str(request_id)],
            )
        finally:
            cur.execute("ALTER TABLE platform_approval_request ENABLE TRIGGER trg_approval_request_immutable")


def _owner() -> tuple[User, Caller]:
    return with_role("owner_admin")


# ------------------------------------------------------------------------------------------- roles
@pytest.mark.django_db
def test_role_lifecycle_and_unapproved_permission_set() -> None:
    _o, owner = _owner()
    role = roles.create_role(owner, code="syn_role_x", name_fa="نقش ساختگی", kind="BUSINESS", reason="test")
    roles.grant_permission(owner, role.pk, action="platform.org.read", mode="SCOPE", reason="test")
    with pytest.raises(RuleNotApproved) as exc:  # no approved matrix version contains this set
        roles.activate_role(owner, role.pk, reason="test")
    assert exc.value.decision_id == "DEC-049"
    tech = roles.create_role(
        owner, code="syn_role_t", name_fa="نقش فنی ساختگی", kind="TECHNICAL", reason="test"
    )
    with pytest.raises(StateTransitionNotAllowed):  # DEC-003
        roles.grant_permission(
            owner, tech.pk, action="platform.workflow.approval.decide", mode="SCOPE", reason="test"
        )
    seeded = type(role).objects.get(code="employee")
    with pytest.raises(StateTransitionNotAllowed):  # grants only while DRAFT
        roles.grant_permission(owner, seeded.pk, action="platform.ops.job.read", mode="SCOPE", reason="test")
    give_role(person(), "employee")
    with pytest.raises(StateTransitionNotAllowed):  # still has live assignments
        roles.retire_role(owner, seeded.pk, reason="test")


@pytest.mark.django_db
def test_role_management_needs_permission_and_step_up() -> None:
    _u, emp = with_role("employee")
    with pytest.raises(AccessDenied):
        roles.create_role(emp, code="syn_role_y", name_fa="ن", kind="BUSINESS", reason="test")
    o, _c = _owner()
    with pytest.raises(MfaRequired):
        roles.create_role(
            caller(o, mfa=False), code="syn_role_z", name_fa="ن", kind="BUSINESS", reason="test"
        )


# ------------------------------------------------------------------------------------- assignments
@pytest.mark.django_db
def test_non_ba_role_is_active_at_once_and_self_assignment_is_explicit_and_flagged() -> None:
    o, owner = _owner()
    target = person()
    ra = roles.grant_role(owner, user_id=target.pk, role_code="employee", reason="new hire")
    assert ra.status == "ACTIVE" and ra.self_assignment is False
    with pytest.raises(ValidationFailed):
        roles.grant_role(owner, user_id=o.pk, role_code="employee", reason="self")
    mine = roles.grant_role(
        owner, user_id=o.pk, role_code="management_viewer", reason="self", allow_self=True
    )
    assert mine.self_assignment is True
    audit = AuditEvent.objects.get(action="platform.identity.assignment.grant", resource_id=str(mine.pk))
    assert audit.scope == {"self_assignment": True}


@pytest.mark.django_db
def test_ba_role_waits_for_a_third_person() -> None:
    o, owner = _owner()
    target = person()
    ra = roles.grant_role(owner, user_id=target.pk, role_code="document_approver", reason="new approver")
    assert ra.status == "PENDING_APPROVAL" and ra.requires_second_approval
    req = ApprovalRequest.objects.get(pk=_rid(ra))
    assert (req.action_id, req.resource_type, req.status) == (
        "platform.identity.assignment.grant",
        "role_assignment",
        "PENDING",
    )
    # the owner holds decide since DEC-056 but is the requester (DEC-032 maker != checker); the grantee
    # cannot decide; the grantor cannot decide
    with pytest.raises(SelfApprovalForbidden):
        approvals.approve(owner, req.pk)
    give_role(target, "workflow_approver")
    with pytest.raises(SelfApprovalForbidden):
        approvals.approve(caller(target), req.pk)
    give_role(o, "workflow_approver")
    with pytest.raises(SelfApprovalForbidden):
        approvals.approve(caller(o), req.pk)
    third = person()
    give_role(third, "workflow_approver")
    with pytest.raises(MfaRequired):
        approvals.approve(caller(third, mfa=False), req.pk)
    out = approvals.approve(caller(third), req.pk, note="ok")
    assert out.request.status == "APPROVED"
    ra.refresh_from_db()
    assert ra.status == "ACTIVE" and ra.approval_request_id == req.pk
    with pytest.raises(StateTransitionNotAllowed):  # decided once
        approvals.approve(caller(third), req.pk)


@pytest.mark.django_db
def test_rejected_request_revokes_the_pending_assignment_and_note_is_mandatory() -> None:
    _o, owner = _owner()
    ra = roles.grant_role(owner, user_id=person().pk, role_code="config_approver", reason="test grant")
    decider = person()
    give_role(decider, "workflow_approver")
    with pytest.raises(ValidationFailed):
        approvals.reject(caller(decider), _rid(ra), note="")
    approvals.reject(caller(decider), _rid(ra), note="not needed")
    ra.refresh_from_db()
    assert ra.status == "REVOKED" and ra.revoke_reason


@pytest.mark.django_db
def test_route_scope_out_of_scope_decider_gets_not_found() -> None:
    unit_a, unit_b = org_unit(), org_unit()
    _o, owner = _owner()
    ra = roles.grant_role(
        owner,
        user_id=person().pk,
        role_code="document_approver",
        scope_kind="ORG_UNIT",
        scope_unit_id=unit_a.pk,
        reason="test grant",
    )
    local = person()
    give_role(local, "workflow_approver", scope_kind="ORG_UNIT", scope_unit=unit_b)
    with pytest.raises(NotFound):  # SEC-01: request outside the decider's scope
        approvals.approve(caller(local), _rid(ra))


@pytest.mark.django_db
def test_revoke_pending_withdraws_request_and_expiry_sweeps() -> None:
    _o, owner = _owner()
    ra = roles.grant_role(owner, user_id=person().pk, role_code="document_approver", reason="test grant")
    roles.revoke_assignment(owner, ra.pk, reason="mistake")
    assert ApprovalRequest.objects.get(pk=_rid(ra)).status == "WITHDRAWN"
    ra2 = roles.grant_role(owner, user_id=person().pk, role_code="document_approver", reason="test grant")
    _age_request(_rid(ra2))
    d = person()
    give_role(d, "workflow_approver")
    with pytest.raises(StateTransitionNotAllowed):  # an expired request cannot be decided
        approvals.approve(caller(d), _rid(ra2))
    assert approvals.expire_due() >= 1
    ra2.refresh_from_db()
    assert ApprovalRequest.objects.get(pk=_rid(ra2)).status == "EXPIRED"
    assert ra2.status == "REVOKED"
    timed = give_role(person(), "employee")
    from django.db.models import F

    RoleAssignment.objects.filter(pk=timed.pk).update(valid_to=F("valid_from") + timedelta(microseconds=1))
    assert roles.expire_due_assignments() >= 1
    timed.refresh_from_db()
    assert timed.status == "EXPIRED"


# ------------------------------------------------------------------------------------ state machine
def test_approval_machine_every_pair() -> None:
    states = sorted(approvals.APPROVAL_MACHINE.states)
    allowed = {("PENDING", s) for s in ("APPROVED", "REJECTED", "WITHDRAWN", "SUPERSEDED", "EXPIRED")}
    for a in states:
        for b in states:
            assert approvals.APPROVAL_MACHINE.can(a, b) is ((a, b) in allowed), (a, b)


def test_role_and_assignment_machines() -> None:
    assert roles.ROLE_MACHINE.can("DRAFT", "ACTIVE") and roles.ROLE_MACHINE.can("ACTIVE", "RETIRED")
    assert not roles.ROLE_MACHINE.can("ACTIVE", "DRAFT") and not roles.ROLE_MACHINE.can("RETIRED", "ACTIVE")
    m = roles.ASSIGNMENT_MACHINE
    assert m.can("PENDING_APPROVAL", "ACTIVE") and m.can("ACTIVE", "EXPIRED") and m.can("ACTIVE", "REVOKED")
    assert (
        not m.can("REVOKED", "ACTIVE")
        and not m.can("EXPIRED", "ACTIVE")
        and not m.can("PENDING_APPROVAL", "EXPIRED")
    )


# ------------------------------------------------------------------------------------ idempotency
@pytest.mark.django_db(transaction=True)
def test_idempotent_command_runs_once_and_refuses_key_reuse(audit_cleanup: None) -> None:
    ensure_catalogue()
    _o, owner = _owner()
    target = person()
    key = uuid.uuid4()
    calls: list[int] = []

    def grant() -> dict[str, str]:
        calls.append(1)
        ra = roles.grant_role(owner, user_id=target.pk, role_code="employee", reason="idempotent")
        return {"id": str(ra.pk), "status": ra.status}

    first, replayed1 = commands.execute(
        owner.context(), key=key, command="grant_role", payload={"u": str(target.pk)}, fn=grant
    )
    second, replayed2 = commands.execute(
        owner.context(), key=key, command="grant_role", payload={"u": str(target.pk)}, fn=grant
    )
    assert (replayed1, replayed2) == (False, True) and first == second and len(calls) == 1
    assert RoleAssignment.objects.filter(user=target).count() == 1
    with pytest.raises(IdempotencyKeyReused):
        commands.execute(owner.context(), key=key, command="grant_role", payload={"u": "other"}, fn=grant)


# ------------------------------------------------------------------------------------------- race
@pytest.mark.django_db(transaction=True)
def test_concurrent_decisions_on_one_request_give_exactly_one_decision(audit_cleanup: None) -> None:
    ensure_catalogue()
    _o, owner = _owner()
    ra = roles.grant_role(owner, user_id=person().pk, role_code="document_approver", reason="race")
    deciders = []
    for _ in range(6):
        d = person()
        give_role(d, "workflow_approver")
        deciders.append(caller(d))

    def decide(i: int) -> str:
        fn = approvals.approve if i % 2 == 0 else approvals.reject
        return fn(deciders[i], _rid(ra), note="race decision").request.status

    results = run_concurrently(decide, 6)
    ok = [r for r in results if isinstance(r, str)]
    errors = [r for r in results if isinstance(r, BaseException)]
    assert len(ok) == 1 and len(errors) == 5
    assert all(isinstance(e, StateTransitionNotAllowed) for e in errors), errors
    req = ApprovalRequest.objects.get(pk=_rid(ra))
    assert req.status == ok[0] and req.decided_by_id is not None
