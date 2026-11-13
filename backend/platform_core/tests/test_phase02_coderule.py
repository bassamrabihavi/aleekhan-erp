"""DEC-005 code rule as pure functions (PHASE_02 / 02.3, ID-01): unit + property tests, no database.

Synthetic values only: type segments in the ``9x`` range, product numbers ``9xxx`` (phase02_factories
convention); they say nothing about the real Planning ``Sorce`` list (R-38).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from platform_core.engine.errors import AleekhanError, ErrorCode, RuleNotApproved, ValidationFailed
from platform_core.product_identity import coderule
from platform_core.product_identity.refusals import REASON_CODE, Reason, error

two = st.text(alphabet="0123456789", min_size=2, max_size=2)
four = st.text(alphabet="0123456789", min_size=4, max_size=4)
style = four.filter(lambda s: s != "0000")
GOLDEN = Path(__file__).parent / "golden" / "phase02_refusals.golden.json"


def _reason(exc: AleekhanError) -> str:
    return exc.errors[0].code


# ------------------------------------------------------------------------------------------ build/parse
def test_build_code_concatenates_text_segments_with_the_product_prefix() -> None:
    assert coderule.build_code("91", "07", "9001", "0003") == "02" + "91" + "07" + "9001" + "0003"
    # leading zeros are significant (ID-01): every segment keeps them
    assert coderule.build_code("90", "00", "0001", "0001") == "02900000010001"


@given(t=two, c=two, p=four, s=style)
def test_build_then_parse_round_trips_and_keeps_widths(t: str, c: str, p: str, s: str) -> None:
    code = coderule.build_code(t, c, p, s)
    assert isinstance(code, str) and len(code) == 14 and code.isdigit() and code.startswith("02")
    parts = coderule.parse_code(code)
    assert (parts.type_code, parts.category_code, parts.product_no, parts.style_no) == (t, c, p, s)
    assert code[2:4] == t and code[4:6] == c and code[6:10] == p and code[10:14] == s
    assert coderule.is_valid_code(code)


@given(n=st.integers(min_value=0, max_value=99))
def test_integer_segments_are_refused_never_padded(n: int) -> None:
    with pytest.raises(ValidationFailed) as exc:
        coderule.build_code(n, "07", "9001", "0001")  # type: ignore[arg-type]
    assert _reason(exc.value) == Reason.SEGMENT_FORMAT


@pytest.mark.parametrize(
    ("args", "field"),
    [
        (("9", "07", "9001", "0001"), "type_code"),
        (("911", "07", "9001", "0001"), "type_code"),
        (("91", "7", "9001", "0001"), "category_code"),
        (("91", "07", "901", "0001"), "product_no"),
        (("91", "07", "90010", "0001"), "product_no"),
        (("91", "07", "9001", "001"), "style_no"),
        (("9a", "07", "9001", "0001"), "type_code"),
        (("٩١", "07", "9001", "0001"), "type_code"),  # Arabic-Indic digits are not ASCII digits
        ((" 91", "07", "9001", "0001"), "type_code"),
    ],
)
def test_wrong_segment_widths_or_characters_are_refused(args: tuple[str, str, str, str], field: str) -> None:
    with pytest.raises(ValidationFailed) as exc:
        coderule.build_code(*args)
    assert exc.value.errors[0].as_dict() == {"field": field, "code": "SEGMENT_FORMAT"}


@pytest.mark.parametrize(
    "code",
    ["0291079001000", "029107900100031", "03910790010003", "02910790010000", 2910790010003, None, "02-91-07"],
)
def test_parse_refuses_anything_that_is_not_a_product_code(code: object) -> None:
    with pytest.raises(ValidationFailed):
        coderule.parse_code(code)
    assert not coderule.is_valid_code(code)


# ----------------------------------------------------------------- legacy style 0000 (DEC-005 amendment)
def test_style_0000_is_never_built_by_the_system_path() -> None:
    with pytest.raises(ValidationFailed) as exc:
        coderule.build_code("91", "07", "9001", "0000")
    assert exc.value.errors[0].as_dict() == {"field": "style_no", "code": "STYLE_0000_LEGACY_ONLY"}
    with pytest.raises(ValidationFailed) as exc:
        coderule.parse_code("02910790010000")  # the system parse refuses it too
    assert _reason(exc.value) == "STYLE_0000_LEGACY_ONLY"
    assert not coderule.is_valid_code("02910790010000")
    assert coderule.next_style_no(0) == "0001"  # new styles start at 0001


def test_legacy_parse_accepts_style_0000_with_exact_segments() -> None:
    parts = coderule.validate_legacy_code("02920190030000")
    assert (parts.type_code, parts.category_code, parts.product_no, parts.style_no) == (
        "92",
        "01",
        "9003",
        "0000",
    )
    assert parts.is_legacy_only and parts.code == "02920190030000"
    assert coderule.parse_code("02920190030000", legacy=True) == parts
    assert coderule.is_valid_code("02920190030000", legacy=True)
    for bad in ("0292019003000", "03920190030000", 2920190030000, "0292019003000a"):
        with pytest.raises(ValidationFailed):
            coderule.validate_legacy_code(bad)


@given(t=two, c=two, p=four, s=four)
def test_legacy_parse_round_trips_every_style_including_0000(t: str, c: str, p: str, s: str) -> None:
    code = "02" + t + c + p + s
    parts = coderule.validate_legacy_code(code)
    assert (parts.type_code, parts.category_code, parts.product_no, parts.style_no, parts.code) == (
        t,
        c,
        p,
        s,
        code,
    )
    assert parts.is_legacy_only is (s == "0000")


# ----------------------------------------------------------------------------------------- numbering
def test_next_product_no_is_max_of_the_type_plus_one() -> None:
    assert coderule.next_product_no([]) == "0001"
    assert coderule.next_product_no(["9001", "0007", "9003"]) == "9004"  # max, not count
    assert coderule.next_product_no(["0009"]) == "0010"  # four digits with leading zeros


@given(nums=st.lists(st.integers(min_value=0, max_value=9998), max_size=30))
def test_next_product_no_property(nums: list[int]) -> None:
    out = coderule.next_product_no([f"{n:04d}" for n in nums])
    assert len(out) == 4 and int(out) == (max(nums) if nums else 0) + 1


def test_product_numbers_are_exhausted_at_9999() -> None:
    with pytest.raises(ValidationFailed) as exc:
        coderule.next_product_no(["9999"])
    assert _reason(exc.value) == Reason.PRODUCT_NO_EXHAUSTED


def test_next_style_no_is_count_plus_one_zero_padded() -> None:
    assert coderule.next_style_no(0) == "0001"
    assert coderule.next_style_no(41) == "0042"
    with pytest.raises(ValidationFailed) as exc:
        coderule.next_style_no(9999)
    assert _reason(exc.value) == Reason.STYLE_NO_EXHAUSTED
    for bad in (-1, True, 1.0):
        with pytest.raises(ValueError):
            coderule.next_style_no(bad)  # type: ignore[arg-type]


@given(n=st.integers(min_value=0, max_value=9998))
def test_next_style_no_property(n: int) -> None:
    out = coderule.next_style_no(n)
    assert len(out) == 4 and int(out) == n + 1 and out != "0000"


@given(b=two, w=two)
def test_belt_product_number_is_buckle_then_width(b: str, w: str) -> None:
    assert coderule.belt_product_no(b, w) == b + w
    assert len(coderule.belt_product_no(b, w)) == 4


@pytest.mark.parametrize(("b", "w"), [("1", "35"), ("01", "5"), (1, "35"), ("01", 35)])
def test_belt_segments_are_two_digit_text(b: object, w: object) -> None:
    with pytest.raises(ValidationFailed):
        coderule.belt_product_no(b, w)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------- golden helper
def _case(**over: object) -> coderule.GoldenCase:
    raw: dict[str, object] = {
        "type_code": "93",
        "category_code": "07",
        "product_no": "9001",
        "style_no": "0003",
        "expected_code": "02930790010003",
        "family": "93",
    }
    raw.update(over)
    return coderule.GoldenCase.from_mapping(raw)


def test_golden_case_problems() -> None:
    assert coderule.golden_case_problems(_case()) == []
    assert coderule.golden_case_problems(_case(expected_code="02930790010004")) == ["GOLDEN_CASE_MISMATCH"]
    assert coderule.golden_case_problems(_case(style_no="3")) == ["SEGMENT_FORMAT"]
    # legacy-only (style 0000): passes when the build path refuses it and the legacy parse is exact
    legacy = _case(style_no="0000", expected_code="02930790010000")
    assert coderule.is_legacy_only_case(legacy) and coderule.golden_case_problems(legacy) == []
    assert coderule.golden_case_problems(_case(style_no="0000", expected_code="02930790020000")) == [
        "GOLDEN_CASE_MISMATCH"
    ]
    assert coderule.golden_case_problems(_case(style_no="0000", expected_code="02930790010001")) == [
        "GOLDEN_CASE_MISMATCH"
    ]
    belt = _case(
        product_no="1235", expected_code="02930712350003", buckle_type_code="12", belt_width_code="35"
    )
    assert coderule.golden_case_problems(belt) == []
    wrong_belt = _case(
        product_no="1235", expected_code="02930712350003", buckle_type_code="12", belt_width_code="40"
    )
    assert coderule.golden_case_problems(wrong_belt) == ["GOLDEN_CASE_MISMATCH"]
    half = _case(buckle_type_code="12")
    assert coderule.golden_case_problems(half) == ["BELT_SEGMENTS_REQUIRED"]
    with pytest.raises(ValueError):
        _case(product_no=9001)  # numbers in a golden file are refused: leading zeros must be text


def test_rule_spec_is_the_documented_dec005_rule() -> None:
    spec = coderule.rule_spec_v1()
    assert spec["prefix"] == "02" and spec["decision_id"] == "DEC-005"
    assert [(s["name"], s["width"]) for s in spec["segments"]] == [
        ("product_type", 2),
        ("category", 2),
        ("product_no", 4),
        ("style_no", 4),
    ]
    assert json.loads(json.dumps(spec)) == spec  # JSON-ready (stored in rule_spec)
    spec["prefix"] = "99"
    assert coderule.rule_spec_v1()["prefix"] == "02"  # a copy, the constant is read-only


# ------------------------------------------------------------------------------------- refusal catalogue
def test_refusal_catalogue_equals_the_reviewed_golden() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    golden.pop("_note")
    assert golden == {"refusals": {r.value: REASON_CODE[r].value for r in Reason}}


def test_every_reason_maps_to_one_stable_top_level_code() -> None:
    assert set(REASON_CODE) == set(Reason)
    allowed = {
        ErrorCode.VALIDATION_FAILED,
        ErrorCode.STATE_TRANSITION_NOT_ALLOWED,
        ErrorCode.SELF_APPROVAL_FORBIDDEN,
        ErrorCode.RULE_NOT_APPROVED,
        ErrorCode.IDEMPOTENCY_KEY_REUSED,
    }
    for reason, code in REASON_CODE.items():
        assert code in allowed
        exc = error(reason, field="f")
        assert exc.code == code and exc.errors[0].as_dict() == {"field": "f", "code": reason.value}
        if code == ErrorCode.RULE_NOT_APPROVED:
            assert isinstance(exc, RuleNotApproved) and exc.decision_id == "DEC-005"
        body = exc.to_problem(__import__("uuid").uuid4())
        assert body["code"] == code.value and body["errors"][0]["code"] == reason.value
