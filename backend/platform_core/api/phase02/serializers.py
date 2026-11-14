"""PHASE_02 response bodies (contract 0.8.0-draft). Every function returns exactly the properties of its
OpenAPI schema (response-schema validation in the API tests). Dates are ISO calendar dates (Gregorian),
instants UTC.

Personal data: the order's ``customer_representative_name`` (DEC-058) is produced only by
:func:`customer_order` from the engine's ``get_order`` view (masked ``[REDACTED]`` for management_viewer,
every unmasked read audited); write responses never carry it in clear (:data:`REDACTED` when one is
recorded), so the value is never stored in an idempotency record or replayed.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Final

from django.db.models import Max

from platform_core.commercial.models import (
    CustomerOrder,
    CustomerOrderLine,
    CustomerOrderVersion,
    OrderChangeRequest,
)
from platform_core.engine.redaction import REDACTED
from platform_core.product_identity.models import (
    CodeRuleRevision,
    Customer,
    CustomerBrand,
    ExternalRef,
    HistoricalOrderRecord,
    Product,
    ProductClass,
    ProductCode,
    Serial,
    SerialSnapshot,
    Style,
    StyleRevision,
    StyleRevisionStatus,
)

from ..phase01.common import sid, utc, utc_req

UNAVAILABLE: Final = [
    {"section": "materials", "phase": "PHASE_06"},
    {"section": "wip", "phase": "PHASE_07"},
    {"section": "production", "phase": "PHASE_07"},
    {"section": "quality", "phase": "PHASE_08"},
    {"section": "dispatch", "phase": "PHASE_09"},
    {"section": "capacity", "phase": "PHASE_05"},
    {"section": "cost", "phase": "PHASE_10"},
]
ATTRIBUTE_KEYS: Final = ("colour_fa", "main_material_fa", "lining_fa", "hardware_colour_fa", "notes_fa")


def _d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def provenance(obj: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "provenance_kind": obj.provenance_kind,
        "import_batch_id": sid(obj.import_batch_id),
    }
    for key in ("source_sheet", "source_cell_ref", "transform_rule_version"):
        value = getattr(obj, key, "")
        if value:
            out[key] = value
    return out


def attributes(raw: Mapping[str, Any] | None) -> dict[str, str]:
    """The contract's attribute keys only (other text keys stay in the record, not in this view)."""
    return {k: v for k, v in (raw or {}).items() if k in ATTRIBUTE_KEYS and isinstance(v, str) and v}


# ----------------------------------------------------------------------------------------------- identity
def customer(c: Customer) -> dict[str, Any]:
    return {
        "customer_id": str(c.pk),
        "customer_no": c.customer_no,
        "display_name_fa": c.display_name_fa,
        "legal_name_fa": c.legal_name_fa,
        "status": c.status,
        "default_required_quality_ref": c.default_required_quality_ref,
        "provenance": provenance(c),
        "row_version": c.row_version,
        "created_at": utc_req(c.created_at),
        "updated_at": utc_req(c.updated_at),
    }


def brand(b: CustomerBrand) -> dict[str, Any]:
    return {
        "brand_id": str(b.pk),
        "customer_id": str(b.customer_id),
        "brand_name_fa": b.brand_name_fa,
        "status": b.status,
        "row_version": b.row_version,
    }


def product_class(c: ProductClass) -> dict[str, Any]:
    return {
        "product_class_id": str(c.pk),
        "parent_class_id": sid(c.parent_id),
        "level_key": c.level_key,
        "label_fa": c.label_fa,
        "segment_value": c.segment_value,
        "uom": c.uom_id,
        "product_no_scheme": c.product_no_scheme,
        "status": c.status,
        "provenance": provenance(c),
        "row_version": c.row_version,
    }


def product(p: Product) -> dict[str, Any]:
    t = p.product_type
    return {
        "product_id": str(p.pk),
        "product_class_id": str(p.product_type_id),
        "product_no": p.product_no,
        "name_fa": p.name_fa,
        "uom": t.uom_id,
        "buckle_type_code": p.buckle_type_code,
        "belt_width_code": p.belt_width_code,
        "status": p.status,
        "provenance": provenance(p),
        "row_version": p.row_version,
        "created_at": utc_req(p.created_at),
        "updated_at": utc_req(p.updated_at),
    }


def style(s: Style) -> dict[str, Any]:
    current = (
        StyleRevision.objects.filter(style_id=s.pk, status=StyleRevisionStatus.ACTIVE)
        .values_list("pk", flat=True)
        .first()
    )
    return {
        "style_id": str(s.pk),
        "product_id": str(s.product_id),
        "category_id": str(s.category_id),
        "style_no": s.style_no,
        "name_fa": s.name_fa,
        "current_revision_id": sid(current),
        "status": s.status,
        "provenance": provenance(s),
        "row_version": s.row_version,
        "created_at": utc_req(s.created_at),
        "updated_at": utc_req(s.updated_at),
    }


def style_revision(r: StyleRevision) -> dict[str, Any]:
    return {
        "style_revision_id": str(r.pk),
        "style_id": str(r.style_id),
        "revision_no": r.revision_no,
        "attributes": attributes(r.attributes),
        "status": r.status,
        "technical_package_revision_id": sid(r.technical_package_revision_id),
        "created_at": utc_req(r.created_at),
        "row_version": r.row_version,
    }


def product_code(pc: ProductCode) -> dict[str, Any]:
    return {
        "product_code_id": str(pc.pk),
        "code": pc.code,
        "code_namespace": pc.code_namespace,
        "style_id": sid(pc.style_id),
        "rule_revision_id": sid(pc.rule_revision_id),
        "status": pc.status,
        "erp_status": pc.erp_status,
        "provenance": provenance(pc),
        "issued_at": utc(pc.issued_at),
        "row_version": pc.row_version,
    }


def code_rule(r: CodeRuleRevision) -> dict[str, Any]:
    return {
        "rule_revision_id": str(r.pk),
        "code_namespace": r.code_namespace,
        "revision_no": r.revision_no,
        "scope": r.scope,
        "rule_spec": r.rule_spec,
        "source_workbook_sha256": r.source_workbook_sha256,
        "evidence_document_id": sid(r.evidence_document_id),
        "golden_case_count": r.golden_case_count,
        "status": r.status,
        "decision_id": r.decision_id,
        "created_by": sid(r.created_by_id),
        "approved_by": sid(r.approved_by_id),
        "approved_at": utc(r.approved_at),
        "row_version": r.row_version,
    }


def _code_of(pk: Any) -> str | None:
    if pk is None:
        return None
    return ProductCode.objects.filter(pk=pk).values_list("code", flat=True).first()


def _line_of(serial: Serial) -> CustomerOrderLine | None:
    return CustomerOrderLine.objects.filter(serial_id=serial.pk).first()


def serial(s: Serial) -> dict[str, Any]:
    ln = _line_of(s)
    code = _code_of(s.product_code_id)
    last = SerialSnapshot.objects.filter(serial_id=s.pk).aggregate(m=Max("version"))["m"] or 1
    return {
        "serial_id": str(s.pk),
        "serial_number": s.serial_number,
        "serial_namespace": s.serial_counter.namespace_key,
        "order_id": sid(ln.order_id if ln else None),
        "order_line_id": sid(ln.pk if ln else None),
        "line_no": ln.line_no if ln else None,
        "customer_id": str(s.customer_id),
        "style_id": str(s.style_id),
        "style_revision_id": str(s.style_revision_id),
        "product_code": code,
        "status": s.status,
        "current_snapshot_version": last,
        "allocated_at": utc_req(s.allocated_at),
        "row_version": s.row_version,
    }


def serial_summary(s: Serial) -> dict[str, Any]:
    ln = _line_of(s)
    rev = StyleRevision.objects.filter(pk=s.style_revision_id).values_list("attributes", flat=True).first()
    return {
        "serial_id": str(s.pk),
        "serial_number": s.serial_number,
        "status": s.status,
        "customer_id": str(s.customer_id),
        "order_id": sid(ln.order_id if ln else None),
        "line_no": ln.line_no if ln else None,
        "quantity": ln.quantity if ln else None,
        "uom": ln.uom_id if ln else None,
        "attributes": attributes(rev),
        "allocated_at": utc_req(s.allocated_at),
    }


SNAPSHOT_KEYS: Final = (
    "order_id",
    "order_no",
    "order_status",
    "customer_id",
    "order_version",
    "line_id",
    "line_no",
    "status",
    "style_id",
    "style_revision_id",
    "product_code",
    "quantity",
    "uom",
    "requested_due_date",
    "serial_id",
)


def snapshot(snap: SerialSnapshot) -> dict[str, Any]:
    image = snap.snapshot if isinstance(snap.snapshot, dict) else {}
    return {
        "serial_id": str(snap.serial_id),
        "version": snap.version,
        "reason": snap.reason,
        "order_version": snap.order_version,
        "change_request_id": sid(snap.change_request_id),
        "created_at": utc_req(snap.created_at),
        "snapshot": {k: image[k] for k in SNAPSHOT_KEYS if k in image},
    }


def external_ref(r: ExternalRef) -> dict[str, Any]:
    return {
        "external_ref_id": str(r.pk),
        "target_type": r.target_type,
        "target_id": str(r.target_id),
        "system": r.system,
        "namespace": r.ref_type_id,
        "value": r.value,
        "valid_from": utc_req(r.valid_from),
        "valid_to": utc(r.valid_to),
        "provenance": provenance(r),
        "row_version": r.row_version,
    }


def historical(h: HistoricalOrderRecord) -> dict[str, Any]:
    return {
        "record_id": str(h.pk),
        "import_batch_id": sid(h.import_batch_id),
        "legacy_order_ref": h.legacy_order_ref or None,
        "legacy_serial_ref": h.legacy_serial_text,
        "legacy_serial_duplicate": h.legacy_serial_duplicate,
        "legacy_product_code_raw": h.legacy_product_code_raw,
        "normalised_product_code": h.normalised_product_code,
        "code_flag": h.code_flag,
        "match_status": h.match_status,
        "matched_style_id": sid(h.matched_style_id),
        "matched_product_code_id": sid(h.matched_product_code_id),
        "matched_serial_id": None,
        "matched_at": utc(h.matched_at),
        "provenance": provenance(h),
    }


# --------------------------------------------------------------------------------------------- commercial
def order_line(ln: CustomerOrderLine) -> dict[str, Any]:
    code = _code_of(ln.product_code_id)
    number = (
        Serial.objects.filter(pk=ln.serial_id).values_list("serial_number", flat=True).first()
        if ln.serial_id
        else None
    )
    return {
        "line_id": str(ln.pk),
        "line_no": ln.line_no,
        "style_id": str(ln.style_id),
        "style_revision_id": str(ln.style_revision_id),
        "product_code_id": sid(ln.product_code_id),
        "product_code": code,
        "quantity": ln.quantity,
        "uom": ln.uom_id,
        "requested_due_date": _d(ln.requested_due_date),
        "status": ln.status,
        "serial_id": sid(ln.serial_id),
        "serial_number": number,
        "order_version": ln.order_version,
        "row_version": ln.row_version,
    }


def customer_order(o: CustomerOrder, *, representative: str | None) -> dict[str, Any]:
    """``representative``: the value the caller may see (engine ``get_order``) or :data:`REDACTED`."""
    lines = CustomerOrderLine.objects.filter(order=o).order_by("line_no")
    return {
        "order_id": str(o.pk),
        "order_no": o.order_no,
        "customer_id": str(o.customer_id),
        "brand_id": sid(o.brand_id),
        "external_po_number": o.external_po_number or None,
        "order_type": o.order_type_id,
        "program_ref": o.program_ref,
        "order_date": o.order_date.isoformat(),
        "requested_due_date": _d(o.requested_due_date),
        "required_quality_requirement": o.required_quality_requirement,
        "customer_representative_name": representative,
        "status": o.status,
        "status_before_hold": o.status_before_hold,
        "hold_reason": o.hold_reason,
        "cancel_reason": o.cancel_reason,
        "current_version": o.current_version,
        "lines": [order_line(ln) for ln in lines],
        "row_version": o.row_version,
        "created_at": utc_req(o.created_at),
        "updated_at": utc_req(o.updated_at),
    }


def written_order(o: CustomerOrder) -> dict[str, Any]:
    """Write responses: a recorded representative name is never echoed (read it with getCustomerOrder)."""
    o.refresh_from_db()
    return customer_order(o, representative=REDACTED if o.customer_representative_name else None)


def order_summary(o: CustomerOrder) -> dict[str, Any]:
    return {
        "order_id": str(o.pk),
        "order_no": o.order_no,
        "customer_id": str(o.customer_id),
        "external_po_number": o.external_po_number or None,
        "order_type": o.order_type_id,
        "status": o.status,
        "order_date": o.order_date.isoformat(),
        "requested_due_date": _d(o.requested_due_date),
        "current_version": o.current_version,
        "line_count": CustomerOrderLine.objects.filter(order=o).exclude(status="REMOVED").count(),
        "row_version": o.row_version,
    }


def version_summary(v: CustomerOrderVersion) -> dict[str, Any]:
    return {
        "order_id": str(v.order_id),
        "version": v.version,
        "reason": v.reason,
        "change_request_id": sid(v.change_request_id),
        "created_at": utc_req(v.created_at),
    }


def version(v: CustomerOrderVersion) -> dict[str, Any]:
    return {**version_summary(v), "created_by": sid(v.created_by_id), "image": v.image}


def change_request(cr: OrderChangeRequest) -> dict[str, Any]:
    return {
        "change_request_id": str(cr.pk),
        "request_no": cr.request_no,
        "order_id": str(cr.order_id),
        "base_order_version": cr.base_order_version,
        "kind": cr.kind,
        "items": cr.items,
        "reason": cr.reason,
        "status": cr.status,
        "requested_by": sid(cr.requested_by_id),
        "submitted_at": utc(cr.submitted_at),
        "decided_by": sid(cr.decided_by_id),
        "decided_at": utc(cr.decided_at),
        "planning_required": cr.kind == "DUE_DATE_CHANGE",
        "planning_approved_by": sid(cr.planning_approved_by_id),
        "planning_approved_at": utc(cr.planning_approved_at),
        "planning_rejected_by": sid(cr.planning_rejected_by_id),
        "planning_rejected_at": utc(cr.planning_rejected_at),
        "applied_version": cr.applied_version,
        "row_version": cr.row_version,
        "created_at": utc_req(cr.created_at),
    }


def impact(cr: OrderChangeRequest, data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "change_request_id": str(cr.pk),
        "base_order_version": cr.base_order_version,
        "lines_affected": list(data["lines"]),
        "serials_affected": list(data["serials"]),
        "new_lines": int(data["new_lines"]),
        "snapshots_to_write": len(data["serials"]),
        "unavailable_sections": UNAVAILABLE,
    }
