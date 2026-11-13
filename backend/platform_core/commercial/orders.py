"""Customer order use cases (PHASE_02 / 02.3; DEC-006/057/058/059, STATE_TRANSITIONS 5.1/5.2).

Machine (engine ``ORDER_MACHINE``, the same graph the DB guard of 0020/0023 enforces)::

    DRAFT --validate--> VALIDATED --confirm--> CONFIRMED --release--> RELEASED_TO_PLAN
      ^  \\               |  \\                   |   \\  (change requests, changes.py)       |
      |   cancel          |   cancel             |    HOLD -> ON_HOLD -> RESUME (stored previous state)
      +----reopen---------+                      +-- CANCEL_ORDER (before release only, DEC-059 C-A;
                                                      also from ON_HOLD when the stored state is CONFIRMED)

* DRAFT is edited directly (header and lines, ``commercial.order.manage`` = commercial_officer); a VALIDATED
  order is frozen until it is reopened. Every line edit touches the order row, so the order ``row_version``
  (ETag) covers its lines.
* Confirm (``commercial.order.confirm``: planning_officer, or the owner directly; business approval + fresh
  MFA; the confirmer is never the creator, DEC-057): in ONE unit of work every OPEN line gets its serial from
  the gapless counter (``product_identity.serials.allocate_serial``, DEC-006 L-A), the Commercial side writes
  ``line.serial_id`` (REV-0201), the order version 1 image is written.
* Release (``commercial.order.release``: planning_officer): CONFIRMED -> RELEASED_TO_PLAN.
* After confirmation nothing is edited in place: every change is a change request (``changes.py``).
* DEC-058: the brand belongs to the customer and is optional; the line unit is the product type's unit (set by
  the engine); the customer PO number is not unique - a duplicate within the same customer is a warning the
  user acknowledges (``DUPLICATE_PO_NUMBER``) when validating; the representative is a **name only** (PII):
  never in events, audit values, version images or serial snapshots; masked for ``management_viewer``; every
  unmasked read is audited (:func:`get_order`).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any, Final

from django.db.models.functions import Now

from platform_core.authz import policy as P
from platform_core.authz.policy import Caller
from platform_core.engine.dbrules import db_rules
from platform_core.engine.errors import NotFound
from platform_core.engine.redaction import REDACTED
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import UnitOfWork, unit_of_work
from platform_core.product_identity.models import (
    Customer,
    CustomerBrand,
    MasterStatus,
    PartyStatus,
    ProductCode,
    ProductCodeStatus,
    Serial,
    Style,
    StyleRevision,
    StyleRevisionStatus,
)
from platform_core.product_identity.refusals import Reason, refuse
from platform_core.product_identity.serials import AllocationRequest, allocate_serial
from platform_core.product_identity.usecase import (
    acknowledged,
    authorize,
    check_version,
    lock,
    next_number,
    optional_text,
    reason_text,
)

from .models import (
    CustomerOrder,
    CustomerOrderLine,
    CustomerOrderVersion,
    LineStatus,
    OrderStatus,
    OrderType,
    VersionReason,
)

ORDER_READ: Final = "commercial.order.read"
ORDER_MANAGE: Final = "commercial.order.manage"
ORDER_CONFIRM: Final = "commercial.order.confirm"
ORDER_RELEASE: Final = "commercial.order.release"
CUSTOMER_READ: Final = "identity.customer.read"
RESOURCE: Final = "commercial.customer_order"
WARN_DUPLICATE_PO: Final = Reason.DUPLICATE_PO_NUMBER.value
# DEC-058: the representative name is visible with identity.customer.read, except through these roles
REPRESENTATIVE_MASKED_ROLES: Final = frozenset({"management_viewer"})
# allocation keys of the confirm are derived per (order, line): a retried confirm can never draw twice
ALLOCATION_NAMESPACE: Final = uuid.UUID("0b3b1a52-2f5c-4c55-9d43-02a3e0c0de06")
# an '@', ASCII digits, Persian digits (U+06F0-U+06F9) or Arabic-Indic digits (U+0660-U+0669)
_CONTACT_LIKE: Final = re.compile(
    "[@0-9" + "".join(chr(c) for c in (*range(0x06F0, 0x06FA), *range(0x0660, 0x066A))) + "]"
)

O, L = OrderStatus, LineStatus  # noqa: E741 - short state aliases
ORDER_MACHINE: Final = StateMachine(
    name="commercial.customer_order",
    states=frozenset(OrderStatus.values),
    transitions={
        O.DRAFT: frozenset({O.VALIDATED, O.CANCELLED}),
        O.VALIDATED: frozenset({O.DRAFT, O.CONFIRMED, O.CANCELLED}),
        O.CONFIRMED: frozenset({O.RELEASED_TO_PLAN, O.ON_HOLD, O.CANCELLED}),
        # cancel after release is blocked until PHASE_05 (DEC-059 C-A); fulfilment is PHASE_07/09
        O.RELEASED_TO_PLAN: frozenset({O.ON_HOLD}),
        # resume to the stored previous state; cancel only when that state is CONFIRMED (amendment 2026-11-12)
        O.ON_HOLD: frozenset({O.CONFIRMED, O.RELEASED_TO_PLAN, O.CANCELLED}),
        O.CANCELLED: frozenset(),
        O.PARTIAL_FULFILLED: frozenset(),
        O.FULFILLED: frozenset(),
        O.CLOSED: frozenset(),
    },
)
LINE_MACHINE: Final = StateMachine(
    name="commercial.customer_order_line",
    states=frozenset(LineStatus.values),
    transitions={
        L.OPEN: frozenset({L.CONFIRMED, L.REMOVED}),
        L.CONFIRMED: frozenset({L.CANCELLED}),
        L.REMOVED: frozenset(),
        L.CANCELLED: frozenset(),
    },
)
HEADER_FIELDS: Final = (
    "brand_id",
    "external_po_number",
    "order_type",
    "program_ref",
    "order_date",
    "requested_due_date",
    "required_quality_requirement",
    "customer_representative_name",
)


def is_released(o: CustomerOrder) -> bool:
    return o.status == O.RELEASED_TO_PLAN or (
        o.status == O.ON_HOLD and o.status_before_hold == O.RELEASED_TO_PLAN
    )


def assert_order_transition(o: CustomerOrder, dst: str) -> None:
    """``ORDER_MACHINE`` plus the guards that depend on the stored previous state (DEC-059)."""
    if dst == O.CANCELLED and is_released(o):
        refuse(Reason.CANCEL_AFTER_RELEASE, field="status", detail="cancel after release waits for PHASE_05")
    ORDER_MACHINE.assert_transition(o.status, dst)
    if o.status == O.ON_HOLD and dst != O.CANCELLED and dst != o.status_before_hold:
        refuse(Reason.STATE_NOT_ALLOWED, field="status", detail="a held order resumes to its previous state")


# --------------------------------------------------------------------------------------------- views
def _d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def line_image(ln: CustomerOrderLine) -> dict[str, Any]:
    code = (
        ProductCode.objects.filter(pk=ln.product_code_id).values_list("code", flat=True).first()
        if ln.product_code_id
        else None
    )
    serial = (
        Serial.objects.filter(pk=ln.serial_id).values_list("serial_number", flat=True).first()
        if ln.serial_id
        else None
    )
    return {
        "line_id": str(ln.pk),
        "line_no": ln.line_no,
        "status": ln.status,
        "style_id": str(ln.style_id),
        "style_revision_id": str(ln.style_revision_id),
        "product_code": code,  # 14-digit text or None
        "quantity": ln.quantity,
        "uom": ln.uom_id,
        "requested_due_date": _d(ln.requested_due_date),
        "serial_id": str(ln.serial_id) if ln.serial_id else None,
        "serial_number": serial,
        "order_version": ln.order_version,
    }


def order_image(o: CustomerOrder, lines: Iterable[CustomerOrderLine]) -> dict[str, Any]:
    """Version image (append-only table): identifiers and business fields; the representative name is NOT
    copied (PII stays in one place, DEC-058) - only whether one is recorded."""
    return {
        "order_no": o.order_no,
        "customer_id": str(o.customer_id),
        "brand_id": str(o.brand_id) if o.brand_id else None,
        "external_po_number": o.external_po_number,
        "order_type": o.order_type_id,
        "program_ref": o.program_ref,
        "order_date": _d(o.order_date),
        "requested_due_date": _d(o.requested_due_date),
        "required_quality_requirement": o.required_quality_requirement,
        "has_customer_representative": o.customer_representative_name is not None,
        "status": o.status,
        "status_before_hold": o.status_before_hold,
        "lines": [line_image(ln) for ln in lines],
    }


def line_snapshot(o: CustomerOrder, ln: CustomerOrderLine, version: int) -> dict[str, Any]:
    """Serial snapshot image of one line at an order version (no personal data)."""
    img = line_image(ln)
    img.pop("serial_number", None)
    return {
        "order_id": str(o.pk),
        "order_no": o.order_no,
        "order_status": o.status,
        "customer_id": str(o.customer_id),
        "order_version": version,
        **img,
    }


def _state_view(o: CustomerOrder) -> dict[str, Any]:
    return {"order_no": o.order_no, "status": o.status, "version": o.current_version}


def _event(
    uow: UnitOfWork,
    verb: str,
    o: CustomerOrder,
    *,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None = None,
    reason: str = "",
    scope: Mapping[str, Any] | None = None,
    event: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> None:
    uow.audit(
        action=f"commercial.order.{verb}",
        resource_type=RESOURCE,
        resource_id=str(o.pk),
        resource_version=o.row_version,
        before=before,
        after=dict(after) if after is not None else _state_view(o),
        reason=reason,
        scope=scope,
    )
    uow.emit(
        event_type=event or f"commercial.order.{verb}",
        aggregate_type=RESOURCE,
        aggregate_id=str(o.pk),
        aggregate_version=o.row_version,
        payload=dict(payload)
        if payload is not None
        else {"id": str(o.pk), "status": o.status, "version": o.current_version},
    )


def representative_visible(caller: Caller) -> bool:
    """DEC-058: ``identity.customer.read`` through a role that is not masked (management_viewer sees it
    masked). PHASE_02 records have no unit: only GLOBAL-scope grants count."""
    facts = P.ScopeFacts(caller.user_id)
    return any(
        g.role_code not in REPRESENTATIVE_MASKED_ROLES and P.grant_allows(g, P.RecordScope(), facts)
        for g in P.effective_grants(caller.user_id, CUSTOMER_READ)
    )


def get_order(caller: Caller, order_id: uuid.UUID, *, request_id: uuid.UUID | None = None) -> dict[str, Any]:
    """The order with its lines (``commercial.order.read``). The representative name: the value for callers
    who may see it (every such read of a recorded name is audited, DEC-058), ``[REDACTED]`` otherwise."""
    authorize(caller, ORDER_READ)
    o = CustomerOrder.objects.filter(pk=order_id).first()
    if o is None:
        raise NotFound()
    lines = list(CustomerOrderLine.objects.filter(order=o).order_by("line_no"))
    view = order_image(o, lines)
    view.pop("has_customer_representative")
    view.update({"id": str(o.pk), "version": o.current_version, "row_version": o.row_version})
    name = o.customer_representative_name
    if name is None:
        view["customer_representative_name"] = None
    elif representative_visible(caller):
        with unit_of_work(caller.context(request_id), require_event=False) as uow:
            uow.audit(
                action="commercial.order.representative_read",
                resource_type=RESOURCE,
                resource_id=str(o.pk),
                resource_version=o.row_version,
                scope={"field": "customer_representative_name"},
            )
        view["customer_representative_name"] = name
    else:
        view["customer_representative_name"] = REDACTED
    return view


# ------------------------------------------------------------------------------------------ validation
def representative_name(value: str | None) -> str | None:
    """DEC-058: a name only - no contact data (an '@' or any digit is refused)."""
    text = optional_text(value, max_len=200, field="customer_representative_name")
    if text is not None and _CONTACT_LIKE.search(text):
        refuse(Reason.REPRESENTATIVE_NAME_INVALID, field="customer_representative_name", detail="a name only")
    return text


def _customer(customer_id: uuid.UUID) -> Customer:
    c = Customer.objects.filter(pk=customer_id).first()
    if c is None:
        raise NotFound()
    if c.status != PartyStatus.ACTIVE:
        refuse(Reason.MASTER_NOT_ACTIVE, field="customer_id")
    return c


def _brand(brand_id: uuid.UUID | None, customer_id: uuid.UUID) -> uuid.UUID | None:
    if brand_id is None:
        return None
    b = CustomerBrand.objects.filter(pk=brand_id).first()
    if b is None:
        raise NotFound()
    if b.customer_id != customer_id:
        refuse(Reason.BRAND_OF_OTHER_CUSTOMER, field="brand_id")
    if b.status != PartyStatus.ACTIVE:
        refuse(Reason.MASTER_NOT_ACTIVE, field="brand_id")
    return b.pk


def _order_type(code: str) -> str:
    t = OrderType.objects.filter(pk=code).first()
    if t is None:
        refuse(Reason.INVALID, field="order_type")
    if t.status != PartyStatus.ACTIVE:
        refuse(Reason.MASTER_NOT_ACTIVE, field="order_type")
    return t.code


def _header_values(
    fields: Mapping[str, Any], *, customer_id: uuid.UUID, current: CustomerOrder | None
) -> dict[str, Any]:
    unknown = set(fields) - set(HEADER_FIELDS)
    if unknown:
        refuse(Reason.INVALID, field=sorted(unknown)[0])
    out: dict[str, Any] = {}
    if "brand_id" in fields:
        out["brand_id"] = _brand(fields["brand_id"], customer_id)
    if "external_po_number" in fields:
        out["external_po_number"] = (
            optional_text(fields["external_po_number"], max_len=64, field="external_po_number") or ""
        )
    if "order_type" in fields:
        out["order_type_id"] = _order_type(fields["order_type"])
    if "program_ref" in fields:
        out["program_ref"] = optional_text(fields["program_ref"], max_len=64, field="program_ref")
    if "order_date" in fields:
        if not isinstance(fields["order_date"], date):
            refuse(Reason.REQUIRED, field="order_date")
        out["order_date"] = fields["order_date"]
    if "requested_due_date" in fields:
        due = fields["requested_due_date"]
        if due is not None and not isinstance(due, date):
            refuse(Reason.INVALID, field="requested_due_date")
        out["requested_due_date"] = due
    if "required_quality_requirement" in fields:
        out["required_quality_requirement"] = optional_text(
            fields["required_quality_requirement"], max_len=64, field="required_quality_requirement"
        )
    if "customer_representative_name" in fields:
        out["customer_representative_name"] = representative_name(fields["customer_representative_name"])
    order_date = out.get("order_date", current.order_date if current else None)
    due = out.get("requested_due_date", current.requested_due_date if current else None)
    if order_date is not None and due is not None and due < order_date:
        refuse(Reason.DUE_BEFORE_ORDER_DATE, field="requested_due_date")
    return out


def _check_line_master(
    style_id: uuid.UUID, revision_id: uuid.UUID, product_code_id: uuid.UUID | None
) -> Style:
    s = Style.objects.select_related("product__product_type").filter(pk=style_id).first()
    if s is None:
        raise NotFound()
    if (
        s.status != MasterStatus.ACTIVE
        or s.product.status != MasterStatus.ACTIVE
        or s.product.product_type.status != MasterStatus.ACTIVE
    ):
        refuse(Reason.MASTER_NOT_ACTIVE, field="style_id")
    rev = StyleRevision.objects.filter(pk=revision_id).first()
    if rev is None or rev.style_id != s.pk:
        refuse(Reason.INVALID, field="style_revision_id", detail="the revision belongs to another style")
    if rev.status != StyleRevisionStatus.ACTIVE:
        refuse(Reason.MASTER_NOT_ACTIVE, field="style_revision_id")
    if product_code_id is not None:
        pc = ProductCode.objects.filter(pk=product_code_id).first()
        if pc is None:
            raise NotFound()
        if pc.style_id != s.pk:
            refuse(Reason.CODE_OF_OTHER_STYLE, field="product_code_id")
        if pc.status not in (ProductCodeStatus.RESERVED, ProductCodeStatus.ACTIVE):
            refuse(Reason.MASTER_NOT_ACTIVE, field="product_code_id")
    return s


def _active_revision_of(style_id: uuid.UUID) -> uuid.UUID:
    rid = (
        StyleRevision.objects.filter(style_id=style_id, status=StyleRevisionStatus.ACTIVE)
        .values_list("pk", flat=True)
        .first()
    )
    if rid is None:
        refuse(Reason.MASTER_NOT_ACTIVE, field="style_revision_id", detail="the style has no ACTIVE revision")
    return rid


def valid_quantity(value: Any, *, field: str = "quantity") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        refuse(Reason.INVALID, field=field)
    if value <= 0:
        refuse(Reason.QUANTITY_NOT_POSITIVE, field=field)
    return value


def line_due(value: Any, order_date: date, *, field: str = "requested_due_date") -> date | None:
    if value is None:
        return None
    if not isinstance(value, date):
        refuse(Reason.INVALID, field=field)
    if value < order_date:
        refuse(Reason.DUE_BEFORE_ORDER_DATE, field=field)
    return value


def duplicate_po_orders(o: CustomerOrder) -> int:
    """Other orders of the same customer with the same (non-empty) PO number (DEC-058 warning)."""
    po = (o.external_po_number or "").strip()
    if not po:
        return 0
    return (
        CustomerOrder.objects.filter(customer_id=o.customer_id, external_po_number__iexact=po)
        .exclude(pk=o.pk)
        .count()
    )


# ----------------------------------------------------------------------------------------- draft edits
def create_order(
    caller: Caller,
    *,
    customer_id: uuid.UUID,
    order_type: str,
    order_date: date,
    request_id: uuid.UUID | None = None,
    **header: Any,
) -> CustomerOrder:
    authorize(caller, ORDER_MANAGE)
    with unit_of_work(caller.context(request_id)) as uow:
        c = _customer(customer_id)
        values = _header_values(
            {**header, "order_type": order_type, "order_date": order_date}, customer_id=c.pk, current=None
        )
        with db_rules():
            o = CustomerOrder.objects.create(
                order_no=next_number("order"),
                customer=c,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
                **values,
            )
        o.refresh_from_db()
        _event(
            uow,
            "create",
            o,
            before=None,
            after={**_state_view(o), "customer_id": str(c.pk), "fields": sorted(values)},
            event="commercial.order.drafted",
        )
    return o


def _draft(order_id: uuid.UUID, expected_version: int) -> CustomerOrder:
    o = lock(CustomerOrder, order_id)
    check_version(o, expected_version)
    if o.status != O.DRAFT:
        refuse(
            Reason.STATE_NOT_ALLOWED, field="status", detail="only a DRAFT order is edited directly (DEC-059)"
        )
    return o


def _touch(o: CustomerOrder, caller: Caller) -> None:
    CustomerOrder.objects.filter(pk=o.pk).update(updated_by_id=caller.user_id)
    o.refresh_from_db()


def update_order(
    caller: Caller,
    order_id: uuid.UUID,
    *,
    expected_version: int,
    changes: Mapping[str, Any],
    request_id: uuid.UUID | None = None,
) -> CustomerOrder:
    """Header fields of a DRAFT order (the customer of an order never changes; a new order instead)."""
    authorize(caller, ORDER_MANAGE)
    if not changes:
        refuse(Reason.REQUIRED, field="", detail="nothing to change")
    with unit_of_work(caller.context(request_id)) as uow:
        o = _draft(order_id, expected_version)
        values = _header_values(changes, customer_id=o.customer_id, current=o)
        before = _state_view(o)
        with db_rules():
            CustomerOrder.objects.filter(pk=o.pk).update(updated_by_id=caller.user_id, **values)
        o.refresh_from_db()
        _event(
            uow,
            "update",
            o,
            before=before,
            after={**_state_view(o), "changed": sorted(values)},
            event="commercial.order.draft_changed",
        )
    return o


def add_line(
    caller: Caller,
    order_id: uuid.UUID,
    *,
    expected_version: int,
    style_id: uuid.UUID,
    quantity: int,
    style_revision_id: uuid.UUID | None = None,
    product_code_id: uuid.UUID | None = None,
    requested_due_date: date | None = None,
    request_id: uuid.UUID | None = None,
) -> CustomerOrderLine:
    """A line of a DRAFT order: one style; unit = the product type's unit (DEC-058); ``line_no`` = next free
    number (never re-used, removed lines keep theirs)."""
    authorize(caller, ORDER_MANAGE)
    qty = valid_quantity(quantity)
    with unit_of_work(caller.context(request_id)) as uow:
        o = _draft(order_id, expected_version)
        rev = style_revision_id or _active_revision_of(style_id)
        s = _check_line_master(style_id, rev, product_code_id)
        due = line_due(requested_due_date, o.order_date)
        last = (
            CustomerOrderLine.objects.filter(order=o)
            .order_by("-line_no")
            .values_list("line_no", flat=True)
            .first()
            or 0
        )
        with db_rules():
            ln = CustomerOrderLine.objects.create(
                order=o,
                line_no=last + 1,
                style_id=s.pk,
                style_revision_id=rev,
                product_code_id=product_code_id,
                quantity=qty,
                uom_id=s.product.product_type.uom_id,
                requested_due_date=due,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
            )
        _touch(o, caller)
        _event(
            uow,
            "line_add",
            o,
            before=None,
            after={**_state_view(o), "line_id": str(ln.pk), "line_no": ln.line_no},
            event="commercial.order.draft_changed",
        )
    return ln


def _draft_line(line_id: uuid.UUID, expected_version: int) -> tuple[CustomerOrder, CustomerOrderLine]:
    ln = CustomerOrderLine.objects.filter(pk=line_id).first()
    if ln is None:
        raise NotFound()
    o = _draft(ln.order_id, expected_version)
    ln = lock(CustomerOrderLine, line_id)
    if ln.status != L.OPEN:
        refuse(Reason.STATE_NOT_ALLOWED, field="line", detail="only an OPEN line is edited")
    return o, ln


def update_line(
    caller: Caller,
    line_id: uuid.UUID,
    *,
    expected_version: int,
    changes: Mapping[str, Any],
    request_id: uuid.UUID | None = None,
) -> CustomerOrderLine:
    """``expected_version`` = the order's row version (the order ETag covers its lines)."""
    authorize(caller, ORDER_MANAGE)
    allowed = {"quantity", "style_revision_id", "product_code_id", "requested_due_date"}
    if not changes or set(changes) - allowed:
        refuse(Reason.INVALID, field=sorted(set(changes) - allowed or {""})[0])
    with unit_of_work(caller.context(request_id)) as uow:
        o, ln = _draft_line(line_id, expected_version)
        values: dict[str, Any] = {}
        if "quantity" in changes:
            values["quantity"] = valid_quantity(changes["quantity"])
        if "requested_due_date" in changes:
            values["requested_due_date"] = line_due(changes["requested_due_date"], o.order_date)
        rev = changes.get("style_revision_id", ln.style_revision_id)
        code = changes.get("product_code_id", ln.product_code_id)
        _check_line_master(ln.style_id, rev, code)
        if "style_revision_id" in changes:
            values["style_revision_id"] = rev
        if "product_code_id" in changes:
            values["product_code_id"] = code
        with db_rules():
            CustomerOrderLine.objects.filter(pk=ln.pk).update(updated_by_id=caller.user_id, **values)
        _touch(o, caller)
        _event(
            uow,
            "line_update",
            o,
            before=None,
            after={**_state_view(o), "line_id": str(ln.pk), "changed": sorted(values)},
            event="commercial.order.draft_changed",
        )
        ln.refresh_from_db()
    return ln


def remove_line(
    caller: Caller, line_id: uuid.UUID, *, expected_version: int, request_id: uuid.UUID | None = None
) -> CustomerOrderLine:
    authorize(caller, ORDER_MANAGE)
    with unit_of_work(caller.context(request_id)) as uow:
        o, ln = _draft_line(line_id, expected_version)
        LINE_MACHINE.assert_transition(ln.status, L.REMOVED)
        with db_rules():
            CustomerOrderLine.objects.filter(pk=ln.pk).update(status=L.REMOVED, updated_by_id=caller.user_id)
        _touch(o, caller)
        _event(
            uow,
            "line_remove",
            o,
            before=None,
            after={**_state_view(o), "line_id": str(ln.pk)},
            event="commercial.order.draft_changed",
        )
        ln.refresh_from_db()
    return ln


# ----------------------------------------------------------------------------------------- transitions
def _open_lines(o: CustomerOrder) -> list[CustomerOrderLine]:
    return list(
        CustomerOrderLine.objects.select_for_update().filter(order=o, status=L.OPEN).order_by("line_no")
    )


def _check_ready(o: CustomerOrder, lines: list[CustomerOrderLine]) -> None:
    _customer(o.customer_id)
    _brand(o.brand_id, o.customer_id)
    _order_type(o.order_type_id)
    if not lines:
        refuse(Reason.ORDER_HAS_NO_LINES, field="lines")
    for ln in lines:
        _check_line_master(ln.style_id, ln.style_revision_id, ln.product_code_id)


def validate_order(
    caller: Caller,
    order_id: uuid.UUID,
    *,
    expected_version: int,
    acknowledge_warnings: Iterable[str] = (),
    request_id: uuid.UUID | None = None,
) -> CustomerOrder:
    authorize(caller, ORDER_MANAGE)
    acks = acknowledged(acknowledge_warnings, [WARN_DUPLICATE_PO])
    with unit_of_work(caller.context(request_id)) as uow:
        o = lock(CustomerOrder, order_id)
        check_version(o, expected_version)
        assert_order_transition(o, O.VALIDATED)
        _check_ready(o, _open_lines(o))
        duplicates = duplicate_po_orders(o)
        if duplicates and WARN_DUPLICATE_PO not in acks:
            refuse(
                Reason.DUPLICATE_PO_NUMBER,
                field="external_po_number",
                detail="this customer PO number exists",
            )
        before = _state_view(o)
        with db_rules():
            CustomerOrder.objects.filter(pk=o.pk).update(status=O.VALIDATED, updated_by_id=caller.user_id)
        o.refresh_from_db()
        _event(
            uow,
            "validate",
            o,
            before=before,
            scope={"acknowledged_warnings": [WARN_DUPLICATE_PO] if duplicates else []},
            event="commercial.order.validated",
        )
    return o


def reopen_order(
    caller: Caller,
    order_id: uuid.UUID,
    *,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> CustomerOrder:
    authorize(caller, ORDER_MANAGE)
    text = reason_text(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        o = lock(CustomerOrder, order_id)
        check_version(o, expected_version)
        if o.status != O.VALIDATED:
            refuse(Reason.STATE_NOT_ALLOWED, field="status")
        assert_order_transition(o, O.DRAFT)
        before = _state_view(o)
        with db_rules():
            CustomerOrder.objects.filter(pk=o.pk).update(status=O.DRAFT, updated_by_id=caller.user_id)
        o.refresh_from_db()
        _event(uow, "reopen", o, before=before, reason=text, event="commercial.order.reopened")
    return o


def cancel_unconfirmed_order(
    caller: Caller,
    order_id: uuid.UUID,
    *,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> CustomerOrder:
    """DRAFT / VALIDATED -> CANCELLED (nothing allocated yet). A confirmed order is cancelled only through a
    ``CANCEL_ORDER`` change request (DEC-059)."""
    authorize(caller, ORDER_MANAGE)
    text = reason_text(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        o = lock(CustomerOrder, order_id)
        check_version(o, expected_version)
        if o.status not in (O.DRAFT, O.VALIDATED):
            refuse(
                Reason.STATE_NOT_ALLOWED,
                field="status",
                detail="a confirmed order is cancelled by a change request",
            )
        assert_order_transition(o, O.CANCELLED)
        before = _state_view(o)
        with db_rules():
            CustomerOrder.objects.filter(pk=o.pk).update(
                status=O.CANCELLED, cancel_reason=text, cancelled_at=Now(), updated_by_id=caller.user_id
            )
        o.refresh_from_db()
        _event(uow, "cancel", o, before=before, reason=text, event="commercial.order.cancelled")
    return o


def allocation_key(order_id: uuid.UUID, line_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(ALLOCATION_NAMESPACE, f"line:{order_id}:{line_id}")


def allocate_for_line(
    uow: UnitOfWork, o: CustomerOrder, ln: CustomerOrderLine, *, version: int, by: uuid.UUID
) -> Serial:
    """Identity draws the serial of one line (snapshot v1 = the line at ``version``)."""
    result = allocate_serial(
        uow,
        AllocationRequest(
            idempotency_key=allocation_key(o.pk, ln.pk),
            allocated_by=by,
            customer_id=o.customer_id,
            style_id=ln.style_id,
            style_revision_id=ln.style_revision_id,
            product_code_id=ln.product_code_id,
            order_version=version,
            snapshot={**line_snapshot(o, ln, version), "status": L.CONFIRMED.value},
        ),
    )
    return result.serial


def confirm_order(
    caller: Caller, order_id: uuid.UUID, *, expected_version: int, request_id: uuid.UUID | None = None
) -> CustomerOrder:
    decision = authorize(caller, ORDER_CONFIRM)
    with unit_of_work(caller.context(request_id)) as uow:
        o = lock(CustomerOrder, order_id)
        check_version(o, expected_version)
        if o.created_by_id == caller.user_id:
            refuse(
                Reason.CONFIRMER_IS_CREATOR, field="order", detail="the creator of an order never confirms it"
            )
        assert_order_transition(o, O.CONFIRMED)
        lines = _open_lines(o)
        _check_ready(o, lines)
        before = _state_view(o)
        serials: list[str] = []
        for ln in lines:
            serial = allocate_for_line(uow, o, ln, version=1, by=caller.user_id)
            LINE_MACHINE.assert_transition(ln.status, L.CONFIRMED)
            with db_rules():
                CustomerOrderLine.objects.filter(pk=ln.pk).update(
                    status=L.CONFIRMED, serial_id=serial.pk, order_version=1, updated_by_id=caller.user_id
                )
            serials.append(str(serial.pk))
        with db_rules():
            CustomerOrder.objects.filter(pk=o.pk).update(
                status=O.CONFIRMED,
                current_version=1,
                confirmed_by_id=caller.user_id,
                confirmed_at=Now(),
                updated_by_id=caller.user_id,
            )
            o.refresh_from_db()
            confirmed_lines = list(CustomerOrderLine.objects.filter(order=o).order_by("line_no"))
            CustomerOrderVersion.objects.create(
                order=o,
                version=1,
                image=order_image(o, confirmed_lines),
                reason=VersionReason.CONFIRMED,
                created_by_id=caller.user_id,
            )
        _event(
            uow,
            "confirm",
            o,
            before=before,
            after={**_state_view(o), "lines": len(lines)},
            scope={"via_role": decision.grant.role_code if decision.grant else "", "serial_ids": serials},
            event="commercial.order.confirmed",
            payload={
                "id": str(o.pk),
                "status": o.status,
                "version": o.current_version,
                "line_count": len(lines),
            },
        )
    return o


def release_order(
    caller: Caller, order_id: uuid.UUID, *, expected_version: int, request_id: uuid.UUID | None = None
) -> CustomerOrder:
    authorize(caller, ORDER_RELEASE)
    with unit_of_work(caller.context(request_id)) as uow:
        o = lock(CustomerOrder, order_id)
        check_version(o, expected_version)
        assert_order_transition(o, O.RELEASED_TO_PLAN)
        if not CustomerOrderLine.objects.filter(order=o, status=L.CONFIRMED).exists():
            refuse(Reason.ORDER_HAS_NO_LINES, field="lines")
        before = _state_view(o)
        with db_rules():
            CustomerOrder.objects.filter(pk=o.pk).update(
                status=O.RELEASED_TO_PLAN,
                released_by_id=caller.user_id,
                released_at=Now(),
                updated_by_id=caller.user_id,
            )
        o.refresh_from_db()
        _event(uow, "release", o, before=before, event="commercial.order.released")
    return o
