"""DEC-005 golden harness (PHASE_02 / 02.3): the engine must build exactly the codes of the Planning baseline.

Real golden cases never enter Git (DEC-005 / DEC-028 / DEC-046, R-38). The orchestrator produces them on the
work machine from the baseline workbook (DEC-037 amendment, intake sha ``113f5400...``) into a JSON file
**outside the repository** and points ``ALEEKHAN_GOLDEN_FILE`` at it. Without that variable the real-data test
is skipped with a clear reason (never faked).

File format: a JSON list of objects, every value **text** (leading zeros)::

    {"type_code": "..", "category_code": "..", "product_no": "....", "style_no": "....",
     "expected_code": "..............", "family": "..",
     "category_code_order_form": "..",                        # optional (C-77, REV-0230)
     "buckle_type_code": "..", "belt_width_code": "..",       # optional (belt cases, REV-0231)
     "belt_width_source": "...",                              # optional (where the width was read)
     "legacy_disputed": "reason"}                             # optional (planning disputes the row)

Legacy-only cases (DEC-005 amendment 2026-11-13): a case with style ``0000`` is history only. It counts in
its family; it passes when ``build_code`` REFUSES it (the system never issues style 0000) and the legacy parse
of ``expected_code`` returns exactly its four segments. Their number is reported separately (counts only).

Checks: every case reproduces (``coderule.build_code`` == ``expected_code``; a belt case also
``buckle + width == product_no``), every family (= product type, DEC-005 Q-C) has >= 20 cases (Gate), and
``family`` equals the type segment of the code. Failure output names case **indexes and counts only** -
never a code, product or style value (logs and reports stay free of real data).

* **C-77** (REV-0230, DEC-005 technical note): a case MAY carry ``category_code_order_form`` - the category
  code as the ``Order form`` lookup gives it, next to ``category_code`` from ``NOrder!FY``. The harness counts
  the cases that carry it (``c77_checked``) and those where it differs from ``category_code``
  (``c77_disagree``); **any disagreement fails the run**. A file without the field reports ``c77_checked=0``
  (C-77 then stays open; the harness never claims it was checked).
* **Belt** (REV-0231, DEC-005 Q-C "belt is tested on its own"): a belt case carries ``buckle_type_code`` and
  ``belt_width_code`` (optionally ``belt_width_source``). A family is a belt family when any of its cases
  carries a belt segment, or when it is named in ``ALEEKHAN_GOLDEN_BELT_FAMILIES`` (comma separated type
  codes; the orchestrator sets it from the Planning ``Sorce`` sheet, so a belt family whose cases lack the
  segments fails instead of passing unnoticed). ``belt_checked`` = cases of belt families with both segments;
  every belt family needs >= 20 of them.
* **Legacy disputed** (``legacy_disputed``: a non-empty reason): the case is reported
  (``legacy_disputed=<n>``) and never fails, but it counts neither toward the family minimum nor toward the
  belt minimum, and it is not part of the C-77 counts.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from platform_core.engine.errors import ValidationFailed
from platform_core.product_identity import coderule

ENV = "ALEEKHAN_GOLDEN_FILE"
BELT_ENV = "ALEEKHAN_GOLDEN_BELT_FAMILIES"
MIN_PER_FAMILY = 20
MIN_BELT_CHECKED = 20
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class HarnessResult:
    cases: int
    per_family: dict[str, int]
    failing_indexes: list[int]
    malformed_indexes: list[int]
    family_mismatch_indexes: list[int]
    small_families: list[str]
    legacy_per_family: dict[str, int] = field(default_factory=dict)
    c77_checked: int = 0
    c77_disagree_indexes: list[int] = field(default_factory=list)
    belt_checked_per_family: dict[str, int] = field(default_factory=dict)
    belt_families_below_minimum: list[str] = field(default_factory=list)
    legacy_disputed: int = 0

    @property
    def legacy_only(self) -> int:
        return sum(self.legacy_per_family.values())

    @property
    def belt_checked(self) -> int:
        return sum(self.belt_checked_per_family.values())

    @property
    def ok(self) -> bool:
        return not (
            self.failing_indexes
            or self.malformed_indexes
            or self.family_mismatch_indexes
            or self.small_families
            or self.c77_disagree_indexes
            or self.belt_families_below_minimum
        )

    def summary(self) -> str:
        """Counts and indexes only (safe for logs)."""
        return (
            f"cases={self.cases} families={len(self.per_family)} "
            f"per_family_counts={sorted(self.per_family.values())} "
            f"not_reproduced={len(self.failing_indexes)} first_indexes={self.failing_indexes[:20]} "
            f"malformed={len(self.malformed_indexes)} first_indexes={self.malformed_indexes[:20]} "
            f"family_mismatch={len(self.family_mismatch_indexes)} "
            f"families_below_{MIN_PER_FAMILY}={len(self.small_families)} "
            f"legacy_only_style_0000={self.legacy_only} "
            f"legacy_only_per_family_counts={sorted(self.legacy_per_family.values())} "
            f"c77_checked={self.c77_checked} c77_disagree={len(self.c77_disagree_indexes)} "
            f"c77_first_indexes={self.c77_disagree_indexes[:20]} "
            f"belt_families={len(self.belt_checked_per_family)} belt_checked={self.belt_checked} "
            f"belt_checked_per_family_counts={sorted(self.belt_checked_per_family.values())} "
            f"belt_families_below_{MIN_BELT_CHECKED}={len(self.belt_families_below_minimum)} "
            f"legacy_disputed={self.legacy_disputed}"
        )


def declared_belt_families() -> frozenset[str]:
    raw = os.environ.get(BELT_ENV, "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def run_harness(
    raw_cases: Sequence[Any],
    *,
    min_per_family: int = MIN_PER_FAMILY,
    min_belt_checked: int = MIN_BELT_CHECKED,
    belt_families: frozenset[str] = frozenset(),
) -> HarnessResult:
    per_family: Counter[str] = Counter()
    failing: list[int] = []
    malformed: list[int] = []
    family_mismatch: list[int] = []
    legacy: Counter[str] = Counter()
    c77_checked = 0
    c77_disagree: list[int] = []
    belt_checked: Counter[str] = Counter()
    belts: set[str] = set(belt_families)
    disputed = 0
    for i, raw in enumerate(raw_cases):
        try:
            if not isinstance(raw, dict):
                raise ValueError("not an object")
            case = coderule.GoldenCase.from_mapping(raw)
        except ValueError:
            malformed.append(i)
            continue
        if case.buckle_type_code is not None or case.belt_width_code is not None:
            belts.add(case.family)
        if case.legacy_disputed is not None:
            disputed += 1  # reported only: never failed, never counted (REV-0231)
            continue
        per_family[case.family] += 1
        if case.family != case.type_code or case.expected_code[2:4] != case.type_code:
            family_mismatch.append(i)
        if coderule.is_legacy_only_case(case):
            # DEC-005 amendment 2026-11-13: counted in its family; the build path must refuse it and the
            # legacy parse must reproduce its segments exactly (both inside golden_case_problems)
            legacy[case.family] += 1
        if case.category_code_order_form is not None:
            c77_checked += 1
            if case.c77_disagrees:
                c77_disagree.append(i)
        if case.has_belt_segments:
            belt_checked[case.family] += 1
        if coderule.golden_case_problems(case):
            failing.append(i)
    small = [f for f, n in per_family.items() if n < min_per_family]
    belt_counts = {f: belt_checked[f] for f in sorted(belts)}
    belt_small = [f for f, n in belt_counts.items() if n < min_belt_checked]
    return HarnessResult(
        len(raw_cases),
        dict(per_family),
        failing,
        malformed,
        family_mismatch,
        small,
        dict(legacy),
        c77_checked,
        c77_disagree,
        belt_counts,
        belt_small,
        disputed,
    )


def _synthetic_cases(families: Sequence[str], per_family: int) -> list[dict[str, str]]:
    """SYNTHETIC cases (``9x`` types, ``9xxx`` products) built independently of the engine (plain string
    concatenation), one family as a belt."""
    out = []
    for fi, fam in enumerate(families):
        for n in range(per_family):
            cat, style = f"{n % 7:02d}", f"{n + 1:04d}"
            case = {"type_code": fam, "category_code": cat, "style_no": style, "family": fam}
            if fi == 0:  # belt family: product number = buckle + width
                buckle, width = f"{90 + n % 5:02d}", f"{30 + n % 4:02d}"
                case.update(buckle_type_code=buckle, belt_width_code=width, product_no=buckle + width)
            else:
                case["product_no"] = f"{9000 + n:04d}"
            case["expected_code"] = "02" + fam + cat + case["product_no"] + style
            out.append(case)
    return out


# ----------------------------------------------------------------------------------- harness self-tests
def test_harness_accepts_a_synthetic_baseline(tmp_path: Path) -> None:
    path = tmp_path / "synthetic_golden.json"
    path.write_text(json.dumps(_synthetic_cases(["91", "92", "93"], 20)), encoding="utf-8")
    result = run_harness(json.loads(path.read_text(encoding="utf-8")))
    assert result.ok, result.summary()
    assert result.per_family == {"91": 20, "92": 20, "93": 20}


def test_harness_reports_mismatch_small_family_and_malformed_cases_by_index_only() -> None:
    cases: list[Any] = _synthetic_cases(["91", "92"], 22)
    cases[3] = {**cases[3], "expected_code": "02910099990001"}  # not what the segments build
    cases[5] = {**cases[5], "product_no": 9001}  # a number: leading zeros lost
    cases[7] = {**cases[7], "family": "92"}  # family is not the type segment
    cases.append("not an object")
    cases = [c for i, c in enumerate(cases) if not (22 <= i < 29)]  # family 92 drops to 16 cases
    result = run_harness(cases)
    assert not result.ok
    assert result.failing_indexes == [3] and result.malformed_indexes == [5, len(cases) - 1]
    assert result.family_mismatch_indexes == [7]
    assert result.small_families == ["92"]
    text = result.summary()
    assert "02910099990001" not in text and "9001" not in text  # never a value in the output


def test_harness_legacy_only_style_0000_cases(tmp_path: Path) -> None:
    """Synthetic legacy-only cases: counted in their family, refused by the build path, parsed exactly."""
    cases: list[Any] = _synthetic_cases(["91", "92"], 20)
    for i in (21, 22, 23):  # three legacy cases of family 92 (not the belt family)
        c = dict(cases[i])
        c["style_no"] = "0000"
        c["expected_code"] = "02" + c["type_code"] + c["category_code"] + c["product_no"] + "0000"
        cases[i] = c
    path = tmp_path / "synthetic_legacy.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    result = run_harness(json.loads(path.read_text(encoding="utf-8")))
    assert result.ok, result.summary()
    assert result.per_family == {"91": 20, "92": 20}
    assert (result.legacy_only, result.legacy_per_family) == (3, {"92": 3})
    assert "legacy_only_style_0000=3" in result.summary()
    with pytest.raises(ValidationFailed) as exc:
        coderule.build_code("92", cases[21]["category_code"], cases[21]["product_no"], "0000")
    assert exc.value.errors[0].code == "STYLE_0000_LEGACY_ONLY"
    # a legacy case whose code does not carry its segments fails like any other case
    bad = [*cases]
    bad[22] = {**bad[22], "expected_code": bad[22]["expected_code"][:6] + "9998" + "0000"}
    assert run_harness(bad).failing_indexes == [22]


def test_rev0230_c77_disagreement_fails_and_is_counted_by_index_only() -> None:
    cases: list[Any] = _synthetic_cases(["91", "92"], 20)
    for i in range(20, 40):  # family 92 carries the Order form lookup
        cases[i] = {**cases[i], "category_code_order_form": cases[i]["category_code"]}
    ok = run_harness(cases)
    assert ok.ok, ok.summary()
    assert (ok.c77_checked, ok.c77_disagree_indexes) == (20, [])
    assert "c77_checked=20 c77_disagree=0" in ok.summary()
    bad = [*cases]
    bad[25] = {**bad[25], "category_code_order_form": "98"}  # synthetic categories are 00..06
    result = run_harness(bad)
    assert not result.ok and result.c77_disagree_indexes == [25]
    assert "c77_checked=20 c77_disagree=1 c77_first_indexes=[25]" in result.summary()
    assert result.failing_indexes == [25]  # golden_case_problems also refuses the case (GOLDEN_CASE_MISMATCH)
    assert run_harness(_synthetic_cases(["91"], 20)).c77_checked == 0  # absent field: never claimed


def test_rev0231_belt_family_needs_20_belt_checked_cases() -> None:
    cases: list[Any] = _synthetic_cases(["91", "92"], 20)  # family 91 is the belt family (20 with segments)
    ok = run_harness(cases)
    assert ok.ok, ok.summary()
    assert ok.belt_checked_per_family == {"91": 20} and "belt_checked=20" in ok.summary()
    # a belt family with fewer than 20 cases that carry both segments fails
    fewer = [*cases]
    for i in range(5):
        fewer[i] = {k: v for k, v in fewer[i].items() if k not in ("buckle_type_code", "belt_width_code")}
    result = run_harness(fewer)
    assert not result.ok and result.belt_families_below_minimum == ["91"]
    assert result.belt_checked_per_family == {"91": 15}
    # a declared belt family without any belt segment fails instead of passing unnoticed
    plain = _synthetic_cases(["92", "93"], 20)
    plain = [{k: v for k, v in c.items() if k not in ("buckle_type_code", "belt_width_code")} for c in plain]
    assert run_harness(plain).ok
    declared = run_harness(plain, belt_families=frozenset({"93"}))
    assert not declared.ok and declared.belt_checked_per_family == {"93": 0}
    # belt_width_source is evidence text only
    with_source = [{**c, "belt_width_source": "synthetic sheet"} if c["family"] == "91" else c for c in cases]
    assert run_harness(with_source).ok


def test_rev0231_legacy_disputed_cases_are_reported_not_failed_not_counted() -> None:
    cases: list[Any] = _synthetic_cases(["91", "92"], 20)
    disputed = [
        {**cases[0], "expected_code": "02910099990001", "legacy_disputed": "synthetic: planning disputes it"},
        {**cases[21], "legacy_disputed": "synthetic: duplicate legacy row"},
    ]
    result = run_harness([*cases, *disputed])
    assert result.ok, result.summary()
    assert result.legacy_disputed == 2 and "legacy_disputed=2" in result.summary()
    assert result.per_family == {"91": 20, "92": 20} and result.belt_checked_per_family == {"91": 20}
    # disputed cases never make up a minimum: 19 real belt cases + 1 disputed still fail
    short = [*cases[1:], {**cases[0], "legacy_disputed": "synthetic"}]
    short_result = run_harness(short)
    assert short_result.small_families == ["91"] and short_result.belt_families_below_minimum == ["91"]
    with pytest.raises(ValueError):
        coderule.GoldenCase.from_mapping({**cases[0], "legacy_disputed": " "})  # a reason is required


# --------------------------------------------------------------------------------------- real data
def test_planning_golden_cases_reproduce_exactly() -> None:
    """Real DEC-005 golden cases (work machine only; the file is produced by the orchestrator)."""
    name = os.environ.get(ENV, "").strip()
    if not name:
        pytest.skip(f"{ENV} is not set: the real Planning golden file exists only on the work machine (R-38)")
    path = Path(name).resolve()
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        pytest.fail(
            f"{ENV} points inside the repository; real golden data must stay outside Git", pytrace=False
        )
    if not path.is_file():
        pytest.fail(f"{ENV} does not name a readable file", pytrace=False)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pytest.fail("the golden file is not valid UTF-8 JSON", pytrace=False)
    if not isinstance(raw, list) or not raw:
        pytest.fail("the golden file must be a non-empty JSON list", pytrace=False)
    result = run_harness(raw, belt_families=declared_belt_families())
    print(f"golden harness: {result.summary()}")  # counts only
    if not result.ok:
        pytest.fail(f"golden cases do not pass: {result.summary()}", pytrace=False)
