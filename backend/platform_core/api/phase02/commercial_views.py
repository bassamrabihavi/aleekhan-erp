"""``/commercial/...`` endpoints (PHASE_02 / 02.4) over the 02.3 use cases (``commercial.orders`` /
``commercial.changes``).

* The order's ``ETag`` is its ``row_version``; it covers the lines (every line edit touches the order row), so
  line operations send the ORDER's ``If-Match``.
* ``confirmCustomerOrder`` (planning_officer / owner, fresh MFA, confirmer != creator) allocates every
  line's serial in the same transaction (DEC-006 L-A); of two concurrent confirms with the same ``If-Match``
  exactly one succeeds, the other answers 412 (the version moved) - never a second serial.
* Representative name (DEC-058, PII): ``getCustomerOrder`` returns it from the engine's ``get_order`` (masked
  ``[REDACTED]`` for management_viewer; every unmasked read audited). Lists and write responses never carry it
  in clear, so it is never stored in an idempotency record, an access log or a replay.
* ``createChangeRequest`` carries the order's row version in the body (``order_row_version``: the version the
  requester saw); the request's own ``ETag`` / ``If-Match`` drive submit / withdraw / decide / planning
  decision / apply.
* ``decidePlanningChangeRequest`` (02.4, DEC-059 amendments 2026-11-12 / 2026-11-14): planning approves OR
  rejects a due-date change (permission ``commercial.change.planning_approve`` for both, fresh MFA); a
  rejection needs a note and closes the request REJECTED.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.authz.policy import Caller
from platform_core.commercial import changes, orders
from platform_core.commercial.models import (
    ChangeKind,
    ChangeStatus,
    CustomerOrder,
    CustomerOrderLine,
    CustomerOrderVersion,
    OrderChangeRequest,
    OrderStatus,
)
from platform_core.engine.errors import FieldError, NotFound, ValidationFailed
from platform_core.engine.idempotency import StoredResponse
from platform_core.product_identity.refusals import Reason

from ..phase01.common import (
    body_of,
    etag_response,
    if_match,
    paginate,
    query_choice,
    query_uuid,
    stored,
    write,
)
from . import serializers as S
from .common import Phase02View, apply_search, object_or_404, scoped

ORDER_READ: Final = "commercial.order.read"
ORDER_MANAGE: Final = "commercial.order.manage"
ORDER_CONFIRM: Final = "commercial.order.confirm"
ORDER_RELEASE: Final = "commercial.order.release"
CHANGE_READ: Final = "commercial.change.read"
CHANGE_REQUEST: Final = "commercial.change.request"
CHANGE_DECIDE: Final = "commercial.change.decide"
CHANGE_PLANNING: Final = "commercial.change.planning_approve"
CHANGE_APPLY: Final = "commercial.change.apply"
HEADER_KEYS: Final = (
    "brand_id",
    "external_po_number",
    "order_type",
    "program_ref",
    "order_date",
    "requested_due_date",
    "required_quality_requirement",
    "customer_representative_name",
)


def _order_written(o: CustomerOrder) -> StoredResponse:
    return stored(200, S.written_order(o), etag_version=CustomerOrder.objects.get(pk=o.pk).row_version)


# ----------------------------------------------------------------------------------------------- orders
class CustomerOrdersView(Phase02View):
    required_action = ORDER_READ
    write_action = ORDER_MANAGE

    def get(self, request: Request) -> Response:
        qs = scoped(self, CustomerOrder.objects.all())
        customer = query_uuid(request, "customer_id")
        if customer is not None:
            qs = qs.filter(customer_id=customer)
        po = request.query_params.get("external_po_number")
        if po is not None:
            if not 1 <= len(po) <= 64:
                raise ValidationFailed(errors=[FieldError("external_po_number", "PATTERN_MISMATCH")])
            qs = qs.filter(external_po_number__iexact=po)
        status = query_choice(request, "status", OrderStatus.values)
        if status:
            qs = qs.filter(status=status)
        qs = apply_search(request, qs, "order_no", "external_po_number")
        return paginate(request, self, qs, S.order_summary, ordering="-order_no")

    def post(self, request: Request) -> Response:
        data = body_of(request, "CustomerOrderCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            header = {k: data[k] for k in HEADER_KEYS if k in data and k not in ("order_type", "order_date")}
            o = orders.create_order(
                caller,
                customer_id=data["customer_id"],
                order_type=data["order_type"],
                order_date=data["order_date"],
                request_id=rid,
                **header,
            )
            out = _order_written(o)
            return StoredResponse(201, out.body, out.headers)

        return write(self, run)


class CustomerOrderView(Phase02View):
    required_action = ORDER_READ
    write_action = ORDER_MANAGE

    def get(self, request: Request, order_id: uuid.UUID) -> Response:
        o = object_or_404(self, CustomerOrder.objects.all(), order_id)
        view = orders.get_order(self.caller(), o.pk, request_id=self.rid())  # masking + read audit (DEC-058)
        o.refresh_from_db()
        return etag_response(
            S.customer_order(o, representative=view["customer_representative_name"]), o.row_version
        )

    def patch(self, request: Request, order_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "CustomerOrderUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            o = orders.update_order(
                caller, order_id, expected_version=expected, changes=dict(data), request_id=rid
            )
            return _order_written(o)

        return write(self, run)


def _line_of(order_id: uuid.UUID, line_id: uuid.UUID) -> None:
    if not CustomerOrderLine.objects.filter(pk=line_id, order_id=order_id).exists():
        raise NotFound()


class CustomerOrderLinesView(Phase02View):
    required_action = ORDER_MANAGE

    def post(self, request: Request, order_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "CustomerOrderLineCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            ln = orders.add_line(
                caller,
                order_id,
                expected_version=expected,
                style_id=data["style_id"],
                quantity=data["quantity"],
                style_revision_id=data.get("style_revision_id"),
                product_code_id=data.get("product_code_id"),
                requested_due_date=data.get("requested_due_date"),
                request_id=rid,
            )
            out = _order_written(CustomerOrder.objects.get(pk=ln.order_id))
            return StoredResponse(201, out.body, out.headers)

        return write(self, run)


class CustomerOrderLineView(Phase02View):
    required_action = ORDER_MANAGE

    def patch(self, request: Request, order_id: uuid.UUID, line_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "CustomerOrderLineUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            _line_of(order_id, line_id)
            orders.update_line(caller, line_id, expected_version=expected, changes=dict(data), request_id=rid)
            return _order_written(CustomerOrder.objects.get(pk=order_id))

        return write(self, run)


class RemoveCustomerOrderLineView(Phase02View):
    required_action = ORDER_MANAGE

    def post(self, request: Request, order_id: uuid.UUID, line_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "ReasonRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            _line_of(order_id, line_id)
            orders.remove_line(
                caller, line_id, expected_version=expected, reason=data["reason"], request_id=rid
            )
            return _order_written(CustomerOrder.objects.get(pk=order_id))

        return write(self, run)


def _order_action(action: str, schema: str, call: Any) -> type[Phase02View]:
    class _View(Phase02View):
        required_action = action

        def post(self, request: Request, order_id: uuid.UUID) -> Response:
            expected = if_match(self)
            data = body_of(request, schema)

            def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
                return _order_written(call(caller, order_id, expected, data, rid))

            return write(self, run)

    return _View


ValidateCustomerOrderView = _order_action(
    ORDER_MANAGE,
    "CustomerOrderValidateRequest",
    lambda c, pk, v, d, rid: orders.validate_order(
        c,
        pk,
        expected_version=v,
        acknowledge_warnings=[Reason.DUPLICATE_PO_NUMBER.value]
        if d.get("acknowledge_possible_duplicate")
        else [],
        request_id=rid,
    ),
)
ReopenCustomerOrderView = _order_action(
    ORDER_MANAGE,
    "ReasonRequest",
    lambda c, pk, v, d, rid: orders.reopen_order(
        c, pk, expected_version=v, reason=d["reason"], request_id=rid
    ),
)
CancelCustomerOrderView = _order_action(
    ORDER_MANAGE,
    "ReasonRequest",
    lambda c, pk, v, d, rid: orders.cancel_unconfirmed_order(
        c, pk, expected_version=v, reason=d["reason"], request_id=rid
    ),
)
ConfirmCustomerOrderView = _order_action(
    ORDER_CONFIRM,
    "OptionalNoteRequest",
    lambda c, pk, v, d, rid: orders.confirm_order(c, pk, expected_version=v, request_id=rid),
)
ReleaseCustomerOrderView = _order_action(
    ORDER_RELEASE,
    "OptionalNoteRequest",
    lambda c, pk, v, d, rid: orders.release_order(c, pk, expected_version=v, request_id=rid),
)


class CustomerOrderVersionsView(Phase02View):
    required_action = ORDER_READ

    def get(self, request: Request, order_id: uuid.UUID) -> Response:
        o = object_or_404(self, CustomerOrder.objects.all(), order_id)
        qs = CustomerOrderVersion.objects.filter(order=o)
        return paginate(request, self, qs, S.version_summary, ordering="version")


class CustomerOrderVersionView(Phase02View):
    required_action = ORDER_READ

    def get(self, request: Request, order_id: uuid.UUID, order_version: int) -> Response:
        o = object_or_404(self, CustomerOrder.objects.all(), order_id)
        v = CustomerOrderVersion.objects.filter(order=o, version=order_version).first()
        if v is None:
            raise NotFound()
        return Response(S.version(v), headers={"Cache-Control": "no-store"})


# -------------------------------------------------------------------------------------- change requests
class ChangeRequestsView(Phase02View):
    required_action = CHANGE_READ
    write_action = CHANGE_REQUEST

    def get(self, request: Request) -> Response:
        qs = scoped(self, OrderChangeRequest.objects.all())
        order = query_uuid(request, "order_id")
        if order is not None:
            qs = qs.filter(order_id=order)
        serial = query_uuid(request, "serial_id")
        if serial is not None:
            orders_of = CustomerOrderLine.objects.filter(serial_id=serial).values("order_id")
            qs = qs.filter(order_id__in=orders_of)
        kind = query_choice(request, "kind", ChangeKind.values)
        if kind:
            qs = qs.filter(kind=kind)
        status = query_choice(request, "status", ChangeStatus.values)
        if status:
            qs = qs.filter(status=status)
        return paginate(request, self, qs, S.change_request, ordering="-request_no")

    def post(self, request: Request) -> Response:
        data = body_of(request, "ChangeRequestCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            cr = changes.create_change_request(
                caller,
                data["order_id"],
                kind=data["kind"],
                items=list(data.get("items") or []),
                reason=data["reason"],
                expected_version=data["order_row_version"],
                submit=bool(data.get("submit", False)),
                request_id=rid,
            )
            return stored(201, S.change_request(cr), etag_version=cr.row_version)

        return write(self, run)


class ChangeRequestView(Phase02View):
    required_action = CHANGE_READ

    def get(self, request: Request, change_request_id: uuid.UUID) -> Response:
        cr = object_or_404(self, OrderChangeRequest.objects.all(), change_request_id)
        return etag_response(S.change_request(cr), cr.row_version)


class ChangeRequestImpactView(Phase02View):
    required_action = CHANGE_READ

    def get(self, request: Request, change_request_id: uuid.UUID) -> Response:
        cr = object_or_404(self, OrderChangeRequest.objects.all(), change_request_id)
        data = cr.impact
        if data is None:  # a DRAFT has no stored impact yet: computed now, nothing written
            data = changes.impact_of(CustomerOrder.objects.get(pk=cr.order_id), cr.kind, cr.items)
        return etag_response(S.impact(cr, data), cr.row_version)


def _cr_action(action: str, schema: str, call: Any) -> type[Phase02View]:
    class _View(Phase02View):
        required_action = action

        def post(self, request: Request, change_request_id: uuid.UUID) -> Response:
            expected = if_match(self)
            data = body_of(request, schema)

            def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
                cr = call(caller, change_request_id, expected, data, rid)
                return stored(200, S.change_request(cr), etag_version=cr.row_version)

            return write(self, run)

    return _View


SubmitChangeRequestView = _cr_action(
    CHANGE_REQUEST,
    "OptionalNoteRequest",
    lambda c, pk, v, d, rid: changes.submit_change_request(c, pk, expected_version=v, request_id=rid),
)
WithdrawChangeRequestView = _cr_action(
    CHANGE_REQUEST,
    "ReasonRequest",
    lambda c, pk, v, d, rid: changes.withdraw_change_request(
        c, pk, expected_version=v, reason=d["reason"], request_id=rid
    ),
)
DecideChangeRequestView = _cr_action(
    CHANGE_DECIDE,
    "ChangeRequestDecisionRequest",
    lambda c, pk, v, d, rid: changes.decide_change_request(
        c, pk, approve=d["decision"] == "APPROVE", expected_version=v, note=d.get("note", ""), request_id=rid
    ),
)
PlanningDecideChangeRequestView = _cr_action(
    CHANGE_PLANNING,
    "ChangeRequestDecisionRequest",
    lambda c, pk, v, d, rid: changes.planning_decide_change_request(
        c, pk, approve=d["decision"] == "APPROVE", expected_version=v, note=d.get("note", ""), request_id=rid
    ),
)
ApplyChangeRequestView = _cr_action(
    CHANGE_APPLY,
    "OptionalNoteRequest",
    lambda c, pk, v, d, rid: changes.apply_change_request(c, pk, expected_version=v, request_id=rid),
)
