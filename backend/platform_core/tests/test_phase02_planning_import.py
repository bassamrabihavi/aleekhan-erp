"""PHASE_02 / 02.6 Integration: Planning catalogue import, legacy code registry, golden loader, serial guard.

Every workbook here is SYNTHETIC, built in-test with openpyxl into pytest's tmp directory (outside the
repository) and labelled «ساختگی»: type segments ``9x``, product numbers ``9xxx``, no real type list,
category, code, serial, customer or person value (DEC-005 / DEC-028 / DEC-046 / DEC-060, R-38). The only
hashes are of these synthetic files. The DEC-058 unit words (کفش، کیف، کمربند، جیبی، اکسسوری، ست) are the
decision's generic terms, not workbook values.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.core.management import CommandError, call_command
from django.db import OperationalError

from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import PayloadTooLarge, RuleNotApproved, ValidationFailed
from platform_core.integration import imports as im
from platform_core.integration.models import (
    BatchStatus,
    ConflictItem,
    ConflictStatus,
    ImportBatch,
    IntegrationSource,
    StagingRow,
)
from platform_core.models import AuditEvent, OutboxEvent
from platform_core.product_identity import planning_import as pi
from platform_core.product_identity.models import (
    ClassLevel,
    CodeRuleGoldenCase,
    CodeRuleRevision,
    ProductClass,
    ProductCode,
)

from . import phase02_factories as f
from .phase02_engine import holder

pytestmark = pytest.mark.django_db
REPO_ROOT = Path(__file__).resolve().parents[3]
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


@pytest.fixture
def workbook(tmp_path: Path) -> Path:
    return write_workbook(tmp_path / "synthetic-planning.xlsm", base_sheets())


def run_import(path: Path, **kw: Any) -> pi.ImportReport:
    layout = kw.pop("layout", pi.Layout(codding_code_col="K"))
    return pi.import_planning_workbook(path, expected_sha256=sha(path), layout=layout, **kw)


def open_conflicts(kind: str | None = None) -> list[ConflictItem]:
    qs = ConflictItem.objects.filter(source__code=pi.SOURCE_CODE, status=ConflictStatus.OPEN)
    return list(qs.filter(kind=kind) if kind else qs)


def types() -> dict[str, ProductClass]:
    return {c.segment_value: c for c in ProductClass.objects.filter(level_key=ClassLevel.PRODUCT_TYPE)}


# ----------------------------------------------------------------------------------------------- import
def test_import_applies_types_categories_and_legacy_codes_with_provenance(workbook: Path) -> None:
    report = run_import(workbook)
    assert report.status == BatchStatus.APPLIED and not report.already_applied and report.attempts == 1
    batch = ImportBatch.objects.get(pk=report.batch_id)
    assert batch.source.code == pi.SOURCE_CODE and batch.file_sha256 == sha(workbook)
    assert batch.source_as_of is not None  # freshness: the file's mtime
    source = IntegrationSource.objects.get(code=pi.SOURCE_CODE)
    assert source.last_success_batch_id == batch.pk and source.last_success_at is not None

    t = types()
    assert sorted(t) == ["91", "92", "93"]  # 94 (unit not decided) and 95 (number) are conflicts
    assert (t["91"].uom_id, t["91"].product_no_scheme) == ("PAIR", "SEQUENTIAL_PER_TYPE")
    assert (t["92"].uom_id, t["92"].product_no_scheme) == ("PIECE", "BELT_BUCKLE_WIDTH")
    assert t["93"].uom_id == "PIECE"
    for c in t.values():
        assert c.status == "ACTIVE" and c.provenance_kind == "IMP" and c.import_batch_id == batch.pk
        assert c.staging_row_id is not None
        row = StagingRow.objects.get(pk=c.staging_row_id)
        assert row.batch_id == batch.pk and row.sheet_name == "Sorce"
        assert c.source_cell_ref == f"E{row.row_number}" and c.transform_rule_version == pi.TRANSFORM_VERSION
    assert t["92"].source_raw_value == "كمربند"  # raw kept exactly (Arabic kaf); label is the stripped raw

    shoe_cats = ProductClass.objects.filter(level_key=ClassLevel.CATEGORY, parent=t["91"])
    assert sorted(c.segment_value for c in shoe_cats) == ["07", "91", "92"]
    belt_cats = ProductClass.objects.filter(level_key=ClassLevel.CATEGORY, parent=t["92"])
    assert [c.segment_value for c in belt_cats] == ["91"]
    assert all(c.source_cell_ref.startswith(("BE", "BF")) for c in [*shoe_cats, *belt_cats])

    codes = {pc.code: pc for pc in ProductCode.objects.all()}
    assert sorted(codes) == [
        "02910790010001",
        "02910790010002",
        "02910790010003",
        "02920790010000",
        "02930790020001",
    ]
    for pc in codes.values():
        assert (pc.status, pc.erp_status, pc.provenance_kind) == ("RESERVED", "ERP_PENDING", "LEG")
        assert pc.style_id is None and pc.rule_revision_id is None and pc.import_batch_id == batch.pk
        assert pc.source_raw_value == pc.code and pc.staging_row_id is not None
    assert codes["02930790020001"].source_sheet == "Codding"

    kinds = sorted(c.kind for c in open_conflicts())
    assert kinds == sorted(
        [
            "catalogue_unit_not_decided",
            "catalogue_code_invalid",
            "catalogue_category_column_unmapped",
            "legacy_code_multiple_product_style",
            *["legacy_code_disputed"] * 4,
        ]
    )
    items = open_conflicts("legacy_code_disputed")
    disputed = {f"{c.details['sheet']}!{c.details['cell']}": c.details for c in items}
    assert set(disputed) == {"NOrder!FZ7", "NOrder!FZ8", "NOrder!FZ9", "Codding!K4"}
    for item in items:  # 02.7 (REV-0261): one item per sheet + distinct value, value-free key
        assert re.fullmatch(r"(NOrder|Codding)!value:[0-9a-f]{24}", item.conflict_key), item.conflict_key
        assert item.details["row_count"] == 1 and item.details["cell_refs"] == [item.details["cell"]]
    assert disputed["NOrder!FZ8"]["reason"] == "NOT_TEXT"
    assert disputed["NOrder!FZ7"]["reason"] == "NOT_14_DIGITS" and disputed["NOrder!FZ7"]["shape"] == "9+A9+"
    assert disputed["NOrder!FZ9"]["reason"] == "NOT_PRODUCT_PREFIX"
    for d in disputed.values():  # the raw value stays in its staging row only
        assert StagingRow.objects.get(pk=d["staging_row_id"]).batch_id == batch.pk
        assert d["status"] == "DISPUTED"
    assert report.counts["legacy_codes_registered"] == 5 and report.counts["types_created"] == 3


def test_sorce_header_rows_and_the_list_below_the_type_block_are_not_data(workbook: Path) -> None:
    """02.6 fix2: row 2 is an English header row (no conflict at O2); column E below its first gap holds an
    unrelated list (never a type, never staged as one)."""
    report = run_import(workbook)
    refs = [json.dumps(c.details, ensure_ascii=False) + c.conflict_key for c in open_conflicts()]
    assert not any("O2" in r or "E2" in r or "BE2" in r for r in refs)
    assert not any(f"E{n}" in r for r in refs for n in (10, 11, 12))
    assert len(open_conflicts("catalogue_unit_not_decided")) == 1  # only the synthetic E6 type
    staged = StagingRow.objects.filter(batch_id=report.batch_id, sheet_name="Sorce")
    assert not staged.filter(row_number=2).exists()  # the English header row is never staged
    assert all("E" not in r.payload["cells"] for r in staged if r.row_number >= 9)
    assert report.counts["sorce_e_cells_below_type_block_not_staged"] == 3
    assert sorted(types()) == ["91", "92", "93"]


def test_header_rows_are_configurable(tmp_path: Path) -> None:
    """One header row only (``--sorce-header-rows 1``): row 2 is then data."""
    sheets = base_sheets()
    sorce = {k: v for k, v in sheets["Sorce"].items() if not re.fullmatch(r"[A-Z]+2", k)}  # drop row 2
    sorce.update({"E2": "اکسسوری", "O2": "98"})
    sheets["Sorce"] = sorce
    path = write_workbook(tmp_path / "one-header.xlsm", sheets)
    run_import(path, layout=pi.Layout(codding_code_col="K", header_rows=1))
    assert "98" in types() and types()["98"].source_cell_ref == "E2"
    with pytest.raises(ValueError):
        pi.Layout(header_row=3, header_rows=2)


def test_import_never_reads_other_columns(workbook: Path) -> None:
    report = run_import(workbook)
    payloads = StagingRow.objects.filter(batch_id=report.batch_id).values_list("payload", flat=True)
    text = json.dumps(list(payloads), ensure_ascii=False)
    assert "شخص" not in text and "مشتری" not in text  # Sorce!A / NOrder!E never staged
    nb = StagingRow.objects.filter(batch_id=report.batch_id, sheet_name="NOrder").values_list(
        "payload", flat=True
    )
    assert all(set(p["cells"]) <= {"A", "C", "D", "FZ"} for p in nb)  # no serial column either


def test_events_and_audit_of_the_apply(workbook: Path) -> None:
    report = run_import(workbook)
    bid = str(report.batch_id)
    applied = OutboxEvent.objects.get(event_type="platform.integration.batch_applied", aggregate_id=bid)
    assert applied.payload["source_code"] == pi.SOURCE_CODE and applied.payload["applied_count"] == 3 + 4 + 5
    assert applied.payload["conflict_count"] == 8
    assert OutboxEvent.objects.filter(event_type="identity.product_class.imported").count() == 7
    reg = OutboxEvent.objects.get(event_type="identity.product_code.legacy_registered")
    assert reg.payload == {"batch_id": bid, "registered": 5, "linked": 0, "unchanged": 0}
    assert OutboxEvent.objects.filter(event_type="platform.integration.conflict_raised").count() == 8
    a = AuditEvent.objects.get(action="platform.integration.batch.apply", resource_id=bid)
    assert a.after is not None
    assert a.after["status"] == "APPLIED" and a.after["counts"]["legacy_codes_registered"] == 5


def test_reimport_of_the_same_file_is_a_no_op(workbook: Path) -> None:
    first = run_import(workbook)
    before = (
        ProductClass.objects.count(),
        ProductCode.objects.count(),
        ConflictItem.objects.count(),
        OutboxEvent.objects.count(),
    )
    again = run_import(workbook)
    assert again.already_applied and again.batch_id == first.batch_id and again.attempts == 0
    after = (
        ProductClass.objects.count(),
        ProductCode.objects.count(),
        ConflictItem.objects.count(),
        OutboxEvent.objects.count(),
    )
    assert after == before
    assert ImportBatch.objects.filter(source__code=pi.SOURCE_CODE).count() == 1


def test_changed_file_raises_conflicts_and_never_overwrites(workbook: Path, tmp_path: Path) -> None:
    run_import(workbook)
    label_before = types()["93"].label_fa
    changed = write_workbook(
        tmp_path / "changed.xlsm",
        base_sheets(
            Sorce={"E5": "اکسسوری", "BE3": f"دسته {SYN} الف تغییر"},
            NOrder={"FZ11": "02910790010009", "C11": "9001", "D11": "0009"},
        ),
    )
    report = run_import(changed)
    assert report.status == BatchStatus.APPLIED
    assert types()["93"].label_fa == label_before  # never silently overwritten
    changed_keys = {c.conflict_key for c in open_conflicts("catalogue_value_changed")}
    assert changed_keys == {"type:93", "type:91/category:91"}
    # the conflicts already open for the first file are not duplicated (one OPEN item per key)
    assert len(open_conflicts("legacy_code_disputed")) == 4
    assert report.counts["conflicts_already_open"] >= 8
    assert report.counts["legacy_codes_registered"] == 1 and report.counts["legacy_codes_unchanged"] == 5
    assert report.counts["types_unchanged"] == 2
    assert ImportBatch.objects.filter(source__code=pi.SOURCE_CODE).count() == 2


def test_code_is_linked_only_to_its_unambiguous_style(workbook: Path, tmp_path: Path) -> None:
    run_import(workbook)
    shoe = types()["91"]
    cat07 = ProductClass.objects.get(level_key=ClassLevel.CATEGORY, parent=shoe, segment_value="07")
    prod = f.product(shoe, "9001")
    s5 = f.style(prod, cat07, "0005")
    s6 = f.style(prod, cat07, "0006")
    second = write_workbook(
        tmp_path / "second.xlsm",
        base_sheets(
            NOrder={
                "FZ11": "02910790010005", "C11": "9001", "D11": "0005",
                "FZ12": "02910790010006", "C12": "9001", "D12": "0006",
                "FZ13": "02910790010006", "C13": "9002", "D13": "0006",  # 2 pairs -> conflict, no link
            }
        ),
    )  # fmt: skip
    report = run_import(second)
    assert ProductCode.objects.get(code="02910790010005").style_id == s5.pk
    six = ProductCode.objects.get(code="02910790010006")
    assert six.style_id is None and s6.pk is not None
    assert report.counts["legacy_codes_linked"] == 1 and report.counts["legacy_codes_unlinked"] == 1
    keys = {c.conflict_key for c in open_conflicts("legacy_code_multiple_product_style")}
    assert "code:02910790010006" in keys


def test_explicit_category_column_map_overrides_the_header(workbook: Path) -> None:
    layout = pi.Layout(codding_code_col="K", category_column_types={"BE": "93", "BG": "91"})
    run_import(workbook, layout=layout)
    t = types()
    bag = ProductClass.objects.filter(level_key=ClassLevel.CATEGORY, parent=t["93"])
    assert sorted(c.segment_value for c in bag) == ["07", "91", "92"]
    shoe = ProductClass.objects.filter(level_key=ClassLevel.CATEGORY, parent=t["91"])
    assert [c.segment_value for c in shoe] == ["07"]
    assert {c.conflict_key for c in open_conflicts("catalogue_category_column_unmapped")} == {
        "column:Sorce!BF"
    }


def test_duplicate_codes_and_names_are_conflicts(tmp_path: Path) -> None:
    path = write_workbook(
        tmp_path / "dup.xlsm",
        base_sheets(Sorce={"E5": "کیف", "O5": "91", "E7": "کفش", "O7": "96"}),
    )
    run_import(path)
    # 91 is used by two names -> neither applied; "کفش" now has two codes -> neither applied
    assert sorted(types()) == ["92"]
    assert {c.kind for c in open_conflicts()} >= {"catalogue_code_duplicate", "catalogue_name_duplicate"}


# ------------------------------------------------------------------------------------------------ guards
def test_sha_mismatch_is_refused_before_anything_is_written(workbook: Path) -> None:
    with pytest.raises(ValidationFailed) as exc:
        pi.import_planning_workbook(workbook, expected_sha256="0" * 64, layout=pi.Layout())
    assert exc.value.errors[0].code == "SHA256_MISMATCH"
    assert not ImportBatch.objects.filter(source__code=pi.SOURCE_CODE).exists()
    with pytest.raises(ValidationFailed) as exc:
        pi.import_planning_workbook(workbook, expected_sha256="not-a-hash", layout=pi.Layout())
    assert exc.value.errors[0].code == "SHA256_FORMAT"


def test_path_inside_the_repository_is_refused() -> None:
    inside = REPO_ROOT / "backend" / "manage.py"
    assert inside.is_file()
    with pytest.raises(ValidationFailed) as exc:
        pi.import_planning_workbook(inside, expected_sha256=sha(inside))
    assert exc.value.errors[0].code == "PATH_INSIDE_REPOSITORY"
    with pytest.raises(ValidationFailed) as exc:
        pi.read_golden_file(inside)
    assert exc.value.errors[0].code == "PATH_INSIDE_REPOSITORY"


def _padded_workbook(path: Path, pad_bytes: int) -> Path:
    """The synthetic workbook plus an unreferenced STORED zip member of ``pad_bytes`` (incompressible): a
    valid workbook that is as large as the real baseline (~70 MB) without real content."""
    import os
    import zipfile

    write_workbook(path, base_sheets())
    with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("customXml/synthetic-padding.bin", os.urandom(pad_bytes))
    return path


def test_planning_limit_accepts_a_workbook_above_the_generic_upload_limit(tmp_path: Path) -> None:
    """fix1: the registered baseline is ~70 MB; the Planning commands allow 128 MB (TECHNICAL DEFAULT) while
    the generic 50 MB upload limit of ``integration.imports`` stays unchanged."""
    assert im.MAX_FILE_BYTES == 50 * 1024 * 1024
    assert pi.MAX_PLANNING_WORKBOOK_BYTES == 128 * 1024 * 1024
    big = _padded_workbook(tmp_path / "big.xlsm", im.MAX_FILE_BYTES + 1024)
    size = big.stat().st_size
    assert im.MAX_FILE_BYTES < size < pi.MAX_PLANNING_WORKBOOK_BYTES
    ctx = RequestContext(Actor.system(), request_id=uuid.uuid4())
    with pytest.raises(PayloadTooLarge):  # the generic path still refuses it
        im.receive_file(ctx, source_code=pi.SOURCE_CODE, content=big.read_bytes(), original_name="big.xlsm")
    report = run_import(big)  # the Planning path accepts and applies it
    assert report.status == BatchStatus.APPLIED
    batch = ImportBatch.objects.get(pk=report.batch_id)
    assert batch.byte_size == size and batch.file_sha256 == sha(big)
    assert report.counts["legacy_codes_registered"] == 5


def test_planning_limit_still_refuses_larger_files_before_reading(
    workbook: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pi, "MAX_PLANNING_WORKBOOK_BYTES", workbook.stat().st_size - 1)
    with pytest.raises(ValidationFailed) as exc:
        run_import(workbook)
    assert exc.value.errors[0].code == "FILE_TOO_LARGE"
    assert not ImportBatch.objects.filter(source__code=pi.SOURCE_CODE).exists()


def test_file_changed_between_hash_and_read_is_refused(
    workbook: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = Path.read_bytes

    def tampered(self: Path) -> bytes:
        return real(self) + b"x" if self.name == workbook.name else real(self)

    registered = sha(workbook)  # the hash the streamed check sees (computed before the tampering)
    monkeypatch.setattr(Path, "read_bytes", tampered)
    with pytest.raises(ValidationFailed) as exc:
        pi.import_planning_workbook(workbook, expected_sha256=registered, layout=pi.Layout())
    assert exc.value.errors[0].code == "FILE_CHANGED_WHILE_READING"
    assert not ImportBatch.objects.filter(source__code=pi.SOURCE_CODE).exists()


def test_not_a_workbook_is_refused(tmp_path: Path) -> None:
    junk = tmp_path / "junk.xlsm"
    junk.write_bytes(b"SYNTHETIC not a workbook")
    with pytest.raises(ValidationFailed) as exc:
        run_import(junk)
    assert exc.value.errors[0].code == "WORKBOOK_UNREADABLE"
    assert not ImportBatch.objects.filter(source__code=pi.SOURCE_CODE).exists()


def test_encrypted_workbook_needs_the_password_env(
    workbook: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from msoffcrypto.format.ooxml import OOXMLFile

    synthetic_wb_open = uuid.uuid4().hex  # generated in-test, never real
    encrypted = tmp_path / "encrypted.xlsm"
    with workbook.open("rb") as src, encrypted.open("wb") as sink:
        OOXMLFile(src).encrypt(synthetic_wb_open, sink)
    assert encrypted.read_bytes()[:8] == pi.OLE_MAGIC
    monkeypatch.delenv(pi.PASSWORD_ENV, raising=False)
    with pytest.raises(CommandError) as exc:
        call_command("import_planning_catalogue", str(encrypted), "--expected-sha256", sha(encrypted))
    assert "WORKBOOK_ENCRYPTED" in str(exc.value) and synthetic_wb_open not in str(exc.value)
    monkeypatch.setenv(pi.PASSWORD_ENV, "wrong-" + synthetic_wb_open)
    with pytest.raises(CommandError) as exc:
        call_command("import_planning_catalogue", str(encrypted), "--expected-sha256", sha(encrypted))
    assert "WORKBOOK_DECRYPT_FAILED" in str(exc.value) and synthetic_wb_open not in str(exc.value)
    monkeypatch.setenv(pi.PASSWORD_ENV, synthetic_wb_open)
    out = io.StringIO()
    call_command(
        "import_planning_catalogue",
        str(encrypted),
        "--expected-sha256",
        sha(encrypted),
        "--codding-code-col",
        "K",
        stdout=out,
    )
    body = json.loads(out.getvalue())
    assert body["status"] == "APPLIED" and body["counts"]["legacy_codes_registered"] == 5
    assert synthetic_wb_open not in out.getvalue()
    for code in ProductCode.objects.values_list("code", flat=True):  # counts only, never a value
        assert code not in out.getvalue()


# ------------------------------------------------------------------------------------------ compensation
def test_failed_apply_leaves_no_partial_rows_and_can_be_resumed(
    workbook: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise RuntimeError("synthetic failure after the types were written")

    monkeypatch.setattr(pi, "_apply_codes", boom)
    with pytest.raises(RuntimeError):
        run_import(workbook)
    batch = ImportBatch.objects.get(source__code=pi.SOURCE_CODE)
    assert batch.status == BatchStatus.VALIDATED  # rolled back, staging kept
    assert StagingRow.objects.filter(batch=batch).count() == batch.row_count > 0
    assert not ProductClass.objects.exists() and not ProductCode.objects.exists()
    assert not ConflictItem.objects.filter(batch=batch).exists()
    failed = OutboxEvent.objects.get(event_type="platform.integration.batch_apply_failed")
    assert failed.payload["error_code"] == "RUNTIME_ERROR" and failed.payload["attempts"] == 1
    assert AuditEvent.objects.filter(
        action="platform.integration.batch.apply_failed", outcome="FAILED"
    ).exists()

    monkeypatch.undo()
    report = run_import(workbook)  # resumes the same VALIDATED batch
    assert report.batch_id == batch.pk and report.status == BatchStatus.APPLIED
    assert sorted(types()) == ["91", "92", "93"] and ProductCode.objects.count() == 5


class _Transient(OperationalError):
    sqlstate = "40001"


def _validated_batch() -> ImportBatch:
    ctx = RequestContext(Actor.system(), request_id=uuid.uuid4())
    b = im.receive_file(
        ctx, source_code=pi.SOURCE_CODE, content=b"SYNTHETIC " + uuid.uuid4().bytes, original_name="syn.xlsm"
    ).batch
    im.stage_rows(ctx, b.id, [im.StagingInput(1, {"part": "synthetic", "cells": {}}, "SYN")])
    return im.validate_batch(ctx, b.id)


def test_transient_failures_are_retried_with_backoff() -> None:
    batch = _validated_batch()
    calls: list[int] = []
    sleeps: list[float] = []

    def flaky(uow: Any, b: ImportBatch) -> im.ApplyOutcome:
        calls.append(1)
        if len(calls) < 3:
            raise _Transient("synthetic serialization failure")
        return im.ApplyOutcome(applied_count=0, conflict_count=0, counts={})

    policy = im.ApplyRetryPolicy(max_attempts=4, jitter_permille=0)
    run = im.apply_batch_with_retry(
        RequestContext(Actor.system()), batch.id, applier=flaky, policy=policy, sleep=sleeps.append
    )
    assert run.attempts == 3 and run.batch.status == BatchStatus.APPLIED
    assert sleeps == [0.5, 1.0]  # exponential: base, base * 2
    assert not OutboxEvent.objects.filter(event_type="platform.integration.batch_apply_failed").exists()


def test_retries_give_up_and_record_the_failure() -> None:
    batch = _validated_batch()
    sleeps: list[float] = []

    def always(uow: Any, b: ImportBatch) -> im.ApplyOutcome:
        raise _Transient("synthetic deadlock")

    policy = im.ApplyRetryPolicy(max_attempts=3, base=timedelta(seconds=1), jitter_permille=0)
    with pytest.raises(OperationalError):
        im.apply_batch_with_retry(
            RequestContext(Actor.system()), batch.id, applier=always, policy=policy, sleep=sleeps.append
        )
    assert sleeps == [1.0, 2.0]
    batch.refresh_from_db()
    assert batch.status == BatchStatus.VALIDATED
    ev = OutboxEvent.objects.get(event_type="platform.integration.batch_apply_failed")
    assert ev.payload["attempts"] == 3 and ev.payload["error_code"] == "SQLSTATE_40001"


def test_a_permanent_failure_is_not_retried() -> None:
    batch = _validated_batch()
    sleeps: list[float] = []

    def bad(uow: Any, b: ImportBatch) -> im.ApplyOutcome:
        raise ValueError("synthetic bad data")

    with pytest.raises(ValueError):
        im.apply_batch_with_retry(RequestContext(Actor.system()), batch.id, applier=bad, sleep=sleeps.append)
    assert sleeps == []


def test_other_sources_stay_rule_not_approved() -> None:
    ctx = RequestContext(Actor.system(), request_id=uuid.uuid4())
    for code, decision in (("legacy_planning_xlsm", "DEC-025"), ("rahkaran_excel", "DEC-016")):
        content = b"SYNTHETIC " + uuid.uuid4().bytes
        b = im.receive_file(ctx, source_code=code, content=content, original_name="s").batch
        im.stage_rows(ctx, b.id, [im.StagingInput(1, {"k": "v"}, "SYN")])
        im.validate_batch(ctx, b.id)
        with pytest.raises(RuleNotApproved) as exc:
            im.apply_batch(ctx, b.id, applier=lambda uow, batch: im.ApplyOutcome(0, 0, {}))
        assert exc.value.decision_id == decision
        b.refresh_from_db()
        assert b.status == BatchStatus.VALIDATED
    assert set(im.SOURCE_APPLY_POLICIES) == {"planning_catalogue_xlsm"}


# ------------------------------------------------------------------------------------------ serial guard
def test_serial_guard_reports_counts_only(workbook: Path) -> None:
    out = io.StringIO()
    call_command("legacy_serial_guard", str(workbook), "--expected-sha256", sha(workbook), stdout=out)
    body = json.loads(out.getvalue())
    assert body["threshold"] == 63000  # the counter's legacy_max_exclusive (DEC-006, seed 0021)
    assert body["non_empty"] == 9
    assert body["plain_integer"] == 5  # 100, "101", 63000, 100, 62999.0
    assert body["plain_at_or_above_threshold"] == 1 and body["safe_for_start"] is False
    assert body["plain_values_duplicated"] == 1  # 100 twice
    assert body["non_plain_by_mask"] == {"A9+": 1, "A+9+": 1, "9+-9": 1, "9+": 1}  # S102 BG105 103-1 0104
    assert body["non_plain_total"] == 4
    for value in ("62999", "S102", "BG105", "103-1", "0104"):
        assert value not in out.getvalue()
    assert not ImportBatch.objects.exists()  # read only: no batch, no row


def test_serial_guard_safe_when_all_below(tmp_path: Path) -> None:
    path = write_workbook(tmp_path / "safe.xlsm", {"NOrder": {"B2": 100, "B3": "62999"}})
    out = io.StringIO()
    call_command("legacy_serial_guard", str(path), "--expected-sha256", sha(path), stdout=out)
    assert json.loads(out.getvalue())["safe_for_start"] is True
    with pytest.raises(CommandError, match="SHA256_MISMATCH"):
        call_command("legacy_serial_guard", str(path), "--expected-sha256", "f" * 64)


# ----------------------------------------------------------------------------------------- golden loader
def golden_cases(n: int = 20, fam: str = "91") -> list[dict[str, str]]:
    out = []
    for i in range(n):
        style = f"{i + 1:04d}"
        out.append(
            {
                "type_code": fam,
                "category_code": "07",
                "product_no": "9001",
                "style_no": style,
                "expected_code": "02" + fam + "07" + "9001" + style,  # plain concatenation, not the engine
                "family": fam,
                "source_sheet": "NOrder",
                "source_cell_ref": f"FZ{i + 2}",
            }
        )
    return out


def applied_sha() -> str:
    """02.7 (REV-0266): the loader needs the hash of an APPLIED Planning batch (a synthetic one here)."""
    done = ImportBatch.objects.filter(source__code=pi.SOURCE_CODE, status=BatchStatus.APPLIED).first()
    if done is not None:
        return done.file_sha256
    batch = _validated_batch()
    im.apply_batch(RequestContext(Actor.system()), batch.id, applier=lambda uow, b: im.ApplyOutcome(0, 0, {}))
    batch.refresh_from_db()
    return batch.file_sha256


def write_json(path: Path, value: Any) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_golden_loader_creates_a_draft_revision(tmp_path: Path) -> None:
    maker = holder("product_data_steward")
    path = write_json(tmp_path / "golden.json", golden_cases())
    out = io.StringIO()
    call_command(
        "load_code_rule_golden",
        str(path),
        "--maker",
        str(maker.pk),
        "--source-sha256",
        applied_sha(),
        stdout=out,
    )
    body = json.loads(out.getvalue())
    r = CodeRuleRevision.objects.get(pk=body["revision_id"])
    assert r.status == "DRAFT" and r.created_by_id == maker.pk and r.scope == {"product_types": ["91"]}
    assert body["total"] == 20 and body["per_family"] == {"91": 20} and body["not_reproduced"] == 0
    assert body["families_below_minimum"] == []
    assert CodeRuleGoldenCase.objects.filter(rule_revision=r).count() == 20
    assert "02910790010001" not in out.getvalue()  # counts only


def test_golden_loader_refuses_harness_only_fields_and_unknown_keys(tmp_path: Path) -> None:
    maker = holder("product_data_steward")
    cases = golden_cases()
    cases[3]["legacy_disputed"] = "synthetic"
    cases[5]["note"] = "x"
    path = write_json(tmp_path / "golden.json", cases)
    with pytest.raises(CommandError) as exc:
        call_command(
            "load_code_rule_golden", str(path), "--maker", str(maker.pk), "--source-sha256", applied_sha()
        )
    msg = str(exc.value)
    assert "cases[3].legacy_disputed:GOLDEN_FIELD_NOT_ALLOWED" in msg and "cases[5].<unknown>" in msg
    assert not CodeRuleRevision.objects.exists()


def test_golden_loader_needs_source_fields_and_matching_family(tmp_path: Path) -> None:
    maker = holder("product_data_steward")
    cases = golden_cases()
    del cases[0]["source_cell_ref"]
    cases[1]["family"] = "92"
    path = write_json(tmp_path / "golden.json", cases)
    with pytest.raises(CommandError) as exc:
        call_command(
            "load_code_rule_golden", str(path), "--maker", str(maker.pk), "--source-sha256", applied_sha()
        )
    assert "cases[0].source_cell_ref:REQUIRED" in str(exc.value)
    assert "cases[1].family:FAMILY_NOT_TYPE_SEGMENT" in str(exc.value)


def test_golden_loader_permission_and_repo_path(tmp_path: Path) -> None:
    nobody = holder("employee")
    path = write_json(tmp_path / "golden.json", golden_cases())
    with pytest.raises(CommandError, match="ACCESS_DENIED"):
        call_command(
            "load_code_rule_golden", str(path), "--maker", str(nobody.pk), "--source-sha256", applied_sha()
        )
    assert not CodeRuleRevision.objects.exists()
    maker = holder("product_data_steward")
    inside = REPO_ROOT / "backend" / "platform_core" / "tests" / "golden" / "backoff.golden.json"
    with pytest.raises(CommandError, match="PATH_INSIDE_REPOSITORY"):
        call_command(
            "load_code_rule_golden", str(inside), "--maker", str(maker.pk), "--source-sha256", applied_sha()
        )


def test_golden_loader_is_all_or_nothing_across_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from platform_core.product_identity import codes

    monkeypatch.setattr(codes, "MAX_GOLDEN_PER_CALL", 7)
    maker = holder("product_data_steward")
    cases = golden_cases(20)
    cases[15]["source_cell_ref"] = cases[2]["source_cell_ref"]  # duplicate position in the third chunk
    path = write_json(tmp_path / "golden.json", cases)
    with pytest.raises(CommandError):
        call_command(
            "load_code_rule_golden", str(path), "--maker", str(maker.pk), "--source-sha256", applied_sha()
        )
    assert not CodeRuleRevision.objects.exists() and not CodeRuleGoldenCase.objects.exists()
