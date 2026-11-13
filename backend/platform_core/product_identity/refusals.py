"""Stable refusal reasons of the PHASE_02 engine (02.3), shared by the Identity and Commercial modules.

PHASE_01 style (docs/engine/ERROR_CODES.md): the top-level ``code`` of an error is one of the stable
catalogue codes of ``engine/errors.py`` (no new top-level code, so the OpenAPI ``ErrorCode`` enum is
unchanged); the precise reason is the machine code in ``errors[].code``. Every reason below is bound to
exactly one top-level code (golden: ``tests/golden/phase02_refusals.golden.json``). Clients branch on
``code`` first and may branch on ``errors[].code``; Persian texts may change, the codes may not.

``detail`` texts are generic: never a customer name, a representative name, a code value or a serial.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final, NoReturn

from platform_core.engine.errors import (
    AleekhanError,
    ErrorCode,
    FieldError,
    IdempotencyKeyReused,
    RuleNotApproved,
    SelfApprovalForbidden,
    StateTransitionNotAllowed,
    ValidationFailed,
)


class Reason(StrEnum):
    # --- input (400 VALIDATION_FAILED)
    REQUIRED = "REQUIRED"
    INVALID = "INVALID"
    SEGMENT_FORMAT = "SEGMENT_FORMAT"  # a code segment is not the right number of digits
    CODE_FORMAT = "CODE_FORMAT"  # not 14 digits / not the product prefix "02"
    STYLE_0000_LEGACY_ONLY = "STYLE_0000_LEGACY_ONLY"  # DEC-005 amendment 2026-11-13: never issued
    BELT_SEGMENTS_REQUIRED = "BELT_SEGMENTS_REQUIRED"  # belt type without buckle/width (DEC-005)
    BELT_SEGMENTS_NOT_ALLOWED = "BELT_SEGMENTS_NOT_ALLOWED"  # buckle/width for a non-belt type
    PRODUCT_NO_EXHAUSTED = "PRODUCT_NO_EXHAUSTED"  # max + 1 > 9999
    STYLE_NO_EXHAUSTED = "STYLE_NO_EXHAUSTED"  # count + 1 > 9999
    DUE_BEFORE_ORDER_DATE = "DUE_BEFORE_ORDER_DATE"
    QUANTITY_NOT_POSITIVE = "QUANTITY_NOT_POSITIVE"
    QUANTITY_UNCHANGED = "QUANTITY_UNCHANGED"
    DUE_DATE_UNCHANGED = "DUE_DATE_UNCHANGED"
    DUPLICATE_ITEM = "DUPLICATE_ITEM"
    ITEMS_NOT_ALLOWED = "ITEMS_NOT_ALLOWED"  # kind without items (hold/resume/cancel order) got items
    DUPLICATE_PO_NUMBER = "DUPLICATE_PO_NUMBER"  # DEC-058 warning, not acknowledged
    DUPLICATE_CUSTOMER_NAME = "DUPLICATE_CUSTOMER_NAME"  # warning, not acknowledged
    UNKNOWN_WARNING = "UNKNOWN_WARNING"  # acknowledged a warning code that does not exist
    BRAND_OF_OTHER_CUSTOMER = "BRAND_OF_OTHER_CUSTOMER"  # DEC-058
    REPRESENTATIVE_NAME_INVALID = "REPRESENTATIVE_NAME_INVALID"  # DEC-058: a name only
    # --- state / conflict (409 STATE_TRANSITION_NOT_ALLOWED)
    STATE_NOT_ALLOWED = "STATE_NOT_ALLOWED"  # generic: the record is not in a state that allows it
    MASTER_NOT_ACTIVE = "MASTER_NOT_ACTIVE"  # customer / brand / type / style / revision not ACTIVE
    ORDER_HAS_NO_LINES = "ORDER_HAS_NO_LINES"
    LAST_LINE_CANCEL = "LAST_LINE_CANCEL"  # cancelling the last live line: use CANCEL_ORDER
    PRODUCT_NO_TAKEN = "PRODUCT_NO_TAKEN"
    STYLE_NO_COLLISION = "STYLE_NO_COLLISION"  # count + 1 already used (non-contiguous legacy styles)
    CODE_ALREADY_ISSUED = "CODE_ALREADY_ISSUED"  # the style already has a live code
    CODE_IN_REGISTRY = "CODE_IN_REGISTRY"  # the code value exists (e.g. imported); a person links it
    CODE_NOT_RESERVED = "CODE_NOT_RESERVED"  # ERP match of a code that is not RESERVED / ERP_PENDING
    CODE_OF_OTHER_STYLE = "CODE_OF_OTHER_STYLE"
    GOLDEN_CASES_INSUFFICIENT = "GOLDEN_CASES_INSUFFICIENT"  # < 20 cases for a family (Gate)
    GOLDEN_CASE_MISMATCH = "GOLDEN_CASE_MISMATCH"  # the engine does not reproduce a golden case
    GOLDEN_CASE_OUT_OF_SCOPE = "GOLDEN_CASE_OUT_OF_SCOPE"  # case family not in the revision scope
    RELEASED_KIND_NOT_ALLOWED = "RELEASED_KIND_NOT_ALLOWED"  # DEC-059: after release only due date/hold
    CANCEL_AFTER_RELEASE = "CANCEL_AFTER_RELEASE"  # DEC-059 C-A: blocked until PHASE_05
    ORDER_ON_HOLD = "ORDER_ON_HOLD"  # a change kind not decided for held orders
    ORDER_NOT_ON_HOLD = "ORDER_NOT_ON_HOLD"  # RESUME of a running order
    ORDER_ALREADY_ON_HOLD = "ORDER_ALREADY_ON_HOLD"
    STALE_BASE_VERSION = "STALE_BASE_VERSION"  # the order moved on since the request was made
    PLANNING_APPROVAL_REQUIRED = "PLANNING_APPROVAL_REQUIRED"  # DEC-059 due-date change
    PLANNING_APPROVAL_NOT_APPLICABLE = "PLANNING_APPROVAL_NOT_APPLICABLE"  # not a due-date change
    PLANNING_ALREADY_APPROVED = "PLANNING_ALREADY_APPROVED"
    LINE_NOT_IN_ORDER = "LINE_NOT_IN_ORDER"
    # --- maker-checker (403 SELF_APPROVAL_FORBIDDEN)
    CONFIRMER_IS_CREATOR = "CONFIRMER_IS_CREATOR"  # DEC-057
    DECIDER_IS_REQUESTER = "DECIDER_IS_REQUESTER"  # DEC-057 / DEC-059
    DECIDER_IS_PLANNING_APPROVER = "DECIDER_IS_PLANNING_APPROVER"  # DEC-059 amendment 2026-11-12
    PLANNING_APPROVER_IS_REQUESTER = "PLANNING_APPROVER_IS_REQUESTER"  # DEC-059 amendment 2026-11-12
    PLANNING_APPROVER_IS_DECIDER = "PLANNING_APPROVER_IS_DECIDER"  # DEC-059 amendment 2026-11-12
    APPROVER_IS_MAKER = "APPROVER_IS_MAKER"  # DEC-005 Q-A / DEC-032 (code rule revision)
    # --- rule gate (409 RULE_NOT_APPROVED, decision_id DEC-005)
    NO_ACTIVE_CODE_RULE = "NO_ACTIVE_CODE_RULE"
    TYPE_NOT_IN_RULE_SCOPE = "TYPE_NOT_IN_RULE_SCOPE"
    RULE_SPEC_NOT_IMPLEMENTED = "RULE_SPEC_NOT_IMPLEMENTED"  # ACTIVE revision has a spec this engine lacks
    # --- idempotency (422 IDEMPOTENCY_KEY_REUSED)
    IDEMPOTENCY_PAYLOAD_MISMATCH = "IDEMPOTENCY_PAYLOAD_MISMATCH"  # REV-0220


_V, _S, _SA, _R, _I = (
    ErrorCode.VALIDATION_FAILED,
    ErrorCode.STATE_TRANSITION_NOT_ALLOWED,
    ErrorCode.SELF_APPROVAL_FORBIDDEN,
    ErrorCode.RULE_NOT_APPROVED,
    ErrorCode.IDEMPOTENCY_KEY_REUSED,
)
_BY_CODE: dict[ErrorCode, tuple[Reason, ...]] = {
    _V: (
        Reason.REQUIRED,
        Reason.INVALID,
        Reason.SEGMENT_FORMAT,
        Reason.CODE_FORMAT,
        Reason.STYLE_0000_LEGACY_ONLY,
        Reason.BELT_SEGMENTS_REQUIRED,
        Reason.BELT_SEGMENTS_NOT_ALLOWED,
        Reason.PRODUCT_NO_EXHAUSTED,
        Reason.STYLE_NO_EXHAUSTED,
        Reason.DUE_BEFORE_ORDER_DATE,
        Reason.QUANTITY_NOT_POSITIVE,
        Reason.QUANTITY_UNCHANGED,
        Reason.DUE_DATE_UNCHANGED,
        Reason.DUPLICATE_ITEM,
        Reason.ITEMS_NOT_ALLOWED,
        Reason.DUPLICATE_PO_NUMBER,
        Reason.DUPLICATE_CUSTOMER_NAME,
        Reason.UNKNOWN_WARNING,
        Reason.BRAND_OF_OTHER_CUSTOMER,
        Reason.REPRESENTATIVE_NAME_INVALID,
    ),
    _S: (
        Reason.STATE_NOT_ALLOWED,
        Reason.MASTER_NOT_ACTIVE,
        Reason.ORDER_HAS_NO_LINES,
        Reason.LAST_LINE_CANCEL,
        Reason.PRODUCT_NO_TAKEN,
        Reason.STYLE_NO_COLLISION,
        Reason.CODE_ALREADY_ISSUED,
        Reason.CODE_IN_REGISTRY,
        Reason.CODE_NOT_RESERVED,
        Reason.CODE_OF_OTHER_STYLE,
        Reason.GOLDEN_CASES_INSUFFICIENT,
        Reason.GOLDEN_CASE_MISMATCH,
        Reason.GOLDEN_CASE_OUT_OF_SCOPE,
        Reason.RELEASED_KIND_NOT_ALLOWED,
        Reason.CANCEL_AFTER_RELEASE,
        Reason.ORDER_ON_HOLD,
        Reason.ORDER_NOT_ON_HOLD,
        Reason.ORDER_ALREADY_ON_HOLD,
        Reason.STALE_BASE_VERSION,
        Reason.PLANNING_APPROVAL_REQUIRED,
        Reason.PLANNING_APPROVAL_NOT_APPLICABLE,
        Reason.PLANNING_ALREADY_APPROVED,
        Reason.LINE_NOT_IN_ORDER,
    ),
    _SA: (
        Reason.CONFIRMER_IS_CREATOR,
        Reason.DECIDER_IS_REQUESTER,
        Reason.DECIDER_IS_PLANNING_APPROVER,
        Reason.PLANNING_APPROVER_IS_REQUESTER,
        Reason.PLANNING_APPROVER_IS_DECIDER,
        Reason.APPROVER_IS_MAKER,
    ),
    _R: (
        Reason.NO_ACTIVE_CODE_RULE,
        Reason.TYPE_NOT_IN_RULE_SCOPE,
        Reason.RULE_SPEC_NOT_IMPLEMENTED,
    ),
    _I: (Reason.IDEMPOTENCY_PAYLOAD_MISMATCH,),
}
REASON_CODE: Final[Mapping[Reason, ErrorCode]] = MappingProxyType(
    {reason: code for code, reasons in _BY_CODE.items() for reason in reasons}
)
CODE_RULE_DECISION: Final = "DEC-005"


def error(
    reason: Reason, *, field: str = "", detail: str = "", extra: tuple[FieldError, ...] = ()
) -> AleekhanError:
    """The exception for ``reason`` (top-level code from :data:`REASON_CODE`)."""
    errors = (FieldError(field, reason.value), *extra)
    code = REASON_CODE[reason]
    if code == ErrorCode.VALIDATION_FAILED:
        return ValidationFailed(detail, errors=errors)
    if code == ErrorCode.STATE_TRANSITION_NOT_ALLOWED:
        return StateTransitionNotAllowed(detail, errors=errors)
    if code == ErrorCode.SELF_APPROVAL_FORBIDDEN:
        return SelfApprovalForbidden(detail, errors=errors)
    if code == ErrorCode.IDEMPOTENCY_KEY_REUSED:
        return IdempotencyKeyReused(detail, errors=errors)
    exc = RuleNotApproved(CODE_RULE_DECISION, detail)
    exc.errors = errors
    return exc


def refuse(
    reason: Reason, *, field: str = "", detail: str = "", extra: tuple[FieldError, ...] = ()
) -> NoReturn:
    raise error(reason, field=field, detail=detail, extra=extra)
