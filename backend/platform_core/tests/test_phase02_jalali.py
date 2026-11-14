"""Jalali conversion of the technical numbers (DEC-058 amendment 2026-11-14): known dates, Nowruz boundaries,
month lengths and leap years, the Asia/Tehran instant boundary, and ``first_free_style_no`` (REV-0232)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from platform_core.engine.errors import ValidationFailed
from platform_core.product_identity import coderule
from platform_core.product_identity.jalali import is_leap_jalali_year, jalali_year_tehran, to_jalali

# published Nowruz (1 Farvardin) dates and other fixed points of the Iranian calendar
KNOWN = [
    (date(1921, 3, 21), (1300, 1, 1)),
    (date(1979, 2, 11), (1357, 11, 22)),
    (date(2019, 3, 21), (1398, 1, 1)),
    (date(2020, 3, 20), (1399, 1, 1)),
    (date(2021, 3, 20), (1399, 12, 30)),  # 1399 is a leap year
    (date(2021, 3, 21), (1400, 1, 1)),
    (date(2022, 3, 21), (1401, 1, 1)),
    (date(2023, 3, 21), (1402, 1, 1)),
    (date(2024, 3, 20), (1403, 1, 1)),
    (date(2025, 3, 20), (1403, 12, 30)),  # 1403 is a leap year
    (date(2025, 3, 21), (1404, 1, 1)),
    (date(2026, 3, 20), (1404, 12, 29)),  # 1404 is not a leap year
    (date(2026, 3, 21), (1405, 1, 1)),
    (date(2026, 9, 22), (1405, 6, 31)),
    (date(2026, 9, 23), (1405, 7, 1)),
    (date(2026, 11, 14), (1405, 8, 23)),
]


@pytest.mark.parametrize(("gregorian", "jalali"), KNOWN)
def test_known_dates(gregorian: date, jalali: tuple[int, int, int]) -> None:
    assert to_jalali(gregorian) == jalali


def test_leap_years_of_the_33_year_cycle() -> None:
    assert [y for y in range(1395, 1412) if is_leap_jalali_year(y)] == [1395, 1399, 1403, 1408]


def test_every_day_of_1395_to_1410_advances_by_one_with_the_right_month_lengths() -> None:
    d = date(2016, 3, 20)  # 1395/01/01
    prev = to_jalali(d)
    assert prev == (1395, 1, 1)
    lengths: dict[tuple[int, int], int] = {(1395, 1): 1}
    while prev[0] < 1411:
        d += timedelta(days=1)
        cur = to_jalali(d)
        y, m, day = prev
        if cur[2] == 1:
            assert (cur[0], cur[1]) == ((y, m + 1) if m < 12 else (y + 1, 1)), (prev, cur)
        else:
            assert cur == (y, m, day + 1), (prev, cur)
        lengths[(cur[0], cur[1])] = cur[2]
        prev = cur
    for (y, m), n in lengths.items():
        if y < 1411:
            expected = 31 if m <= 6 else 30 if m <= 11 else (30 if is_leap_jalali_year(y) else 29)
            assert n == expected, (y, m, n)


def test_the_year_of_an_instant_is_the_tehran_local_year() -> None:
    """1404/12/29 23:59:59 Tehran (UTC+3:30) is still 1404; one second later is 1405/01/01."""
    assert jalali_year_tehran(datetime(2026, 3, 20, 20, 29, 59, tzinfo=UTC)) == 1404
    assert jalali_year_tehran(datetime(2026, 3, 20, 20, 30, 0, tzinfo=UTC)) == 1405
    with pytest.raises(ValueError):
        jalali_year_tehran(datetime(2026, 3, 20, 20, 30))  # naive: refused


# ------------------------------------------------------------------------------- REV-0232 style numbers
def test_first_free_style_no_examples() -> None:
    assert coderule.first_free_style_no([]) == ("0001", None)
    assert coderule.first_free_style_no(["0001", "0002"]) == ("0003", None)
    assert coderule.first_free_style_no(["0001", "0003"]) == ("0004", "0003")
    assert coderule.first_free_style_no(["0001", "0003", "0004"]) == ("0005", "0004")
    assert coderule.first_free_style_no(["0000"]) == ("0002", None)  # a legacy 0000 style counts as a style
    with pytest.raises(ValidationFailed) as exc:  # count + 1 = 9999 taken and nothing free after it
        coderule.first_free_style_no([f"{n:04d}" for n in range(2, 10000)])
    assert exc.value.errors[0].code == "STYLE_NO_EXHAUSTED"


@given(st.sets(st.integers(min_value=0, max_value=60), max_size=40))
def test_first_free_style_no_is_free_and_not_below_count_plus_one(used_numbers: set[int]) -> None:
    used = [f"{n:04d}" for n in used_numbers]
    number, collided = coderule.first_free_style_no(used)
    assert number not in used  # never a duplicate
    assert int(number) >= len(used) + 1  # count + 1 or the first free number after it
    assert (collided is None) == (f"{len(used) + 1:04d}" not in used)
    between = range(len(used) + 1, int(number))
    assert all(f"{n:04d}" in used for n in between)  # the FIRST free one
