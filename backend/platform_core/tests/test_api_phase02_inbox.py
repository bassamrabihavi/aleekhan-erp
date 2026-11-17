"""02.5: ``GET /me/decision-inbox`` (contract 0.8.3-draft, employer decision 2026-11-15).

The PHASE_02 decisions waiting for the caller appear in the page 39 approval inbox: only kinds the caller may
decide (deciding permission, GLOBAL), never the caller's own request (maker-checker), never a decided item, no
personal data. Synthetic data only (R-38).
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db.models.functions import Now
from django.test import Client

from platform_core.commercial import changes
from platform_core.devtools import phase02_factories as f
from platform_core.devtools.phase02_engine import People, confirmed_order, people, validated_order
from platform_core.product_identity.models import CodeRuleRevision

from . import openapi_contract as oc
from .phase01_api import API, body, code, session_client

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("api_db", "clear_cache")]
PATH = "/me/decision-inbox"


def inbox(c: Client) -> dict[str, Any]:
    r = c.get(f"{API}{PATH}")
    assert r.status_code == 200, r.content[:300]
    oc.validate_response(PATH, "get", r)
    assert r["Cache-Control"] == "no-store"
    out: dict[str, Any] = body(r)
    return out


def kinds(c: Client) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for it in inbox(c)["items"]:
        out.setdefault(it["kind"], set()).add(it["entity_id"])
    return out


@pytest.fixture
def p() -> People:
    return people()


def _due_cr(p: People) -> Any:
    o = confirmed_order(p.co, p.po)
    o.refresh_from_db()
    return changes.create_change_request(
        p.co.caller,
        o.pk,
        kind="DUE_DATE_CHANGE",
        items=[{"line_id": None, "requested_due_date": "2030-03-01"}],
        reason="synthetic due date change",
        expected_version=o.row_version,
        submit=True,
    )


def test_anonymous_is_refused(client: Client) -> None:
    r = client.get(f"{API}{PATH}")
    assert r.status_code == 401 and code(r) == "AUTHENTICATION_REQUIRED"


def test_order_confirm_item_for_planning_and_owner_never_for_the_creator(p: People) -> None:
    o = validated_order(p.co)
    assert str(o.pk) in kinds(session_client(p.po.user)).get("ORDER_CONFIRM", set())
    assert str(o.pk) in kinds(session_client(p.owner.user)).get("ORDER_CONFIRM", set())
    for who in (p.co, p.cm, p.viewer, p.employee, p.pds):  # creator / no confirm permission
        assert "ORDER_CONFIRM" not in kinds(session_client(who.user))
    item = next(i for i in inbox(session_client(p.po.user))["items"] if i["entity_id"] == str(o.pk))
    assert item["entity_type"] == "customer_order" and item["number"] == o.order_no
    assert item["requested_by"] == str(p.co.pk) and item["revision_no"] is None
    assert item["requested_by_name"] == p.co.user.display_name  # DEC-032 amendment 2026-11-17 (REV-0291)


def test_owner_never_sees_his_own_validated_order() -> None:
    from platform_core.devtools.phase02_engine import holder

    owner = holder("owner_admin", "commercial_officer")
    o = validated_order(owner)
    assert str(o.pk) not in kinds(session_client(owner.user)).get("ORDER_CONFIRM", set())


def test_confirmed_order_leaves_the_inbox(p: People) -> None:
    o = confirmed_order(p.co, p.po)
    assert str(o.pk) not in kinds(session_client(p.po2.user)).get("ORDER_CONFIRM", set())


def test_change_decide_and_planning_items_follow_maker_checker(p: People) -> None:
    cr = _due_cr(p)
    cid = str(cr.pk)
    assert cid in kinds(session_client(p.cm.user)).get("CHANGE_DECIDE", set())
    assert cid in kinds(session_client(p.owner.user)).get("CHANGE_DECIDE", set())
    assert cid in kinds(session_client(p.po.user)).get("CHANGE_PLANNING_DECISION", set())
    assert "CHANGE_DECIDE" not in kinds(session_client(p.co.user))  # requester, no decide permission
    assert "CHANGE_PLANNING_DECISION" not in kinds(session_client(p.cm.user))
    for who in (p.viewer, p.employee):
        assert inbox(session_client(who.user))["items"] == []
    # the manager decides: CHANGE_DECIDE disappears, planning still waits but never for that manager
    cr = changes.decide_change_request(p.cm.caller, cr.pk, approve=True, expected_version=cr.row_version)
    assert cid not in kinds(session_client(p.cm2.user)).get("CHANGE_DECIDE", set())
    assert cid in kinds(session_client(p.po.user)).get("CHANGE_PLANNING_DECISION", set())
    # planning approves: nothing left
    changes.planning_decide_change_request(p.po.caller, cr.pk, approve=True, expected_version=cr.row_version)
    assert cid not in kinds(session_client(p.po2.user)).get("CHANGE_PLANNING_DECISION", set())


def test_planning_approver_is_not_offered_the_manager_decision(p: People) -> None:
    from platform_core.devtools.phase02_engine import holder

    both = holder("commercial_manager", "planning_officer")
    cr = _due_cr(p)
    changes.planning_decide_change_request(both.caller, cr.pk, approve=True, expected_version=cr.row_version)
    assert str(cr.pk) not in kinds(session_client(both.user)).get("CHANGE_DECIDE", set())
    assert str(cr.pk) in kinds(session_client(p.cm.user)).get("CHANGE_DECIDE", set())


def test_qty_change_never_asks_planning(p: People) -> None:
    o = confirmed_order(p.co, p.po)
    o.refresh_from_db()
    from platform_core.devtools.phase02_engine import live_lines

    ln = live_lines(o)[0]
    cr = changes.create_change_request(
        p.co.caller,
        o.pk,
        kind="QTY_CHANGE",
        items=[{"line_id": str(ln.pk), "quantity": 12}],
        reason="synthetic qty change",
        expected_version=o.row_version,
        submit=True,
    )
    assert str(cr.pk) in kinds(session_client(p.cm.user)).get("CHANGE_DECIDE", set())
    assert str(cr.pk) not in kinds(session_client(p.po.user)).get("CHANGE_PLANNING_DECISION", set())


def test_code_rule_in_review_for_approver_never_the_maker(p: People) -> None:
    rule = f.code_rule(p.pds.user)
    CodeRuleRevision.objects.filter(pk=rule.pk).update(status="IN_REVIEW", updated_at=Now())
    rid = str(rule.pk)
    assert rid in kinds(session_client(p.cra.user)).get("CODE_RULE_APPROVE", set())
    assert rid in kinds(session_client(p.owner.user)).get("CODE_RULE_APPROVE", set())
    assert "CODE_RULE_APPROVE" not in kinds(session_client(p.pds.user))
    maker_cra = f.code_rule(p.cra.user)
    CodeRuleRevision.objects.filter(pk=maker_cra.pk).update(status="IN_REVIEW")
    assert str(maker_cra.pk) not in kinds(session_client(p.cra.user))["CODE_RULE_APPROVE"]
    item = next(i for i in inbox(session_client(p.cra.user))["items"] if i["entity_id"] == rid)
    assert item["number"] is None and item["revision_no"] == rule.revision_no


def test_no_personal_data_in_the_feed(p: People) -> None:
    validated_order(p.co)
    raw = session_client(p.po.user).get(f"{API}{PATH}").content.decode("utf-8")
    assert "نماینده" not in raw and "مشتری" not in raw


def test_caller_without_the_four_deciding_permissions_gets_an_empty_inbox(p: People) -> None:
    """REV-0255: one item of every kind is waiting; a caller who holds none of order confirm, change decide,
    planning approve and code-rule approve gets ``items == []`` (not only a hidden page)."""
    from platform_core.devtools.phase02_engine import holder

    validated_order(p.co)
    _due_cr(p)
    rule = f.code_rule(p.pds.user)
    CodeRuleRevision.objects.filter(pk=rule.pk).update(status="IN_REVIEW", updated_at=Now())
    assert set(kinds(session_client(p.owner.user))) == {
        "ORDER_CONFIRM",
        "CHANGE_DECIDE",
        "CODE_RULE_APPROVE",
    }  # the owner decides directly (DEC-057); planning approval stays with planning_officer
    assert "CHANGE_PLANNING_DECISION" in kinds(session_client(p.po.user))
    for who in (p.employee, p.viewer, p.co2, holder("product_data_steward")):
        feed = inbox(session_client(who.user))
        assert feed["items"] == [], who.user.pk
