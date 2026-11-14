"""Jalali (Solar Hijri) calendar conversion for technical numbers (PHASE_02 / 02.4, DEC-058 amendment
2026-11-14: ``SO-<jalali year>-<6+ digits>``, likewise ``CU-`` and ``CR-``).

No third-party dependency: this is the well-known arithmetic of the ``jalaali-js`` / ``jalaali-python``
libraries (Kazimierz M. Borkowski's 2820-year-free break table, valid for Jalali years -61 .. 3177), reduced
to Gregorian -> Jalali. It is verified by unit tests against published Nowruz dates and month lengths
(``tests/test_phase02_jalali.py``), including the boundary 1404/12/29 -> 1405/01/01 = 2026-03-21 (Tehran).

The Jalali year of a technical number is the year of its **creation instant in Asia/Tehran local time**
(:func:`jalali_year_tehran`); the instant is the database clock (``db_now``) of the creating transaction.
Dates are stored in UTC; this module only derives the number prefix and is never used to store a date.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final
from zoneinfo import ZoneInfo

TEHRAN: Final = ZoneInfo("Asia/Tehran")

# Jalali years at which the 33-year leap cycle pattern breaks (Borkowski)
_BREAKS: Final = (
    -61,
    9,
    38,
    199,
    426,
    686,
    756,
    818,
    1111,
    1181,
    1210,
    1635,
    2060,
    2097,
    2192,
    2262,
    2324,
    2394,
    2456,
    3178,
)


def _div(a: int, b: int) -> int:
    """Integer division truncating toward zero (the ``~~(a / b)`` of the reference implementation)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def _mod(a: int, b: int) -> int:
    return a - _div(a, b) * b


def _jal_cal(jy: int) -> tuple[int, int]:
    """``(leap, march)``: ``leap`` = years since the last leap year (0 = ``jy`` is a leap year), ``march`` =
    the day of March (Gregorian year ``jy + 621``) on which Farvardin 1 of ``jy`` falls."""
    if jy < _BREAKS[0] or jy >= _BREAKS[-1]:
        raise ValueError(f"Jalali year {jy} is outside the supported range")
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    for jm in _BREAKS[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j += _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return leap, march


def is_leap_jalali_year(jy: int) -> bool:
    return _jal_cal(jy)[0] == 0


def to_jalali(d: date) -> tuple[int, int, int]:
    """Gregorian calendar date -> ``(year, month, day)`` in the Jalali calendar."""
    gy = d.year
    jy = gy - 621
    leap, march = _jal_cal(jy)
    k = (d - date(gy, 3, march)).days
    if k >= 0:
        if k <= 185:  # the first six months have 31 days
            return jy, 1 + k // 31, k % 31 + 1
        k -= 186
    else:
        jy -= 1
        k += 179
        if leap == 1:  # the previous Jalali year was a leap year: Esfand has 30 days
            k += 1
    return jy, 7 + k // 30, k % 30 + 1


def jalali_year_tehran(instant: datetime) -> int:
    """The Jalali year of an aware instant in Asia/Tehran local time."""
    if instant.tzinfo is None:
        raise ValueError("an aware datetime is required (UTC from the database)")
    return to_jalali(instant.astimezone(TEHRAN).date())[0]
