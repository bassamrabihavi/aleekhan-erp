"""The synthetic Planning workbook of the PHASE_02 / 02.6 import tests and the ops drill (02.8, REV-0275:
moved from ``platform_core.tests.test_phase02_planning_import``).

SYNTHETIC only, labelled «ساختگی»: type segments ``9x``, product numbers ``9xxx``, no real type list,
category, code, serial, customer or person value (DEC-005 / DEC-028 / DEC-046 / DEC-060, R-38). Written with
openpyxl to a caller-given path outside the repository.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SYN = "ساختگی"

# ------------------------------------------------------------------------------------ synthetic workbook
SORCE: dict[str, Any] = {
    # header row 1 (Persian): the category column of a type carries the type's name (header detection)
    "BE1": "کفش",
    "BF1": "کمربند",
    "BG1": f"ستون {SYN}",
    # header row 2 (English labels, 02.6 fix2): never data, never a conflict
    "E2": "Product type",
    "O2": "Code",
    "BE2": "Shoe category",
    "BF2": "Belt category",
    "BG2": "Other",
    # data from row 3; the type list is the contiguous E block E3..E7
    "E3": "کفش",
    "O3": "91",
    "BE3": f"دسته {SYN} الف",
    "BF3": f"دسته {SYN} کمربند",
    "E4": "كمربند",  # Arabic kaf: normalised to the Persian word (DEC-058 belt)
    "O4": "92",
    "BE4": f"دسته {SYN} ب",
    "E5": "کیف",
    "O5": "93",
    "E6": f"نوع {SYN} بی‌واحد",  # not in the DEC-058 unit list -> conflict, not created
    "O6": "94",
    "E7": "جیبی",
    "O7": 95,  # a number, not 2-digit text -> conflict
    # E8 empty: end of the type block. The category columns continue below it.
    "O8": "07",
    "BE8": f"دسته {SYN} ج",
    "BG8": f"دسته {SYN} بی‌ستون",  # column without a type -> conflict
    # an unrelated list further down column E (below the gap): never a type (02.6 fix2)
    "E10": f"برچسب {SYN}",
    "E11": 5,
    "E12": 7.5,
    "A1": f"شخص {SYN}",  # a column the importer never reads
}
NORDER: dict[str, Any] = {
    "A1": "نوع",
    "FZ1": "کد",
    **{f"A{r}": "کفش" for r in range(2, 11)},
    "C2": "9001", "D2": "0001", "FZ2": "02910790010001",
    "C3": "9001", "D3": "0001", "FZ3": "02910790010001",  # same code, same pair (an order repeat)
    "C4": "9001", "D4": "0002", "FZ4": "02910790010002",
    "C5": "9001", "D5": "0003", "FZ5": "02910790010003",
    "C6": "9001", "D6": "0004", "FZ6": "02910790010003",  # same code, another pair -> conflict
    "FZ7": "0291079001A001",  # not 14 digits -> disputed
    "FZ8": 2910790010005,  # a number (leading zero lost) -> disputed
    "FZ9": "03910790010001",  # not the product prefix -> disputed
    "FZ10": "02920790010000",  # style 0000: legacy only, registered
    "E2": f"مشتری {SYN}",  # a column the importer never reads
    # serials (NOrder!B) for the guard report
    "B2": 100, "B3": "101", "B4": "S102", "B5": "103-1", "B6": 63000, "B7": "0104", "B8": 100,
    "B9": 62999.0, "B10": "BG105",
}  # fmt: skip
CODDING: dict[str, Any] = {"K1": "کد", "K2": "02930790020001", "K3": "02910790010001", "K4": f"x{SYN}"}


def write_workbook(path: Path, sheets: Mapping[str, Mapping[str, Any]]) -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, cells in sheets.items():
        ws = wb.create_sheet(name)
        for ref, value in cells.items():
            ws[ref] = value
    wb.save(path)
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_sheets(**over: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    sheets = {"Sorce": dict(SORCE), "NOrder": dict(NORDER), "Codding": dict(CODDING)}
    for name, cells in over.items():
        sheets[name].update(cells)
    return sheets
