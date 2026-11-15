"""Planning workbook import (PHASE_02 / 02.6): the product-type / category catalogue and the legacy
14-digit code registry, from the DEC-037 baseline workbook, through the integration framework (staging ->
validate -> apply).

Owned by the Identity module: the applier below is the only writer of ``identity_product_class`` /
``identity_product_code`` rows of provenance IMP / LEG (``master.py``: types and categories are never created
in-app). The integration framework stores provenance, staging rows, freshness and the conflict queue; it never
writes Identity tables.

What is read (and nothing else - the workbook also holds customers, people and order data that are never read
here, DEC-028 / DEC-060)::

    Sorce   E (type name), O (2-digit code), BE..BI (category names, one column per type), header row
    NOrder  A (type name), C (product no.), D (style no.), FZ (14-digit code)      - order rows: codes only
    Codding <operator-given column> (14-digit code)                               - optional

How (never executes anything): the bytes are hashed and compared with the operator's
``--expected-sha256`` (the registered intake hash, DEC-037; not stored in the repo). An encrypted workbook is
decrypted **in memory** with ``msoffcrypto`` only when a password is given (env ``ALEEKHAN_SRC_PASSWORD``,
never printed or logged); openpyxl opens it ``read_only`` + ``data_only`` + ``keep_vba=False`` (cached
values; macros are neither loaded nor run).

Rules applied (APPROVED decisions only; anything else becomes a conflict item, never a guess):

* **Types** (DEC-005 E-2): ``Sorce!E`` name -> ``Sorce!O`` code (2-digit **text**; a number or another
  width is ``catalogue_code_invalid``). Duplicate code or duplicate name -> conflict, none of them applied.
  **Unit** (DEC-058): shoe = PAIR; bag, belt, pocket item, accessory, set = PIECE, matched on the normalised
  name; a type outside that list -> ``catalogue_unit_not_decided`` and the type is not created (its
  categories neither). Belt (DEC-005) -> product-number scheme buckle + width; every other type -> max + 1.
* **Categories** (the ``NOrder!FY`` path, type-keyed): ``Sorce!BE..BI`` name -> ``Sorce!O`` code of the same
  row. Which column belongs to which type: the operator's explicit map (``--category-columns BE=01,...``) or,
  without it, the header cell of the column equal to a type name; an unmapped column with values ->
  ``catalogue_category_column_unmapped``.
* **Legacy codes** (DEC-005 B1 / Q-D, amendments 2026-11-13 / 2026-11-14): distinct ``NOrder!FZ`` and
  ``Codding`` values that are 14-digit text with prefix ``02`` (style ``0000`` accepted as legacy) are
  registered LEG, ``RESERVED / ERP_PENDING`` (``ERP_MATCHED`` only through a Rahkaran import). Every other
  value -> ``legacy_code_disputed``: ONE item per sheet and distinct value (02.7, REV-0261; DECISION_LOG
  2026-11-15 "one decision per distinct value"), with ``row_count`` and the cell references of every row that
  carries it, identical (DUPLICATE_PAYLOAD) order rows included; the raw value stays in its staging rows,
  never corrected, and the decision on the item covers all of those rows. The
  code is authoritative (belt rows included); a code whose order rows show more than one (product, style)
  pair -> ``legacy_code_multiple_product_style`` and the code is registered without a style link. A code is
  linked to a style only when exactly that style (type, category, product, style segments) exists and has no
  other live code; otherwise it stays unlinked.
* **Never overwrite**: a value that differs from an existing official row -> ``catalogue_value_changed``.
  Re-importing the same file is a no-op (one batch per source + SHA-256, the batch is already APPLIED).

The apply is one transaction (``imports.apply_batch_with_retry``): partial official rows never survive a
failure, the batch stays VALIDATED with its staging rows and can be applied again. Conflict items are raised
inside the same transaction (they belong to the applied batch).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Final

from django.conf import settings
from django.db import transaction

from platform_core.authz.policy import Caller
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.dbrules import db_rules
from platform_core.engine.errors import FieldError, ValidationFailed
from platform_core.engine.redaction import normalize_key
from platform_core.engine.uow import UnitOfWork
from platform_core.integration import imports as im
from platform_core.integration.conflicts import raise_conflict
from platform_core.integration.models import (
    BatchStatus,
    ImportBatch,
    IntegrationSource,
    RowStatus,
    StagingRow,
)
from platform_core.schema_common import ProvenanceKind

from . import coderule
from .models import (
    PRODUCT_CODE_NAMESPACE,
    ClassLevel,
    ErpStatus,
    MasterStatus,
    ProductClass,
    ProductCode,
    ProductCodeStatus,
    ProductNoScheme,
    Style,
)

SOURCE_CODE: Final = "planning_catalogue_xlsm"
TRANSFORM_VERSION: Final = "planning_catalogue.v1"
PASSWORD_ENV: Final = "ALEEKHAN_SRC_PASSWORD"  # noqa: S105 - the NAME of the variable, never a value
OLE_MAGIC: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # encrypted OOXML (or legacy .xls) container
ZIP_MAGIC: Final = b"PK"
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
TWO_DIGITS_RE: Final = re.compile(r"[0-9]{2}")
CODE14_RE: Final = re.compile(r"[0-9]{14}")
COLUMN_RE: Final = re.compile(r"[A-Z]{1,3}")
# TECHNICAL DEFAULT (not a business rule): size limit of the server-side Planning commands. The registered
# baseline is ~70 MB, above the generic 50 MB upload limit (``imports.MAX_FILE_BYTES``, unchanged); the file
# is read from the server disk by the operator's command, never uploaded.
MAX_PLANNING_WORKBOOK_BYTES: Final = 128 * 1024 * 1024

# DEC-058 (APPROVED 2026-11-12): unit per product type, by the type's name. Keys are normalised with
# ``redaction.normalize_key`` (NFKC, case fold, Arabic -> Persian yeh/kaf, ZWNJ / spaces removed) before
# matching; no fuzzy matching beyond that. A type outside this list is a conflict, never a guess.
DEC058_UNIT_BY_TYPE_NAME: Final[Mapping[str, str]] = {
    "کفش": "PAIR",
    "کیف": "PIECE",
    "کمربند": "PIECE",
    "جیبی": "PIECE",
    "اکسسوری": "PIECE",
    "ست": "PIECE",
}
# DEC-005: the belt type is numbered buckle-type code + width; every other type max + 1
BELT_TYPE_NAMES: Final = frozenset({"کمربند"})

PART_SORCE: Final = "sorce"
PART_SORCE_HEADER: Final = "sorce_header"
PART_NORDER: Final = "norder_code"
PART_CODDING: Final = "codding_code"


def _norm(text: str) -> str:
    return normalize_key(text)


_UNIT_BY_NORM: Final = {_norm(k): v for k, v in DEC058_UNIT_BY_TYPE_NAME.items()}
_BELT_NORM: Final = frozenset(_norm(n) for n in BELT_TYPE_NAMES)


# --------------------------------------------------------------------------------------------- layout
@dataclass(frozen=True)
class Layout:
    """Where the values are (PLANNING_EXTRACTION_SUMMARY E-1..E-6). Defaults are the baseline layout."""

    sorce_sheet: str = "Sorce"
    type_name_col: str = "E"
    code_col: str = "O"
    category_cols: tuple[str, ...] = ("BE", "BF", "BG", "BH", "BI")
    # Sorce has TWO header rows (02.6 fix2): row 1 = Persian labels (the category columns carry the type
    # names, used for the column -> type detection), row 2 = English labels. Data starts after them.
    header_row: int = 1
    header_rows: int = 2
    norder_sheet: str = "NOrder"
    norder_type_col: str = "A"
    norder_product_col: str = "C"
    norder_style_col: str = "D"
    norder_code_col: str = "FZ"
    norder_serial_col: str = "B"
    norder_first_row: int = 2
    codding_sheet: str = "Codding"
    codding_code_col: str | None = None
    codding_first_row: int = 2
    # explicit category column -> product type code (overrides the header detection)
    category_column_types: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        cols = [self.type_name_col, self.code_col, *self.category_cols, self.norder_type_col]
        cols += [self.norder_product_col, self.norder_style_col, self.norder_code_col, self.norder_serial_col]
        cols += [self.codding_code_col] if self.codding_code_col else []
        cols += list(self.category_column_types)
        for c in cols:
            if not COLUMN_RE.fullmatch(c):
                raise ValueError("a column is given as letters (e.g. BE)")
        for c, t in self.category_column_types.items():
            if c not in self.category_cols or not TWO_DIGITS_RE.fullmatch(t):
                raise ValueError("--category-columns maps a category column to a 2-digit type code")
        if len(set(self.category_column_types.values())) != len(self.category_column_types):
            raise ValueError("--category-columns maps two columns to the same type")
        if min(self.header_row, self.header_rows, self.norder_first_row, self.codding_first_row) < 1:
            raise ValueError("row numbers start at 1")
        if self.header_row > self.header_rows:
            raise ValueError("the detection header row is one of the header rows")

    @property
    def first_row(self) -> int:
        """First data row of ``Sorce`` (after all header rows)."""
        return self.header_rows + 1


def parse_category_columns(text: str) -> dict[str, str]:
    """``"BE=01,BF=02"`` -> ``{"BE": "01", "BF": "02"}`` (validated by :class:`Layout`)."""
    out: dict[str, str] = {}
    for part in (p.strip() for p in text.split(",") if p.strip()):
        col, sep, code = part.partition("=")
        if not sep:
            raise ValueError("--category-columns expects COLUMN=TYPECODE pairs")
        out[col.strip().upper()] = code.strip()
    return out


# ------------------------------------------------------------------------------------------- file guards
def refuse(code: str, field_name: str = "file", detail: str = "") -> ValidationFailed:
    return ValidationFailed(detail or code, errors=[FieldError(field=field_name, code=code)])


def repository_root() -> Path:
    base = Path(settings.BASE_DIR).resolve()
    return base.parent if (base.parent / ".git").exists() else base


def outside_repository(path: Path) -> Path:
    """Private sources and golden files never live in the repository (DEC-028 / DEC-046, R-38)."""
    resolved = path.resolve()
    if resolved.is_relative_to(repository_root()):
        raise refuse("PATH_INSIDE_REPOSITORY", "path", "the file must be outside the repository")
    if not resolved.is_file():
        raise refuse("FILE_NOT_FOUND", "path")
    return resolved


def expected_hash(value: str) -> str:
    text = (value or "").strip().lower()
    if not SHA256_RE.fullmatch(text):
        raise refuse("SHA256_FORMAT", "expected_sha256")
    return text


@dataclass(frozen=True)
class SourceFile:
    path: Path
    data: bytes
    sha256: str
    mtime: datetime


def _streamed_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(im.HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def read_source_file(path: Path, *, expected_sha256: str, max_bytes: int | None = None) -> SourceFile:
    """Bytes of a workbook outside the repo whose SHA-256 is exactly the registered one (DEC-037).

    The hash is streamed from disk first (a wrong or oversized file is refused before anything is loaded); the
    bytes are then read into memory ONCE and checked again (the file must not change between the two reads).
    """
    limit = MAX_PLANNING_WORKBOOK_BYTES if max_bytes is None else max_bytes
    resolved = outside_repository(path)
    want = expected_hash(expected_sha256)
    size = resolved.stat().st_size
    if size > limit:
        raise refuse("FILE_TOO_LARGE")
    if size == 0:
        raise refuse("EMPTY_FILE")
    if _streamed_sha256(resolved) != want:
        raise refuse("SHA256_MISMATCH", "expected_sha256", "the file is not the registered workbook")
    data = resolved.read_bytes()
    if len(data) > limit or hashlib.sha256(data).hexdigest() != want:
        raise refuse("FILE_CHANGED_WHILE_READING")
    mtime = datetime.fromtimestamp(resolved.stat().st_mtime, UTC)
    return SourceFile(resolved, data, want, mtime)


def open_workbook(data: bytes, *, password: str | None) -> Any:
    """openpyxl workbook (read only, cached values, no VBA). Decrypts in memory when encrypted + password."""
    import openpyxl

    buf = data
    if data[:8] == OLE_MAGIC:
        if not password:
            raise refuse("WORKBOOK_ENCRYPTED", detail=f"encrypted workbook: set {PASSWORD_ENV}")
        import msoffcrypto

        try:
            office = msoffcrypto.OfficeFile(io.BytesIO(data))
            office.load_key(password=password)
            out = io.BytesIO()
            office.decrypt(out)
        except Exception:  # never echo the library message (it may carry key material context)
            raise refuse("WORKBOOK_DECRYPT_FAILED") from None
        buf = out.getvalue()
    elif data[:2] != ZIP_MAGIC:
        raise refuse("WORKBOOK_UNREADABLE")
    try:
        return openpyxl.load_workbook(
            io.BytesIO(buf), read_only=True, keep_vba=False, data_only=True, keep_links=False
        )
    except Exception:
        raise refuse("WORKBOOK_UNREADABLE") from None


# ------------------------------------------------------------------------------------------- extraction
def cell_value(value: Any) -> dict[str, Any] | None:
    """A cell as staged: ``{"t": type, "v": raw value}`` (text never trimmed); ``None`` for an empty cell."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return {"t": "b", "v": value}
    if isinstance(value, int):
        return {"t": "n", "v": value}
    if isinstance(value, float):
        return (
            {"t": "n", "v": value}
            if value == value and abs(value) != float("inf")
            else {"t": "e", "v": "NaN"}
        )
    if isinstance(value, str):
        return {"t": "s", "v": value}
    if isinstance(value, datetime):
        return {"t": "d", "v": value.isoformat()}
    return {"t": "o", "v": str(value)}


def _col_index(col: str) -> int:
    from openpyxl.utils import column_index_from_string

    return int(column_index_from_string(col))


def _sheet(wb: Any, name: str, *, required: bool = True) -> Any:
    if name in wb.sheetnames:
        return wb[name]
    if required:
        raise refuse("SHEET_MISSING", "sheet")
    return None


def _read_columns(
    ws: Any, cols: Sequence[str], first_row: int
) -> Iterator[tuple[int, dict[str, dict[str, Any]]]]:
    idx = {c: _col_index(c) for c in cols}
    lo, hi = min(idx.values()), max(idx.values())
    for r, values in enumerate(
        ws.iter_rows(min_row=first_row, min_col=lo, max_col=hi, values_only=True), start=first_row
    ):
        cells: dict[str, dict[str, Any]] = {}
        for c, i in idx.items():
            pos = i - lo
            v = cell_value(values[pos]) if pos < len(values) else None
            if v is not None:
                cells[c] = v
        yield r, cells


@dataclass
class Extraction:
    rows: list[im.StagingInput]
    counts: Counter[str]


def extract(wb: Any, layout: Layout) -> Extraction:
    """Staging rows of the columns above only (sheet + row number; payload = part + raw cells)."""
    rows: list[im.StagingInput] = []
    counts: Counter[str] = Counter()
    ws = _sheet(wb, layout.sorce_sheet)
    _hr, header = next(_read_columns(ws, layout.category_cols, layout.header_row), (0, {}))
    if header:
        rows.append(
            im.StagingInput(
                row_number=layout.header_row,
                sheet_name=layout.sorce_sheet,
                payload={"part": PART_SORCE_HEADER, "cells": header},
            )
        )
    sorce_cols = [layout.type_name_col, layout.code_col, *layout.category_cols]
    # 02.6 fix2: the product types are ONLY the first contiguous non-empty block of column E after the header
    # rows; below its first gap column E holds an unrelated list, never staged (not a type candidate).
    # The category columns and the code column continue down as before.
    type_block = "before"
    for r, cells in _read_columns(ws, sorce_cols, layout.first_row):
        has_name = layout.type_name_col in cells
        if type_block == "before" and has_name:
            type_block = "inside"
        elif type_block == "inside" and not has_name:
            type_block = "after"
        if type_block == "after" and has_name:
            del cells[layout.type_name_col]
            counts["sorce_e_cells_below_type_block_not_staged"] += 1
        if cells:
            rows.append(
                im.StagingInput(
                    row_number=r, sheet_name=layout.sorce_sheet, payload={"part": PART_SORCE, "cells": cells}
                )
            )
            counts["sorce_rows"] += 1
    ws = _sheet(wb, layout.norder_sheet)
    norder_cols = [
        layout.norder_type_col,
        layout.norder_product_col,
        layout.norder_style_col,
        layout.norder_code_col,
    ]
    for r, cells in _read_columns(ws, norder_cols, layout.norder_first_row):
        if layout.norder_code_col not in cells:
            if cells:
                counts["norder_rows_without_code"] += 1
            continue
        rows.append(
            im.StagingInput(
                row_number=r, sheet_name=layout.norder_sheet, payload={"part": PART_NORDER, "cells": cells}
            )
        )
        counts["norder_rows"] += 1
    if layout.codding_code_col:
        ws = _sheet(wb, layout.codding_sheet)
        for r, cells in _read_columns(ws, [layout.codding_code_col], layout.codding_first_row):
            if cells:
                rows.append(
                    im.StagingInput(
                        row_number=r,
                        sheet_name=layout.codding_sheet,
                        payload={"part": PART_CODDING, "cells": cells},
                    )
                )
                counts["codding_rows"] += 1
    return Extraction(rows, counts)


# ------------------------------------------------------------------------------------------------ apply
@dataclass(frozen=True)
class Cell:
    row: StagingRow
    col: str

    @property
    def raw(self) -> dict[str, Any] | None:
        cells = self.row.payload.get("cells", {})
        value = cells.get(self.col) if isinstance(cells, dict) else None
        return value if isinstance(value, dict) else None

    @property
    def ref(self) -> str:
        return f"{self.col}{self.row.row_number}"

    @property
    def text(self) -> str | None:
        """Text cell content (raw, untrimmed) or ``None`` for an empty / non-text cell."""
        raw = self.raw
        return raw["v"] if raw is not None and raw.get("t") == "s" and isinstance(raw.get("v"), str) else None

    @property
    def raw_text(self) -> str | None:
        raw = self.raw
        return None if raw is None else str(raw.get("v"))

    def details(self, reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "sheet": self.row.sheet_name,
            "cell": self.ref,
            "staging_row_id": self.row.pk,
            "reason": reason,
            **extra,
        }


@dataclass
class ApplyState:
    uow: UnitOfWork
    batch: ImportBatch
    layout: Layout
    counts: Counter[str] = field(default_factory=Counter)
    conflicts: int = 0
    applied: int = 0

    def conflict(self, kind: str, key: str, details: Mapping[str, Any]) -> None:
        result = raise_conflict(
            self.uow.ctx, source_code=SOURCE_CODE, kind=kind, key=key, details=details, batch_id=self.batch.id
        )
        self.conflicts += 1
        self.counts[f"conflict.{kind}"] += 1
        if not result.created:
            self.counts["conflicts_already_open"] += 1


def _code_of(cell: Cell) -> str | None:
    text = cell.text
    return text if text is not None and TWO_DIGITS_RE.fullmatch(text) else None


def _provenance(cell: Cell, batch: ImportBatch, kind: str = ProvenanceKind.IMP) -> dict[str, Any]:
    return {
        "provenance_kind": kind,
        "import_batch": batch,
        "staging_row": cell.row,
        "source_sheet": cell.row.sheet_name,
        "source_cell_ref": cell.ref,
        "source_raw_value": (cell.raw_text or "")[:4000] or None,
        "transform_rule_version": TRANSFORM_VERSION,
    }


@dataclass(frozen=True)
class Entry:
    name_cell: Cell
    code_cell: Cell
    code: str
    label: str


def _entries(state: ApplyState, pairs: Iterable[tuple[Cell, Cell]], scope: str) -> list[Entry]:
    """Valid (name, code) entries of one level; invalid codes and duplicates become conflicts."""
    candidates: list[Entry] = []
    for name_cell, code_cell in pairs:
        label = (name_cell.text or name_cell.raw_text or "").strip()
        if not label:
            continue
        code = _code_of(code_cell)
        if code is None:
            state.conflict(
                "catalogue_code_invalid",
                f"{scope}:{code_cell.row.sheet_name}!{code_cell.ref}",
                code_cell.details("NOT_TWO_DIGIT_TEXT", scope=scope),
            )
            continue
        candidates.append(Entry(name_cell, code_cell, code, label))
    by_code: dict[str, list[Entry]] = defaultdict(list)
    by_name: dict[str, list[Entry]] = defaultdict(list)
    for e in candidates:
        by_code[e.code].append(e)
        by_name[_norm(e.label)].append(e)
    bad: set[int] = set()
    for code, group in sorted(by_code.items()):
        if len({_norm(e.label) for e in group}) > 1:
            state.conflict(
                "catalogue_code_duplicate",
                f"{scope}:code:{code}",
                {
                    "code": code,
                    "cells": [f"{e.name_cell.row.sheet_name}!{e.name_cell.ref}" for e in group][:20],
                },
            )
            bad.update(id(e) for e in group)
    for group in by_name.values():
        if len({e.code for e in group}) > 1:
            first = group[0]
            state.conflict(
                "catalogue_name_duplicate",
                f"{scope}:{first.name_cell.row.sheet_name}!{first.name_cell.ref}",
                {
                    "codes": sorted({e.code for e in group}),
                    "cells": [f"{e.name_cell.row.sheet_name}!{e.name_cell.ref}" for e in group][:20],
                },
            )
            bad.update(id(e) for e in group)
    seen: set[str] = set()
    out: list[Entry] = []
    for e in candidates:
        if id(e) in bad or e.code in seen:  # the same (name, code) twice: one entry
            continue
        seen.add(e.code)
        out.append(e)
    return out


def _class_written(state: ApplyState, obj: ProductClass) -> None:
    state.uow.audit(
        action="identity.product_class.import",
        resource_type="identity.product_class",
        resource_id=str(obj.pk),
        resource_version=obj.row_version,
        after={
            "level_key": obj.level_key,
            "segment_value": obj.segment_value,
            "status": obj.status,
            "uom": obj.uom_id,
            "product_no_scheme": obj.product_no_scheme,
        },
        scope={"batch_id": str(state.batch.id), "source_cell_ref": obj.source_cell_ref},
    )
    state.uow.emit(
        event_type="identity.product_class.imported",
        aggregate_type="identity.product_class",
        aggregate_id=str(obj.pk),
        aggregate_version=obj.row_version,
        payload={
            "id": str(obj.pk),
            "level_key": obj.level_key,
            "status": obj.status,
            "batch_id": str(state.batch.id),
        },
    )
    state.applied += 1


def _apply_types(state: ApplyState, sorce: list[StagingRow]) -> dict[str, ProductClass]:
    """Types of this file -> the official type rows that now exist for them (created or unchanged)."""
    lay = state.layout
    pairs = [(Cell(r, lay.type_name_col), Cell(r, lay.code_col)) for r in sorce]
    entries = _entries(state, pairs, "type")
    existing = {
        c.segment_value: c
        for c in ProductClass.objects.select_for_update().filter(level_key=ClassLevel.PRODUCT_TYPE)
    }
    by_label = {_norm(c.label_fa): c for c in existing.values()}
    result: dict[str, ProductClass] = {}
    for e in entries:
        norm = _norm(e.label)
        unit = _UNIT_BY_NORM.get(norm)
        scheme = (
            ProductNoScheme.BELT_BUCKLE_WIDTH if norm in _BELT_NORM else ProductNoScheme.SEQUENTIAL_PER_TYPE
        )
        if unit is None:
            state.conflict(
                "catalogue_unit_not_decided",
                f"type:{e.code}",
                e.name_cell.details("TYPE_NOT_IN_DEC058_UNIT_LIST", code=e.code),
            )
            state.counts["types_not_created_unit"] += 1
            continue
        current = existing.get(e.code)
        if current is not None:
            changed = [
                f
                for f, same in (
                    ("label_fa", _norm(current.label_fa) == norm),
                    ("uom", current.uom_id == unit),
                    ("product_no_scheme", current.product_no_scheme == scheme),
                )
                if not same
            ]
            if changed:
                state.conflict(
                    "catalogue_value_changed",
                    f"type:{e.code}",
                    e.name_cell.details("DIFFERS_FROM_OFFICIAL", code=e.code, fields=changed),
                )
            else:
                state.counts["types_unchanged"] += 1
                result[e.code] = current
            continue
        other = by_label.get(norm)
        if other is not None:
            state.conflict(
                "catalogue_value_changed",
                f"type:{e.code}",
                e.name_cell.details("NAME_UNDER_OTHER_CODE", code=e.code, official_code=other.segment_value),
            )
            continue
        with db_rules():
            obj = ProductClass.objects.create(
                level_key=ClassLevel.PRODUCT_TYPE,
                segment_value=e.code,
                label_fa=e.label,
                uom_id=unit,
                product_no_scheme=scheme,
                status=MasterStatus.ACTIVE,
                **_provenance(e.name_cell, state.batch),
            )
        obj.refresh_from_db()
        _class_written(state, obj)
        state.counts["types_created"] += 1
        existing[e.code] = obj
        by_label[norm] = obj
        result[e.code] = obj
    return result


def _column_types(
    state: ApplyState, header: StagingRow | None, sorce: list[StagingRow], types: Mapping[str, ProductClass]
) -> dict[str, str]:
    lay = state.layout
    used = {c for r in sorce for c in lay.category_cols if Cell(r, c).raw is not None}
    if lay.category_column_types:
        mapping = dict(lay.category_column_types)
        state.counts["category_columns_mapped_explicitly"] = len(mapping)
    else:
        by_name = {_norm(t.label_fa): code for code, t in types.items()}
        mapping = {}
        for c in lay.category_cols:
            label = Cell(header, c).text if header is not None else None
            code = by_name.get(_norm(label)) if label else None
            if code is not None:
                mapping[c] = code
        dup = {code for code, n in Counter(mapping.values()).items() if n > 1}
        mapping = {c: code for c, code in mapping.items() if code not in dup}
        state.counts["category_columns_mapped_by_header"] = len(mapping)
    for c in sorted(used - set(mapping)):
        state.conflict(
            "catalogue_category_column_unmapped",
            f"column:{lay.sorce_sheet}!{c}",
            {"sheet": lay.sorce_sheet, "column": c, "reason": "NO_PRODUCT_TYPE_FOR_COLUMN"},
        )
    return {c: code for c, code in mapping.items() if c in used}


def _apply_categories(
    state: ApplyState, header: StagingRow | None, sorce: list[StagingRow], types: Mapping[str, ProductClass]
) -> None:
    lay = state.layout
    for col, type_code in sorted(_column_types(state, header, sorce, types).items()):
        ptype = types.get(type_code)
        if ptype is None:  # the type was not created (unit not decided / conflict) or is unknown
            n = sum(1 for r in sorce if Cell(r, col).raw is not None)
            state.counts["categories_skipped_type_not_imported"] += n
            continue
        pairs = [(Cell(r, col), Cell(r, lay.code_col)) for r in sorce]
        entries = _entries(state, pairs, f"type:{type_code}/category")
        existing = {
            c.segment_value: c
            for c in ProductClass.objects.select_for_update().filter(
                level_key=ClassLevel.CATEGORY, parent=ptype
            )
        }
        by_label = {_norm(c.label_fa): c for c in existing.values()}
        for e in entries:
            norm = _norm(e.label)
            key = f"type:{type_code}/category:{e.code}"
            current = existing.get(e.code)
            if current is not None:
                if _norm(current.label_fa) != norm:
                    state.conflict(
                        "catalogue_value_changed",
                        key,
                        e.name_cell.details("DIFFERS_FROM_OFFICIAL", code=e.code, fields=["label_fa"]),
                    )
                else:
                    state.counts["categories_unchanged"] += 1
                continue
            other = by_label.get(norm)
            if other is not None:
                state.conflict(
                    "catalogue_value_changed",
                    key,
                    e.name_cell.details(
                        "NAME_UNDER_OTHER_CODE", code=e.code, official_code=other.segment_value
                    ),
                )
                continue
            with db_rules():
                obj = ProductClass.objects.create(
                    level_key=ClassLevel.CATEGORY,
                    parent=ptype,
                    segment_value=e.code,
                    label_fa=e.label,
                    status=MasterStatus.ACTIVE,
                    **_provenance(e.name_cell, state.batch),
                )
            obj.refresh_from_db()
            _class_written(state, obj)
            state.counts["categories_created"] += 1
            existing[e.code] = obj
            by_label[norm] = obj


_TYPE_MASKS: Final = {"n": "<number>", "b": "<bool>", "d": "<date>"}


def _mask(raw: dict[str, Any] | None) -> str:
    """Shape of a value without the value: digits -> 9, letters -> A, runs collapsed (``A9+-9``)."""
    if raw is None:
        return "<empty>"
    if raw.get("t") != "s":
        return _TYPE_MASKS.get(str(raw.get("t")), "<other>")
    out: list[str] = []
    for ch in str(raw.get("v")):
        m = "9" if ch.isdigit() else "A" if ch.isalpha() else "_" if ch.isspace() else ch
        if out and out[-1] in (m, m + "+"):
            out[-1] = m + "+"
        else:
            out.append(m)
    return "".join(out)[:32]


def legacy_code(raw: dict[str, Any] | None) -> tuple[str | None, str]:
    """``(code, "")`` for a valid legacy code (14-digit text, prefix 02, style 0000 allowed), else
    ``(None, reason)``."""
    if raw is None:
        return None, "EMPTY"
    if raw.get("t") != "s":
        return None, "NOT_TEXT"
    value = raw.get("v")
    if not isinstance(value, str) or not CODE14_RE.fullmatch(value):
        return None, "NOT_14_DIGITS"
    if not coderule.is_valid_code(value, legacy=True):
        return None, "NOT_PRODUCT_PREFIX"
    return value, ""


def _style_index() -> dict[str, uuid.UUID]:
    """``type seg + category seg + product no + style no`` -> style id (unique by the table constraints)."""
    out: dict[str, uuid.UUID] = {}
    for sid, t, c, p, s in Style.objects.values_list(
        "id",
        "product__product_type__segment_value",
        "category__segment_value",
        "product__product_no",
        "style_no",
    ):
        out[f"{t}{c}{p}{s}"] = sid
    return out


# 02.7 (REV-0261): at most this many cell references are listed on one disputed-value item (8 KiB details)
MAX_DISPUTED_CELL_REFS: Final = 100


def disputed_value_key(raw: dict[str, Any] | None) -> str:
    """A stable, value-free key of one distinct disputed cell value (type + value, SHA-256 prefix): equal
    values -> one conflict item, whatever their rows (DECISION_LOG 2026-11-15: one decision per distinct
    value). The value itself stays in its staging rows only."""
    if raw is None:
        return "empty"
    canon = json.dumps(
        {"t": raw.get("t"), "v": raw.get("v")}, ensure_ascii=False, sort_keys=True, default=str
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:24]


def _raise_disputed(state: ApplyState, disputed: Mapping[tuple[str, str], list[tuple[Cell, str]]]) -> None:
    """One ``legacy_code_disputed`` item per (sheet, distinct value), carrying the number of rows with that
    value and their cell references (the decision applies to every one of them)."""
    for (sheet, vkey), cells in disputed.items():
        cell, reason = cells[0]
        refs = [c.ref for c, _r in cells]
        state.conflict(
            "legacy_code_disputed",
            f"{sheet}!value:{vkey}",
            cell.details(
                reason,
                shape=_mask(cell.raw),
                status=ProductCodeStatus.DISPUTED.value,
                row_count=len(cells),
                cell_refs=refs[:MAX_DISPUTED_CELL_REFS],
                cell_refs_truncated=len(refs) > MAX_DISPUTED_CELL_REFS,
            ),
        )
        state.counts["legacy_values_disputed"] += 1
        state.counts["legacy_rows_disputed"] += len(cells)


def _apply_codes(state: ApplyState, norder: list[StagingRow], codding: list[StagingRow]) -> None:
    lay = state.layout
    first: dict[str, Cell] = {}
    pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    disputed: dict[tuple[str, str], list[tuple[Cell, str]]] = {}
    for rows, col, is_order in ((norder, lay.norder_code_col, True), (codding, lay.codding_code_col, False)):
        if not col:
            continue
        for r in sorted(rows, key=lambda x: (x.sheet_name, x.row_number)):
            cell = Cell(r, col)
            code, reason = legacy_code(cell.raw)
            if code is None:
                disputed.setdefault((r.sheet_name, disputed_value_key(cell.raw)), []).append((cell, reason))
                continue
            first.setdefault(code, cell)
            if is_order:
                product = Cell(r, lay.norder_product_col).raw_text or ""
                style = Cell(r, lay.norder_style_col).raw_text or ""
                pairs[code].add((product.strip(), style.strip()))
    _raise_disputed(state, disputed)
    multi = {code for code, p in pairs.items() if len(p) > 1}
    for code in sorted(multi):
        state.conflict(
            "legacy_code_multiple_product_style",
            f"code:{code}",
            first[code].details("MORE_THAN_ONE_PRODUCT_STYLE", code=code, pairs=len(pairs[code])),
        )
    state.counts["legacy_codes_distinct"] = len(first)
    registered = set(
        ProductCode.objects.filter(code_namespace=PRODUCT_CODE_NAMESPACE, code__in=list(first)).values_list(
            "code", flat=True
        )
    )
    styles = _style_index()
    live = set(
        ProductCode.objects.filter(
            status__in=[ProductCodeStatus.RESERVED, ProductCodeStatus.ACTIVE], style__isnull=False
        ).values_list("style_id", flat=True)
    )
    objs: list[ProductCode] = []
    linked = 0
    for code in sorted(first):
        if code in registered:
            state.counts["legacy_codes_unchanged"] += 1
            continue
        cell = first[code]
        style_id = styles.get(code[2:]) if code not in multi else None
        if style_id is not None and style_id in live:
            state.conflict(
                "legacy_code_style_has_other_code",
                f"code:{code}",
                cell.details("STYLE_HAS_ANOTHER_LIVE_CODE", code=code),
            )
            style_id = None
        if style_id is not None:
            live.add(style_id)
            linked += 1
        objs.append(
            ProductCode(
                code=code,
                code_namespace=PRODUCT_CODE_NAMESPACE,
                style_id=style_id,
                status=ProductCodeStatus.RESERVED,
                erp_status=ErpStatus.ERP_PENDING,
                **_provenance(cell, state.batch, ProvenanceKind.LEG),
            )
        )
    with db_rules():
        for start in range(0, len(objs), im.BULK_CHUNK):
            ProductCode.objects.bulk_create(objs[start : start + im.BULK_CHUNK])
    state.counts["legacy_codes_registered"] = len(objs)
    state.counts["legacy_codes_linked"] = linked
    state.counts["legacy_codes_unlinked"] = len(objs) - linked
    state.applied += len(objs)
    state.uow.audit(
        action="identity.product_code.legacy_register",
        resource_type="identity.legacy_code_import",
        resource_id=str(state.batch.id),
        after={
            "registered": len(objs),
            "linked": linked,
            "unchanged": state.counts["legacy_codes_unchanged"],
            "disputed": state.counts["legacy_values_disputed"],
            "multiple_product_style": len(multi),
        },
        scope={"batch_id": str(state.batch.id), "status": "RESERVED", "erp_status": "ERP_PENDING"},
    )
    state.uow.emit(
        event_type="identity.product_code.legacy_registered",
        aggregate_type="identity.legacy_code_import",
        aggregate_id=str(state.batch.id),
        aggregate_version=1,
        payload={
            "batch_id": str(state.batch.id),
            "registered": len(objs),
            "linked": linked,
            "unchanged": state.counts["legacy_codes_unchanged"],
        },
    )


def apply_planning_batch(uow: UnitOfWork, batch: ImportBatch, *, layout: Layout) -> im.ApplyOutcome:
    """The Identity applier of a ``planning_catalogue_xlsm`` batch (called inside ``imports.apply_batch``)."""
    state = ApplyState(uow, batch, layout)
    rows = list(
        StagingRow.objects.filter(batch=batch, validation_status=RowStatus.PENDING_REVIEW).order_by(
            "sheet_name", "row_number"
        )
    )
    parts: dict[str, list[StagingRow]] = defaultdict(list)
    for r in rows:
        parts[str(r.payload.get("part"))].append(r)
    # 02.7 (REV-0261): an order row identical to an earlier one (validation ERROR DUPLICATE_PAYLOAD and
    # nothing else) is still a row of the legacy register: it is counted on the disputed-value item of its
    # value (a valid code repeated changes nothing - one code row per distinct code)
    for r in StagingRow.objects.filter(
        batch=batch, validation_status=RowStatus.ERROR, error_codes=[im.ROW_DUPLICATE_PAYLOAD]
    ).order_by("sheet_name", "row_number"):
        part = str(r.payload.get("part"))
        if part in (PART_NORDER, PART_CODDING):
            parts[part].append(r)
            state.counts["legacy_duplicate_rows_counted"] += 1
    header = next(iter(parts[PART_SORCE_HEADER]), None)
    types = _apply_types(state, parts[PART_SORCE])
    _apply_categories(state, header, parts[PART_SORCE], types)
    _apply_codes(state, parts[PART_NORDER], parts[PART_CODDING])
    return im.ApplyOutcome(
        applied_count=state.applied, conflict_count=state.conflicts, counts=dict(state.counts)
    )


# --------------------------------------------------------------------------------------------- pipeline
@dataclass(frozen=True)
class ImportReport:
    batch_id: uuid.UUID
    status: str
    already_applied: bool
    attempts: int
    counts: Mapping[str, int]


def _system_ctx() -> RequestContext:
    return RequestContext(Actor.system(), request_id=uuid.uuid4())


def import_planning_workbook(
    path: Path,
    *,
    expected_sha256: str,
    layout: Layout | None = None,
    password: str | None = None,
    retry: im.ApplyRetryPolicy = im.APPLY_RETRY_POLICY,
) -> ImportReport:
    """receive -> stage -> validate -> apply (resumes a batch left at an earlier state; no-op if APPLIED)."""
    lay = layout or Layout()
    src = read_source_file(path, expected_sha256=expected_sha256)
    source = IntegrationSource.objects.filter(code=SOURCE_CODE).first()
    if source is None:
        raise refuse("SOURCE_NOT_SEEDED", "source")
    existing = ImportBatch.objects.filter(source=source, file_sha256=src.sha256).first()
    if existing is not None and existing.status == BatchStatus.APPLIED:
        return ImportReport(existing.id, existing.status, True, 0, {"row_count": existing.row_count})
    extraction: Extraction | None = None
    if existing is None or existing.status == BatchStatus.RECEIVED:
        wb = open_workbook(src.data, password=password)
        try:
            extraction = extract(wb, lay)
        finally:
            wb.close()
    ctx = _system_ctx()
    batch = im.receive_file(
        ctx,
        source_code=SOURCE_CODE,
        content=src.data,
        original_name=src.path.name,
        source_as_of=src.mtime,
        max_bytes=MAX_PLANNING_WORKBOOK_BYTES,
    ).batch
    if batch.status in (BatchStatus.REJECTED, BatchStatus.SUPERSEDED, BatchStatus.COMPENSATED):
        raise refuse("BATCH_CLOSED", "batch")
    if batch.status == BatchStatus.APPLIED:  # applied concurrently by another run
        return ImportReport(batch.id, batch.status, True, 0, {"row_count": batch.row_count})
    if batch.status == BatchStatus.RECEIVED:
        assert extraction is not None
        batch = im.stage_rows(ctx, batch.id, extraction.rows)
    if batch.status == BatchStatus.STAGED:
        batch = im.validate_batch(ctx, batch.id)
    run = im.apply_batch_with_retry(
        ctx, batch.id, applier=partial(apply_planning_batch, layout=lay), policy=retry
    )
    counts = {
        "row_count": run.batch.row_count,
        "error_row_count": run.batch.error_row_count,
        **(dict(extraction.counts) if extraction else {}),
        "applied": run.outcome.applied_count,
        "conflicts": run.outcome.conflict_count,
        **dict(run.outcome.counts),
    }
    return ImportReport(run.batch.id, run.batch.status, False, run.attempts, counts)


# --------------------------------------------------------------------------------------- serial guard
SERIAL_PLAIN_RE: Final = re.compile(r"[1-9][0-9]*")


def serial_guard_counts(wb: Any, layout: Layout, *, threshold: int) -> dict[str, Any]:
    """DEC-006 P-A check, read only: counts of legacy ``NOrder!B`` values, never a value.

    ``plain_*`` = plain integers (an integer cell, or text of digits without a leading zero); everything else
    is counted by its shape mask. ``plain_at_or_above_threshold`` must be 0 for the start 63001 to be safe.
    """
    ws = _sheet(wb, layout.norder_sheet)
    counts: Counter[str] = Counter()
    masks: Counter[str] = Counter()
    seen: Counter[int] = Counter()
    for _r, cells in _read_columns(ws, [layout.norder_serial_col], layout.norder_first_row):
        raw = cells.get(layout.norder_serial_col)
        if raw is None:
            continue
        counts["non_empty"] += 1
        value = raw.get("v")
        number: int | None = None
        if raw.get("t") == "n" and isinstance(value, int) and value >= 1:
            number = value
        elif raw.get("t") == "n" and isinstance(value, float) and value.is_integer() and value >= 1:
            number = int(value)
            counts["plain_from_integral_float"] += 1
        elif raw.get("t") == "s" and isinstance(value, str) and SERIAL_PLAIN_RE.fullmatch(value):
            number = int(value)
        if number is None:
            masks[_mask(raw)] += 1
            continue
        counts["plain_integer"] += 1
        seen[number] += 1
        if number >= threshold:
            counts["plain_at_or_above_threshold"] += 1
    counts["plain_values_duplicated"] = sum(1 for n in seen.values() if n > 1)
    return {
        "threshold": threshold,
        "non_empty": counts["non_empty"],
        "plain_integer": counts["plain_integer"],
        "plain_at_or_above_threshold": counts["plain_at_or_above_threshold"],
        "plain_from_integral_float": counts["plain_from_integral_float"],
        "plain_values_duplicated": counts["plain_values_duplicated"],
        "non_plain_total": sum(masks.values()),
        "non_plain_by_mask": dict(sorted(masks.items())),
        "safe_for_start": counts["plain_at_or_above_threshold"] == 0,
    }


# --------------------------------------------------------------------------------------- golden loader
GOLDEN_FILE_KEYS: Final = frozenset(
    {
        "type_code",
        "category_code",
        "product_no",
        "style_no",
        "expected_code",
        "family",
        "category_code_order_form",
        "buckle_type_code",
        "belt_width_code",
        "source_sheet",
        "source_cell_ref",
    }
)
MAX_GOLDEN_FILE_BYTES: Final = 20 * 1024 * 1024


def read_golden_file(path: Path) -> list[dict[str, Any]]:
    """The harness format (a JSON list of flat text objects) + ``source_sheet`` / ``source_cell_ref``; the
    harness-only fields (``legacy_disputed``, ``belt_width_source``) and unknown keys are refused. Problems
    are reported by index and field name only (never a value)."""
    resolved = outside_repository(path)
    if resolved.stat().st_size > MAX_GOLDEN_FILE_BYTES:
        raise refuse("FILE_TOO_LARGE")
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise refuse("NOT_JSON") from None
    if not isinstance(raw, list) or not raw:
        raise refuse("NOT_A_LIST")
    from .codes import HARNESS_ONLY_GOLDEN_FIELDS

    errors: list[FieldError] = []
    out: list[dict[str, Any]] = []
    for i, case in enumerate(raw):
        if not isinstance(case, dict):
            errors.append(FieldError(f"cases[{i}]", "NOT_AN_OBJECT"))
            continue
        for key in sorted(set(case) - GOLDEN_FILE_KEYS):
            code = "GOLDEN_FIELD_NOT_ALLOWED"
            name = key if key in HARNESS_ONLY_GOLDEN_FIELDS else "<unknown>"
            errors.append(FieldError(f"cases[{i}].{name}", code))
        for key in ("type_code", "category_code", "product_no", "style_no", "expected_code", "family"):
            if not isinstance(case.get(key), str):
                errors.append(FieldError(f"cases[{i}].{key}", "TEXT_REQUIRED"))
        for key in ("source_sheet", "source_cell_ref"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                errors.append(FieldError(f"cases[{i}].{key}", "REQUIRED"))
        expected = case.get("expected_code")
        if isinstance(expected, str) and (len(expected) != 14 or case.get("family") != expected[2:4]):
            errors.append(FieldError(f"cases[{i}].family", "FAMILY_NOT_TYPE_SEGMENT"))
        out.append(case)
    if errors:
        raise ValidationFailed("golden file refused; nothing was loaded", errors=errors)
    return out


CONSOLE_LOAD_ACTION: Final = "identity.code_rule.console_load"
GOLDEN_LOAD_COMMAND: Final = "load_code_rule_golden"


def golden_maker(maker_id: uuid.UUID) -> Caller:
    """02.7 (REV-0262): the console maker must be an ACTIVE user who holds ``identity.code_rule.manage``
    himself. The operator runs the command with HIS OWN user id (docs/integration/README.md, "Console
    operator rules"): the maker can never approve the revision (maker-checker), so naming somebody else
    would both misattribute the draft and bar that person from approving it."""
    from platform_core.authz import policy as P
    from platform_core.engine.errors import AccessDenied
    from platform_core.identity.models import User, UserStatus

    from .codes import RULE_MANAGE

    status = User.objects.filter(pk=maker_id).values_list("status", flat=True).first()
    if status is None:
        raise refuse("MAKER_NOT_FOUND", "maker")
    if status != UserStatus.ACTIVE:
        raise refuse("MAKER_NOT_ACTIVE", "maker")
    caller = Caller(user_id=maker_id)
    if not P.can(caller, RULE_MANAGE):
        raise AccessDenied()
    return caller


def applied_planning_batch(source_sha256: str) -> ImportBatch:
    """02.7 (REV-0266): the golden file must come from a Planning workbook that was imported and APPLIED
    (same SHA-256 as an APPLIED ``planning_catalogue_xlsm`` batch); any other hash is refused."""
    sha = expected_hash(source_sha256)
    batch = ImportBatch.objects.filter(
        source__code=SOURCE_CODE, file_sha256=sha, status=BatchStatus.APPLIED
    ).first()
    if batch is None:
        raise refuse("SOURCE_BATCH_NOT_APPLIED", "source_sha256", "no APPLIED Planning batch has this hash")
    return batch


def load_golden_cases(
    path: Path,
    *,
    maker_id: uuid.UUID,
    source_sha256: str,
    product_types: Sequence[str] | None = None,
) -> dict[str, Any]:
    """A NEW DRAFT code rule revision (02.3 engine, maker = ``maker_id``, permission
    ``identity.code_rule.manage``) with every case of the file, all or nothing. Returns counts only.

    02.7: the maker is an ACTIVE holder of ``identity.code_rule.manage`` (:func:`golden_maker`, REV-0262), the
    hash names an APPLIED Planning batch (:func:`applied_planning_batch`, REV-0266), and the same transaction
    writes an audit row :data:`CONSOLE_LOAD_ACTION` that records the console origin (command, batch, case
    count) next to the engine's own create / golden rows."""
    from platform_core.engine.uow import unit_of_work

    from .codes import MAX_GOLDEN_PER_CALL, add_golden_cases, create_rule_revision, golden_summary

    caller = golden_maker(maker_id)
    batch = applied_planning_batch(source_sha256)
    cases = read_golden_file(path)
    sha = batch.file_sha256
    types = sorted(set(product_types)) if product_types else sorted({c["family"] for c in cases})
    inputs = [
        {
            "inputs": {k: c[k] for k in sorted(set(c) & set(_GOLDEN_INPUTS))},
            "expected_code": c["expected_code"],
            "source_sheet": c["source_sheet"],
            "source_cell_ref": c["source_cell_ref"],
        }
        for c in cases
    ]
    request_id = uuid.uuid4()
    with transaction.atomic():
        revision = create_rule_revision(
            caller, product_type_codes=types, source_workbook_sha256=sha, request_id=request_id
        )
        for start in range(0, len(inputs), MAX_GOLDEN_PER_CALL):
            add_golden_cases(
                caller, revision.id, cases=inputs[start : start + MAX_GOLDEN_PER_CALL], request_id=request_id
            )
        revision.refresh_from_db()
        with unit_of_work(caller.context(request_id), require_event=False) as uow:
            uow.audit(
                action=CONSOLE_LOAD_ACTION,
                resource_type="identity.code_rule_revision",
                resource_id=str(revision.id),
                resource_version=revision.row_version,
                after={"status": revision.status, "golden_cases": len(inputs)},
                scope={
                    "origin": "console",
                    "command": GOLDEN_LOAD_COMMAND,
                    "source_batch_id": str(batch.id),
                    "operator_rule": "own_account_only",
                },
            )
    return {
        "revision_id": str(revision.id),
        "revision_no": revision.revision_no,
        "status": revision.status,
        "scope_types": types,
        "source_batch_id": str(batch.id),
        **golden_summary(revision),
    }


_GOLDEN_INPUTS: Final = (
    "type_code",
    "category_code",
    "product_no",
    "style_no",
    "buckle_type_code",
    "belt_width_code",
    "category_code_order_form",
)


def password_from_env() -> str | None:
    value = os.environ.get(PASSWORD_ENV)
    return value or None
