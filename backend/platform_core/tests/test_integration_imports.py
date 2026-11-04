"""00.6 import batches + staging: provenance, idempotent receive (WH-01 framework), staging guards,
validation,
freshness update, rule-gated transitions, DB guards, duplicate-import race.

All files and rows are SYNTHETIC, created in-test (tiny byte strings / dicts); no real factory data.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from hypothesis import given
from hypothesis import strategies as st

from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import (
    EngineContractError,
    NotFound,
    PayloadTooLarge,
    RuleNotApproved,
    SourceDisabled,
    SourceReadOnly,
    StateTransitionNotAllowed,
    ValidationFailed,
    VersionConflict,
)
from platform_core.integration import imports as im
from platform_core.integration.models import (
    BatchStatus,
    ImportBatch,
    IntegrationSource,
    RowStatus,
    StagingRow,
)
from platform_core.integration.sources import get_source, require_writable
from platform_core.models import AuditEvent, OutboxEvent

from . import factories
from .threads import run_concurrently

GOLDEN = Path(__file__).parent / "golden" / "import_batch_machine.golden.json"
SYNTHETIC_FILE = b"SYNTHETIC test workbook bytes - not a real file"
USER = uuid.UUID("00000000-0000-4000-8000-0000000000b1")


def _ctx(user: bool = False) -> RequestContext:
    return RequestContext(Actor.user(USER) if user else Actor.system(), request_id=uuid.uuid4())


def _rows(n: int, sheet: str = "SYN") -> list[im.StagingInput]:
    return [
        im.StagingInput(row_number=i + 1, sheet_name=sheet, payload={"col_a": f"v{i}", "col_b": i})
        for i in range(n)
    ]


def _staged(
    source: IntegrationSource, rows: list[im.StagingInput], content: bytes = SYNTHETIC_FILE
) -> ImportBatch:
    batch = im.receive_file(_ctx(), source_code=source.code, content=content, original_name="syn.xlsx").batch
    return im.stage_rows(_ctx(), batch.id, rows)


# ------------------------------------------------------------------------------------------- machine
def test_import_batch_machine_golden() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    m = im.IMPORT_BATCH_MACHINE
    actual = {src: sorted(dsts) for src, dsts in sorted(m.transitions.items())}
    assert actual == golden["transitions"]
    assert sorted(f"{a}->{b}" for a, b in im.SOURCE_POLICY_GATED) == golden["source_policy_gated"]
    assert sorted(m.terminal_states) == golden["terminal"]


# ------------------------------------------------------------------------------------------- helpers
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("C:\\Users\\someone\\Desktop\\ListData (2).xlsx", "ListData (2).xlsx"),
        ("/home/u/files/WH-.xlsm", "WH-.xlsm"),
        ("جدول\u200cپیگیری.xlsx", "جدول\u200cپیگیری.xlsx"),  # ZWNJ kept
        ("evil\u202egpj.exe", "evilgpj.exe"),  # bidi override removed
        ("a\x00b\nc.xlsx", "abc.xlsx"),
        ("", "unnamed"),
        ("../..", "unnamed"),
    ],
)
def test_safe_basename(raw: str, expected: str) -> None:
    assert im.safe_basename(raw) == expected


@given(st.text(max_size=400))
def test_safe_basename_never_returns_a_path_or_control(raw: str) -> None:
    out = im.safe_basename(raw)
    assert out and len(out) <= 255
    assert "/" not in out and "\\" not in out
    assert not any(ord(ch) < 32 or 0x7F <= ord(ch) < 0xA0 for ch in out)


def test_digest_streaming_equals_bytes_and_limits() -> None:
    data = SYNTHETIC_FILE * 3000
    assert im.digest_content(io.BytesIO(data)) == im.digest_content(data)
    assert im.digest_content(data).sha256 == hashlib.sha256(data).hexdigest()
    with pytest.raises(PayloadTooLarge):
        im.digest_content(io.BytesIO(data), max_bytes=len(data) - 1)
    with pytest.raises(ValidationFailed) as exc:
        im.digest_content(b"")
    assert exc.value.errors[0].code == "EMPTY_FILE"


# ------------------------------------------------------------------------------------------- receive
@pytest.mark.django_db
def test_receive_records_provenance_audit_and_event() -> None:
    src = factories.integration_source()
    as_of = datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    ctx = _ctx(user=True)
    res = im.receive_file(
        ctx, source_code=src.code, content=SYNTHETIC_FILE, original_name="D:\\x\\syn.xlsx", source_as_of=as_of
    )
    b = res.batch
    assert res.created
    assert (b.status, b.file_sha256, b.byte_size) == (
        BatchStatus.RECEIVED,
        hashlib.sha256(SYNTHETIC_FILE).hexdigest(),
        len(SYNTHETIC_FILE),
    )
    assert (b.original_name, b.actor_id, b.request_id, b.source_as_of) == (
        "syn.xlsx",
        USER,
        ctx.request_id,
        as_of,
    )
    audit = AuditEvent.objects.get(request_id=ctx.request_id)
    assert audit.action == "platform.integration.batch.receive" and audit.resource_id == str(b.id)
    event = OutboxEvent.objects.get(request_id=ctx.request_id)
    assert event.event_type == "platform.integration.batch_received"
    assert event.payload == {
        "batch_id": str(b.id),
        "source_code": src.code,
        "sha256": b.file_sha256,
        "byte_size": b.byte_size,
    }


@pytest.mark.django_db
def test_same_file_twice_is_one_batch_wh01_framework() -> None:
    """WH-01 (phase 6) semantics supported by the framework: re-import of the same snapshot = one batch."""
    src = factories.integration_source()
    first = im.receive_file(_ctx(), source_code=src.code, content=SYNTHETIC_FILE, original_name="a.xlsx")
    im.stage_rows(_ctx(), first.batch.id, _rows(2))
    im.validate_batch(_ctx(), first.batch.id)
    src.refresh_from_db()
    fresh_at = src.last_success_at
    ctx2 = _ctx()
    again = im.receive_file(
        ctx2, source_code=src.code, content=io.BytesIO(SYNTHETIC_FILE), original_name="b.xlsx"
    )
    assert not again.created and again.batch.id == first.batch.id
    assert again.batch.original_name == "a.xlsx"  # provenance of the first receipt kept
    assert ImportBatch.objects.filter(source=src).count() == 1
    assert StagingRow.objects.filter(batch__source=src).count() == 2
    assert not OutboxEvent.objects.filter(request_id=ctx2.request_id).exists()  # no second event
    assert (
        AuditEvent.objects.get(request_id=ctx2.request_id).action
        == "platform.integration.batch.receive_duplicate"
    )
    src.refresh_from_db()
    assert src.last_success_at == fresh_at  # a duplicate is not new evidence
    # a different file of the same source, or the same file of another source, is a new batch
    assert im.receive_file(
        _ctx(), source_code=src.code, content=SYNTHETIC_FILE + b"!", original_name="c"
    ).created
    other = factories.integration_source()
    assert im.receive_file(_ctx(), source_code=other.code, content=SYNTHETIC_FILE, original_name="d").created


@pytest.mark.django_db
def test_receive_guards() -> None:
    src = factories.integration_source()
    with pytest.raises(NotFound):
        im.receive_file(_ctx(), source_code="synthetic_missing", content=SYNTHETIC_FILE, original_name="x")
    with pytest.raises(ValidationFailed):
        im.receive_file(
            _ctx(),
            source_code=src.code,
            content=SYNTHETIC_FILE,
            original_name="x",
            source_as_of=datetime(2026, 1, 1),
        )
    with pytest.raises(PayloadTooLarge):
        im.receive_file(_ctx(), source_code=src.code, content=SYNTHETIC_FILE, original_name="x", max_bytes=4)
    IntegrationSource.objects.filter(pk=src.pk).update(is_enabled=False)
    with pytest.raises(SourceDisabled):
        im.receive_file(_ctx(), source_code=src.code, content=SYNTHETIC_FILE, original_name="x")
    assert not ImportBatch.objects.filter(source=src).exists()


@pytest.mark.django_db
def test_every_source_is_read_only() -> None:
    src = factories.integration_source()
    with pytest.raises(SourceReadOnly) as exc:
        require_writable(src)
    assert exc.value.http_status == 409
    for seeded in ("rahkaran_excel", "legacy_planning_xlsm", "legacy_wh_xlsm"):
        with pytest.raises(SourceReadOnly):
            require_writable(get_source(seeded))
    with pytest.raises(IntegrityError) as db_exc, transaction.atomic():
        IntegrationSource.objects.filter(pk=src.pk).update(direction="READ_WRITE")
    assert "ck_integration_source_read_only" in str(db_exc.value)


# ------------------------------------------------------------------------------------------- stage
@pytest.mark.django_db
def test_stage_rows_and_transition() -> None:
    src = factories.integration_source()
    batch = _staged(src, _rows(3))
    assert (batch.status, batch.row_count) == (BatchStatus.STAGED, 3)
    assert batch.staged_at is not None
    rows = list(StagingRow.objects.filter(batch=batch).order_by("row_number"))
    assert [r.validation_status for r in rows] == [RowStatus.NEW] * 3
    assert rows[0].payload == {"col_a": "v0", "col_b": 0}
    assert rows[0].payload_sha256 == hashlib.sha256(im.canonical_payload(rows[0].payload)).hexdigest()
    with pytest.raises(StateTransitionNotAllowed):  # staging twice
        im.stage_rows(_ctx(), batch.id, _rows(1))
    assert StagingRow.objects.filter(batch=batch).count() == 3


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("rows", "field", "code"),
    [
        (
            [im.StagingInput(1, {"user_password": "<synthetic-not-a-secret>"})],
            "rows[0].payload.user_password",
            "SENSITIVE_FIELD",
        ),
        ([im.StagingInput(1, {"x": {"Salary": 1}})], "rows[0].payload.x.Salary", "SENSITIVE_FIELD"),
        (
            [im.StagingInput(1, {"a": 1}), im.StagingInput(1, {"a": 2})],
            "rows[1].row_number",
            "DUPLICATE_POSITION",
        ),
        ([im.StagingInput(0, {"a": 1})], "rows[0].row_number", "OUT_OF_RANGE"),
        ([im.StagingInput(1, {"a": "x" * (im.MAX_ROW_PAYLOAD_BYTES + 1)})], "rows[0].payload", "TOO_LARGE"),
        ([im.StagingInput(1, {"a": float("nan")})], "rows[0].payload", "NOT_JSON"),
    ],
)
def test_stage_refuses_bad_rows_and_stores_nothing(
    rows: list[im.StagingInput], field: str, code: str
) -> None:
    src = factories.integration_source()
    batch = im.receive_file(_ctx(), source_code=src.code, content=SYNTHETIC_FILE, original_name="x").batch
    with pytest.raises(ValidationFailed) as exc:
        im.stage_rows(_ctx(), batch.id, rows)
    assert (exc.value.errors[0].field, exc.value.errors[0].code) == (field, code)
    assert "<synthetic-not-a-secret>" not in str(exc.value.to_problem(uuid.uuid4()))  # values never echoed
    batch.refresh_from_db()
    assert batch.status == BatchStatus.RECEIVED
    assert not StagingRow.objects.filter(batch=batch).exists()


@pytest.mark.django_db
def test_stage_version_check() -> None:
    src = factories.integration_source()
    batch = im.receive_file(_ctx(), source_code=src.code, content=SYNTHETIC_FILE, original_name="x").batch
    with pytest.raises(VersionConflict):
        im.stage_rows(_ctx(), batch.id, _rows(1), expected_version=batch.row_version + 5)
    with pytest.raises(NotFound):
        im.stage_rows(_ctx(), uuid.uuid4(), _rows(1))


# ------------------------------------------------------------------------------------------- validate
@pytest.mark.django_db
def test_validate_marks_rows_counts_and_refreshes_source() -> None:
    src = factories.integration_source()
    rows = [
        im.StagingInput(1, {"code": "00000000000001", "qty": "5"}, "S"),
        im.StagingInput(2, {"code": "00000000000001", "qty": "5"}, "S"),  # duplicate payload
        im.StagingInput(3, {"code": None, "qty": "  "}, "S"),  # empty
        im.StagingInput(4, {"code": "00000000000002", "qty": "x"}, "S"),
    ]
    batch = _staged(src, rows)

    def synthetic_validator(payload: Any) -> list[str]:
        return ["SYNTHETIC_QTY_NOT_NUMERIC"] if payload.get("qty") == "x" else []

    ctx = _ctx()
    batch = im.validate_batch(ctx, batch.id, validators=[synthetic_validator])
    assert (batch.status, batch.row_count, batch.error_row_count) == (BatchStatus.VALIDATED, 4, 3)
    got = {r.row_number: (r.validation_status, r.error_codes) for r in StagingRow.objects.filter(batch=batch)}
    assert got == {
        1: (RowStatus.PENDING_REVIEW, []),
        2: (RowStatus.ERROR, ["DUPLICATE_PAYLOAD"]),
        3: (RowStatus.ERROR, ["EMPTY_ROW"]),
        4: (RowStatus.ERROR, ["SYNTHETIC_QTY_NOT_NUMERIC"]),
    }
    assert got[1][0] != RowStatus.APPROVED  # nothing is approved/applied in PHASE_00
    src.refresh_from_db()
    assert src.last_success_batch_id == batch.id and src.last_success_at == batch.validated_at
    assert (
        OutboxEvent.objects.get(request_id=ctx.request_id).event_type
        == "platform.integration.batch_validated"
    )


@pytest.mark.django_db
def test_validate_all_error_rows_does_not_refresh_freshness() -> None:
    src = factories.integration_source()
    batch = _staged(src, [im.StagingInput(1, {"a": ""})])
    im.validate_batch(_ctx(), batch.id)
    src.refresh_from_db()
    assert src.last_success_at is None and src.last_success_batch_id is None


@pytest.mark.django_db
def test_validator_must_return_codes() -> None:
    src = factories.integration_source()
    batch = _staged(src, _rows(1))
    with pytest.raises(EngineContractError):
        im.validate_batch(_ctx(), batch.id, validators=[lambda p: ["bad code"]])
    batch.refresh_from_db()
    assert batch.status == BatchStatus.STAGED  # rolled back


# ------------------------------------------------------------------------------------------- reject / gated
@pytest.mark.django_db
def test_reject_requires_user_and_reason_and_is_terminal() -> None:
    src = factories.integration_source()
    batch = _staged(src, _rows(1))
    with pytest.raises(EngineContractError):
        im.reject_batch(_ctx(), batch.id, reason="synthetic")
    with pytest.raises(ValidationFailed):
        im.reject_batch(_ctx(user=True), batch.id, reason="  ")
    ctx = _ctx(user=True)
    batch = im.reject_batch(ctx, batch.id, reason="synthetic wrong sheet")
    assert (batch.status, batch.close_reason) == (BatchStatus.REJECTED, "synthetic wrong sheet")
    assert AuditEvent.objects.get(request_id=ctx.request_id).reason == "synthetic wrong sheet"
    with pytest.raises(StateTransitionNotAllowed):
        im.validate_batch(_ctx(), batch.id)


@pytest.mark.django_db
@pytest.mark.parametrize("fn", [im.apply_batch, im.supersede_batch])
def test_apply_and_supersede_are_blocked_with_the_source_decision(fn: Any) -> None:
    src = factories.integration_source(policy_decision_id="DEC-016")
    batch = _staged(src, _rows(1))
    with pytest.raises(StateTransitionNotAllowed):  # not VALIDATED yet
        fn(_ctx(user=True), batch.id)
    im.validate_batch(_ctx(), batch.id)
    with pytest.raises(RuleNotApproved) as exc:
        fn(_ctx(user=True), batch.id)
    assert exc.value.decision_id == "DEC-016"
    batch.refresh_from_db()
    assert batch.status == BatchStatus.VALIDATED


@pytest.mark.django_db
def test_compensate_needs_applied_batch() -> None:
    src = factories.integration_source()
    batch = _staged(src, _rows(1))
    im.validate_batch(_ctx(), batch.id)
    with pytest.raises(StateTransitionNotAllowed):
        im.compensate_batch(_ctx(user=True), batch.id)


@pytest.mark.django_db
def test_seeded_sources_policy_decisions() -> None:
    got = {
        s.code: s.policy_decision_id
        for s in IntegrationSource.objects.filter(
            code__in=["rahkaran_excel", "legacy_planning_xlsm", "legacy_wh_xlsm"]
        )
    }
    assert got == {
        "rahkaran_excel": "DEC-016",
        "legacy_planning_xlsm": "DEC-025",
        "legacy_wh_xlsm": "DEC-025",
    }


# ------------------------------------------------------------------------------------------- DB guards
@pytest.mark.django_db
@pytest.mark.parametrize(
    "change",
    [
        {"file_sha256": "0" * 64},
        {"byte_size": 1},
        {"original_name": "other"},
        {"actor_id": USER},
        {"received_at": datetime(2020, 1, 1, tzinfo=UTC)},
    ],
)
def test_batch_provenance_is_immutable_in_db(change: dict[str, Any]) -> None:
    src = factories.integration_source()
    batch = im.receive_file(_ctx(), source_code=src.code, content=SYNTHETIC_FILE, original_name="x").batch
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        ImportBatch.objects.filter(pk=batch.pk).update(**change)
    assert "provenance is immutable" in str(exc.value)


@pytest.mark.django_db
def test_staged_payload_is_immutable_in_db_but_status_may_change() -> None:
    src = factories.integration_source()
    batch = _staged(src, _rows(1))
    row = StagingRow.objects.get(batch=batch)
    with pytest.raises(IntegrityError), transaction.atomic():
        StagingRow.objects.filter(pk=row.pk).update(payload={"col_a": "tampered"})
    StagingRow.objects.filter(pk=row.pk).update(validation_status=RowStatus.PENDING_REVIEW)
    row.refresh_from_db()
    assert row.row_version == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("change", "constraint"),
    [
        ({"error_row_count": 5}, "ck_import_batch_error_rows_range"),
        ({"status": BatchStatus.VALIDATED}, "ck_import_batch_staged_has_ts"),
        ({"status": BatchStatus.REJECTED}, "ck_import_batch_closed_has_reason"),
    ],
)
def test_batch_check_constraints(change: dict[str, Any], constraint: str) -> None:
    src = factories.integration_source()
    batch = im.receive_file(_ctx(), source_code=src.code, content=SYNTHETIC_FILE, original_name="x").batch
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        ImportBatch.objects.filter(pk=batch.pk).update(**change)
    assert constraint in str(exc.value)


@pytest.mark.django_db
def test_error_row_needs_codes() -> None:
    src = factories.integration_source()
    batch = _staged(src, _rows(1))
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        StagingRow.objects.filter(batch=batch).update(validation_status=RowStatus.ERROR)
    assert "ck_staging_row_error_has_codes" in str(exc.value)


# ------------------------------------------------------------------------------------------- race
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_concurrent_duplicate_imports_create_exactly_one_batch() -> None:
    """6 importers on separate connections receive the same synthetic file at the same instant."""
    src = factories.integration_source()

    def importer(i: int) -> tuple[uuid.UUID, bool]:
        res = im.receive_file(
            _ctx(), source_code=src.code, content=SYNTHETIC_FILE, original_name=f"syn-{i}.xlsx"
        )
        return res.batch.id, res.created

    results = run_concurrently(importer, 6)
    assert all(isinstance(r, tuple) for r in results), results
    assert len({r[0] for r in results}) == 1
    assert sum(r[1] for r in results) == 1
    assert ImportBatch.objects.filter(source=src).count() == 1
    assert OutboxEvent.objects.filter(event_type="platform.integration.batch_received").count() == 1
    assert AuditEvent.objects.filter(action="platform.integration.batch.receive_duplicate").count() == 5
    assert timedelta(0) <= datetime.now(UTC) - ImportBatch.objects.get(source=src).received_at
