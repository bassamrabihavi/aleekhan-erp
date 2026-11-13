"""Synthetic people and chains for the PHASE_02 / 02.3 engine tests (labelled synthetic data only, R-38).

* :func:`people` - one synthetic holder per PHASE_02 role (GLOBAL assignment, fresh MFA) plus the owner, the
  management viewer and an employee.
* :func:`chain` - a synthetic ACTIVE type -> category -> product -> style -> ACTIVE revision (factories: types
  and categories come from the import, never from the engine).
* :func:`draft_order` / :func:`confirmed_order` / :func:`released_order` - orders built through the engine.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from django.db import connection

from platform_core.authz.policy import Caller
from platform_core.commercial import changes, orders
from platform_core.commercial.models import CustomerOrder
from platform_core.identity.models import User
from platform_core.product_identity.models import Customer, Style, StyleRevision

from . import phase02_factories as f
from .engine_fixtures import caller, give_role, person

SYN_REP = f"نماینده ساختگی {f.SYN}"  # synthetic representative name (DEC-058: tests use synthetic names only)
ORDER_DATE = date(2030, 1, 10)


@dataclass(frozen=True)
class Who:
    user: User
    caller: Caller

    @property
    def pk(self) -> Any:
        return self.user.pk


def holder(*roles: str, mfa: bool = True) -> Who:
    u = person()
    for r in roles:
        give_role(u, r)
    return Who(u, caller(u, mfa=mfa))


@dataclass(frozen=True)
class People:
    co: Who
    co2: Who
    cm: Who
    cm2: Who
    po: Who
    po2: Who
    pds: Who
    cra: Who
    owner: Who
    viewer: Who
    employee: Who


def people() -> People:
    return People(
        co=holder("commercial_officer"),
        co2=holder("commercial_officer"),
        cm=holder("commercial_manager"),
        cm2=holder("commercial_manager"),
        po=holder("planning_officer"),
        po2=holder("planning_officer"),
        pds=holder("product_data_steward"),
        cra=holder("code_rule_approver"),
        owner=holder("owner_admin"),
        viewer=holder("management_viewer"),
        employee=holder("employee"),
    )


def chain(**over: Any) -> tuple[Style, StyleRevision]:
    _t, _c, _p, s, r = f.styled(**over)
    return s, r


def draft_order(
    who: Who, *, lines: int = 1, customer: Customer | None = None, rep: str | None = SYN_REP, **header: Any
) -> CustomerOrder:
    cust = customer or f.customer()
    o = orders.create_order(
        who.caller,
        customer_id=cust.pk,
        order_type="series_production",
        order_date=ORDER_DATE,
        customer_representative_name=rep,
        **header,
    )
    s, _r = chain()
    for _ in range(lines):
        o.refresh_from_db()
        orders.add_line(who.caller, o.pk, expected_version=o.row_version, style_id=s.pk, quantity=10)
    o.refresh_from_db()
    return o


def validated_order(who: Who, **kw: Any) -> CustomerOrder:
    o = draft_order(who, **kw)
    return orders.validate_order(who.caller, o.pk, expected_version=o.row_version)


def confirmed_order(maker: Who, confirmer: Who, **kw: Any) -> CustomerOrder:
    o = validated_order(maker, **kw)
    return orders.confirm_order(confirmer.caller, o.pk, expected_version=o.row_version)


def released_order(maker: Who, planner: Who, **kw: Any) -> CustomerOrder:
    o = confirmed_order(maker, planner, **kw)
    return orders.release_order(planner.caller, o.pk, expected_version=o.row_version)


def live_lines(o: CustomerOrder) -> list[Any]:
    from platform_core.commercial.models import CustomerOrderLine

    return list(CustomerOrderLine.objects.filter(order=o, status="CONFIRMED").order_by("line_no"))


def applied(
    p: People,
    o: CustomerOrder,
    kind: str,
    items: list[dict[str, Any]] | None = None,
    *,
    requester: Who | None = None,
    reason: str = "synthetic change",
) -> Any:
    """Create + submit + decide + (planning approval) + apply one change request with distinct people."""
    req = requester or p.co
    o.refresh_from_db()
    cr = changes.create_change_request(
        req.caller,
        o.pk,
        kind=kind,
        items=items or [],
        reason=reason,
        expected_version=o.row_version,
        submit=True,
    )
    if kind == "DUE_DATE_CHANGE":
        cr = changes.planning_approve_change_request(p.po2.caller, cr.pk, expected_version=cr.row_version)
    cr = changes.decide_change_request(p.cm.caller, cr.pk, approve=True, expected_version=cr.row_version)
    return changes.apply_change_request(p.po.caller, cr.pk, expected_version=cr.row_version)


@pytest.fixture
def deferred_checks() -> Iterator[None]:
    """Fire the deferred commit-time DB checks of 0020 (gapless counter, serial <-> line pairing, snapshot v1,
    order version row, applied CR has its version) at the end of a test that never commits."""
    yield
    with connection.cursor() as cur:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
