"""Org services (DEC-048) and REV-0109: person-to-position assignments are never back-dated (0011)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from platform_core.engine.context import db_now
from platform_core.engine.errors import AccessDenied, MfaRequired, StateTransitionNotAllowed, ValidationFailed
from platform_core.models import AuditEvent
from platform_core.org import service as org
from platform_core.org.models import OrgUnitHistory, PositionAssignment

from .engine_fixtures import caller, person, with_role
from .phase01_factories import SYN, db_refuses, org_unit, position, position_assignment, user

pytestmark = pytest.mark.django_db


# ----------------------------------------------------------------------------------------- REV-0109
def test_back_dated_assignment_insert_is_refused() -> None:
    pos, who = position(org_unit()), user()
    with db_refuses("ck_position_assignment_not_backdated"):
        position_assignment(pos, who, valid_from=db_now() - timedelta(days=30))


def test_assignment_within_clock_tolerance_and_future_start_are_accepted() -> None:
    pos = position(org_unit(), primary_capacity=2)
    position_assignment(pos, user(), valid_from=db_now() - timedelta(seconds=30))
    position_assignment(pos, user(), valid_from=db_now() + timedelta(days=1))


def test_retroactive_end_is_refused_and_end_now_is_accepted() -> None:
    pa = position_assignment(position(org_unit()), user())
    with db_refuses("ck_position_assignment_not_backdated"):
        PositionAssignment.objects.filter(pk=pa.pk).update(valid_to=db_now() - timedelta(days=10))
    PositionAssignment.objects.filter(pk=pa.pk).update(valid_to=db_now() + timedelta(seconds=1))


def test_an_ended_assignment_is_never_changed_again() -> None:
    """An assignment that ended in the past is closed history: no retroactive re-opening or re-ending."""
    from django.db import connection

    pa = position_assignment(position(org_unit()), user())
    with connection.cursor() as cur:  # TEST-ONLY: build an old, ended row as the throw-away DB owner
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute("ALTER TABLE platform_position_assignment DISABLE TRIGGER USER")
        try:
            cur.execute(
                "UPDATE platform_position_assignment SET valid_from = now() - interval '2 days', "
                "valid_to = now() - interval '1 day' WHERE id = %s",
                [str(pa.pk)],
            )
        finally:
            cur.execute("ALTER TABLE platform_position_assignment ENABLE TRIGGER USER")
    with db_refuses("ck_position_assignment_not_backdated"):
        PositionAssignment.objects.filter(pk=pa.pk).update(valid_to=db_now() + timedelta(days=1))
    with db_refuses("ck_position_assignment_not_backdated"):
        PositionAssignment.objects.filter(pk=pa.pk).update(valid_to=None)


# -------------------------------------------------------------------------------------------- services
def test_org_services_require_manage_permission_and_step_up() -> None:
    _u, emp = with_role("employee")
    with pytest.raises(AccessDenied):
        org.create_unit(
            emp, code="syn_u_denied", name_fa=f"و {SYN}", unit_type="COMPANY", parent_id=None, reason="test"
        )
    owner = person()
    from .engine_fixtures import give_role

    give_role(owner, "owner_admin")
    with pytest.raises(MfaRequired):
        org.create_unit(
            caller(owner, mfa=False),
            code="syn_u_nomfa",
            name_fa=f"و {SYN}",
            unit_type="COMPANY",
            parent_id=None,
            reason="test",
        )


def test_create_move_deactivate_with_history_and_audit() -> None:
    _o, owner = with_role("owner_admin")
    root = org.create_unit(
        owner,
        code="syn_root_1",
        name_fa=f"ریشه {SYN}",
        unit_type="COMPANY",
        parent_id=None,
        reason="setup",
        provenance="SEED_SYNTHETIC",
    )
    a = org.create_unit(
        owner,
        code="syn_a_1",
        name_fa=f"الف {SYN}",
        unit_type="DEPARTMENT",
        parent_id=root.pk,
        reason="setup",
        provenance="SEED_SYNTHETIC",
    )
    b = org.create_unit(
        owner,
        code="syn_b_1",
        name_fa=f"ب {SYN}",
        unit_type="DEPARTMENT",
        parent_id=root.pk,
        reason="setup",
        provenance="SEED_SYNTHETIC",
    )
    moved = org.move_unit(
        owner, b.pk, new_parent_id=a.pk, expected_version=b.row_version, reason="reorganise"
    )
    assert moved.parent_id == a.pk
    assert OrgUnitHistory.objects.filter(unit=b).count() == 2
    with pytest.raises(StateTransitionNotAllowed) as exc:  # cycle refused by the tree guard
        org.move_unit(owner, a.pk, new_parent_id=b.pk, expected_version=a.row_version, reason="cycle")
    assert exc.value.errors[0].code == "CK_ORG_UNIT_ACYCLIC"
    org.deactivate_unit(owner, moved.pk, expected_version=moved.row_version, reason="closed")
    assert AuditEvent.objects.filter(action="platform.org.unit.move", resource_id=str(b.pk)).exists()


def test_stale_version_is_a_conflict() -> None:
    from platform_core.engine.errors import VersionConflict

    _o, owner = with_role("owner_admin")
    unit = org_unit()
    with pytest.raises(VersionConflict):
        org.move_unit(
            owner, unit.pk, new_parent_id=None, expected_version=unit.row_version + 1, reason="stale"
        )


def test_assignments_primary_acting_capacity_and_head() -> None:
    _o, owner = with_role("owner_admin")
    unit = org_unit()
    head = org.create_position(
        owner,
        unit_id=unit.pk,
        code="syn_head_1",
        title_fa=f"مدیر {SYN}",
        is_unit_head=True,
        reason="setup",
        provenance="SEED_SYNTHETIC",
    )
    with pytest.raises(ValidationFailed):
        org.create_position(
            owner,
            unit_id=unit.pk,
            code="syn_head_2",
            title_fa=f"مدیر {SYN}",
            is_unit_head=True,
            primary_capacity=2,
            reason="setup",
        )
    with pytest.raises(StateTransitionNotAllowed):  # one ACTIVE head per unit
        org.create_position(
            owner,
            unit_id=unit.pk,
            code="syn_head_3",
            title_fa=f"مدیر {SYN}",
            is_unit_head=True,
            reason="setup",
            provenance="SEED_SYNTHETIC",
        )
    a, b = user(), user()
    org.assign_position(owner, position_id=head.pk, user_id=a.pk, kind="PRIMARY", reason="appoint")
    with pytest.raises(StateTransitionNotAllowed) as exc:  # unit head capacity 1
        org.assign_position(owner, position_id=head.pk, user_id=b.pk, kind="PRIMARY", reason="appoint")
    assert exc.value.errors[0].code == "CK_POSITION_PRIMARY_CAPACITY"
    with pytest.raises(ValidationFailed):  # ACTING needs an end
        org.assign_position(owner, position_id=head.pk, user_id=b.pk, kind="ACTING", reason="stand-in")
    acting = org.assign_position(
        owner,
        position_id=head.pk,
        user_id=b.pk,
        kind="ACTING",
        reason="stand-in",
        valid_to=db_now() + timedelta(days=7),
    )
    with pytest.raises(StateTransitionNotAllowed):  # back-dated start refused (REV-0109)
        org.assign_position(
            owner,
            position_id=head.pk,
            user_id=user().pk,
            kind="ACTING",
            reason="late",
            valid_from=db_now() - timedelta(days=3),
            valid_to=db_now() + timedelta(days=3),
        )
    ended = org.end_position_assignment(owner, acting.pk, expected_version=acting.row_version, reason="back")
    assert ended.valid_to is not None
    with pytest.raises(StateTransitionNotAllowed):
        org.end_position_assignment(
            owner,
            ended.pk,
            expected_version=ended.row_version,
            reason="retro",
            valid_to=db_now() - timedelta(days=1),
        )
