"""PHASE_02 / 02.3 order engine (DEC-006 / DEC-057 / DEC-058 / DEC-059) against PostgreSQL.

ID-02/03/04 at engine level: every line of a confirmed order has its own serial drawn in the confirm unit of
work; a replayed confirm has a single effect. State machine: every allowed and every refused transition of the
order (engine machine == DB guard). Permissions per role, maker-checker, PII masking + read audit, PO
duplicate warning, brand of the customer, line unit of the product type. All data synthetic.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from itertools import product
from typing import Any

import pytest
from django.db.models.functions import Now

from platform_core.commercial import orders
from platform_core.commercial.models import (
    CustomerOrder,
    CustomerOrderLine,
    CustomerOrderVersion,
    OrderStatus,
)
from platform_core.engine.errors import (
    AccessDenied,
    AleekhanError,
    IdempotencyKeyReused,
    MfaRequired,
    NotFound,
    SelfApprovalForbidden,
    StateTransitionNotAllowed,
    ValidationFailed,
    VersionConflict,
)
from platform_core.engine.redaction import REDACTED
from platform_core.engine.uow import unit_of_work
from platform_core.models import AuditEvent, OutboxEvent
from platform_core.product_identity.models import Serial, SerialCounter, SerialSnapshot
from platform_core.product_identity.serials import AllocationRequest, allocate_serial

from . import phase02_engine as e
from . import phase02_factories as f
from .phase02_engine import deferred_checks  # noqa: F401 - fixture

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("deferred_checks")]


def _reason(exc: AleekhanError) -> str:
    return exc.errors[0].code


@pytest.fixture
def p() -> e.People:
    return e.people()


def _next() -> int:
    return SerialCounter.objects.get(namespace_key="factory_serial").next_value


# --------------------------------------------------------------------------------------------- happy path
def test_draft_validate_confirm_release_allocates_one_serial_per_line_in_one_unit(p: e.People) -> None:
    first = _next()
    o = e.draft_order(p.co, lines=3)
    assert o.status == "DRAFT" and o.order_no.startswith("SO-") and o.current_version == 0
    o = orders.validate_order(p.co.caller, o.pk, expected_version=o.row_version)
    o = orders.confirm_order(p.po.caller, o.pk, expected_version=o.row_version)
    assert (o.status, o.current_version, o.confirmed_by_id) == ("CONFIRMED", 1, p.po.pk)
    lines = e.live_lines(o)
    assert [ln.line_no for ln in lines] == [1, 2, 3]
    serials = [Serial.objects.get(pk=ln.serial_id) for ln in lines]
    assert [s.serial_number for s in serials] == [str(first), str(first + 1), str(first + 2)]  # ID-03
    assert all(s.status == "ALLOCATED" and s.allocated_by_id == p.po.pk for s in serials)
    assert all(SerialSnapshot.objects.filter(serial=s, version=1).count() == 1 for s in serials)
    v1 = CustomerOrderVersion.objects.get(order=o, version=1)
    assert v1.reason == "CONFIRMED" and len(v1.image["lines"]) == 3
    assert e.SYN_REP not in str(v1.image)  # PII never copied into the append-only image (DEC-058)
    assert v1.image["has_customer_representative"] is True
    confirmed = OutboxEvent.objects.get(event_type="commercial.order.confirmed", aggregate_id=str(o.pk))
    assert confirmed.payload == {"id": str(o.pk), "status": "CONFIRMED", "version": 1, "line_count": 3}
    assert confirmed.producer == "platform_core.commercial"
    assert OutboxEvent.objects.filter(event_type="identity.serial.allocated").count() == 3
    o = orders.release_order(p.po.caller, o.pk, expected_version=o.row_version)
    assert (o.status, o.released_by_id, o.current_version) == ("RELEASED_TO_PLAN", p.po.pk, 1)
    for ev in OutboxEvent.objects.filter(aggregate_type="commercial.customer_order"):
        assert e.SYN_REP not in str(ev.payload)


def test_line_unit_is_the_product_type_unit_and_line_numbers_are_never_reused(p: e.People) -> None:
    s, _r = e.chain(uom="PAIR")
    o = orders.create_order(
        p.co.caller, customer_id=f.customer().pk, order_type="sampling", order_date=e.ORDER_DATE
    )
    a = orders.add_line(p.co.caller, o.pk, expected_version=o.row_version, style_id=s.pk, quantity=4)
    assert a.uom_id == "PAIR"  # DEC-058: shoes = pair, set by the engine
    o.refresh_from_db()
    orders.remove_line(p.co.caller, a.pk, expected_version=o.row_version)
    o.refresh_from_db()
    b = orders.add_line(p.co.caller, o.pk, expected_version=o.row_version, style_id=s.pk, quantity=2)
    assert (b.line_no, CustomerOrderLine.objects.get(pk=a.pk).status) == (2, "REMOVED")


def test_every_line_edit_moves_the_order_etag(p: e.People) -> None:
    o = e.draft_order(p.co, lines=1)
    ln = CustomerOrderLine.objects.get(order=o)
    stale = o.row_version
    orders.update_line(p.co.caller, ln.pk, expected_version=stale, changes={"quantity": 11})
    with pytest.raises(VersionConflict):
        orders.update_line(p.co.caller, ln.pk, expected_version=stale, changes={"quantity": 12})
    with pytest.raises(VersionConflict):
        orders.update_order(p.co.caller, o.pk, expected_version=stale, changes={"program_ref": "SYN-PRG"})
    assert CustomerOrderLine.objects.get(pk=ln.pk).quantity == 11


# --------------------------------------------------------------------------------------- input refusals
def test_brand_must_belong_to_the_customer_and_due_not_before_order_date(p: e.People) -> None:
    c1, c2 = f.customer(), f.customer()
    other_brand = f.brand(c2)
    with pytest.raises(ValidationFailed) as exc:
        orders.create_order(
            p.co.caller,
            customer_id=c1.pk,
            order_type="sampling",
            order_date=e.ORDER_DATE,
            brand_id=other_brand.pk,
        )
    assert _reason(exc.value) == "BRAND_OF_OTHER_CUSTOMER"
    with pytest.raises(ValidationFailed) as exc:
        orders.create_order(
            p.co.caller,
            customer_id=c1.pk,
            order_type="sampling",
            order_date=e.ORDER_DATE,
            requested_due_date=e.ORDER_DATE - timedelta(days=1),
        )
    assert _reason(exc.value) == "DUE_BEFORE_ORDER_DATE"
    o = orders.create_order(
        p.co.caller,
        customer_id=c1.pk,
        order_type="sampling",
        order_date=e.ORDER_DATE,
        brand_id=f.brand(c1).pk,
    )
    assert o.brand_id is not None  # the brand is optional, but if given it is the customer's
    with pytest.raises(ValidationFailed) as exc:
        orders.create_order(
            p.co.caller, customer_id=c1.pk, order_type="no_such_type", order_date=e.ORDER_DATE
        )
    assert _reason(exc.value) == "INVALID"


@pytest.mark.parametrize("bad", ["syn@example.invalid", "SYN 0912", "ساختگی ۰۹۱۲", "x" * 201])
def test_representative_is_a_name_only(p: e.People, bad: str) -> None:
    with pytest.raises(ValidationFailed) as exc:
        orders.create_order(
            p.co.caller,
            customer_id=f.customer().pk,
            order_type="sampling",
            order_date=e.ORDER_DATE,
            customer_representative_name=bad,
        )
    assert _reason(exc.value) in ("REPRESENTATIVE_NAME_INVALID", "INVALID")


def test_quantity_must_be_a_positive_integer_and_the_style_live(p: e.People) -> None:
    o = orders.create_order(
        p.co.caller, customer_id=f.customer().pk, order_type="sampling", order_date=e.ORDER_DATE
    )
    s, _r = e.chain()
    for bad, code in (
        (0, "QUANTITY_NOT_POSITIVE"),
        (-3, "QUANTITY_NOT_POSITIVE"),
        (1.5, "INVALID"),
        (True, "INVALID"),
    ):
        with pytest.raises(ValidationFailed) as exc:
            orders.add_line(p.co.caller, o.pk, expected_version=o.row_version, style_id=s.pk, quantity=bad)  # type: ignore[arg-type]
        assert _reason(exc.value) == code
    draft_style, _r2 = e.chain()
    draft_style.__class__.objects.filter(pk=draft_style.pk).update(status="DRAFT")
    with pytest.raises(StateTransitionNotAllowed) as exc2:
        orders.add_line(
            p.co.caller, o.pk, expected_version=o.row_version, style_id=draft_style.pk, quantity=1
        )
    assert _reason(exc2.value) == "MASTER_NOT_ACTIVE"


def test_duplicate_po_number_of_the_same_customer_needs_acknowledgement(p: e.People) -> None:
    cust = f.customer()
    e.draft_order(p.co, customer=cust, external_po_number="SYN-PO-1")
    second = e.draft_order(p.co, customer=cust, external_po_number="syn-po-1")
    with pytest.raises(ValidationFailed) as exc:
        orders.validate_order(p.co.caller, second.pk, expected_version=second.row_version)
    assert _reason(exc.value) == "DUPLICATE_PO_NUMBER"
    with pytest.raises(ValidationFailed) as exc:
        orders.validate_order(
            p.co.caller, second.pk, expected_version=second.row_version, acknowledge_warnings=["TYPO"]
        )
    assert _reason(exc.value) == "UNKNOWN_WARNING"
    ok = orders.validate_order(
        p.co.caller,
        second.pk,
        expected_version=second.row_version,
        acknowledge_warnings=["DUPLICATE_PO_NUMBER"],
    )
    assert ok.status == "VALIDATED"
    audit = AuditEvent.objects.get(action="commercial.order.validate", resource_id=str(second.pk))
    assert audit.scope == {"acknowledged_warnings": ["DUPLICATE_PO_NUMBER"]}
    other = e.draft_order(p.co, external_po_number="SYN-PO-1")  # another customer: no warning
    assert (
        orders.validate_order(p.co.caller, other.pk, expected_version=other.row_version).status == "VALIDATED"
    )


def test_validate_needs_a_line(p: e.People) -> None:
    o = orders.create_order(
        p.co.caller, customer_id=f.customer().pk, order_type="sampling", order_date=e.ORDER_DATE
    )
    with pytest.raises(StateTransitionNotAllowed) as exc:
        orders.validate_order(p.co.caller, o.pk, expected_version=o.row_version)
    assert _reason(exc.value) == "ORDER_HAS_NO_LINES"


# ------------------------------------------------------------------------------------- maker-checker/MFA
def test_confirmer_is_never_the_creator_not_even_the_owner(p: e.People) -> None:
    both = e.holder("commercial_officer", "planning_officer")
    o = e.validated_order(both)
    with pytest.raises(SelfApprovalForbidden) as exc:
        orders.confirm_order(both.caller, o.pk, expected_version=o.row_version)
    assert _reason(exc.value) == "CONFIRMER_IS_CREATOR"
    owner_maker = e.holder("owner_admin", "commercial_officer")
    o2 = e.validated_order(owner_maker)
    with pytest.raises(SelfApprovalForbidden):
        orders.confirm_order(owner_maker.caller, o2.pk, expected_version=o2.row_version)
    # the owner confirms directly an order somebody else made (DEC-057)
    o3 = e.validated_order(p.co)
    done = orders.confirm_order(p.owner.caller, o3.pk, expected_version=o3.row_version)
    assert done.status == "CONFIRMED"
    audit = AuditEvent.objects.get(action="commercial.order.confirm", resource_id=str(o3.pk))
    assert audit.scope["via_role"] == "owner_admin"


def test_confirm_needs_fresh_mfa(p: e.People) -> None:
    stale = e.holder("planning_officer", mfa=False)
    o = e.validated_order(p.co)
    with pytest.raises(MfaRequired):
        orders.confirm_order(stale.caller, o.pk, expected_version=o.row_version)
    assert CustomerOrder.objects.get(pk=o.pk).status == "VALIDATED"


ROLE_ACTIONS: dict[str, set[str]] = {
    # role -> order actions it may run (matrix v2.0/v2.1, PERMISSION_MATRIX_DRAFT section 7)
    "commercial_officer": {"read", "create", "validate"},
    "commercial_manager": {"read"},
    "planning_officer": {"read", "confirm", "release"},
    "product_data_steward": {"read"},
    "code_rule_approver": {"read"},
    "owner_admin": {"read", "confirm"},
    "management_viewer": {"read"},
    "employee": set(),
    "it_ops": set(),
    "security_auditor": set(),
}


@pytest.mark.parametrize("role", sorted(ROLE_ACTIONS))
def test_order_permissions_per_role(p: e.People, role: str) -> None:
    who = e.holder(role)
    allowed = ROLE_ACTIONS[role]
    draft = e.draft_order(p.co)
    validated = e.validated_order(p.co)
    confirmed = e.confirmed_order(p.co, p.po)
    attempts: dict[str, Any] = {
        "read": lambda: orders.get_order(who.caller, draft.pk),
        "create": lambda: orders.create_order(
            who.caller, customer_id=f.customer().pk, order_type="sampling", order_date=e.ORDER_DATE
        ),
        "validate": lambda: orders.validate_order(who.caller, draft.pk, expected_version=draft.row_version),
        "confirm": lambda: orders.confirm_order(
            who.caller, validated.pk, expected_version=validated.row_version
        ),
        "release": lambda: orders.release_order(
            who.caller, confirmed.pk, expected_version=confirmed.row_version
        ),
    }
    for action, run in attempts.items():
        if action in allowed:
            run()
        else:
            with pytest.raises(AccessDenied):
                run()


# --------------------------------------------------------------------------------------------- PII (DEC-058)
def test_representative_name_masked_for_viewer_and_every_unmasked_read_audited(p: e.People) -> None:
    o = e.draft_order(p.co)
    before = AuditEvent.objects.filter(action="commercial.order.representative_read").count()
    assert orders.get_order(p.viewer.caller, o.pk)["customer_representative_name"] == REDACTED
    assert AuditEvent.objects.filter(action="commercial.order.representative_read").count() == before
    for who in (p.co, p.cm, p.po, p.owner):
        assert orders.get_order(who.caller, o.pk)["customer_representative_name"] == e.SYN_REP
    reads = AuditEvent.objects.filter(action="commercial.order.representative_read", resource_id=str(o.pk))
    assert {a.actor_id for a in reads} == {p.co.pk, p.cm.pk, p.po.pk, p.owner.pk}
    for a in reads:
        assert e.SYN_REP not in str(a.after) and e.SYN_REP not in str(a.scope) and e.SYN_REP not in a.reason
    # a viewer who ALSO holds an unmasked role sees it (masking follows the role, DEC-058)
    both = e.holder("management_viewer", "commercial_manager")
    assert orders.get_order(both.caller, o.pk)["customer_representative_name"] == e.SYN_REP
    # no name recorded: nothing to mask, nothing audited
    none = e.draft_order(p.co, rep=None)
    assert orders.get_order(p.co.caller, none.pk)["customer_representative_name"] is None
    assert not AuditEvent.objects.filter(
        action="commercial.order.representative_read", resource_id=str(none.pk)
    )


def test_representative_change_is_audited_without_the_value(p: e.People) -> None:
    o = e.draft_order(p.co, rep=None)
    orders.update_order(
        p.co.caller, o.pk, expected_version=o.row_version, changes={"customer_representative_name": e.SYN_REP}
    )
    audit = AuditEvent.objects.filter(action="commercial.order.update", resource_id=str(o.pk)).latest(
        "occurred_at"
    )
    assert audit.after is not None and "customer_representative_name" in audit.after["changed"]
    assert e.SYN_REP not in str(audit.after) and e.SYN_REP not in str(audit.before)


# ---------------------------------------------------------------------------------------- state machine
ALL_STATES = sorted(OrderStatus.values)
ALLOWED = {
    ("DRAFT", "VALIDATED"),
    ("DRAFT", "CANCELLED"),
    ("VALIDATED", "DRAFT"),
    ("VALIDATED", "CONFIRMED"),
    ("VALIDATED", "CANCELLED"),
    ("CONFIRMED", "RELEASED_TO_PLAN"),
    ("CONFIRMED", "ON_HOLD"),
    ("CONFIRMED", "CANCELLED"),
    ("RELEASED_TO_PLAN", "ON_HOLD"),
    ("ON_HOLD", "CONFIRMED"),
    ("ON_HOLD", "RELEASED_TO_PLAN"),
    ("ON_HOLD", "CANCELLED"),
}


@pytest.mark.parametrize(("src", "dst"), list(product(ALL_STATES, ALL_STATES)))
def test_order_machine_lists_exactly_the_decided_transitions(src: str, dst: str) -> None:
    assert orders.ORDER_MACHINE.can(src, dst) is ((src, dst) in ALLOWED)


def _held(before: str) -> Any:
    return CustomerOrder(status="ON_HOLD", status_before_hold=before)


@pytest.mark.parametrize(
    ("o", "dst", "ok"),
    [
        (_held("CONFIRMED"), "CONFIRMED", True),
        (_held("CONFIRMED"), "RELEASED_TO_PLAN", False),  # resume returns to the stored state only
        (_held("RELEASED_TO_PLAN"), "RELEASED_TO_PLAN", True),
        (_held("RELEASED_TO_PLAN"), "CONFIRMED", False),
        (_held("CONFIRMED"), "CANCELLED", True),  # amendment 2026-11-12
        (_held("RELEASED_TO_PLAN"), "CANCELLED", False),  # C-A
        (CustomerOrder(status="RELEASED_TO_PLAN"), "CANCELLED", False),  # C-A
    ],
)
def test_order_guards_on_the_stored_previous_state(o: CustomerOrder, dst: str, ok: bool) -> None:
    if ok:
        orders.assert_order_transition(o, dst)
    else:
        with pytest.raises(StateTransitionNotAllowed):
            orders.assert_order_transition(o, dst)


def test_direct_transitions_refused_from_wrong_states(p: e.People) -> None:
    draft = e.draft_order(p.co)
    with pytest.raises(StateTransitionNotAllowed):  # DRAFT -> CONFIRMED (must validate)
        orders.confirm_order(p.po.caller, draft.pk, expected_version=draft.row_version)
    with pytest.raises(StateTransitionNotAllowed):  # DRAFT -> RELEASED
        orders.release_order(p.po.caller, draft.pk, expected_version=draft.row_version)
    with pytest.raises(StateTransitionNotAllowed):  # reopen of a DRAFT
        orders.reopen_order(p.co.caller, draft.pk, expected_version=draft.row_version, reason="synthetic")
    v = e.validated_order(p.co)
    with pytest.raises(StateTransitionNotAllowed):  # VALIDATED is frozen until reopened
        orders.update_order(p.co.caller, v.pk, expected_version=v.row_version, changes={"program_ref": "SYN"})
    v = orders.reopen_order(p.co.caller, v.pk, expected_version=v.row_version, reason="synthetic reopen")
    assert v.status == "DRAFT"
    c = e.confirmed_order(p.co, p.po)
    with pytest.raises(StateTransitionNotAllowed):  # confirmed: edited only through change requests
        orders.update_order(p.co.caller, c.pk, expected_version=c.row_version, changes={"program_ref": "SYN"})
    with pytest.raises(StateTransitionNotAllowed):
        orders.cancel_unconfirmed_order(p.co.caller, c.pk, expected_version=c.row_version, reason="synthetic")
    with pytest.raises(StateTransitionNotAllowed):  # confirm twice
        orders.confirm_order(p.po2.caller, c.pk, expected_version=c.row_version)
    r = orders.release_order(p.po.caller, c.pk, expected_version=c.row_version)
    with pytest.raises(StateTransitionNotAllowed):  # release twice
        orders.release_order(p.po.caller, r.pk, expected_version=r.row_version)
    for o in (e.draft_order(p.co), e.validated_order(p.co)):
        done = orders.cancel_unconfirmed_order(
            p.co.caller, o.pk, expected_version=o.row_version, reason="synthetic"
        )
        assert done.status == "CANCELLED" and done.current_version == 0
        with pytest.raises(StateTransitionNotAllowed):
            orders.validate_order(p.co.caller, o.pk, expected_version=done.row_version)


def test_other_records_are_not_found(p: e.People) -> None:
    with pytest.raises(NotFound):
        orders.get_order(p.co.caller, uuid.uuid4())
    with pytest.raises(NotFound):
        orders.confirm_order(p.po.caller, uuid.uuid4(), expected_version=1)


# --------------------------------------------------------------------------------------- idempotency
def test_rev0220_same_allocation_key_with_another_payload_is_refused(p: e.People) -> None:
    o = e.validated_order(p.co, lines=1)
    ln = CustomerOrderLine.objects.get(order=o)
    other_style, other_rev = e.chain()
    key = uuid.uuid4()
    first = _next()

    def req(style_id: Any, rev_id: Any) -> AllocationRequest:
        return AllocationRequest(
            idempotency_key=key,
            allocated_by=p.po.pk,
            customer_id=o.customer_id,
            style_id=style_id,
            style_revision_id=rev_id,
            product_code_id=None,
            order_version=1,
            snapshot={"synthetic": True},
        )

    with unit_of_work(p.po.caller.context()) as uow:
        a = allocate_serial(uow, req(ln.style_id, ln.style_revision_id))
        events = OutboxEvent.objects.filter(event_type="identity.serial.allocated").count()
        with pytest.raises(IdempotencyKeyReused) as exc:
            allocate_serial(uow, req(other_style.pk, other_rev.pk))
        assert _reason(exc.value) == "IDEMPOTENCY_PAYLOAD_MISMATCH"
        assert OutboxEvent.objects.filter(event_type="identity.serial.allocated").count() == events
        assert _next() == first + 1  # no second number drawn
        same = allocate_serial(uow, req(ln.style_id, ln.style_revision_id))
        assert same.replayed and same.serial.pk == a.serial.pk
        CustomerOrderLine.objects.filter(pk=ln.pk).update(
            status="CONFIRMED", serial=a.serial, order_version=1
        )
        CustomerOrderVersion.objects.create(
            order=o, version=1, image={}, reason="CONFIRMED", created_by_id=p.po.pk
        )
        CustomerOrder.objects.filter(pk=o.pk).update(
            status="CONFIRMED", current_version=1, confirmed_by_id=p.po.pk, confirmed_at=Now()
        )
    assert Serial.objects.filter(allocation_idempotency_key=key).count() == 1
