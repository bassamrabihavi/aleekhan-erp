"""PHASE_01 / 01.2 race tests on real PostgreSQL: the database (exclusion constraints, partial unique indexes,
advisory-locked tree triggers) decides, never a read-then-write in application code.

Transactional tests: the seed is flushed between them, so each test re-creates the parameters it needs
(``ensure_parameters``) with the same values as migration 0010.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from platform_core.identity.models import Role, RoleAssignment
from platform_core.org.models import OrgUnit, PositionAssignment
from platform_core.workflow.models import ApprovalRequest

from .phase01_factories import approval, ensure_parameters, org_unit, position, position_assignment, user
from .threads import run_concurrently

pytestmark = pytest.mark.django_db(transaction=True)
N = 6


def _outcomes(results: list[object]) -> tuple[int, list[BaseException]]:
    ok = sum(1 for r in results if not isinstance(r, BaseException))
    errors = [r for r in results if isinstance(r, BaseException)]
    return ok, errors


def test_concurrent_primary_position_assignment_only_one_wins() -> None:
    """DEC-048: N parallel PRIMARY assignments of one person -> one row, the rest exclusion_violation."""
    ensure_parameters()
    unit = org_unit()
    positions = [position(unit) for _ in range(N)]
    person = user()

    def assign(i: int) -> str:
        with transaction.atomic():
            return str(position_assignment(positions[i], person).pk)

    ok, errors = _outcomes(run_concurrently(assign, N))
    assert ok == 1
    assert len(errors) == N - 1
    assert all(
        isinstance(e, IntegrityError) and "ex_position_assignment_one_primary" in str(e) for e in errors
    )
    assert PositionAssignment.objects.filter(user=person, kind="PRIMARY").count() == 1


def test_concurrent_cross_moves_never_build_a_cycle() -> None:
    """Two units moved under each other at the same time: the advisory lock serialises, one move fails."""
    ensure_parameters()
    root = org_unit(unit_type_id="COMPANY")
    a, b = org_unit(parent=root), org_unit(parent=root)

    def move(i: int) -> None:
        child, new_parent = (a, b) if i == 0 else (b, a)
        with transaction.atomic():
            OrgUnit.objects.filter(pk=child.pk).update(parent=new_parent)

    ok, errors = _outcomes(run_concurrently(move, 2))
    assert ok == 1 and len(errors) == 1
    assert "ck_org_unit_acyclic" in str(errors[0])
    a.refresh_from_db()
    b.refresh_from_db()
    assert not (a.parent_id == b.pk and b.parent_id == a.pk)


def test_concurrent_children_never_exceed_max_depth() -> None:
    """Depth is checked under the tree lock: parallel inserts at the deepest level cannot overshoot."""
    ensure_parameters()
    units = [org_unit(unit_type_id="COMPANY")]
    for _ in range(4):
        units.append(org_unit(parent=units[-1]))  # depth 5
    level6 = org_unit(parent=units[-1])

    def add(i: int) -> None:
        with transaction.atomic():
            org_unit(parent=level6 if i % 2 else units[-1])

    ok, errors = _outcomes(run_concurrently(add, N))
    # children of level 5 (depth 6) are fine, children of level 6 (depth 7) are refused
    assert ok == N // 2
    assert all("ck_org_unit_max_depth" in str(e) for e in errors)


def test_concurrent_pending_approval_requests_only_one() -> None:
    ensure_parameters()
    maker = user()
    template = approval(maker)
    ApprovalRequest.objects.filter(pk=template.pk).update(status="WITHDRAWN", closed_at=template.requested_at)

    def raise_request(i: int) -> None:
        with transaction.atomic():
            approval(maker, resource_id=template.resource_id)

    ok, errors = _outcomes(run_concurrently(raise_request, N))
    assert ok == 1
    assert all("uq_approval_request_one_pending" in str(e) for e in errors)


def test_concurrent_duplicate_role_grants_only_one() -> None:
    ensure_parameters()
    owner, target = user(), user()
    role = Role.objects.create(code="syn_role_race", name_fa="نقش ساختگی", kind="BUSINESS", status="DRAFT")
    Role.objects.filter(pk=role.pk).update(status="ACTIVE", matrix_version="1.0")

    def grant(i: int) -> None:
        with transaction.atomic():
            RoleAssignment.objects.create(
                user=target,
                role=role,
                scope_kind="GLOBAL",
                status="ACTIVE",
                granted_by=owner,
                reason="race test",
            )

    ok, errors = _outcomes(run_concurrently(grant, N))
    assert ok == 1
    assert all("ex_role_assignment_no_overlap" in str(e) for e in errors)
