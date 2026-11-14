"""Order change requests (PHASE_02 / 02.3; DEC-059 + amendment 2026-11-12, STATE_TRANSITIONS 5.5).

A confirmed order is never edited in place. Every change is a change request (CR)::

    create (DRAFT or SUBMITTED)  commercial.change.request  (commercial_officer, planning_officer)
    submit  DRAFT -> SUBMITTED   the requester
    withdraw DRAFT/SUBMITTED -> WITHDRAWN   the requester
    decide  SUBMITTED -> APPROVED / REJECTED  commercial.change.decide (commercial_manager, or the owner
                                  directly; business approval + fresh MFA); never the requester (DEC-057)
    planning decision (DUE_DATE_CHANGE only)  commercial.change.planning_approve (planning_officer,
                                  fresh MFA) - approve OR reject (amendment 2026-11-14; one permission for
                                  both); a rejection needs a reason and closes the request REJECTED (the old
                                  due date stays); a person different from the requester AND from the deciding
                                  manager (amendment 2026-11-12; DB CHECKs, migrations 0023 / 0025)
    apply   APPROVED -> APPLIED  commercial.change.apply (planning_officer): base version still current,
                                  writes order version n+1 (image) and the next serial snapshot of every line
                                  it touches - in one unit of work

Kinds (DEC-059): QTY_CHANGE (the line keeps its serial), DUE_DATE_CHANGE (header and/or lines), ADD_LINE (a
new line with a new serial), CANCEL_LINE / CANCEL_ORDER (before release only, C-A; the serial becomes
CANCELLED and is never re-used), HOLD (single ON_HOLD with the stored previous state) and RESUME.
After release only DUE_DATE_CHANGE / HOLD / RESUME. A held order whose stored state is CONFIRMED may be
cancelled directly (CANCEL_ORDER / CANCEL_LINE, amendment 2026-11-12); quantity, due date and new lines on a
held order are not decided and are refused (``ORDER_ON_HOLD``). Not decided and therefore NOT enforced
(REV-0203): one open CR per order, a CR expiry period. Concurrent CRs on the same base are safe: the first
applied one moves the version, every other one is then ``STALE_BASE_VERSION`` (re-submit).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Final

from django.db.models.functions import Now

from platform_core.authz.policy import Caller
from platform_core.engine.dbrules import db_rules
from platform_core.engine.errors import NotFound
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import UnitOfWork, unit_of_work
from platform_core.product_identity.refusals import Reason, refuse
from platform_core.product_identity.serials import add_snapshot, cancel_serial
from platform_core.product_identity.usecase import (
    authorize,
    check_version,
    lock,
    next_number,
    reason_text,
    uuid_or_refuse,
)

from . import orders as ord_
from .models import (
    AFTER_RELEASE_KINDS,
    ChangeKind,
    ChangeStatus,
    CustomerOrder,
    CustomerOrderLine,
    CustomerOrderVersion,
    LineStatus,
    OrderChangeRequest,
    OrderStatus,
    VersionReason,
)

CHANGE_READ: Final = "commercial.change.read"
CHANGE_REQUEST: Final = "commercial.change.request"
CHANGE_DECIDE: Final = "commercial.change.decide"
CHANGE_PLANNING_APPROVE: Final = "commercial.change.planning_approve"
CHANGE_APPLY: Final = "commercial.change.apply"
RESOURCE: Final = "commercial.change_request"
K, C, O, L = ChangeKind, ChangeStatus, OrderStatus, LineStatus  # noqa: E741 - short state aliases
ORDER_LEVEL_KINDS: Final = frozenset({K.CANCEL_ORDER, K.HOLD, K.RESUME})
HELD_ALLOWED_KINDS: Final = frozenset({K.RESUME, K.CANCEL_ORDER, K.CANCEL_LINE})
MAX_ITEMS: Final = 200

CHANGE_MACHINE: Final = StateMachine(
    name="commercial.change_request",
    states=frozenset(ChangeStatus.values),
    transitions={
        C.DRAFT: frozenset({C.SUBMITTED, C.WITHDRAWN}),
        # EXPIRED is reserved: no expiry period is decided (REV-0203), the engine never writes it
        C.SUBMITTED: frozenset({C.APPROVED, C.REJECTED, C.WITHDRAWN, C.EXPIRED}),
        # APPROVED -> REJECTED: only a planning rejection of a due-date change (amendment 2026-11-14)
        C.APPROVED: frozenset({C.APPLIED, C.EXPIRED, C.REJECTED}),
        C.REJECTED: frozenset(),
        C.APPLIED: frozenset(),
        C.WITHDRAWN: frozenset(),
        C.EXPIRED: frozenset(),
    },
)


# -------------------------------------------------------------------------------------------- helpers
def _view(cr: OrderChangeRequest) -> dict[str, Any]:
    return {
        "request_no": cr.request_no,
        "order_id": str(cr.order_id),
        "kind": cr.kind,
        "status": cr.status,
        "base_order_version": cr.base_order_version,
        "planning_approved": cr.planning_approved_by_id is not None,
        "planning_rejected": cr.planning_rejected_by_id is not None,
    }


def _event(
    uow: UnitOfWork,
    verb: str,
    past: str,
    cr: OrderChangeRequest,
    *,
    before: Mapping[str, Any] | None,
    reason: str = "",
    scope: Mapping[str, Any] | None = None,
) -> None:
    uow.audit(
        action=f"commercial.change_request.{verb}",
        resource_type=RESOURCE,
        resource_id=str(cr.pk),
        resource_version=cr.row_version,
        before=before,
        after=_view(cr),
        reason=reason,
        scope=scope,
    )
    uow.emit(
        event_type=f"commercial.change_request.{past}",
        aggregate_type=RESOURCE,
        aggregate_id=str(cr.pk),
        aggregate_version=cr.row_version,
        payload={"id": str(cr.pk), "order_id": str(cr.order_id), "kind": cr.kind, "status": cr.status},
    )


def _iso(value: Any, field: str) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    refuse(Reason.INVALID, field=field)


def check_kind_allowed(o: CustomerOrder, kind: str) -> None:
    """DEC-059 (+ amendment 2026-11-12): which kinds a CR may have in the order's current state."""
    if kind not in K.values:
        refuse(Reason.INVALID, field="kind")
    if o.status not in (O.CONFIRMED, O.RELEASED_TO_PLAN, O.ON_HOLD):
        refuse(
            Reason.STATE_NOT_ALLOWED, field="order", detail="change requests exist only for confirmed orders"
        )
    if ord_.is_released(o) and kind not in AFTER_RELEASE_KINDS:
        if kind in (K.CANCEL_LINE, K.CANCEL_ORDER):
            refuse(
                Reason.CANCEL_AFTER_RELEASE, field="kind", detail="cancel after release waits for PHASE_05"
            )
        refuse(
            Reason.RELEASED_KIND_NOT_ALLOWED, field="kind", detail="after release: due date and hold/resume"
        )
    if kind == K.HOLD and o.status == O.ON_HOLD:
        refuse(Reason.ORDER_ALREADY_ON_HOLD, field="kind")
    if kind == K.RESUME and o.status != O.ON_HOLD:
        refuse(Reason.ORDER_NOT_ON_HOLD, field="kind")
    if o.status == O.ON_HOLD and kind not in HELD_ALLOWED_KINDS:
        refuse(Reason.ORDER_ON_HOLD, field="kind", detail="not decided for a held order; resume it first")


def _live_lines(o: CustomerOrder) -> dict[str, CustomerOrderLine]:
    return {str(ln.pk): ln for ln in CustomerOrderLine.objects.filter(order=o, status=L.CONFIRMED)}


def _line_ref(raw: Mapping[str, Any], live: Mapping[str, CustomerOrderLine], i: int) -> CustomerOrderLine:
    lid = str(uuid_or_refuse(raw.get("line_id"), field=f"items[{i}].line_id"))
    ln = live.get(lid)
    if ln is None:
        refuse(Reason.LINE_NOT_IN_ORDER, field=f"items[{i}].line_id")
    return ln


def normalise_items(o: CustomerOrder, kind: str, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validated, JSON-ready items of one kind against the order as it is now."""
    if not isinstance(items, Sequence) or isinstance(items, str | bytes) or len(items) > MAX_ITEMS:
        refuse(Reason.INVALID, field="items")
    if kind in ORDER_LEVEL_KINDS:
        if items:
            refuse(Reason.ITEMS_NOT_ALLOWED, field="items")
        return []
    if not items:
        refuse(Reason.REQUIRED, field="items")
    live = _live_lines(o)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, raw in enumerate(items):
        if not isinstance(raw, Mapping):
            refuse(Reason.INVALID, field=f"items[{i}]")
        if kind == K.QTY_CHANGE:
            ln = _line_ref(raw, live, i)
            qty = ord_.valid_quantity(raw.get("quantity"), field=f"items[{i}].quantity")
            if qty == ln.quantity:
                refuse(Reason.QUANTITY_UNCHANGED, field=f"items[{i}].quantity")
            key, item = str(ln.pk), {"line_id": str(ln.pk), "quantity": qty}
        elif kind == K.DUE_DATE_CHANGE:
            due = _iso(raw.get("requested_due_date"), f"items[{i}].requested_due_date")
            if due < o.order_date:
                refuse(Reason.DUE_BEFORE_ORDER_DATE, field=f"items[{i}].requested_due_date")
            if raw.get("line_id") is None:
                if due == o.requested_due_date:
                    refuse(Reason.DUE_DATE_UNCHANGED, field=f"items[{i}].requested_due_date")
                key, item = "header", {"line_id": None, "requested_due_date": due.isoformat()}
            else:
                ln = _line_ref(raw, live, i)
                if due == ln.requested_due_date:
                    refuse(Reason.DUE_DATE_UNCHANGED, field=f"items[{i}].requested_due_date")
                key, item = str(ln.pk), {"line_id": str(ln.pk), "requested_due_date": due.isoformat()}
        elif kind == K.CANCEL_LINE:
            ln = _line_ref(raw, live, i)
            key, item = str(ln.pk), {"line_id": str(ln.pk)}
        else:  # ADD_LINE
            style_id = uuid_or_refuse(raw.get("style_id"), field=f"items[{i}].style_id")
            rev = raw.get("style_revision_id")
            rev_id = (
                uuid_or_refuse(rev, field=f"items[{i}].style_revision_id")
                if rev
                else ord_._active_revision_of(style_id)
            )
            code = raw.get("product_code_id")
            code_id = uuid_or_refuse(code, field=f"items[{i}].product_code_id") if code else None
            ord_._check_line_master(style_id, rev_id, code_id)
            qty = ord_.valid_quantity(raw.get("quantity"), field=f"items[{i}].quantity")
            due_raw = raw.get("requested_due_date")
            due_s = None
            if due_raw is not None:
                due_d = _iso(due_raw, f"items[{i}].requested_due_date")
                ord_.line_due(due_d, o.order_date, field=f"items[{i}].requested_due_date")
                due_s = due_d.isoformat()
            key = f"add:{i}"
            item = {
                "style_id": str(style_id),
                "style_revision_id": str(rev_id),
                "product_code_id": str(code_id) if code_id else None,
                "quantity": qty,
                "requested_due_date": due_s,
            }
        if key in seen:
            refuse(Reason.DUPLICATE_ITEM, field=f"items[{i}]")
        seen.add(key)
        out.append(item)
    if kind == K.CANCEL_LINE and len(seen) >= len(live):
        # cancelling every live line is not decided as "cancel the order": the employer chose CANCEL_ORDER
        refuse(Reason.LAST_LINE_CANCEL, field="items", detail="use CANCEL_ORDER to cancel every line")
    return out


def impact_of(o: CustomerOrder, kind: str, items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PHASE_02 part of the impact (lines and serials touched); other modules are not available yet."""
    live = _live_lines(o)
    if kind in ORDER_LEVEL_KINDS or (
        kind == K.DUE_DATE_CHANGE and any(i.get("line_id") is None for i in items)
    ):
        touched = list(live.values())
    else:
        touched = [live[i["line_id"]] for i in items if i.get("line_id") in live]
    return {
        "lines": sorted(str(ln.pk) for ln in touched),
        "serials": sorted(str(ln.serial_id) for ln in touched if ln.serial_id),
        "new_lines": sum(1 for _ in items) if kind == K.ADD_LINE else 0,
        "other_modules": "NOT_AVAILABLE_IN_PHASE_02",
    }


# ----------------------------------------------------------------------------------------- use cases
def create_change_request(
    caller: Caller,
    order_id: uuid.UUID,
    *,
    kind: str,
    items: Sequence[Mapping[str, Any]],
    reason: str,
    expected_version: int,
    submit: bool = False,
    request_id: uuid.UUID | None = None,
) -> OrderChangeRequest:
    """``expected_version`` = the order's row version the requester saw."""
    authorize(caller, CHANGE_REQUEST)
    text = reason_text(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        o = lock(CustomerOrder, order_id)
        check_version(o, expected_version)
        check_kind_allowed(o, kind)
        norm = normalise_items(o, kind, items)
        with db_rules():
            cr = OrderChangeRequest.objects.create(
                request_no=next_number("change_request"),
                order=o,
                base_order_version=o.current_version,
                kind=kind,
                items=norm,
                reason=text,
                status=C.SUBMITTED if submit else C.DRAFT,
                submitted_at=Now() if submit else None,
                impact=impact_of(o, kind, norm) if submit else None,
                requested_by_id=caller.user_id,
            )
        cr.refresh_from_db()
        _event(uow, "create", "created", cr, before=None, reason=text)
        if submit:
            _event(uow, "submit", "submitted", cr, before=None)
    return cr


def _requester_only(caller: Caller, cr: OrderChangeRequest) -> None:
    if cr.requested_by_id != caller.user_id:
        raise NotFound()  # only the requester submits / withdraws (an other person's request: not found)


def submit_change_request(
    caller: Caller, cr_id: uuid.UUID, *, expected_version: int, request_id: uuid.UUID | None = None
) -> OrderChangeRequest:
    authorize(caller, CHANGE_REQUEST)
    with unit_of_work(caller.context(request_id)) as uow:
        cr = lock(OrderChangeRequest, cr_id)
        _requester_only(caller, cr)
        check_version(cr, expected_version)
        CHANGE_MACHINE.assert_transition(cr.status, C.SUBMITTED)
        o = CustomerOrder.objects.get(pk=cr.order_id)
        if o.current_version != cr.base_order_version:
            refuse(Reason.STALE_BASE_VERSION, field="base_order_version")
        check_kind_allowed(o, cr.kind)
        before = _view(cr)
        with db_rules():
            OrderChangeRequest.objects.filter(pk=cr.pk).update(
                status=C.SUBMITTED, submitted_at=Now(), impact=impact_of(o, cr.kind, cr.items)
            )
        cr.refresh_from_db()
        _event(uow, "submit", "submitted", cr, before=before)
    return cr


def withdraw_change_request(
    caller: Caller,
    cr_id: uuid.UUID,
    *,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> OrderChangeRequest:
    authorize(caller, CHANGE_REQUEST)
    text = reason_text(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        cr = lock(OrderChangeRequest, cr_id)
        _requester_only(caller, cr)
        check_version(cr, expected_version)
        CHANGE_MACHINE.assert_transition(cr.status, C.WITHDRAWN)
        before = _view(cr)
        OrderChangeRequest.objects.filter(pk=cr.pk).update(status=C.WITHDRAWN)
        cr.refresh_from_db()
        _event(uow, "withdraw", "withdrawn", cr, before=before, reason=text)
    return cr


def decide_change_request(
    caller: Caller,
    cr_id: uuid.UUID,
    *,
    approve: bool,
    expected_version: int,
    note: str = "",
    request_id: uuid.UUID | None = None,
) -> OrderChangeRequest:
    decision = authorize(caller, CHANGE_DECIDE)
    text = note.strip()[:500] if approve else reason_text(note, field="note")
    with unit_of_work(caller.context(request_id)) as uow:
        cr = lock(OrderChangeRequest, cr_id)
        check_version(cr, expected_version)
        if cr.requested_by_id == caller.user_id:
            refuse(Reason.DECIDER_IS_REQUESTER, field="change_request")
        if cr.planning_approved_by_id == caller.user_id:
            refuse(Reason.DECIDER_IS_PLANNING_APPROVER, field="change_request")
        target = C.APPROVED if approve else C.REJECTED
        if cr.status != C.SUBMITTED:  # the manager decides a submitted request once
            refuse(Reason.STATE_NOT_ALLOWED, field="status")
        CHANGE_MACHINE.assert_transition(cr.status, target)
        before = _view(cr)
        with db_rules():
            OrderChangeRequest.objects.filter(pk=cr.pk).update(
                status=target, decided_by_id=caller.user_id, decided_at=Now()
            )
        cr.refresh_from_db()
        _event(
            uow,
            "decide",
            "decided",
            cr,
            before=before,
            reason=text,
            scope={"via_role": decision.grant.role_code if decision.grant else "", "approved": approve},
        )
    return cr


def planning_decide_change_request(
    caller: Caller,
    cr_id: uuid.UUID,
    *,
    approve: bool,
    expected_version: int,
    note: str = "",
    request_id: uuid.UUID | None = None,
) -> OrderChangeRequest:
    """DEC-059: the second decision on a due-date change, by planning (before or after the manager's
    decision, never by the requester or the deciding manager). Approve: the request may be applied once the
    manager approved it too. Reject (amendment 2026-11-14): a reason is required, the request closes REJECTED
    and the order keeps its due date. Permission ``commercial.change.planning_approve`` covers both."""
    decision = authorize(caller, CHANGE_PLANNING_APPROVE)
    text = note.strip()[:500] if approve else reason_text(note, field="note")
    with unit_of_work(caller.context(request_id)) as uow:
        cr = lock(OrderChangeRequest, cr_id)
        check_version(cr, expected_version)
        if cr.kind != K.DUE_DATE_CHANGE:
            refuse(Reason.PLANNING_APPROVAL_NOT_APPLICABLE, field="kind")
        if cr.requested_by_id == caller.user_id:
            refuse(Reason.PLANNING_APPROVER_IS_REQUESTER, field="change_request")
        if cr.decided_by_id == caller.user_id:
            refuse(Reason.PLANNING_APPROVER_IS_DECIDER, field="change_request")
        if cr.status not in (C.SUBMITTED, C.APPROVED):
            refuse(Reason.STATE_NOT_ALLOWED, field="status")
        if cr.planning_approved_by_id is not None:
            refuse(Reason.PLANNING_ALREADY_APPROVED, field="change_request")
        before = _view(cr)
        with db_rules():
            if approve:
                OrderChangeRequest.objects.filter(pk=cr.pk).update(
                    planning_approved_by_id=caller.user_id, planning_approved_at=Now()
                )
            else:
                CHANGE_MACHINE.assert_transition(cr.status, C.REJECTED)
                OrderChangeRequest.objects.filter(pk=cr.pk).update(
                    status=C.REJECTED, planning_rejected_by_id=caller.user_id, planning_rejected_at=Now()
                )
        cr.refresh_from_db()
        verb, past = (
            ("planning_approve", "planning_approved") if approve else ("planning_reject", "planning_rejected")
        )
        _event(
            uow,
            verb,
            past,
            cr,
            before=before,
            reason=text,
            scope={"via_role": decision.grant.role_code if decision.grant else "", "approved": approve},
        )
    return cr


def planning_approve_change_request(
    caller: Caller,
    cr_id: uuid.UUID,
    *,
    expected_version: int,
    note: str = "",
    request_id: uuid.UUID | None = None,
) -> OrderChangeRequest:
    """The approve half of :func:`planning_decide_change_request` (02.3 name, kept for callers)."""
    return planning_decide_change_request(
        caller, cr_id, approve=True, expected_version=expected_version, note=note, request_id=request_id
    )


def _snapshot_lines(
    uow: UnitOfWork, o: CustomerOrder, line_ids: Sequence[uuid.UUID], *, version: int, cr: OrderChangeRequest
) -> None:
    for ln in CustomerOrderLine.objects.filter(pk__in=list(line_ids)).order_by("line_no"):
        if ln.serial_id is not None:
            add_snapshot(
                uow,
                ln.serial_id,
                snapshot=ord_.line_snapshot(o, ln, version),
                order_version=version,
                change_request_id=cr.pk,
            )


def apply_change_request(
    caller: Caller, cr_id: uuid.UUID, *, expected_version: int, request_id: uuid.UUID | None = None
) -> OrderChangeRequest:
    authorize(caller, CHANGE_APPLY)
    with unit_of_work(caller.context(request_id)) as uow:
        cr = lock(OrderChangeRequest, cr_id)
        check_version(cr, expected_version)
        CHANGE_MACHINE.assert_transition(cr.status, C.APPLIED)
        if cr.kind == K.DUE_DATE_CHANGE and cr.planning_approved_by_id is None:
            refuse(Reason.PLANNING_APPROVAL_REQUIRED, field="change_request")
        o = lock(CustomerOrder, cr.order_id)
        if o.current_version != cr.base_order_version:
            refuse(
                Reason.STALE_BASE_VERSION,
                field="base_order_version",
                detail="re-submit on the current version",
            )
        check_kind_allowed(o, cr.kind)  # the order may have been released / held since the request
        new_v = o.current_version + 1
        order_before = ord_._state_view(o)
        live = {
            str(ln.pk): ln
            for ln in CustomerOrderLine.objects.select_for_update().filter(order=o, status=L.CONFIRMED)
        }
        items: list[dict[str, Any]] = list(cr.items)
        header: dict[str, Any] = {"current_version": new_v, "updated_by_id": caller.user_id}
        touched: list[uuid.UUID] = []
        to_cancel: list[CustomerOrderLine] = []
        if cr.kind == K.HOLD:
            ord_.assert_order_transition(o, O.ON_HOLD)
            header.update(status=O.ON_HOLD, status_before_hold=o.status, hold_reason=cr.reason)
            touched = [ln.pk for ln in live.values()]
        elif cr.kind == K.RESUME:
            ord_.assert_order_transition(o, str(o.status_before_hold))
            header.update(status=o.status_before_hold, status_before_hold=None, hold_reason=None)
            touched = [ln.pk for ln in live.values()]
        elif cr.kind == K.CANCEL_ORDER:
            ord_.assert_order_transition(o, O.CANCELLED)
            header.update(
                status=O.CANCELLED,
                cancel_reason=cr.reason,
                cancelled_at=Now(),
                status_before_hold=None,
                hold_reason=None,
            )
            to_cancel = list(live.values())
        elif cr.kind == K.DUE_DATE_CHANGE:
            for it in items:
                if it["line_id"] is None:
                    header["requested_due_date"] = date.fromisoformat(it["requested_due_date"])
                    touched = [ln.pk for ln in live.values()]
        elif cr.kind == K.CANCEL_LINE:
            missing = [it["line_id"] for it in items if it["line_id"] not in live]
            if missing:
                refuse(Reason.LINE_NOT_IN_ORDER, field="items")
            to_cancel = [live[it["line_id"]] for it in items]
            if len(to_cancel) >= len(live):
                refuse(Reason.LAST_LINE_CANCEL, field="items")
        with db_rules():
            CustomerOrder.objects.filter(pk=o.pk).update(**header)
        o.refresh_from_db()
        with db_rules():
            if cr.kind in (K.QTY_CHANGE, K.DUE_DATE_CHANGE):
                for it in items:
                    if it.get("line_id") is None:
                        continue
                    ln = live.get(it["line_id"])
                    if ln is None:
                        refuse(Reason.LINE_NOT_IN_ORDER, field="items")
                    values: dict[str, Any] = {"order_version": new_v, "updated_by_id": caller.user_id}
                    if cr.kind == K.QTY_CHANGE:
                        values["quantity"] = it["quantity"]  # DEC-059: the line keeps its serial
                    else:
                        values["requested_due_date"] = date.fromisoformat(it["requested_due_date"])
                    CustomerOrderLine.objects.filter(pk=ln.pk).update(**values)
                    if ln.pk not in touched:
                        touched.append(ln.pk)
            for ln in to_cancel:
                ord_.LINE_MACHINE.assert_transition(ln.status, L.CANCELLED)
                CustomerOrderLine.objects.filter(pk=ln.pk).update(
                    status=L.CANCELLED,
                    cancel_reason=cr.reason,
                    order_version=new_v,
                    updated_by_id=caller.user_id,
                )
                touched.append(ln.pk)
        _snapshot_lines(uow, o, touched, version=new_v, cr=cr)
        for ln in to_cancel:
            assert ln.serial_id is not None
            cancel_serial(uow, ln.serial_id, reason=cr.reason)
        if cr.kind == K.ADD_LINE:
            last = (
                CustomerOrderLine.objects.filter(order=o)
                .order_by("-line_no")
                .values_list("line_no", flat=True)
                .first()
                or 0
            )
            for n, it in enumerate(items, start=1):
                style_id = uuid.UUID(it["style_id"])
                rev_id = uuid.UUID(it["style_revision_id"])
                code_id = uuid.UUID(it["product_code_id"]) if it.get("product_code_id") else None
                s = ord_._check_line_master(style_id, rev_id, code_id)
                ln = CustomerOrderLine(
                    id=uuid.uuid4(),
                    order=o,
                    line_no=last + n,
                    style_id=style_id,
                    style_revision_id=rev_id,
                    product_code_id=code_id,
                    quantity=it["quantity"],
                    uom_id=s.product.product_type.uom_id,
                    requested_due_date=date.fromisoformat(it["requested_due_date"])
                    if it.get("requested_due_date")
                    else None,
                    status=L.CONFIRMED,
                    order_version=new_v,
                    created_by_id=caller.user_id,
                    updated_by_id=caller.user_id,
                )
                serial = ord_.allocate_for_line(uow, o, ln, version=new_v, by=caller.user_id)
                ln.serial_id = serial.pk
                with db_rules():
                    ln.save(force_insert=True)
        all_lines = list(CustomerOrderLine.objects.filter(order=o).order_by("line_no"))
        with db_rules():
            CustomerOrderVersion.objects.create(
                order=o,
                version=new_v,
                image=ord_.order_image(o, all_lines),
                reason=VersionReason.CANCELLED if cr.kind == K.CANCEL_ORDER else VersionReason.CHANGE_APPLIED,
                change_request=cr,
                created_by_id=caller.user_id,
            )
            OrderChangeRequest.objects.filter(pk=cr.pk).update(
                status=C.APPLIED, applied_by_id=caller.user_id, applied_at=Now(), applied_version=new_v
            )
        cr_before = _view(cr)
        cr.refresh_from_db()
        _event(uow, "apply", "applied", cr, before=cr_before, scope={"order_version": new_v})
        uow.audit(
            action="commercial.order.change_apply",
            resource_type=ord_.RESOURCE,
            resource_id=str(o.pk),
            resource_version=o.row_version,
            before=order_before,
            after={**ord_._state_view(o), "kind": cr.kind, "lines_touched": len(touched)},
            reason=cr.reason,
            scope={"change_request_id": str(cr.pk)},
        )
        uow.emit(
            event_type="commercial.order.changed",
            aggregate_type=ord_.RESOURCE,
            aggregate_id=str(o.pk),
            aggregate_version=o.row_version,
            payload={
                "id": str(o.pk),
                "status": o.status,
                "version": new_v,
                "change_request_id": str(cr.pk),
                "kind": cr.kind,
            },
        )
        if cr.kind == K.CANCEL_ORDER:
            uow.emit(
                event_type="commercial.order.cancelled",
                aggregate_type=ord_.RESOURCE,
                aggregate_id=str(o.pk),
                aggregate_version=o.row_version,
                payload={"id": str(o.pk), "status": o.status, "version": new_v},
            )
    return cr


def get_change_request(caller: Caller, cr_id: uuid.UUID) -> dict[str, Any]:
    authorize(caller, CHANGE_READ)
    cr = OrderChangeRequest.objects.filter(pk=cr_id).first()
    if cr is None:
        raise NotFound()
    return {
        **_view(cr),
        "id": str(cr.pk),
        "items": cr.items,
        "impact": cr.impact,
        "reason": cr.reason,
        "requested_by": str(cr.requested_by_id),
        "decided_by": str(cr.decided_by_id) if cr.decided_by_id else None,
        "planning_approved_by": str(cr.planning_approved_by_id) if cr.planning_approved_by_id else None,
        "planning_rejected_by": str(cr.planning_rejected_by_id) if cr.planning_rejected_by_id else None,
        "applied_version": cr.applied_version,
        "row_version": cr.row_version,
    }
