"""DEC-005 (APPROVED 2026-11-12): the 14-digit product code rule as pure functions (no database, no clock).

``code = "02" + product-type code (2) + category code (2) + product number (4) + style number (4)``

* Every segment is a string of ASCII digits of its exact width; leading zeros are significant and never
  dropped (ID-01). Integers are never accepted as segments: ``7`` is not ``"07"``.
* New product number (sequential types): the largest product number of the same product type + 1, four
  digits (Planning ``Order form!J10``: ``MAXIFS(...) + 1``). A type without products starts at ``0001``.
  Above ``9999`` the engine refuses (``PRODUCT_NO_EXHAUSTED``); it never wraps or widens.
* Belt types: product number = buckle-type code (2) + belt width (2).
* New style number: styles are counted per (product, category) and numbered ``count + 1``, four digits
  (Planning ``Order form!J11``: ``COUNTIFS(...) + 1``). DEC-005 amendment 2026-11-14 (REV-0232): when
  ``count + 1`` is already used (legacy styles that are not contiguous), the style gets the **first free
  number after it** (:func:`first_free_style_no`); the use case records the collision in the audit row. A
  duplicate style number is never created (UNIQUE constraint) and nothing is refused for this case.
* DEC-005 amendment 2026-11-13: style segment ``0000`` is **legacy only**. Existing codes with it are accepted
  as history (:func:`validate_legacy_code` / ``parse_code(..., legacy=True)`` return their exact segments),
  but the system path never builds or issues one (``STYLE_0000_LEGACY_ONLY``); new styles start at ``0001``.
  Golden cases with style ``0000`` pass only if the build path refuses them and the legacy parse reproduces
  their segments exactly.

``RULE_SPEC_V1`` is the machine description of this rule written into ``CodeRuleRevision.rule_spec``; an
ACTIVE revision whose spec differs from what this module implements cannot issue codes
(``RULE_SPEC_NOT_IMPLEMENTED``, 409 RULE_NOT_APPROVED).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from platform_core.engine.errors import AleekhanError

from .refusals import Reason, refuse

PRODUCT_PREFIX: Final = "02"  # DEC-005 / Planning E-9: nature = product
TYPE_WIDTH: Final = 2
CATEGORY_WIDTH: Final = 2
PRODUCT_NO_WIDTH: Final = 4
STYLE_NO_WIDTH: Final = 4
BUCKLE_WIDTH: Final = 2
BELT_WIDTH_WIDTH: Final = 2
CODE_LENGTH: Final = 14
LEGACY_ONLY_STYLE_NO: Final = "0000"  # DEC-005 amendment 2026-11-13: history only, never issued
MAX_FOUR_DIGITS: Final = 9999

_DIGITS = {n: re.compile(rf"^[0-9]{{{n}}}$") for n in (2, 4, 14)}

RULE_SPEC_V1: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "rule": "aleekhan.product_code",
        "spec_version": 1,
        "decision_id": "DEC-005",
        "prefix": PRODUCT_PREFIX,
        "segments": [
            {"name": "product_type", "width": TYPE_WIDTH},
            {"name": "category", "width": CATEGORY_WIDTH},
            {"name": "product_no", "width": PRODUCT_NO_WIDTH},
            {"name": "style_no", "width": STYLE_NO_WIDTH},
        ],
        "product_no": {
            "SEQUENTIAL_PER_TYPE": "max_of_type_plus_one",
            "BELT_BUCKLE_WIDTH": "buckle_code_2_then_width_2",
        },
        "style_no": "count_per_product_and_category_plus_one",
    }
)


def rule_spec_v1() -> dict[str, Any]:
    """A JSON-ready copy of :data:`RULE_SPEC_V1` (what ``rule_spec`` must equal)."""
    out = dict(RULE_SPEC_V1)
    out["segments"] = [dict(s) for s in RULE_SPEC_V1["segments"]]
    out["product_no"] = dict(RULE_SPEC_V1["product_no"])
    return out


def _segment(value: object, width: int, field: str) -> str:
    if not isinstance(value, str) or not _DIGITS[width].fullmatch(value):
        refuse(Reason.SEGMENT_FORMAT, field=field, detail=f"{field} must be {width} ASCII digits as text")
    return value


@dataclass(frozen=True)
class CodeParts:
    """The four segments. ``legacy=True`` (DEC-005 amendment 2026-11-13) accepts the legacy-only style
    segment ``0000``; the system path (``legacy=False``: build, issue) refuses it."""

    type_code: str
    category_code: str
    product_no: str
    style_no: str
    legacy: bool = False

    def __post_init__(self) -> None:
        _segment(self.type_code, TYPE_WIDTH, "type_code")
        _segment(self.category_code, CATEGORY_WIDTH, "category_code")
        _segment(self.product_no, PRODUCT_NO_WIDTH, "product_no")
        _segment(self.style_no, STYLE_NO_WIDTH, "style_no")
        if self.style_no == LEGACY_ONLY_STYLE_NO and not self.legacy:
            refuse(
                Reason.STYLE_0000_LEGACY_ONLY,
                field="style_no",
                detail="style 0000 exists only in legacy codes; new styles start at 0001",
            )

    @property
    def is_legacy_only(self) -> bool:
        return self.style_no == LEGACY_ONLY_STYLE_NO

    @property
    def code(self) -> str:
        return PRODUCT_PREFIX + self.type_code + self.category_code + self.product_no + self.style_no


def build_code(type_code: str, category_code: str, product_no: str, style_no: str) -> str:
    """The 14-digit code of the four segments (validated; text in, text out)."""
    return CodeParts(type_code, category_code, product_no, style_no).code


def parse_code(code: object, *, legacy: bool = False) -> CodeParts:
    """Split a code back into its segments; refuses anything that is not ``02`` + 12 digits. ``legacy=True``
    is the import / history path: it also accepts style ``0000`` (DEC-005 amendment 2026-11-13)."""
    if not isinstance(code, str) or not _DIGITS[CODE_LENGTH].fullmatch(code):
        refuse(Reason.CODE_FORMAT, field="code", detail="a product code is 14 ASCII digits as text")
    if not code.startswith(PRODUCT_PREFIX):
        refuse(Reason.CODE_FORMAT, field="code", detail="a product code starts with the product prefix")
    return CodeParts(code[2:4], code[4:6], code[6:10], code[10:14], legacy=legacy)


def validate_legacy_code(code: object) -> CodeParts:
    """Legacy import / matching: the exact segments of a 14-digit product code, style ``0000`` included."""
    return parse_code(code, legacy=True)


def is_valid_code(code: object, *, legacy: bool = False) -> bool:
    try:
        parse_code(code, legacy=legacy)
    except Exception:
        return False
    return True


def belt_product_no(buckle_type_code: str, belt_width_code: str) -> str:
    """DEC-005, belt: product number = buckle-type code (2) + belt width (2)."""
    return _segment(buckle_type_code, BUCKLE_WIDTH, "buckle_type_code") + _segment(
        belt_width_code, BELT_WIDTH_WIDTH, "belt_width_code"
    )


def next_product_no(existing: Iterable[str]) -> str:
    """DEC-005: largest product number of the type + 1 (four digits); ``existing`` = the type's numbers."""
    top = 0
    for value in existing:
        top = max(top, int(_segment(value, PRODUCT_NO_WIDTH, "product_no")))
    nxt = top + 1
    if nxt > MAX_FOUR_DIGITS:
        refuse(Reason.PRODUCT_NO_EXHAUSTED, field="product_no", detail="no four-digit product number is left")
    return f"{nxt:04d}"


def next_style_no(existing_count: int) -> str:
    """DEC-005: styles of a (product, category) are numbered ``count + 1`` from 0001 (four digits)."""
    if isinstance(existing_count, bool) or not isinstance(existing_count, int) or existing_count < 0:
        raise ValueError("existing_count must be a non-negative integer")
    nxt = existing_count + 1
    if nxt > MAX_FOUR_DIGITS:
        refuse(Reason.STYLE_NO_EXHAUSTED, field="style_no", detail="no four-digit style number is left")
    return f"{nxt:04d}"


def first_free_style_no(used: Iterable[str]) -> tuple[str, str | None]:
    """DEC-005 + amendment 2026-11-14: ``(style_no, collided)`` for a (product, category) whose existing
    style numbers are ``used``. ``style_no`` = ``count + 1`` when free, else the first free number after it;
    ``collided`` = the taken ``count + 1`` (``None`` without a collision). Never above ``9999``."""
    taken = {_segment(v, STYLE_NO_WIDTH, "style_no") for v in used}
    first = next_style_no(len(taken))
    if first not in taken:
        return first, None
    n = int(first)
    while True:
        n += 1
        if n > MAX_FOUR_DIGITS:
            refuse(Reason.STYLE_NO_EXHAUSTED, field="style_no", detail="no four-digit style number is left")
        candidate = f"{n:04d}"
        if candidate not in taken:
            return candidate, first


# ------------------------------------------------------------------------------------- golden cases
@dataclass(frozen=True)
class GoldenCase:
    """One golden case: the four segments as text and the code the source shows for them."""

    type_code: str
    category_code: str
    product_no: str
    style_no: str
    expected_code: str
    family: str
    buckle_type_code: str | None = None
    belt_width_code: str | None = None
    # REV-0230 (C-77): the category code as the ``Order form`` lookup gives it (must equal category_code)
    category_code_order_form: str | None = None
    # REV-0231: where the belt width segment was read (evidence text only, never checked as data)
    belt_width_source: str | None = None
    # REV-0231: a legacy row planning disputes (non-empty reason): reported, never failed, never counted
    legacy_disputed: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> GoldenCase:
        def text(key: str, *, optional: bool = False) -> str | None:
            value = raw.get(key)
            if value is None and optional:
                return None
            if not isinstance(value, str):
                raise ValueError(
                    f"golden case field {key!r} must be text (leading zeros), got {type(value).__name__}"
                )
            return value

        return cls(
            type_code=str(text("type_code")),
            category_code=str(text("category_code")),
            product_no=str(text("product_no")),
            style_no=str(text("style_no")),
            expected_code=str(text("expected_code")),
            family=str(text("family")),
            buckle_type_code=text("buckle_type_code", optional=True),
            belt_width_code=text("belt_width_code", optional=True),
            category_code_order_form=text("category_code_order_form", optional=True),
            belt_width_source=text("belt_width_source", optional=True),
            legacy_disputed=_reason_text(raw.get("legacy_disputed")),
        )

    @property
    def has_belt_segments(self) -> bool:
        return self.buckle_type_code is not None and self.belt_width_code is not None

    @property
    def c77_disagrees(self) -> bool:
        """C-77: the two category lookups of the workbook give different codes for this case."""
        return (
            self.category_code_order_form is not None and self.category_code_order_form != self.category_code
        )


def _reason_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("golden case field 'legacy_disputed' must be a non-empty reason text")
    return value


def is_legacy_only_case(case: GoldenCase) -> bool:
    """DEC-005 amendment 2026-11-13: a case with style ``0000`` is legacy-only."""
    return case.style_no == LEGACY_ONLY_STYLE_NO


def golden_case_problems(case: GoldenCase) -> list[str]:
    """Machine codes of what does not reproduce (empty = the engine builds exactly ``expected_code``).

    A legacy-only case (style ``0000``) passes when the build path REFUSES it and the legacy parse of
    ``expected_code`` gives exactly the case's four segments."""
    problems: list[str] = []
    if is_legacy_only_case(case):
        try:
            build_code(case.type_code, case.category_code, case.product_no, case.style_no)
            problems.append(Reason.GOLDEN_CASE_MISMATCH.value)  # the system path must never build it
        except AleekhanError as exc:
            if not exc.errors or exc.errors[0].code != Reason.STYLE_0000_LEGACY_ONLY.value:
                return [Reason.SEGMENT_FORMAT.value]
        try:
            parts = validate_legacy_code(case.expected_code)
        except AleekhanError:
            return [*problems, Reason.GOLDEN_CASE_MISMATCH.value]
        if (parts.type_code, parts.category_code, parts.product_no, parts.style_no) != (
            case.type_code,
            case.category_code,
            case.product_no,
            case.style_no,
        ):
            problems.append(Reason.GOLDEN_CASE_MISMATCH.value)
    else:
        try:
            built = build_code(case.type_code, case.category_code, case.product_no, case.style_no)
        except Exception:
            return [Reason.SEGMENT_FORMAT.value]
        if built != case.expected_code:
            problems.append(Reason.GOLDEN_CASE_MISMATCH.value)
    if case.c77_disagrees:  # REV-0230 / DEC-005 C-77: both category lookups must give the same code
        problems.append(Reason.GOLDEN_CASE_MISMATCH.value)
    if (case.buckle_type_code is None) != (case.belt_width_code is None):
        problems.append(Reason.BELT_SEGMENTS_REQUIRED.value)
    elif case.buckle_type_code is not None and case.belt_width_code is not None:
        try:
            if belt_product_no(case.buckle_type_code, case.belt_width_code) != case.product_no:
                problems.append(Reason.GOLDEN_CASE_MISMATCH.value)
        except Exception:
            problems.append(Reason.SEGMENT_FORMAT.value)
    return problems
