"""PHASE_02 / 02.3 change requests (DEC-059 + amendment 2026-11-12) against PostgreSQL.

Every kind, every allowed and refused CR transition, the after-release restrictions, the single ON_HOLD with
its stored previous state, cancel from hold (migration 0023), the due-date planning approval by a third person
(engine + DB CHECK 0023), quantity changes keep the serial, stale bases, permissions per role. Synthetic data.
"""

from __future__ import annotations

import uuid
from datetime import date
from itertools import product
from typing import Any

import pytest
from django.db.models.functions import Now

from platform_core.commercial import changes, orders
from platform_core.commercial.models import (
    ChangeStatus,
    CustomerOrder,
    CustomerOrderLine,
    CustomerOrderVersion,
    OrderChangeRequest,
)
from platform_core.engine.errors import (
    AccessDenied,
    AleekhanError,
    MfaRequired,
    NotFound,
    SelfApprovalForbidden,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.models import OutboxEvent
from platform_core.product_identity.models import Serial, SerialCounter, SerialSnapshot

from . import phase02_engine as e
from .phase01_factories import db_refuses
from .phase02_engine import deferred_checks  # noqa: F401 - fixture

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("deferred_checks")]


def _reason(exc: AleekhanError) -> str:
    return exc.errors[0].code


@pytest.fixture
def p() -> e.People:
    return e.people()


def _cr(who: e.Who, o: CustomerOrder, kind: str, items: list[Any] | None = None, **kw: Any) -> Any:
    o.refresh_from_db()
    return changes.create_change_request(
        who.caller,
        o.pk,
        kind=kind,
        items=items or [],
        reason="synthetic change",
        expected_version=o.row_version,
        **kw,
    )


def _approved(p: e.People, o: CustomerOrder, kind: str, items: list[Any] | None = None) -> Any:
    cr = _cr(p.co, o, kind, items, submit=True)
    return changes.decide_change_request(p.cm.caller, cr.pk, approve=True, expected_version=cr.row_version)


# ------------------------------------------------------------------------------------------------ kinds
def test_quantity_change_keeps_the_serial_and_writes_version_2_and_snapshot_2(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po, lines=2)
    ln = e.live_lines(o)[0]
    counter = SerialCounter.objects.get().next_value
    cr = e.applied(p, o, "QTY_CHANGE", [{"line_id": str(ln.pk), "quantity": 25}])
    assert (cr.status, cr.applied_version, cr.applied_by_id) == ("APPLIED", 2, p.po.pk)
    o.refresh_from_db()
    after = CustomerOrderLine.objects.get(pk=ln.pk)
    assert (o.current_version, after.quantity, after.serial_id, after.order_version) == (
        2,
        25,
        ln.serial_id,
        2,
    )
    assert SerialCounter.objects.get().next_value == counter  # DEC-059: no new serial for a quantity change
    snap = SerialSnapshot.objects.get(serial_id=ln.serial_id, version=2)
    assert (snap.reason, snap.order_version, snap.change_request_id) == ("CHANGE_APPLIED", 2, cr.pk)
    assert snap.snapshot["quantity"] == 25
    other = e.live_lines(o)[1]
    assert not SerialSnapshot.objects.filter(serial_id=other.serial_id, version=2).exists()  # untouched line
    v2 = CustomerOrderVersion.objects.get(order=o, version=2)
    assert (v2.reason, v2.change_request_id) == ("CHANGE_APPLIED", cr.pk)
    assert (
        CustomerOrderVersion.objects.get(order=o, version=1).image["lines"][0]["quantity"] == 10
    )  # v1 intact
    changed = OutboxEvent.objects.get(event_type="commercial.order.changed", aggregate_id=str(o.pk))
    assert changed.payload == {
        "id": str(o.pk),
        "status": "CONFIRMED",
        "version": 2,
        "change_request_id": str(cr.pk),
        "kind": "QTY_CHANGE",
    }


def test_due_date_change_needs_planning_approval_by_a_third_person(p: e.People) -> None:
    o = e.released_order(p.co, p.po)  # allowed after release
    ln = e.live_lines(o)[0]
    items = [
        {"line_id": None, "requested_due_date": "2030-03-01"},
        {"line_id": str(ln.pk), "requested_due_date": "2030-03-05"},
    ]
    cr = _cr(p.co, o, "DUE_DATE_CHANGE", items, submit=True)
    cr = changes.decide_change_request(p.cm.caller, cr.pk, approve=True, expected_version=cr.row_version)
    with pytest.raises(StateTransitionNotAllowed) as exc:
        changes.apply_change_request(p.po.caller, cr.pk, expected_version=cr.row_version)
    assert _reason(exc.value) == "PLANNING_APPROVAL_REQUIRED"
    # the requester may not give it (a planner who requested is still the requester)
    planner_requester = e.holder("planning_officer")
    cr2 = _cr(planner_requester, o, "DUE_DATE_CHANGE", items, submit=True)
    with pytest.raises(SelfApprovalForbidden) as exc2:
        changes.planning_approve_change_request(
            planner_requester.caller, cr2.pk, expected_version=cr2.row_version
        )
    assert _reason(exc2.value) == "PLANNING_APPROVER_IS_REQUESTER"
    # the deciding manager may not give it (a person holding both roles)
    mgr_planner = e.holder("commercial_manager", "planning_officer")
    cr3 = _cr(p.co, o, "DUE_DATE_CHANGE", items, submit=True)
    cr3 = changes.decide_change_request(
        mgr_planner.caller, cr3.pk, approve=True, expected_version=cr3.row_version
    )
    with pytest.raises(SelfApprovalForbidden) as exc3:
        changes.planning_approve_change_request(mgr_planner.caller, cr3.pk, expected_version=cr3.row_version)
    assert _reason(exc3.value) == "PLANNING_APPROVER_IS_DECIDER"
    # ... nor decide after having given it
    cr4 = _cr(p.co, o, "DUE_DATE_CHANGE", items, submit=True)
    cr4 = changes.planning_approve_change_request(
        mgr_planner.caller, cr4.pk, expected_version=cr4.row_version
    )
    with pytest.raises(SelfApprovalForbidden) as exc4:
        changes.decide_change_request(
            mgr_planner.caller, cr4.pk, approve=True, expected_version=cr4.row_version
        )
    assert _reason(exc4.value) == "DECIDER_IS_PLANNING_APPROVER"
    # planning approval of a non-due-date change does not exist
    cr5 = _cr(p.co, o, "HOLD", submit=True)
    with pytest.raises(StateTransitionNotAllowed) as exc5:
        changes.planning_approve_change_request(p.po.caller, cr5.pk, expected_version=cr5.row_version)
    assert _reason(exc5.value) == "PLANNING_APPROVAL_NOT_APPLICABLE"
    # a third planner approves, the first request is applied: header + line due dates, version 2
    cr = changes.planning_approve_change_request(p.po2.caller, cr.pk, expected_version=cr.row_version)
    with pytest.raises(StateTransitionNotAllowed) as exc6:
        changes.planning_approve_change_request(p.po.caller, cr.pk, expected_version=cr.row_version)
    assert _reason(exc6.value) == "PLANNING_ALREADY_APPROVED"
    cr = changes.apply_change_request(p.po.caller, cr.pk, expected_version=cr.row_version)
    o.refresh_from_db()
    assert (o.status, o.current_version, o.requested_due_date) == ("RELEASED_TO_PLAN", 2, date(2030, 3, 1))
    assert CustomerOrderLine.objects.get(pk=ln.pk).requested_due_date == date(2030, 3, 5)
    assert SerialSnapshot.objects.filter(serial_id=ln.serial_id, version=2).count() == 1
    # the other open requests are now stale (the order moved on)
    cr4 = changes.decide_change_request(p.cm.caller, cr4.pk, approve=True, expected_version=cr4.row_version)
    with pytest.raises(StateTransitionNotAllowed) as exc7:
        changes.apply_change_request(p.po.caller, cr4.pk, expected_version=cr4.row_version)
    assert _reason(exc7.value) == "STALE_BASE_VERSION"


def test_db_refuses_a_planning_approver_who_is_the_requester_or_the_decider(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    cr = _cr(p.co, o, "DUE_DATE_CHANGE", [{"line_id": None, "requested_due_date": "2030-02-01"}], submit=True)
    with db_refuses("ck_commercial_cr_planner_not_requester"):
        OrderChangeRequest.objects.filter(pk=cr.pk).update(
            planning_approved_by_id=p.co.pk, planning_approved_at=Now()
        )
    OrderChangeRequest.objects.filter(pk=cr.pk).update(
        status="APPROVED", decided_by_id=p.cm.pk, decided_at=Now()
    )
    with db_refuses("ck_commercial_cr_planner_not_decider"):
        OrderChangeRequest.objects.filter(pk=cr.pk).update(
            planning_approved_by_id=p.cm.pk, planning_approved_at=Now()
        )


def test_add_line_gets_a_new_serial_and_the_next_line_number(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po, lines=1)
    s, _r = e.chain(uom="PAIR")
    first = SerialCounter.objects.get().next_value
    cr = e.applied(p, o, "ADD_LINE", [{"style_id": str(s.pk), "quantity": 6}])
    new = CustomerOrderLine.objects.get(order=o, line_no=2)
    assert (new.status, new.order_version, new.uom_id, new.quantity) == ("CONFIRMED", 2, "PAIR", 6)
    assert new.serial_id is not None
    serial = Serial.objects.get(pk=new.serial_id)
    assert serial.serial_number == str(first) and serial.allocated_by_id == p.po.pk
    assert SerialSnapshot.objects.get(serial=serial).version == 1
    assert cr.applied_version == 2


def test_cancel_line_cancels_its_serial_and_the_number_is_never_reused(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po, lines=2)
    a, b = e.live_lines(o)
    counter = SerialCounter.objects.get().next_value
    with pytest.raises(StateTransitionNotAllowed) as exc:  # every live line: use CANCEL_ORDER (open item)
        _cr(p.co, o, "CANCEL_LINE", [{"line_id": str(a.pk)}, {"line_id": str(b.pk)}])
    assert _reason(exc.value) == "LAST_LINE_CANCEL"
    e.applied(p, o, "CANCEL_LINE", [{"line_id": str(a.pk)}])
    a.refresh_from_db()
    serial = Serial.objects.get(pk=a.serial_id)
    assert (a.status, serial.status, a.order_version) == ("CANCELLED", "CANCELLED", 2)
    assert SerialCounter.objects.get().next_value == counter  # never moves back: the number is not re-used
    assert (
        OutboxEvent.objects.filter(
            event_type="identity.serial.cancelled", aggregate_id=str(serial.pk)
        ).count()
        == 1
    )
    with pytest.raises(StateTransitionNotAllowed) as exc2:  # a cancelled line is not a live line any more
        _cr(p.co, o, "QTY_CHANGE", [{"line_id": str(a.pk), "quantity": 3}])
    assert _reason(exc2.value) == "LINE_NOT_IN_ORDER"


def test_cancel_order_before_release(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po, lines=2)
    e.applied(p, o, "CANCEL_ORDER")
    o.refresh_from_db()
    assert (o.status, o.current_version, o.cancel_reason) == ("CANCELLED", 2, "synthetic change")
    assert set(CustomerOrderLine.objects.filter(order=o).values_list("status", flat=True)) == {"CANCELLED"}
    assert set(
        Serial.objects.filter(
            pk__in=[ln.serial_id for ln in CustomerOrderLine.objects.filter(order=o)]
        ).values_list("status", flat=True)
    ) == {"CANCELLED"}
    assert CustomerOrderVersion.objects.get(order=o, version=2).reason == "CANCELLED"
    assert (
        OutboxEvent.objects.filter(event_type="commercial.order.cancelled", aggregate_id=str(o.pk)).count()
        == 1
    )
    with pytest.raises(StateTransitionNotAllowed):
        _cr(p.co, o, "HOLD")


def test_hold_resume_to_the_stored_state_and_cancel_from_hold_before_release(p: e.People) -> None:
    released = e.released_order(p.co, p.po)
    e.applied(p, released, "HOLD")
    released.refresh_from_db()
    assert (released.status, released.status_before_hold, released.current_version) == (
        "ON_HOLD",
        "RELEASED_TO_PLAN",
        2,
    )
    for kind, reason in (("HOLD", "ORDER_ALREADY_ON_HOLD"), ("CANCEL_ORDER", "CANCEL_AFTER_RELEASE")):
        with pytest.raises(StateTransitionNotAllowed) as exc:
            _cr(p.co, released, kind)
        assert _reason(exc.value) == reason
    e.applied(p, released, "RESUME")
    released.refresh_from_db()
    assert (released.status, released.status_before_hold, released.hold_reason, released.current_version) == (
        "RELEASED_TO_PLAN",
        None,
        None,
        3,
    )
    confirmed = e.confirmed_order(p.co, p.po, lines=2)
    e.applied(p, confirmed, "HOLD")
    confirmed.refresh_from_db()
    assert (confirmed.status, confirmed.status_before_hold) == ("ON_HOLD", "CONFIRMED")
    with pytest.raises(StateTransitionNotAllowed) as exc2:  # not decided for a held order
        _cr(p.co, confirmed, "QTY_CHANGE", [{"line_id": str(e.live_lines(confirmed)[0].pk), "quantity": 2}])
    assert _reason(exc2.value) == "ORDER_ON_HOLD"
    a = e.live_lines(confirmed)[0]
    e.applied(p, confirmed, "CANCEL_LINE", [{"line_id": str(a.pk)}])  # amendment: cancel from hold
    confirmed.refresh_from_db()
    assert (confirmed.status, confirmed.current_version) == ("ON_HOLD", 3)
    e.applied(p, confirmed, "CANCEL_ORDER")  # amendment 2026-11-12 + DB guard 0023
    confirmed.refresh_from_db()
    assert (confirmed.status, confirmed.status_before_hold, confirmed.hold_reason) == (
        "CANCELLED",
        None,
        None,
    )
    assert set(
        Serial.objects.filter(
            pk__in=[ln.serial_id for ln in CustomerOrderLine.objects.filter(order=confirmed)]
        ).values_list("status", flat=True)
    ) == {"CANCELLED"}


def test_db_guard_0023_cancel_from_hold_only_when_the_stored_state_is_confirmed(p: e.People) -> None:
    held_released = e.released_order(p.co, p.po)
    e.applied(p, held_released, "HOLD")
    with db_refuses("ck_commercial_order_transition"):
        CustomerOrder.objects.filter(pk=held_released.pk).update(
            status="CANCELLED",
            status_before_hold=None,
            hold_reason=None,
            cancel_reason="synthetic",
            cancelled_at=Now(),
            current_version=3,
        )


def test_after_release_only_due_date_and_hold_resume(p: e.People) -> None:
    o = e.released_order(p.co, p.po)
    ln = e.live_lines(o)[0]
    s, _r = e.chain()
    cases: list[tuple[str, list[Any], str]] = [
        ("QTY_CHANGE", [{"line_id": str(ln.pk), "quantity": 99}], "RELEASED_KIND_NOT_ALLOWED"),
        ("ADD_LINE", [{"style_id": str(s.pk), "quantity": 1}], "RELEASED_KIND_NOT_ALLOWED"),
        ("CANCEL_LINE", [{"line_id": str(ln.pk)}], "CANCEL_AFTER_RELEASE"),
        ("CANCEL_ORDER", [], "CANCEL_AFTER_RELEASE"),
        ("RESUME", [], "ORDER_NOT_ON_HOLD"),
    ]
    for kind, items, reason in cases:
        with pytest.raises(StateTransitionNotAllowed) as exc:
            _cr(p.co, o, kind, items)
        assert _reason(exc.value) == reason, kind


def test_apply_rechecks_the_order_state_released_since_the_request(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    ln = e.live_lines(o)[0]
    cr = _approved(p, o, "QTY_CHANGE", [{"line_id": str(ln.pk), "quantity": 33}])
    o.refresh_from_db()
    orders.release_order(p.po.caller, o.pk, expected_version=o.row_version)  # no version bump
    with pytest.raises(StateTransitionNotAllowed) as exc:
        changes.apply_change_request(p.po.caller, cr.pk, expected_version=cr.row_version)
    assert _reason(exc.value) == "RELEASED_KIND_NOT_ALLOWED"
    assert CustomerOrderLine.objects.get(pk=ln.pk).quantity == 10


def test_item_validation(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    ln = e.live_lines(o)[0]
    bad: list[tuple[str, list[Any], str]] = [
        ("QTY_CHANGE", [], "REQUIRED"),
        ("QTY_CHANGE", [{"line_id": str(ln.pk), "quantity": 10}], "QUANTITY_UNCHANGED"),
        ("QTY_CHANGE", [{"line_id": str(ln.pk), "quantity": 0}], "QUANTITY_NOT_POSITIVE"),
        ("QTY_CHANGE", [{"line_id": "not-a-uuid", "quantity": 3}], "INVALID"),
        (
            "QTY_CHANGE",
            [{"line_id": str(ln.pk), "quantity": 3}, {"line_id": str(ln.pk), "quantity": 4}],
            "DUPLICATE_ITEM",
        ),
        ("DUE_DATE_CHANGE", [{"line_id": None, "requested_due_date": "2029-01-01"}], "DUE_BEFORE_ORDER_DATE"),
        ("DUE_DATE_CHANGE", [{"line_id": None, "requested_due_date": "31/12/2030"}], "INVALID"),
        ("HOLD", [{"line_id": str(ln.pk)}], "ITEMS_NOT_ALLOWED"),
        ("NO_SUCH_KIND", [], "INVALID"),
    ]
    for kind, items, reason in bad:
        with pytest.raises(ValidationFailed) as exc:
            _cr(p.co, o, kind, items)
        assert _reason(exc.value) == reason, (kind, items)
    with pytest.raises(StateTransitionNotAllowed) as exc2:
        _cr(p.co, o, "QTY_CHANGE", [{"line_id": str(uuid.uuid4()), "quantity": 3}])
    assert _reason(exc2.value) == "LINE_NOT_IN_ORDER"
    with pytest.raises(ValidationFailed):
        changes.create_change_request(
            p.co.caller, o.pk, kind="HOLD", items=[], reason="  ", expected_version=o.row_version
        )


def test_change_requests_exist_only_for_confirmed_orders(p: e.People) -> None:
    for o in (e.draft_order(p.co), e.validated_order(p.co)):
        with pytest.raises(StateTransitionNotAllowed) as exc:
            _cr(p.co, o, "HOLD")
        assert _reason(exc.value) == "STATE_NOT_ALLOWED"


# ------------------------------------------------------------------------------------- CR lifecycle
ALL = sorted(ChangeStatus.values)
CR_ALLOWED = {
    ("DRAFT", "SUBMITTED"),
    ("DRAFT", "WITHDRAWN"),
    ("SUBMITTED", "APPROVED"),
    ("SUBMITTED", "REJECTED"),
    ("SUBMITTED", "WITHDRAWN"),
    ("SUBMITTED", "EXPIRED"),
    ("APPROVED", "APPLIED"),
    ("APPROVED", "EXPIRED"),
}


@pytest.mark.parametrize(("src", "dst"), list(product(ALL, ALL)))
def test_change_machine_lists_exactly_the_db_lifecycle(src: str, dst: str) -> None:
    assert changes.CHANGE_MACHINE.can(src, dst) is ((src, dst) in CR_ALLOWED)


def test_lifecycle_through_the_use_cases(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    draft = _cr(p.co, o, "HOLD")
    assert draft.status == "DRAFT" and draft.request_no.startswith("CR-") and draft.impact is None
    with pytest.raises(StateTransitionNotAllowed):  # a DRAFT is not decided
        changes.decide_change_request(p.cm.caller, draft.pk, approve=True, expected_version=draft.row_version)
    with pytest.raises(NotFound):  # only the requester submits
        changes.submit_change_request(p.co2.caller, draft.pk, expected_version=draft.row_version)
    sub = changes.submit_change_request(p.co.caller, draft.pk, expected_version=draft.row_version)
    assert sub.status == "SUBMITTED" and sub.impact is not None and sub.impact["serials"]
    with pytest.raises(StateTransitionNotAllowed):  # not approved yet
        changes.apply_change_request(p.po.caller, sub.pk, expected_version=sub.row_version)
    with pytest.raises(ValidationFailed):  # a rejection needs a note
        changes.decide_change_request(
            p.cm.caller, sub.pk, approve=False, expected_version=sub.row_version, note=""
        )
    rej = changes.decide_change_request(
        p.cm.caller, sub.pk, approve=False, expected_version=sub.row_version, note="synthetic rejection"
    )
    assert (rej.status, rej.decided_by_id) == ("REJECTED", p.cm.pk)
    runs: list[Any] = [
        lambda: changes.decide_change_request(
            p.cm2.caller, rej.pk, approve=True, expected_version=rej.row_version
        ),
        lambda: changes.withdraw_change_request(
            p.co.caller, rej.pk, expected_version=rej.row_version, reason="syn"
        ),
        lambda: changes.apply_change_request(p.po.caller, rej.pk, expected_version=rej.row_version),
    ]
    for run in runs:
        with pytest.raises(StateTransitionNotAllowed):
            run()
    w = _cr(p.co, o, "HOLD", submit=True)
    with pytest.raises(NotFound):  # only the requester withdraws
        changes.withdraw_change_request(
            p.co2.caller, w.pk, expected_version=w.row_version, reason="synthetic"
        )
    w = changes.withdraw_change_request(p.co.caller, w.pk, expected_version=w.row_version, reason="synthetic")
    assert w.status == "WITHDRAWN"
    ok = _approved(p, o, "HOLD")
    ok = changes.apply_change_request(p.po.caller, ok.pk, expected_version=ok.row_version)
    with pytest.raises(StateTransitionNotAllowed):  # applied once
        changes.apply_change_request(p.po.caller, ok.pk, expected_version=ok.row_version)
    view = changes.get_change_request(p.viewer.caller, ok.pk)
    assert view["status"] == "APPLIED" and view["applied_version"] == 2


def test_submit_of_a_stale_draft_is_refused(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po, lines=2)
    draft = _cr(p.co, o, "QTY_CHANGE", [{"line_id": str(e.live_lines(o)[0].pk), "quantity": 2}])
    e.applied(p, o, "HOLD")
    with pytest.raises(StateTransitionNotAllowed) as exc:
        changes.submit_change_request(p.co.caller, draft.pk, expected_version=draft.row_version)
    assert _reason(exc.value) == "STALE_BASE_VERSION"


def test_requester_never_decides_and_the_owner_decides_directly(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    both = e.holder("commercial_officer", "commercial_manager")
    cr = _cr(both, o, "HOLD", submit=True)
    with pytest.raises(SelfApprovalForbidden) as exc:
        changes.decide_change_request(both.caller, cr.pk, approve=True, expected_version=cr.row_version)
    assert _reason(exc.value) == "DECIDER_IS_REQUESTER"
    decided = changes.decide_change_request(
        p.owner.caller, cr.pk, approve=True, expected_version=cr.row_version
    )
    assert decided.decided_by_id == p.owner.pk
    stale = e.holder("commercial_manager", mfa=False)
    cr2 = _cr(p.co, o, "HOLD", submit=True)
    with pytest.raises(MfaRequired):
        changes.decide_change_request(stale.caller, cr2.pk, approve=True, expected_version=cr2.row_version)


CR_ROLE_ACTIONS: dict[str, set[str]] = {
    "commercial_officer": {"read", "request"},
    "commercial_manager": {"read", "decide"},
    "planning_officer": {"read", "request", "planning_approve", "apply"},
    "product_data_steward": {"read"},
    "code_rule_approver": {"read"},
    "owner_admin": {"read", "decide"},
    "management_viewer": {"read"},
    "employee": set(),
    "it_ops": set(),
    "security_auditor": set(),
}


@pytest.mark.parametrize("role", sorted(CR_ROLE_ACTIONS))
def test_change_request_permissions_per_role(p: e.People, role: str) -> None:
    who = e.holder(role)
    allowed = CR_ROLE_ACTIONS[role]
    o = e.confirmed_order(p.co, p.po)
    due = [{"line_id": None, "requested_due_date": "2030-04-01"}]
    submitted = _cr(p.co, o, "DUE_DATE_CHANGE", due, submit=True)
    submitted2 = _cr(p.co, o, "DUE_DATE_CHANGE", due, submit=True)
    approved = _cr(p.co, o, "DUE_DATE_CHANGE", due, submit=True)
    approved = changes.planning_approve_change_request(
        p.po2.caller, approved.pk, expected_version=approved.row_version
    )
    approved = changes.decide_change_request(
        p.cm.caller, approved.pk, approve=True, expected_version=approved.row_version
    )
    attempts: dict[str, Any] = {
        "read": lambda: changes.get_change_request(who.caller, submitted.pk),
        "request": lambda: _cr(who, o, "HOLD"),
        "decide": lambda: changes.decide_change_request(
            who.caller, submitted.pk, approve=True, expected_version=submitted.row_version
        ),
        "planning_approve": lambda: changes.planning_approve_change_request(
            who.caller, submitted2.pk, expected_version=submitted2.row_version
        ),
        "apply": lambda: changes.apply_change_request(
            who.caller, approved.pk, expected_version=approved.row_version
        ),
    }
    for action, run in attempts.items():
        if action in allowed:
            run()
        else:
            with pytest.raises(AccessDenied):
                run()
