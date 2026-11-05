"""PHASE_01 / 01.2: organisation tree guards (DEC-043, DEC-048 APPROVED). Synthetic, labelled data only."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from platform_core.org.models import OrgUnit, OrgUnitHistory, Position, PositionAssignment, PositionHistory
from platform_core.params.models import ParameterValue

from .phase01_factories import chain, db_refuses, org_unit, position, position_assignment, user

pytestmark = pytest.mark.django_db


def test_seeded_unit_types_and_max_depth_parameter() -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT code FROM platform_org_unit_type ORDER BY sort_order")
        assert [r[0] for r in cur.fetchall()] == ["COMPANY", "DEPARTMENT", "SECTION", "LINE"]
        cur.execute("SELECT platform_param_int('org_tree_max_depth')")
        assert cur.fetchone()[0] == 6
    assert ParameterValue.objects.get(definition_id="org_tree_max_depth").decision_id == "DEC-048"


def test_depth_six_allowed_seven_refused() -> None:
    units = chain(6)
    with db_refuses("ck_org_unit_max_depth"):
        org_unit(parent=units[-1])


def test_moving_a_subtree_respects_max_depth() -> None:
    deep = chain(4)
    other = chain(3)  # root + 2 levels below -> height 3
    # moving `other` root under the 4th level would make depth 4 + 3 = 7
    with db_refuses("ck_org_unit_max_depth"):
        OrgUnit.objects.filter(pk=other[0].pk).update(parent=deep[3])
    OrgUnit.objects.filter(pk=other[0].pk).update(parent=deep[2])  # 3 + 3 = 6 fits


def test_no_cycles_in_the_tree() -> None:
    a, _b, c = chain(3)
    with db_refuses("ck_org_unit_acyclic"):  # trigger first; CHECK ck_org_unit_not_own_parent is the backstop
        OrgUnit.objects.filter(pk=a.pk).update(parent=a)
    with db_refuses("ck_org_unit_acyclic"):
        OrgUnit.objects.filter(pk=a.pk).update(parent=c)


def test_active_unit_needs_active_parent_and_deactivation_needs_empty_unit() -> None:
    root, child = chain(2)
    with db_refuses("ck_org_unit_deactivate_empty"):
        OrgUnit.objects.filter(pk=root.pk).update(status="INACTIVE")
    pos = position(child)
    with db_refuses("ck_org_unit_deactivate_empty"):
        OrgUnit.objects.filter(pk=child.pk).update(status="INACTIVE")
    Position.objects.filter(pk=pos.pk).update(status="INACTIVE")
    OrgUnit.objects.filter(pk=child.pk).update(status="INACTIVE")
    with db_refuses("ck_org_unit_parent_active"):
        org_unit(parent=child)


def test_unit_type_must_exist_and_be_active() -> None:
    with db_refuses("platform_org_unit"):  # FK violation (unknown type)
        org_unit(unit_type_id="TEAM")
    with connection.cursor() as cur:
        cur.execute("UPDATE platform_org_unit_type SET is_active = false WHERE code = 'LINE'")
    with db_refuses("ck_org_unit_type_active"):
        org_unit(unit_type_id="LINE")


def test_history_written_by_trigger_effective_dated_and_append_only() -> None:
    """DEC-048 item 7: history with effective dates; never rewritten."""
    root_a, root_b = org_unit(unit_type_id="COMPANY"), org_unit(unit_type_id="COMPANY")
    unit = org_unit(parent=root_a)
    OrgUnit.objects.filter(pk=unit.pk).update(parent=root_b)
    rows = list(OrgUnitHistory.objects.filter(unit=unit).order_by("unit_row_version"))
    assert [r.parent_id for r in rows] == [root_a.pk, root_b.pk]
    assert rows[0].valid_to == rows[1].valid_from and rows[1].valid_to is None
    with db_refuses("append_only"):
        OrgUnitHistory.objects.filter(pk=rows[0].pk).update(parent=root_b)
    with db_refuses("append_only"):
        OrgUnitHistory.objects.filter(pk=rows[0].pk).delete()
    # updating only the audit columns writes no history row
    OrgUnit.objects.filter(pk=unit.pk).update(updated_by=user())
    assert OrgUnitHistory.objects.filter(unit=unit).count() == 2


def test_effective_from_never_back_dated_or_future_and_code_immutable() -> None:
    unit = org_unit()
    with db_refuses("ck_effective_from_not_backdated"):
        OrgUnit.objects.filter(pk=unit.pk).update(
            name_fa=unit.name_fa + " ۲", effective_from=timezone.now() - timedelta(days=1)
        )
    # REV-0107 repro: a change dated after the previous change but before now is refused as well
    with db_refuses("ck_effective_from_not_backdated"):
        org_unit(effective_from=timezone.now() - timedelta(days=7))
    with db_refuses("ck_effective_from_not_backdated"):
        position(unit, effective_from=timezone.now() - timedelta(hours=1))
    # the documented 60 s clock tolerance accepts a slightly older application timestamp (new unit)
    org_unit(effective_from=timezone.now() - timedelta(seconds=5))
    with db_refuses("ck_effective_from_not_future"):
        OrgUnit.objects.filter(pk=unit.pk).update(effective_from=timezone.now() + timedelta(days=1))
    with db_refuses("immutable_column"):
        OrgUnit.objects.filter(pk=unit.pk).update(code="syn_other")


def test_names_only_no_contact_columns_in_the_tree() -> None:
    """DEC-048 item 6: names visible, no contact data."""
    forbidden = {"email", "phone", "mobile", "address", "national_id"}
    for model in (OrgUnit, Position, PositionAssignment, OrgUnitHistory, PositionHistory):
        assert not {f.name for f in model._meta.get_fields()} & forbidden


def test_one_active_head_per_unit() -> None:
    unit = org_unit()
    position(unit, is_unit_head=True)
    with db_refuses("uq_position_one_active_head"):
        position(unit, is_unit_head=True)


def test_reports_to_between_positions_is_acyclic() -> None:
    unit = org_unit()
    p1 = position(unit)
    p2 = position(unit, reports_to=p1)
    p3 = position(unit, reports_to=p2)
    with db_refuses("ck_position_reports_to_acyclic"):  # CHECK ck_position_not_own_manager is the backstop
        Position.objects.filter(pk=p1.pk).update(reports_to=p1)
    with db_refuses("ck_position_reports_to_acyclic"):
        Position.objects.filter(pk=p1.pk).update(reports_to=p3)
    assert PositionHistory.objects.filter(position=p3).count() == 1


def test_position_needs_active_unit_and_deactivation_needs_no_holder() -> None:
    unit = org_unit()
    pos = position(unit)
    holder = user()
    position_assignment(pos, holder)
    with db_refuses("ck_position_deactivate_empty"):
        Position.objects.filter(pk=pos.pk).update(status="INACTIVE")


def test_one_primary_position_per_person_at_any_instant() -> None:
    """DEC-048 item 2: one primary position + ACTING (with end date); no ADDITIONAL kind."""
    unit = org_unit()
    p1, p2, p3 = position(unit), position(unit), position(unit)
    person = user()
    first = position_assignment(p1, person)
    with db_refuses("ex_position_assignment_one_primary"):
        position_assignment(p2, person)
    with db_refuses("ck_position_assignment_acting_has_end"):
        position_assignment(p2, person, kind="ACTING")
    position_assignment(p2, person, kind="ACTING", valid_to=timezone.now() + timedelta(days=14))
    with db_refuses("ck_position_assignment_kind"):
        position_assignment(p3, person, kind="EXTRA")  # no ADDITIONAL/extra kind in PHASE_01
    # ending the first primary assignment allows a new primary one afterwards
    end = timezone.now() + timedelta(days=1)
    PositionAssignment.objects.filter(pk=first.pk).update(valid_to=end)
    position_assignment(p3, person, valid_from=end)
    with db_refuses("immutable_column"):
        PositionAssignment.objects.filter(pk=first.pk).update(position=p3)


def test_holding_a_position_grants_no_permission() -> None:
    """DEC-049: permissions come only from role assignments - no FK from positions to roles/permissions."""
    for model in (Position, PositionAssignment):
        related = {
            f.related_model.__name__ for f in model._meta.get_fields() if f.is_relation and f.related_model
        }
        assert not related & {"Role", "Permission", "RolePermission", "RoleAssignment"}


def test_position_primary_capacity() -> None:
    """Q-0106 (employer answer 2026-11-05): PRIMARY holders up to the position capacity; heads stay 1."""
    unit = org_unit()
    with db_refuses("ck_position_head_capacity_one"):
        position(unit, is_unit_head=True, primary_capacity=2)
    with db_refuses("ck_position_capacity_pos"):
        position(unit, primary_capacity=0)
    single = position(unit)
    position_assignment(single, user())
    with db_refuses("ck_position_primary_capacity"):
        position_assignment(single, user())
    shared = position(unit, primary_capacity=2)
    a, b = user(), user()
    first = position_assignment(shared, a)
    position_assignment(shared, b)
    with db_refuses("ck_position_primary_capacity"):
        position_assignment(shared, user())
    # ACTING does not count against the PRIMARY capacity
    position_assignment(shared, user(), kind="ACTING", valid_to=timezone.now() + timedelta(days=3))
    # a later period after one holder leaves is free again
    end = timezone.now() + timedelta(days=10)
    PositionAssignment.objects.filter(pk=first.pk).update(valid_to=end)
    position_assignment(shared, user(), valid_from=end)
    with db_refuses("ck_position_primary_capacity"):
        Position.objects.filter(pk=shared.pk).update(primary_capacity=1)
    assert (
        PositionHistory.objects.filter(position=shared).latest("position_row_version").primary_capacity == 2
    )
