"""PHASE_02 / 02.7 Security & Ops regressions (synthetic workbooks in pytest's tmp dir, labelled «ساختگی»).

* REV-0261 - one ``legacy_code_disputed`` item per distinct value, carrying the row count (identical order
  rows included); resolving the item settles every row of that value.
* REV-0262 - ``load_code_rule_golden --maker``: an ACTIVE holder of ``identity.code_rule.manage`` only, and
  the console origin is in the audit trail.
* REV-0266 - ``--source-sha256`` must name an APPLIED Planning batch.
* REV-0265 - an applied source is fresh only after a successful APPLY; a failed apply is visible in
  ``outbox_status`` / ``job_status`` (``IMPORT_APPLY_FAILED``).
* Job monitoring - event families of PHASE_02 (identity, commercial, platform.integration) are reported.
* REV-0244 - the golden summary is stored at the write and read from the store by lists; the single GET is
  live.
"""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from django.core.management import CommandError, call_command

from platform_core.engine.context import Actor, RequestContext
from platform_core.identity.models import User
from platform_core.integration import imports as im
from platform_core.integration.conflicts import resolve_conflict
from platform_core.integration.models import (
    BatchStatus,
    ConflictItem,
    ConflictStatus,
    ImportBatch,
    IntegrationSource,
)
from platform_core.models import AuditEvent
from platform_core.ops.monitoring import event_families, import_health
from platform_core.product_identity import codes
from platform_core.product_identity import planning_import as pi
from platform_core.product_identity.models import CodeRuleRevision

from .phase02_engine import holder
from .test_phase02_planning_import import (
    _validated_batch,
    applied_sha,
    base_sheets,
    golden_cases,
    run_import,
    write_json,
    write_workbook,
)

pytestmark = pytest.mark.django_db
SYN = "ساختگی"
DISPUTED = f"SYN-{SYN}-X"  # synthetic non-14-digit value


def _source() -> IntegrationSource:
    return IntegrationSource.objects.get(code=pi.SOURCE_CODE)


def _json(cmd: str, *args: str) -> dict[str, Any]:
    out = io.StringIO()
    call_command(cmd, "--json", *args, stdout=out)
    body: dict[str, Any] = json.loads(out.getvalue())
    return body


# ----------------------------------------------------------------------------------------- REV-0261
def test_disputed_value_is_one_item_with_the_count_of_every_row(tmp_path: Path) -> None:
    sheets = base_sheets(
        NOrder={
            "FZ12": DISPUTED,  # three rows with one distinct disputed value:
            "FZ13": DISPUTED,  # row 13 is identical to row 12 (DUPLICATE_PAYLOAD at validation)
            "FZ14": DISPUTED,
            "C14": "9002",  # row 14 differs in another column
        }
    )
    path = write_workbook(tmp_path / "dup.xlsm", sheets)
    report = run_import(path)
    assert report.status == BatchStatus.APPLIED
    items = [
        c
        for c in ConflictItem.objects.filter(kind="legacy_code_disputed", status=ConflictStatus.OPEN)
        if c.details["cell"] in ("FZ12", "FZ13", "FZ14")
    ]
    assert len(items) == 1
    item = items[0]
    assert item.details["row_count"] == 3 and item.details["cell_refs"] == ["FZ12", "FZ13", "FZ14"]
    assert item.details["cell_refs_truncated"] is False
    assert DISPUTED not in json.dumps(item.details, ensure_ascii=False) + item.conflict_key  # value-free
    assert report.counts["legacy_duplicate_rows_counted"] >= 1
    assert report.counts["legacy_rows_disputed"] == report.counts["legacy_values_disputed"] + 2

    steward = holder("product_data_steward")
    ctx = RequestContext(Actor.user(steward.pk), request_id=uuid.uuid4())
    done = resolve_conflict(
        ctx,
        ConflictItem.objects.all(),
        item.conflict_id,
        expected_version=item.row_version,
        outcome="RESOLVED",
        note="تصمیم ساختگی برای همه ردیف‌ها",  # noqa: RUF001 - Persian text
    )
    assert done.status == ConflictStatus.RESOLVED
    left = ConflictItem.objects.filter(
        kind="legacy_code_disputed", status=ConflictStatus.OPEN, conflict_key=item.conflict_key
    )
    assert not left.exists()  # one decision covered all three rows

    # the same value in a later file (rows moved) maps to the same key: a new item only because the old
    # one is closed, never one per row
    moved = write_workbook(
        tmp_path / "moved.xlsm",
        base_sheets(NOrder={"FZ20": DISPUTED, "FZ21": DISPUTED, "C21": "9003"}),
    )
    run_import(moved)
    again = ConflictItem.objects.filter(conflict_key=item.conflict_key, status=ConflictStatus.OPEN)
    assert again.count() == 1 and again.get().details["row_count"] == 2


# ------------------------------------------------------------------------------- REV-0262 / REV-0266
def test_golden_loader_maker_must_be_an_active_holder_and_the_console_is_audited(tmp_path: Path) -> None:
    path = write_json(tmp_path / "golden.json", golden_cases())
    good = applied_sha()
    gone = holder("product_data_steward")
    User.objects.filter(pk=gone.pk).update(status="DISABLED")
    with pytest.raises(CommandError, match="MAKER_NOT_ACTIVE"):
        call_command("load_code_rule_golden", str(path), "--maker", str(gone.pk), "--source-sha256", good)
    with pytest.raises(CommandError, match="MAKER_NOT_FOUND"):
        call_command(
            "load_code_rule_golden", str(path), "--maker", str(uuid.uuid4()), "--source-sha256", good
        )
    approver = holder("code_rule_approver")  # active, but no identity.code_rule.manage
    with pytest.raises(CommandError, match="ACCESS_DENIED"):
        call_command("load_code_rule_golden", str(path), "--maker", str(approver.pk), "--source-sha256", good)
    assert not CodeRuleRevision.objects.exists()

    maker = holder("product_data_steward")
    out = io.StringIO()
    call_command(
        "load_code_rule_golden", str(path), "--maker", str(maker.pk), "--source-sha256", good, stdout=out
    )
    rid = json.loads(out.getvalue())["revision_id"]
    console = AuditEvent.objects.get(action=pi.CONSOLE_LOAD_ACTION, resource_id=rid)
    assert console.actor_id == maker.pk
    assert console.scope["origin"] == "console" and console.scope["command"] == "load_code_rule_golden"
    batch = ImportBatch.objects.get(file_sha256=good, status=BatchStatus.APPLIED)
    assert console.scope["source_batch_id"] == str(batch.id)
    assert console.after == {"status": "DRAFT", "golden_cases": 20}
    # the console row shares the request id with the engine's create row (one traceable operation)
    created = AuditEvent.objects.get(action="identity.code_rule.create", resource_id=rid)
    assert created.request_id == console.request_id


def test_golden_loader_refuses_a_hash_without_an_applied_planning_batch(tmp_path: Path) -> None:
    path = write_json(tmp_path / "golden.json", golden_cases())
    maker = holder("product_data_steward")
    for bad in ("b" * 64, _validated_batch().file_sha256):  # unknown / validated but never applied
        with pytest.raises(CommandError, match="SOURCE_BATCH_NOT_APPLIED"):
            call_command("load_code_rule_golden", str(path), "--maker", str(maker.pk), "--source-sha256", bad)
    assert not CodeRuleRevision.objects.exists()


# ----------------------------------------------------------------------------------------- REV-0265
def test_freshness_counts_only_an_applied_batch_and_a_failed_apply_is_monitored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _validated_batch()  # validated, never applied: not fresh, waiting for the operator
    assert _source().last_success_at is None
    health = {h.source_code: h for h in import_health()}[pi.SOURCE_CODE]
    assert (health.apply_failed, health.awaiting_apply) == (0, 1)

    path = write_workbook(tmp_path / "wb.xlsm", base_sheets())

    def boom(*a: Any, **k: Any) -> None:
        raise RuntimeError("synthetic failure inside the apply")

    monkeypatch.setattr(pi, "_apply_codes", boom)
    with pytest.raises(RuntimeError):
        run_import(path)
    assert _source().last_success_at is None and _source().last_success_batch_id is None
    snap = _json("outbox_status")
    imp = {i["source_code"]: i for i in snap["imports"]}[pi.SOURCE_CODE]
    assert imp["apply_failed"] == 1 and imp["last_apply_failed_at"] is not None
    assert "IMPORT_APPLY_FAILED" in snap["reasons"] and snap["verdict"] in ("warn", "critical")
    jobs = _json("job_status")
    assert jobs["verdict"] == "warn" and "IMPORT_APPLY_FAILED" in jobs["reasons"]
    assert {i["source_code"]: i for i in jobs["imports"]}[pi.SOURCE_CODE]["apply_failed"] == 1
    with pytest.raises(CommandError):
        call_command("job_status", "--fail-on", "warn", stdout=io.StringIO())
    text = io.StringIO()
    call_command("outbox_status", stdout=text)
    assert f"imports.{pi.SOURCE_CODE}: apply_failed=1" in text.getvalue()
    assert "synthetic failure" not in text.getvalue()  # codes only, never an exception text

    monkeypatch.undo()
    report = run_import(path)  # the operator re-runs: same batch, applied now
    assert report.status == BatchStatus.APPLIED
    src = _source()
    assert src.last_success_batch_id == report.batch_id and src.last_success_at is not None
    imp = {i["source_code"]: i for i in _json("outbox_status")["imports"]}[pi.SOURCE_CODE]
    assert imp["apply_failed"] == 0 and imp["last_applied_at"] is not None
    assert "IMPORT_APPLY_FAILED" not in _json("job_status")["reasons"]
    validate = AuditEvent.objects.filter(
        action="platform.integration.batch.validate", resource_id=str(report.batch_id)
    ).get()
    assert validate.after is not None
    assert validate.after["freshness_deferred_to_apply"] is True
    assert validate.after["freshness_advanced"] is False
    apply = AuditEvent.objects.get(
        action="platform.integration.batch.apply", resource_id=str(report.batch_id)
    )
    assert apply.after is not None and apply.after["freshness_advanced"] is True


def test_sources_without_an_apply_policy_still_refresh_at_validation() -> None:
    ctx = RequestContext(Actor.system(), request_id=uuid.uuid4())
    b = im.receive_file(
        ctx, source_code="rahkaran_excel", content=b"SYNTHETIC " + uuid.uuid4().bytes, original_name="s"
    ).batch
    im.stage_rows(ctx, b.id, [im.StagingInput(1, {"k": "v"}, "SYN")])
    im.validate_batch(ctx, b.id)
    assert IntegrationSource.objects.get(code="rahkaran_excel").last_success_batch_id == b.id


# --------------------------------------------------------------------------------- job monitoring
def test_event_families_cover_the_phase02_events(tmp_path: Path) -> None:
    fam = event_families()
    assert {"identity", "commercial", "platform.integration", "platform.workflow", "other"} <= set(fam)
    run_import(write_workbook(tmp_path / "wb.xlsm", base_sheets()))
    fam = event_families()
    assert fam["identity"]["undelivered"] >= 1  # identity.product_code.legacy_registered
    assert fam["platform.integration"]["undelivered"] >= 4  # received / staged / validated / applied
    assert _json("outbox_status")["event_families"]["identity"] == fam["identity"]


# ------------------------------------------------------------------------------------------ REV-0244
def test_golden_summary_is_stored_at_the_write_and_lists_read_the_store() -> None:
    maker = holder("product_data_steward")
    r = codes.create_rule_revision(maker.caller, product_type_codes=["91"], source_workbook_sha256="c" * 64)
    assert r.golden_summary is None  # no case yet: computed on read (cheap)
    assert codes.stored_golden_summary(r)["families_below_minimum"] == ["91"]
    rows = [
        {
            "inputs": {k: c[k] for k in ("type_code", "category_code", "product_no", "style_no")},
            "expected_code": c["expected_code"],
            "source_sheet": c["source_sheet"],
            "source_cell_ref": c["source_cell_ref"],
        }
        for c in golden_cases(20)
    ]
    codes.add_golden_cases(maker.caller, r.pk, cases=rows)
    r.refresh_from_db()
    assert r.golden_summary is not None and r.golden_summary == codes.golden_summary(r)
    assert r.golden_summary["total"] == 20 and r.golden_summary["families_below_minimum"] == []
    r = codes.submit_rule_revision(maker.caller, r.pk, expected_version=r.row_version)
    assert r.status == "IN_REVIEW" and r.golden_summary == codes.golden_summary(r)  # guard allows it
    # the store is what lists read: a planted value proves no recomputation happens there
    planted = {**r.golden_summary, "total": 999}
    CodeRuleRevision.objects.filter(pk=r.pk).update(golden_summary=planted)
    r.refresh_from_db()
    from platform_core.api.phase02 import serializers as S

    assert S.code_rule(r)["golden_summary"]["total"] == 999
    assert S.code_rule(r, live_summary=True)["golden_summary"]["total"] == 20  # the single GET is live
    with pytest.raises(Exception, match="ck_identity_code_rule_golden_summary_object"):
        CodeRuleRevision.objects.filter(pk=r.pk).update(golden_summary=[1, 2])


# --------------------------------------------------------------------------------- import safety
def test_workbook_is_opened_as_data_only_without_macros_or_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Planning workbook is read as data: macros are dropped (never executed), cached values only, no
    external links (CLAUDE.md: never execute legacy XLSM/VBA)."""
    import openpyxl

    seen: list[dict[str, Any]] = []
    real = openpyxl.load_workbook

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(openpyxl, "load_workbook", spy)
    run_import(write_workbook(tmp_path / "wb.xlsm", base_sheets()))
    assert seen and all(
        k.get("keep_vba") is False
        and k.get("data_only") is True
        and k.get("read_only") is True
        and k.get("keep_links") is False
        for k in seen
    )
