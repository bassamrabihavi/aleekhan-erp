"""PHASE_02 request bodies (contract 0.8.0-draft, step 02.4) as field specs of the shared validator.

They mirror the OpenAPI request schemas exactly (``additionalProperties: false``; a contract test compares
field names, required sets and constraints with docs/api/openapi-draft.yaml). They are registered in the
shared ``BODIES`` table so nested specs (``StyleAttributes``, ``ChangeRequestItem``, golden cases) resolve.
"""

from __future__ import annotations

from typing import Final

from ..phase01.common import BODIES, REASON, F

SYSTEM_KEY: Final = r"^[a-z][a-z0-9_]{2,63}$"
TWO: Final = r"^[0-9]{2}$"
FOUR: Final = r"^[0-9]{4}$"
CODE14: Final = r"^[0-9]{14}$"
SHA256: Final = r"^[0-9a-f]{64}$"
PARTY_STATUSES: Final = ("ACTIVE", "INACTIVE")
MASTER_STATUSES: Final = ("DRAFT", "ACTIVE", "RETIRED")
TARGET_TYPES: Final = ("customer", "product", "style", "customer_order", "order_line", "serial")
SYSTEMS: Final = ("RAHKARAN", "CUSTOMER", "LEGACY_PLANNING", "OTHER")
CR_KINDS: Final = (
    "QTY_CHANGE",
    "DUE_DATE_CHANGE",
    "ADD_LINE",
    "CANCEL_LINE",
    "CANCEL_ORDER",
    "HOLD",
    "RESUME",
)
NAME200: Final = F("str", min_len=1, max_len=200)
NAME200_REQ: Final = F("str", required=True, min_len=1, max_len=200)
TEXT64_NULL: Final = F("str", nullable=True, max_len=64)
ACK: Final = F("bool")
SEGMENT2_NULL: Final = F("str", nullable=True, pattern=TWO)
ATTR: Final = F("str", min_len=1, max_len=200)

PHASE02_BODIES: Final[dict[str, dict[str, F]]] = {
    # ------------------------------------------------------------------------------------- identity
    "CustomerCreateRequest": {
        "display_name_fa": NAME200_REQ,
        "legal_name_fa": F("str", nullable=True, max_len=300),
        "default_required_quality_ref": TEXT64_NULL,
        "acknowledge_possible_duplicate": ACK,
    },
    "CustomerUpdateRequest": {
        "display_name_fa": NAME200,
        "legal_name_fa": F("str", nullable=True, max_len=300),
        "status": F("str", choices=PARTY_STATUSES),
        "default_required_quality_ref": TEXT64_NULL,
        "acknowledge_possible_duplicate": ACK,
        "reason": REASON,
    },
    "CustomerBrandCreateRequest": {"brand_name_fa": NAME200_REQ},
    "CustomerBrandUpdateRequest": {
        "status": F("str", required=True, choices=PARTY_STATUSES),
        "reason": REASON,
    },
    "ProductCreateRequest": {
        "product_class_id": F("uuid", required=True),
        "name_fa": NAME200_REQ,
        "buckle_type_code": SEGMENT2_NULL,
        "belt_width_code": SEGMENT2_NULL,
    },
    "ProductUpdateRequest": {"status": F("str", required=True, choices=MASTER_STATUSES), "reason": REASON},
    "StyleAttributes": {
        "colour_fa": ATTR,
        "main_material_fa": ATTR,
        "lining_fa": ATTR,
        "hardware_colour_fa": ATTR,
        "notes_fa": F("str", min_len=1, max_len=500),
    },
    "StyleCreateRequest": {
        "category_id": F("uuid", required=True),
        "name_fa": NAME200_REQ,
        "initial_attributes": F("obj", nested="StyleAttributes"),
    },
    "StyleUpdateRequest": {"status": F("str", required=True, choices=MASTER_STATUSES), "reason": REASON},
    "StyleRevisionCreateRequest": {
        "attributes": F("obj", required=True, nested="StyleAttributes"),
        "reason": REASON,
    },
    "ProductCodeValidateRequest": {
        "code": F("str", required=True, max_len=64),
        "code_namespace": F("str", required=True, choices=("product_code", "die_code")),
    },
    "ProductCodePreviewRequest": {
        "style_id": F("uuid"),
        "product_class_id": F("uuid"),
        "category_id": F("uuid"),
        "product_id": F("uuid"),
        "buckle_type_code": SEGMENT2_NULL,
        "belt_width_code": SEGMENT2_NULL,
    },
    "ProductCodeIssueRequest": {"style_id": F("uuid", required=True), "rule_revision_id": F("uuid")},
    "CodeRuleRevisionCreateRequest": {
        "product_type_codes": F(
            "strlist", required=True, min_items=1, max_items=99, item_pattern=TWO, item_max_len=2
        ),
        "source_workbook_sha256": F("str", required=True, pattern=SHA256),
        "evidence_document_id": F("uuid", nullable=True),
        "reason": REASON,
    },
    "GoldenCaseInputs": {
        "type_code": F("str", required=True, pattern=TWO),
        "category_code": F("str", required=True, pattern=TWO),
        "product_no": F("str", required=True, pattern=FOUR),
        "style_no": F("str", required=True, pattern=FOUR),
        "buckle_type_code": F("str", pattern=TWO),
        "belt_width_code": F("str", pattern=TWO),
        "category_code_order_form": F("str", pattern=TWO),
        "belt_width_source": F("str", min_len=1, max_len=200),
        "legacy_disputed": F("str", min_len=3, max_len=500),
    },
    "GoldenCase": {
        "inputs": F("obj", required=True, nested="GoldenCaseInputs"),
        "expected_code": F("str", required=True, min_len=14, max_len=14, pattern=CODE14),
        "source_sheet": F("str", required=True, min_len=1, max_len=100),
        "source_cell_ref": F("str", required=True, min_len=1, max_len=32),
    },
    "GoldenCasesAddRequest": {
        "cases": F("objlist", required=True, nested="GoldenCase", min_items=1, max_items=2000),
    },
    "SerialAllocateRequest": {
        "order_line_id": F("uuid", required=True),
        "order_line_row_version": F("int", required=True, minimum=1),
    },
    "ExternalRefCreateRequest": {
        "target_type": F("str", required=True, choices=TARGET_TYPES),
        "target_id": F("uuid", required=True),
        "system": F("str", required=True, choices=SYSTEMS),
        "namespace": F("str", required=True, pattern=SYSTEM_KEY),
        "value": F("str", required=True, min_len=1, max_len=64),
        "reason": REASON,
    },
    # ----------------------------------------------------------------------------------- commercial
    "CustomerOrderCreateRequest": {
        "customer_id": F("uuid", required=True),
        "brand_id": F("uuid", nullable=True),
        "external_po_number": TEXT64_NULL,
        "order_type": F("str", required=True, pattern=SYSTEM_KEY),
        "program_ref": TEXT64_NULL,
        "order_date": F("date", required=True),
        "requested_due_date": F("date", nullable=True),
        "required_quality_requirement": TEXT64_NULL,
        "customer_representative_name": F("str", nullable=True, max_len=200),
    },
    "CustomerOrderUpdateRequest": {
        "brand_id": F("uuid", nullable=True),
        "external_po_number": TEXT64_NULL,
        "order_type": F("str", pattern=SYSTEM_KEY),
        "program_ref": TEXT64_NULL,
        "order_date": F("date"),
        "requested_due_date": F("date", nullable=True),
        "required_quality_requirement": TEXT64_NULL,
        "customer_representative_name": F("str", nullable=True, max_len=200),
    },
    "CustomerOrderLineCreateRequest": {
        "style_id": F("uuid", required=True),
        "style_revision_id": F("uuid"),
        "product_code_id": F("uuid", nullable=True),
        "quantity": F("int", required=True, minimum=1),
        "requested_due_date": F("date", nullable=True),
    },
    "CustomerOrderLineUpdateRequest": {
        "style_revision_id": F("uuid"),
        "product_code_id": F("uuid", nullable=True),
        "quantity": F("int", minimum=1),
        "requested_due_date": F("date", nullable=True),
    },
    "CustomerOrderValidateRequest": {"note": F("str", max_len=500), "acknowledge_possible_duplicate": ACK},
    "ChangeRequestItem": {
        "line_id": F("uuid", nullable=True),
        "quantity": F("int", minimum=1),
        "requested_due_date": F("date"),
        "style_id": F("uuid"),
        "style_revision_id": F("uuid"),
        "product_code_id": F("uuid", nullable=True),
    },
    "ChangeRequestCreateRequest": {
        "order_id": F("uuid", required=True),
        "order_row_version": F("int", required=True, minimum=1),
        "kind": F("str", required=True, choices=CR_KINDS),
        "items": F("objlist", nested="ChangeRequestItem", max_items=200),
        "reason": REASON,
        "submit": F("bool"),
    },
    "ChangeRequestDecisionRequest": {
        "decision": F("str", required=True, choices=("APPROVE", "REJECT")),
        "note": F("str", max_len=500),
    },
}

_shared = set(PHASE02_BODIES) & set(BODIES)
assert not _shared, f"PHASE_02 body specs must not shadow PHASE_01 specs: {sorted(_shared)}"
BODIES.update(PHASE02_BODIES)
