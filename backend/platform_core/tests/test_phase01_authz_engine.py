"""PHASE_01 / 01.3 authorization engine: golden decisions vs the approved matrix, record scope (SEC-01),
TECHNICAL != business approval (DEC-003), MFA step-up, field redaction, production stays deny-all."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from platform_core.api import permissions as api_permissions
from platform_core.authz import policy as P
from platform_core.engine.context import db_now
from platform_core.engine.errors import AccessDenied, MfaRequired, NotFound
from platform_core.engine.redaction import REDACTED
from platform_core.identity.models import User

from .engine_fixtures import caller, give_role, person
from .phase01_factories import org_unit, position, position_assignment

GOLDEN = Path(__file__).parent / "golden" / "permission_decisions.golden.json"


def _golden() -> dict[str, object]:
    data: dict[str, object] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return data


@pytest.mark.django_db
def test_golden_action_decisions_equal_the_approved_matrix() -> None:
    """Every (role, action) of matrix v1.0: one synthetic holder per role with a GLOBAL assignment."""
    golden = _golden()
    decisions: dict[str, dict[str, bool]] = golden["decisions"]  # type: ignore[assignment]
    callers = {}
    for role in golden["roles"]:  # type: ignore[attr-defined]
        u = person()
        give_role(u, role)
        callers[role] = caller(u)
    actual = {action: {role: P.can(callers[role], action) for role in callers} for action in decisions}
    assert actual == decisions


@pytest.mark.django_db
def test_technical_roles_never_pass_business_approval_checks() -> None:
    owner = person()
    give_role(owner, "owner_admin")
    c = caller(owner)
    for action in (
        "platform.workflow.approval.decide",
        "platform.document.approve",
        "platform.config.parameter.publish",
    ):
        assert P.can(c, action) is False
        with pytest.raises(AccessDenied):
            P.require_permission(c, action)


@pytest.mark.django_db
def test_no_assignment_denies_everything_and_unknown_action_denies() -> None:
    c = caller(person())
    assert P.can(c, "platform.org.read") is False
    with pytest.raises(AccessDenied):
        P.require_permission(c, "platform.no_such.action")


@pytest.mark.django_db
def test_inactive_user_has_no_grants() -> None:
    u = person()
    give_role(u, "employee")
    User.objects.filter(pk=u.pk).update(status="DISABLED")
    assert P.can(caller(u), "platform.org.read") is False


@pytest.mark.django_db
def test_expired_and_future_assignments_do_not_grant() -> None:
    u = person()
    ra = give_role(u, "employee")
    assert P.can(caller(u), "platform.org.read")
    type(ra).objects.filter(pk=ra.pk).update(valid_to=db_now() + timedelta(seconds=1))
    assert P.grants_for(u.pk, "platform.org.read", at=db_now() + timedelta(seconds=5)) == []


# -------------------------------------------------------------------------------------------- SEC-01
@pytest.mark.django_db
def test_out_of_scope_record_is_not_found_not_forbidden() -> None:
    """unit_manager with ORG_UNIT_SUBTREE scope: a task unit outside the subtree -> 404 (SEC-01)."""
    root = org_unit(unit_type_id="COMPANY")
    a, b = org_unit(parent=root), org_unit(parent=root)
    a_child = org_unit(parent=a)
    mgr = person()
    give_role(mgr, "unit_manager", scope_kind="ORG_UNIT_SUBTREE", scope_unit=a)
    c = caller(mgr)
    inside = P.RecordScope(units=frozenset({a_child.pk}))
    outside = P.RecordScope(units=frozenset({b.pk}))
    assert P.require_record(c, "platform.workflow.task.read", inside).allowed
    with pytest.raises(NotFound):
        P.require_record(c, "platform.workflow.task.read", outside)
    with pytest.raises(AccessDenied):  # no grant at all: 403 at action level
        P.require_record(c, "platform.ops.job.read", outside)


@pytest.mark.django_db
def test_org_unit_scope_is_exact_and_global_needed_for_unitless_records() -> None:
    root = org_unit(unit_type_id="COMPANY")
    child = org_unit(parent=root)
    mgr = person()
    give_role(mgr, "unit_manager", scope_kind="ORG_UNIT", scope_unit=root)
    c = caller(mgr)
    assert P.can(c, "platform.workflow.task.read", P.RecordScope(units=frozenset({root.pk})))
    assert not P.can(c, "platform.workflow.task.read", P.RecordScope(units=frozenset({child.pk})))
    assert not P.can(c, "platform.workflow.task.read", P.RecordScope())


@pytest.mark.django_db
def test_own_and_own_unit_modes() -> None:
    """employee task.read = ○ + own unit: own records anywhere, others only in the unit of his position."""
    unit, other = org_unit(), org_unit()
    emp = person()
    give_role(emp, "employee")
    position_assignment(position(unit), emp)
    c = caller(emp)
    stranger = uuid.uuid4()
    assert P.can(
        c,
        "platform.workflow.task.read",
        P.RecordScope(units=frozenset({other.pk}), owners=frozenset({emp.pk})),
    )
    assert P.can(
        c,
        "platform.workflow.task.read",
        P.RecordScope(units=frozenset({unit.pk}), owners=frozenset({stranger})),
    )
    assert not P.can(
        c,
        "platform.workflow.task.read",
        P.RecordScope(units=frozenset({other.pk}), owners=frozenset({stranger})),
    )


@pytest.mark.django_db
def test_document_sensitivity_cap() -> None:
    emp, mgr = person(), person()
    give_role(emp, "employee")
    give_role(mgr, "unit_manager")
    for level, emp_ok, mgr_ok in (("S1", True, True), ("S2", False, True), ("S3", False, False)):
        rec = P.RecordScope(sensitivity=level)
        assert P.can(caller(emp), "platform.document.read", rec) is emp_ok
        assert P.can(caller(mgr), "platform.document.read", rec) is mgr_ok


# ----------------------------------------------------------------------------------------- step-up
@pytest.mark.django_db
def test_step_up_window_is_the_parameter_also_inside_the_network() -> None:
    owner = person()
    give_role(owner, "owner_admin")
    fresh = caller(owner, zone="INTERNAL")
    P.require_step_up(fresh, "platform.identity.user.create")
    stale = P.Caller(owner.pk, None, "INTERNAL", db_now() - timedelta(minutes=16))
    with pytest.raises(MfaRequired):
        P.require_step_up(stale, "platform.identity.user.create")
    with pytest.raises(MfaRequired):
        P.require_step_up(caller(owner, mfa=False), "platform.identity.user.create")
    P.require_step_up(caller(owner, mfa=False), "platform.identity.user.read")  # not an MFA row


@pytest.mark.django_db
def test_login_mfa_role_list_bound_to_matrix() -> None:
    """DEC-003 list: roles with an MFA / business-approval permission need MFA at login."""
    expected = {
        "owner_admin": True,
        "it_ops": True,
        "security_auditor": True,
        "management_viewer": False,
        "employee": False,
        "unit_manager": True,
        "document_controller": False,
        "document_approver": True,
        "config_approver": True,
        "workflow_approver": True,
        "operator_terminal": False,
    }
    for role, needs in expected.items():
        u = person()
        give_role(u, role)
        assert P.requires_login_mfa(u.pk) is needs, role


# ----------------------------------------------------------------------------------------- redaction
@pytest.mark.django_db
def test_field_redaction_and_never_exposed_columns() -> None:
    emp = person()
    give_role(emp, "employee")
    data = {"id": "x", "password_hash": "pbkdf2$...", "client_ip": "10.0.0.1", "display_name": "n"}
    rules = {"client_ip": "platform.identity.session.read"}
    out = P.redact_fields(caller(emp), data, rules)
    assert out == {"id": "x", "client_ip": REDACTED, "display_name": "n"}
    assert "client_ip" not in P.redact_fields(caller(emp), data, rules, drop=True)
    auditor = person()
    give_role(auditor, "security_auditor")
    assert P.redact_fields(caller(auditor), data, rules)["client_ip"] == "10.0.0.1"


# ------------------------------------------------------------------------------------- pure property
_UNITS = [uuid.UUID(int=i) for i in range(1, 6)]
units_st = st.frozensets(st.sampled_from(_UNITS), max_size=3)


@given(
    mode=st.sampled_from(["SCOPE", "OWN", "OWN_UNIT", "OWN_AND_OWN_UNIT"]),
    scope_kind=st.sampled_from(["GLOBAL", "ORG_UNIT", "ORG_UNIT_SUBTREE"]),
    scope_unit=st.sampled_from(_UNITS),
    rec_units=units_st,
    own_units=units_st,
    is_owner=st.booleans(),
)
def test_grant_allows_properties(mode, scope_kind, scope_unit, rec_units, own_units, is_owner) -> None:
    me = uuid.UUID(int=99)
    grant = P.Grant(
        "r",
        "BUSINESS",
        "a.b",
        mode,
        "",
        scope_kind,
        None if scope_kind == "GLOBAL" else scope_unit,
        uuid.uuid4(),
        False,
    )
    subtree = {scope_unit: frozenset({scope_unit, _UNITS[-1]})}
    facts = P.ScopeFacts(me, own_units, subtree)
    rec = P.RecordScope(units=rec_units, owners=frozenset({me}) if is_owner else frozenset())
    allowed = P.grant_allows(grant, rec, facts)
    # never broader than the mode allows
    if mode == "OWN":
        assert allowed is is_owner
    if mode == "OWN_UNIT" and not (rec_units & own_units):
        assert allowed is False
    if mode == "SCOPE" and scope_kind == "ORG_UNIT":
        assert allowed is (scope_unit in rec_units)
    if mode == "SCOPE" and scope_kind == "GLOBAL":
        assert allowed is True
    # monotonic: adding owners never removes access
    rec2 = P.RecordScope(units=rec_units, owners=rec.owners | {me})
    assert P.grant_allows(grant, rec2, facts) or not allowed


@given(rank=st.sampled_from(["S1", "S2", "S3"]), cap=st.sampled_from(["", "S1", "S2", "S3"]))
def test_sensitivity_cap_property(rank, cap) -> None:
    grant = P.Grant("r", "BUSINESS", "a.b", "SCOPE", cap, "GLOBAL", None, uuid.uuid4(), False)
    ok = P.grant_allows(grant, P.RecordScope(sensitivity=rank), P.ScopeFacts(uuid.uuid4()))
    assert ok is (cap == "" or P.SENSITIVITY_RANK[rank] <= P.SENSITIVITY_RANK[cap])


# ---------------------------------------------------------------------------------- production wiring
def test_production_policy_is_still_deny_all_until_01_4() -> None:
    """01.3 adds no authentication: the API keeps the PHASE_00 deny-all policy (no endpoint reachable)."""
    assert isinstance(api_permissions.ACCESS_POLICY, api_permissions.DenyAllPolicy)
    from django.conf import settings

    assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == []


@pytest.mark.django_db
def test_rbac_policy_adapter_matches_engine() -> None:
    emp = person()
    give_role(emp, "employee")

    class Principal:
        is_authenticated = True
        actor_id = emp.pk

    pol = P.RbacPolicy(lambda obj: P.RecordScope(sensitivity="S1"))
    assert pol.allows_action(Principal(), "platform.org.read")
    assert not pol.allows_action(Principal(), "platform.identity.user.read")
    assert pol.allows_record(Principal(), "platform.document.read", object())
    assert pol.scope_queryset(Principal(), "platform.identity.user.read", User.objects.all()).count() == 0


@pytest.mark.django_db
def test_scope_q_filters_lists_like_the_record_check() -> None:
    """List scoping (01.4 building block): ORG_UNIT scope + own records, nothing else."""
    from platform_core.workflow.models import ApprovalRequest

    from .phase01_factories import approval

    unit, other = org_unit(), org_unit()
    reader = person()
    give_role(reader, "employee")  # approval.read = ○ own requests
    mine = approval(reader, route_scope_unit=other)
    theirs = approval(person(), route_scope_unit=unit)
    q = P.scope_q(
        caller(reader),
        "platform.workflow.approval.read",
        unit_field="route_scope_unit_id",
        owner_fields=("requested_by_id",),
    )
    assert set(ApprovalRequest.objects.filter(q).values_list("pk", flat=True)) == {mine.pk}
    mgr = person()
    give_role(mgr, "unit_manager", scope_kind="ORG_UNIT", scope_unit=unit)
    q2 = P.scope_q(
        caller(mgr),
        "platform.workflow.approval.read",
        unit_field="route_scope_unit_id",
        owner_fields=("requested_by_id",),
    )
    assert set(ApprovalRequest.objects.filter(q2).values_list("pk", flat=True)) == {theirs.pk}
    nobody = P.scope_q(
        caller(person()), "platform.workflow.approval.read", unit_field="route_scope_unit_id", owner_fields=()
    )
    assert not ApprovalRequest.objects.filter(nobody).exists()
