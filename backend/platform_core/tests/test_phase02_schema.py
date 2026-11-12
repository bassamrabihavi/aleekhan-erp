"""PHASE_02 / 02.2 schema contract: tables, names, CHECK/UNIQUE/FK/trigger guards, seeds (synthetic data
only).

Acceptance: ID-01 (14-digit code kept as exact text), ID-03 (independent lines, one serial each),
INV-02-01/02/05/
06/07/09. The allocation primitive and the ID-02/ID-04 race proofs are in
``test_phase02_serial_allocation.py``.
Every value below is synthetic (``phase02_factories``); no real type, category, code, customer or serial.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, connection, transaction
from django.db.models.functions import Now

from platform_core.code14 import Code14Field
from platform_core.commercial.models import (
    CustomerOrder,
    CustomerOrderLine,
    CustomerOrderVersion,
    OrderChangeRequest,
    OrderType,
)
from platform_core.product_identity.models import (
    CodeRuleRevision,
    Customer,
    ExternalRef,
    ExternalRefType,
    HistoricalOrderRecord,
    Product,
    ProductClass,
    ProductCode,
    Serial,
    SerialCounter,
    SerialSnapshot,
    Style,
    StyleRevision,
    UnitOfMeasure,
)
from platform_core.workflow.models import ApprovalRequest

from . import phase02_factories as f
from .phase01_factories import user

pytestmark = pytest.mark.django_db
SEED21 = __import__("importlib").import_module("platform_core.migrations.0021_phase02_seed_catalogue")
GUARDS20 = __import__("importlib").import_module("platform_core.migrations.0020_phase02_db_guards")
PHASE02_TABLES = list(GUARDS20.PHASE02_TABLES)


@contextmanager
def refused(rule: str) -> Iterator[None]:
    """The statement (or the deferred check at the end of the block) is refused with ``rule`` in the
    message."""
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        yield
        with connection.cursor() as cur:
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")  # fire the deferred constraint triggers now
    assert rule in str(exc.value), str(exc.value)


def _raw_delete(table: str, pk: Any) -> None:
    """DELETE in SQL (the ORM collector would stop at PROTECT before the DB trigger is reached)."""
    with connection.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE id = %s", [pk])  # noqa: S608 - fixed test table names


def _immediate() -> None:
    """Fire the pending deferred checks now, then defer again (later multi-statement steps stay atomic)."""
    with connection.cursor() as cur:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute("SET CONSTRAINTS ALL DEFERRED")


def _rows(sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        return list(cur.fetchall())


# ----------------------------------------------------------------------------------------- structure
def test_phase02_tables_exist_with_owning_module_prefix() -> None:
    tables = {r[0] for r in _rows("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert set(PHASE02_TABLES) <= tables
    assert all(t.startswith(("identity_", "commercial_")) for t in PHASE02_TABLES)
    assert len(PHASE02_TABLES) == 21


def test_phase02_constraint_and_index_names_follow_convention() -> None:
    prefix = {"c": "ck_", "f": "fk_", "u": "uq_", "x": "ex_", "t": "trg_"}  # t = deferred constraint trigger
    bad = [
        (t, n)
        for n, t, k in _rows(
            "SELECT c.conname, t.relname, c.contype FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = ANY(%s)",
            [PHASE02_TABLES],
        )
        if not (str(n).endswith("_pkey") if k == "p" else str(n).startswith(prefix.get(str(k), "?")))
    ]
    bad += [
        (t, n)
        for n, t in _rows(
            "SELECT ic.relname, t.relname FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid "
            "JOIN pg_class t ON t.oid = i.indrelid WHERE t.relname = ANY(%s) "
            "AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)",
            [PHASE02_TABLES],
        )
        if not str(n).startswith(("ix_", "uq_"))  # uq_ = partial / expression unique index
    ]
    assert bad == []


def test_phase02_timestamps_are_timestamptz_and_codes_are_varchar() -> None:
    rows = _rows(
        "SELECT table_name, column_name, data_type, character_maximum_length FROM information_schema.columns "
        "WHERE table_name = ANY(%s)",
        [PHASE02_TABLES],
    )
    stamps = {r[2] for r in rows if str(r[1]).endswith("_at") or r[1] in ("valid_from", "valid_to")}
    assert stamps == {"timestamp with time zone"}
    by_col = {(r[0], r[1]): (r[2], r[3]) for r in rows}
    # ID-01: 14-digit codes are varchar(14), never numeric; DEC-006: serial numbers are varchar(32)
    for col in (
        ("identity_product_code", "code"),
        ("identity_code_rule_golden_case", "expected_code"),
        ("identity_historical_order_record", "normalised_product_code"),
    ):
        assert by_col[col] == ("character varying", 14), col
    assert by_col[("identity_serial", "serial_number")] == ("character varying", 32)
    assert by_col[("identity_historical_order_record", "legacy_serial_text")] == ("character varying", 32)


def test_every_phase02_foreign_key_is_protect_and_indexed() -> None:
    rows = _rows(
        "SELECT t.relname, c.conname, c.confdeltype, "
        "  EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]) "
        "FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
        "WHERE c.contype = 'f' AND t.relname = ANY(%s)",
        [PHASE02_TABLES],
    )
    assert len(rows) >= 60
    assert {r[2] for r in rows} == {"a"}  # NO ACTION (Django PROTECT): never cascades
    assert [r[:2] for r in rows if not r[3]] == []  # every FK column leads an index (no seq-scan on delete)


def test_every_mutable_phase02_table_has_touch_and_no_delete_triggers() -> None:
    trig = {
        (str(t), str(n))
        for t, n in _rows(
            "SELECT c.relname, tg.tgname FROM pg_trigger tg JOIN pg_class c ON c.oid = tg.tgrelid "
            "WHERE NOT tg.tgisinternal AND c.relname = ANY(%s)",
            [PHASE02_TABLES],
        )
    }
    for t in GUARDS20.IDENTITY_TOUCH + GUARDS20.BUMP:
        assert (t, f"trg_{t}_touch") in trig, t
    for t in GUARDS20.NO_DELETE:
        assert (t, f"trg_{t}_no_delete") in trig, t
    for t in GUARDS20.APPEND_ONLY:
        assert (t, f"trg_{t}_append_only") in trig, t
    deferred = {
        str(n)
        for (n,) in _rows(
            "SELECT tgname FROM pg_trigger WHERE tgdeferrable AND tginitdeferred AND tgname LIKE 'trg_%%'"
        )
    }
    assert {
        "trg_identity_serial_counter_gapless",
        "trg_identity_serial_committed",
        "trg_commercial_customer_order_committed",
        "trg_commercial_order_change_request_applied",
        "trg_commercial_customer_order_line_cancel_paired",
        "trg_identity_serial_cancel_paired",
    } <= deferred


# -------------------------------------------------------------------------------------------- seeds
def test_seed_is_generic_only_and_no_real_master_data_is_seeded() -> None:
    assert dict(UnitOfMeasure.objects.values_list("code", "decision_id")) == {
        "PIECE": "DEC-058",
        "PAIR": "DEC-058",
    }
    assert list(OrderType.objects.order_by("sort_order").values_list("code", flat=True)) == [
        c for c, _l, _o in SEED21.ORDER_TYPES
    ]
    assert set(ExternalRefType.objects.values_list("key", flat=True)) == {
        k for k, _ in SEED21.EXTERNAL_REF_TYPES
    }
    counter = SerialCounter.objects.get()
    assert (
        counter.namespace_key,
        counter.start_value,
        counter.legacy_max_exclusive,
        counter.decision_id,
    ) == (
        "factory_serial",
        63001,
        63000,
        "DEC-006",
    )
    assert counter.number_pattern == r"^[1-9][0-9]*$"
    # DEC-005 / R-38: no type, category, product, style, code, customer or serial comes from Git
    for model in (ProductClass, Product, Style, ProductCode, Customer, Serial, HistoricalOrderRecord):
        assert not model.objects.exists(), model


def test_only_one_factory_serial_namespace_can_exist() -> None:
    with refused("ck_identity_serial_counter_single_ns"):
        SerialCounter.objects.create(
            namespace_key="second_namespace",
            start_value=1,
            next_value=1,
            legacy_max_exclusive=0,
            number_pattern=r"^[1-9][0-9]*$",
            decision_id="DEC-006",
        )
    with refused("uq_identity_serial_counter_namespace"):
        SerialCounter.objects.create(**SEED21.SERIAL_COUNTER)


# ------------------------------------------------------------------------------ ID-01: 14-digit codes
LEADING_ZERO_CODE = "00012345678901"  # synthetic


def test_id01_code_with_leading_zeros_is_stored_and_read_back_as_the_same_text() -> None:
    batch, row = f.staging()
    pc = ProductCode.objects.create(
        code=LEADING_ZERO_CODE,
        status="RESERVED",
        provenance_kind="IMP",
        import_batch=batch,
        staging_row=row,
        source_raw_value=LEADING_ZERO_CODE,
    )
    got = ProductCode.objects.values_list("code", flat=True).get(pk=pc.pk)
    assert got == LEADING_ZERO_CODE and isinstance(got, str) and len(got) == 14
    assert _rows("SELECT pg_typeof(code)::text FROM identity_product_code WHERE id = %s", [pc.pk]) == [
        ("character varying",)
    ]


@pytest.mark.parametrize(
    "bad",
    ["1234567890123", "", "0001234567890a", "۰۲۰۱۰۷۹۰۰۱۰۰۰۳", "0201 079001000", " 0201079001000"],
)
def test_id01_db_refuses_any_code_that_is_not_14_ascii_digits(bad: str) -> None:
    batch, row = f.staging()
    with refused("ck_identity_product_code_fmt"):
        ProductCode.objects.create(
            code=bad, status="RESERVED", provenance_kind="IMP", import_batch=batch, staging_row=row
        )


def test_id01_db_refuses_a_15_character_code() -> None:
    batch, row = f.staging()
    with pytest.raises(DataError), transaction.atomic():
        ProductCode.objects.create(
            code="1" * 15, status="RESERVED", provenance_kind="IMP", import_batch=batch, staging_row=row
        )


def test_id01_field_never_coerces_an_integer() -> None:
    with pytest.raises(ValidationError):
        Code14Field().to_python(12345678901234)


def test_code_unique_in_its_namespace() -> None:
    batch, row = f.staging()
    batch2, row2 = f.staging()
    ProductCode.objects.create(
        code=LEADING_ZERO_CODE, status="RESERVED", provenance_kind="IMP", import_batch=batch, staging_row=row
    )
    with refused("uq_identity_product_code_ns_code"):
        ProductCode.objects.create(
            code=LEADING_ZERO_CODE,
            status="RESERVED",
            provenance_kind="IMP",
            import_batch=batch2,
            staging_row=row2,
        )


# -------------------------------------------------------------------------------- provenance (INV-02-09)
def test_imported_rows_point_to_their_raw_row_and_sys_rows_carry_no_batch() -> None:
    batch, row = f.staging()
    with refused("ck_identity_customer_prov_imp_has_row"):
        f.customer(provenance_kind="IMP", import_batch=batch)
    with refused("ck_identity_customer_prov_sys_no_batch"):
        f.customer(import_batch=batch, staging_row=row)
    c = f.customer(
        provenance_kind="IMP", import_batch=batch, staging_row=row, source_sheet="Syn", source_cell_ref="A1"
    )
    assert (c.provenance_kind, c.import_batch_id, c.staging_row_id) == ("IMP", batch.pk, row.pk)


# ---------------------------------------------------------------------------- classification (DEC-005)
def test_code_segments_are_fixed_width_digits() -> None:
    t = f.product_type(f.free_type_segment())
    with refused("ck_identity_class_segment_fmt"):
        f.category(t, segment="7")
    with refused("ck_identity_product_no_fmt"):
        f.product(t, product_no="901")
    p = f.product(t)
    c = f.category(t)
    with refused("ck_identity_style_no_fmt"):
        f.style(p, c, style_no="0000")  # styles count from 0001 (DEC-005)
    with refused("ck_identity_style_no_fmt"):
        f.style(p, c, style_no="A-99")


def test_category_belongs_to_a_type_and_style_pairs_product_with_category_of_the_same_type() -> None:
    t1 = f.product_type(f.free_type_segment())
    t2 = f.product_type(f.free_type_segment())
    c1 = f.category(t1)
    with refused("ck_identity_class_category_under_type"):
        f.category(c1, segment="08")
    with refused("ck_identity_product_of_type"):
        f.product(c1)
    p2 = f.product(t2)
    with refused("ck_identity_style_category_of_type"):
        f.style(p2, c1)


def test_type_has_unit_and_scheme_and_belt_numbers_are_buckle_plus_width() -> None:
    with refused("ck_identity_class_type_attributes"):
        f.product_type(f.free_type_segment(), uom=None)  # type: ignore[arg-type]
    belt = f.product_type(f.free_type_segment(), product_no_scheme="BELT_BUCKLE_WIDTH")
    with refused("ck_identity_product_belt_scheme"):
        f.product(belt, product_no="9001")
    with refused("ck_identity_product_belt_no"):
        f.product(belt, product_no="1234", buckle_type_code="12", belt_width_code="35")
    p = f.product(belt, product_no="1235", buckle_type_code="12", belt_width_code="35")
    assert p.product_no == "1235"
    plain = f.product_type(f.free_type_segment())
    with refused("ck_identity_product_belt_scheme"):
        f.product(plain, product_no="1235", buckle_type_code="12", belt_width_code="35")


def test_segments_never_change_once_written() -> None:
    t, _c, p, s, _r = f.styled()
    with refused("immutable_column"):
        ProductClass.objects.filter(pk=t.pk).update(segment_value="00")
    with refused("immutable_column"):
        Product.objects.filter(pk=p.pk).update(product_no="9002")
    with refused("immutable_column"):
        Style.objects.filter(pk=s.pk).update(style_no="0002")
    with refused("is append-only"):
        _raw_delete("identity_style", s.pk)


def test_style_revision_one_active_and_immutable_after_draft() -> None:
    _t, _c, _p, s, r1 = f.styled()
    with refused("uq_identity_style_revision_one_active"):
        f.style_revision(s, revision_no=2, status="ACTIVE")
    with refused("ck_identity_style_revision_immutable"):
        StyleRevision.objects.filter(pk=r1.pk).update(attributes={"colour_fa": "x"})
    StyleRevision.objects.filter(pk=r1.pk).update(status="SUPERSEDED")
    with refused("terminal_immutable"):
        StyleRevision.objects.filter(pk=r1.pk).update(status="ACTIVE")


# ----------------------------------------------------------------- code rule + registry (DEC-005, INV-02-07)
def test_code_rule_maker_checker_and_lifecycle() -> None:
    maker, approver = user(), user()
    rule = f.code_rule(maker)
    with refused("ck_identity_code_rule_lifecycle"):
        CodeRuleRevision.objects.filter(pk=rule.pk).update(status="ACTIVE")
    CodeRuleRevision.objects.filter(pk=rule.pk).update(status="IN_REVIEW")
    with refused("ck_identity_code_rule_content_frozen"):
        CodeRuleRevision.objects.filter(pk=rule.pk).update(rule_spec={"changed": True})
    with refused("ck_identity_code_rule_approved_by_other"):
        CodeRuleRevision.objects.filter(pk=rule.pk).update(
            status="APPROVED", approved_by=maker, approved_at=Now()
        )
    CodeRuleRevision.objects.filter(pk=rule.pk).update(
        status="APPROVED", approved_by=approver, approved_at=Now()
    )
    with refused("uq_identity_code_rule_one_active"), transaction.atomic():
        CodeRuleRevision.objects.filter(pk=rule.pk).update(status="ACTIVE")
        other = f.code_rule(maker)
        CodeRuleRevision.objects.filter(pk=other.pk).update(status="IN_REVIEW")
        CodeRuleRevision.objects.filter(pk=other.pk).update(
            status="APPROVED", approved_by=approver, approved_at=Now()
        )
        CodeRuleRevision.objects.filter(pk=other.pk).update(status="ACTIVE")


def _issue(sty: Style, rule: CodeRuleRevision | None, issuer: Any, code: str | None = None) -> ProductCode:
    return ProductCode.objects.create(
        code=code or f.code_for(sty),
        style=sty,
        rule_revision=rule,
        status="RESERVED",
        issue_idempotency_key=uuid.uuid4(),
        issued_by=issuer,
        issued_at=Now(),
    )


def test_issuing_needs_an_active_rule_and_a_code_equal_to_the_style_segments() -> None:
    maker, approver, issuer = user(), user(), user()
    _t, _c, _p, sty, _r = f.styled()
    draft = f.code_rule(maker)
    with refused("RULE_NOT_APPROVED"):
        _issue(sty, draft, issuer)
    rule = f.active_code_rule(maker, approver)
    with refused("ck_identity_product_code_matches_style"):
        _issue(sty, rule, issuer, code=f.code_for(sty)[:-1] + "9")
    with refused("ck_identity_product_code_sys_issued"):
        _issue(sty, rule, issuer, code="03" + f.code_for(sty)[2:])  # prefix "02" = product nature (DEC-005)
    pc = _issue(sty, rule, issuer)
    assert (pc.status, pc.erp_status, pc.code) == ("RESERVED", "ERP_PENDING", f.code_for(sty))
    with refused("ck_identity_product_code_active_matched"):
        ProductCode.objects.filter(pk=pc.pk).update(status="ACTIVE")
    with refused("immutable_column"):
        ProductCode.objects.filter(pk=pc.pk).update(code=LEADING_ZERO_CODE)
    _t2, _c2, _p2, other, _r2 = f.styled()
    with refused("ck_identity_product_code_style_set_once"):
        ProductCode.objects.filter(pk=pc.pk).update(style=other)


# ---------------------------------------------------------------------------- serial (DEC-006, INV-02-05)
def _counter() -> SerialCounter:
    return SerialCounter.objects.get(namespace_key="factory_serial")


def test_counter_moves_by_exactly_one_and_keeps_its_fixed_columns() -> None:
    c = _counter()
    with refused("ck_identity_serial_counter_step"):
        SerialCounter.objects.filter(pk=c.pk).update(next_value=c.next_value + 2)
    with refused("immutable_column"):
        SerialCounter.objects.filter(pk=c.pk).update(start_value=1)
    with refused("is append-only"):
        _raw_delete("identity_serial_counter", c.pk)
    # a drawn number that no serial holds is a gap: refused at COMMIT (G-B)
    with refused("ck_identity_serial_counter_gapless"):
        SerialCounter.objects.filter(pk=c.pk).update(next_value=c.next_value + 1)


@pytest.mark.parametrize("bad", ["0{n}", "S{n}", "{n}-1", "{n}-P", "{n}-N", "BG{n}", " {n}", ""])
def test_system_serial_numbers_are_plain_integer_text(bad: str) -> None:
    """DEC-006: a new serial is a plain integer as text; legacy shapes are never generated."""
    _t, _c, _p, sty, rev = f.styled()
    with refused("ck_identity_serial_number"):
        c = SerialCounter.objects.select_for_update().get(namespace_key="factory_serial")
        SerialCounter.objects.filter(pk=c.pk).update(next_value=c.next_value + 1)  # draw the number
        Serial.objects.create(
            serial_counter=c,
            serial_number=bad.format(n=c.next_value),
            serial_value=c.next_value,
            customer=f.customer(),
            style=sty,
            style_revision=rev,
            allocation_idempotency_key=uuid.uuid4(),
            allocated_by=user(),
        )


def test_a_serial_number_must_have_been_drawn_from_the_counter() -> None:
    _t, _c, _p, sty, rev = f.styled()
    c = _counter()
    with refused("ck_identity_serial_drawn_from_counter"):
        Serial.objects.create(
            serial_counter=c,
            serial_number=str(c.next_value),  # not drawn yet (no FOR UPDATE + step)
            serial_value=c.next_value,
            customer=f.customer(),
            style=sty,
            style_revision=rev,
            allocation_idempotency_key=uuid.uuid4(),
            allocated_by=user(),
        )


def test_confirmed_serial_is_immutable_never_deleted_and_cancel_is_terminal() -> None:
    o, _lines, _creator = f.validated_order(1)
    f.confirm_order(o.pk, user())
    _immediate()
    serial = Serial.objects.get(pk=CustomerOrderLine.objects.values_list("serial_id", flat=True).get(order=o))
    with refused("immutable_column"):
        Serial.objects.filter(pk=serial.pk).update(serial_number="99999", serial_value=99999)
    with refused("is append-only"):
        _raw_delete("identity_serial", serial.pk)
    with refused("ck_identity_serial_lifecycle"):
        Serial.objects.filter(pk=serial.pk).update(status="DELIVERED")
    with refused("ck_identity_serial_cancel_has_reason"):
        Serial.objects.filter(pk=serial.pk).update(status="CANCELLED", cancelled_at=Now())
    snap = SerialSnapshot.objects.get(serial=serial)
    with refused("is append-only"):
        SerialSnapshot.objects.filter(pk=snap.pk).update(snapshot={})
    with refused("ck_identity_serial_snapshot_contiguous"):
        SerialSnapshot.objects.create(
            serial=serial,
            version=3,
            snapshot={},
            reason="CHANGE_APPLIED",
            order_version=2,
            change_request_id=uuid.uuid4(),
            created_by=user(),
        )


def test_a_cancelled_line_and_its_serial_are_cancelled_together() -> None:
    o, _lines, _creator = f.validated_order(1)
    f.confirm_order(o.pk, user())
    _immediate()
    serial_id = CustomerOrderLine.objects.values_list("serial_id", flat=True).get(order=o)
    with refused("ck_phase02_line_serial_cancel_paired"):
        Serial.objects.filter(pk=serial_id).update(
            status="CANCELLED", cancelled_at=Now(), cancel_reason="synthetic"
        )


def test_serial_without_snapshot_or_line_cannot_commit() -> None:
    """INV-02-04 / REV-0201: the deferred pairing checks refuse an orphan serial at COMMIT."""
    _t, _c, _p, sty, rev = f.styled()
    with refused("ck_identity_serial_has_snapshot_v1"):
        c = SerialCounter.objects.select_for_update().get(namespace_key="factory_serial")
        SerialCounter.objects.filter(pk=c.pk).update(next_value=c.next_value + 1)
        Serial.objects.create(
            serial_counter=c,
            serial_number=str(c.next_value),
            serial_value=c.next_value,
            customer=f.customer(),
            style=sty,
            style_revision=rev,
            allocation_idempotency_key=uuid.uuid4(),
            allocated_by=user(),
        )


# ---------------------------------------------------------------------------------- legacy (DEC-005/006)
def _legacy(**over: Any) -> HistoricalOrderRecord:
    batch, row = f.staging("NOrderSynthetic")
    data: dict[str, Any] = {
        "provenance_kind": "LEG",
        "import_batch": batch,
        "staging_row": row,
        "code_flag": "ABSENT",
    }
    data.update(over)
    return HistoricalOrderRecord.objects.create(**data)


def test_legacy_serials_stay_text_duplicates_are_flagged_and_the_system_range_is_protected() -> None:
    for text in ("S1234", "1234-1", "1234-P", "1234-N", "BG12"):  # synthetic shapes, history only
        assert _legacy(legacy_serial_text=text).legacy_serial_text == text
    a = _legacy(legacy_serial_text="1234", legacy_serial_value=1234)
    b = _legacy(legacy_serial_text="1234", legacy_serial_value=1234, legacy_serial_duplicate=True)
    assert (a.legacy_serial_text, b.legacy_serial_duplicate) == ("1234", True)  # not merged, not unique
    with refused("ck_identity_historical_plain_serial_has_value"):
        _legacy(legacy_serial_text="1235")
    with refused("ck_identity_historical_legacy_serial_below_system_range"):
        _legacy(legacy_serial_text="63000", legacy_serial_value=63000)  # DEC-006: legacy must stay < 63000
    with refused("ck_identity_historical_is_legacy"):
        _legacy(provenance_kind="IMP")


def test_legacy_non_14_code_is_kept_as_disputed_history_and_never_auto_fixed() -> None:
    rec = _legacy(legacy_product_code_raw="0201079001*", code_flag="DISPUTED")
    assert rec.legacy_product_code_raw == "0201079001*" and rec.normalised_product_code is None
    with refused("ck_identity_historical_ok_has_code"):
        _legacy(legacy_product_code_raw="0201079001*", code_flag="OK")
    with refused("ck_identity_historical_immutable"):
        HistoricalOrderRecord.objects.filter(pk=rec.pk).update(normalised_product_code="02010790010001")
    HistoricalOrderRecord.objects.filter(pk=rec.pk).update(match_status="SUGGESTED")


# --------------------------------------------------------------------------------- external references
def test_external_refs_are_typed_raw_text_and_not_globally_unique() -> None:
    cust, other = f.customer(), f.customer()
    for target in (cust, other):  # the same customer style code under two customers (C-56)
        ExternalRef.objects.create(
            target_type="customer",
            target_id=target.pk,
            system="CUSTOMER",
            ref_type_id="customer_style_code",
            value="007",
        )
    assert ExternalRef.objects.filter(value="007").count() == 2
    with refused("uq_identity_ext_ref_target_value"):
        ExternalRef.objects.create(
            target_type="customer",
            target_id=cust.pk,
            system="CUSTOMER",
            ref_type_id="customer_style_code",
            value="007",
        )
    with refused("fk_identity_external_ref"):
        ExternalRef.objects.create(
            target_type="customer", target_id=cust.pk, system="CUSTOMER", ref_type_id="not_a_type", value="1"
        )
    ExternalRefType.objects.create(
        key="syn_new_ref_type", label_fa=f"نوع ساختگی {f.SYN}"
    )  # extensible (DEC-058)


# ------------------------------------------------------------------------------------- commercial orders
def test_po_number_is_not_unique_and_brand_must_belong_to_the_customer() -> None:
    creator = user()
    cust, other = f.customer(), f.customer()
    f.order(cust, creator, external_po_number="PO-SYN-1")
    f.order(cust, creator, external_po_number="PO-SYN-1")  # duplicate -> warning in the engine, never refused
    assert CustomerOrder.objects.filter(external_po_number="PO-SYN-1").count() == 2
    with refused("ck_commercial_order_brand_of_customer"):
        f.order(cust, creator, brand=f.brand(other))
    assert f.order(cust, creator, brand=f.brand(cust)).brand_id is not None


def test_representative_name_is_only_a_name_and_contact_columns_do_not_exist() -> None:
    cols = {
        r[0]
        for r in _rows(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ANY(%s)", [PHASE02_TABLES]
        )
    }
    assert "customer_representative_name" in cols
    assert not {c for c in cols if any(k in c for k in ("phone", "email", "mobile", "address", "contact"))}
    with refused("ck_commercial_order_rep_name_nonempty"):
        f.order(f.customer(), user(), customer_representative_name="")


def test_id03_one_po_many_independent_lines_each_with_its_own_serial() -> None:
    o, lines, _creator = f.validated_order(3)
    numbers = f.confirm_order(o.pk, user())
    _immediate()
    assert len(set(numbers)) == 3
    serial_ids = list(CustomerOrderLine.objects.filter(order=o).values_list("serial_id", flat=True))
    assert len(set(serial_ids)) == 3 and None not in serial_ids
    # a serial belongs to one line: UNIQUE(serial_id) (the set-once trigger refuses re-pointing first)
    assert _rows(
        "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
        "WHERE c.conname = 'uq_commercial_line_serial'"
    ) == [("UNIQUE (serial_id)",)]
    with refused("ck_commercial_line_serial_set_once"):
        CustomerOrderLine.objects.filter(pk=lines[0].pk).update(serial_id=serial_ids[1])


def test_line_unit_is_the_type_unit_and_line_numbers_are_unique_and_never_deleted() -> None:
    o, lines, _creator = f.validated_order(1)
    CustomerOrder.objects.filter(pk=o.pk).update(status="DRAFT")
    _t, _c, _p, shoe_style, shoe_rev = f.styled(uom="PAIR")
    with refused("ck_commercial_line_uom_of_type"):
        f.line(o, shoe_style, shoe_rev, line_no=2, uom_id="PIECE")
    assert f.line(o, shoe_style, shoe_rev, line_no=2).uom_id == "PAIR"
    with refused("uq_commercial_line_order_no"):
        f.line(o, shoe_style, shoe_rev, line_no=1)
    with refused("is append-only"):
        _raw_delete("commercial_customer_order_line", lines[0].pk)


def test_order_confirmer_is_not_its_creator_and_confirmed_line_needs_a_serial() -> None:
    o, lines, creator = f.validated_order(1)
    with refused("ck_commercial_order_confirmer_not_creator"):
        f.confirm_order(o.pk, creator)
    with refused("ck_commercial_line_serial_by_status"):
        CustomerOrderLine.objects.filter(pk=lines[0].pk).update(status="CONFIRMED", order_version=1)


def test_confirmed_order_header_is_frozen_and_changes_only_with_a_new_version() -> None:
    o, _lines, _creator = f.validated_order(1)
    f.confirm_order(o.pk, user())
    _immediate()
    with refused("ck_commercial_order_frozen"):
        CustomerOrder.objects.filter(pk=o.pk).update(external_po_number="PO-SYN-X")
    with refused("ck_commercial_order_frozen"):
        CustomerOrder.objects.filter(pk=o.pk).update(requested_due_date=date(2030, 2, 1))
    with refused("ck_commercial_order_version_step"):
        CustomerOrder.objects.filter(pk=o.pk).update(current_version=3)
    with refused("ck_commercial_order_version_row"):  # bump without the version row of the change request
        CustomerOrder.objects.filter(pk=o.pk).update(requested_due_date=date(2030, 2, 1), current_version=2)


def test_order_status_graph_single_hold_resumes_to_the_previous_state() -> None:
    o, _lines, _creator = f.validated_order(1)
    f.confirm_order(o.pk, user())
    _immediate()
    with refused("ck_commercial_order_transition"):
        CustomerOrder.objects.filter(pk=o.pk).update(status="DRAFT")
    rel = user()
    CustomerOrder.objects.filter(pk=o.pk).update(
        status="RELEASED_TO_PLAN", released_by=rel, released_at=Now()
    )
    with refused("ck_commercial_order_transition"):  # a hold must remember the state it resumes to
        CustomerOrder.objects.filter(pk=o.pk).update(status="ON_HOLD", current_version=2, hold_reason="syn")
    with refused("ck_commercial_order_hold_consistent"):  # ... and carries a reason
        CustomerOrder.objects.filter(pk=o.pk).update(
            status="ON_HOLD", current_version=2, status_before_hold="RELEASED_TO_PLAN"
        )
    with refused("ck_commercial_order_transition"):  # no direct way back
        CustomerOrder.objects.filter(pk=o.pk).update(status="CONFIRMED")
    with refused("ck_commercial_order_transition"):  # DEC-059 C-A: no cancel after release (PHASE_05)
        CustomerOrder.objects.filter(pk=o.pk).update(
            status="CANCELLED", current_version=2, cancel_reason="syn"
        )


def test_hold_and_resume_return_to_the_stored_state_with_a_version_each() -> None:
    o, _lines, creator = f.validated_order(1)
    f.confirm_order(o.pk, user())
    _immediate()
    applier = user()
    for version, update in (
        (2, {"status": "ON_HOLD", "status_before_hold": "CONFIRMED", "hold_reason": "synthetic hold"}),
        (3, {"status": "CONFIRMED", "status_before_hold": None, "hold_reason": None}),
    ):
        with transaction.atomic():
            kind = "HOLD" if update["status"] == "ON_HOLD" else "RESUME"
            o.refresh_from_db()
            cr = _change_request(o, creator, kind, status="SUBMITTED", submitted_at=Now())
            OrderChangeRequest.objects.filter(pk=cr.pk).update(
                status="APPROVED", decided_by=applier, decided_at=Now()
            )
            CustomerOrder.objects.filter(pk=o.pk).update(current_version=version, **update)
            CustomerOrderVersion.objects.create(
                order=o,
                version=version,
                image={},
                reason="CHANGE_APPLIED",
                change_request=cr,
                created_by=applier,
            )
            OrderChangeRequest.objects.filter(pk=cr.pk).update(
                status="APPLIED", applied_by=applier, applied_at=Now(), applied_version=version
            )
            _immediate()
    o.refresh_from_db()
    assert (o.status, o.current_version, o.status_before_hold) == ("CONFIRMED", 3, None)


def _change_request(o: CustomerOrder, requester: Any, kind: str, **over: Any) -> OrderChangeRequest:
    data: dict[str, Any] = {
        "request_no": f"SYN-CR-{uuid.uuid4().hex[:8]}",
        "order": o,
        "base_order_version": o.current_version,
        "kind": kind,
        "items": [],
        "reason": "synthetic change",
        "requested_by": requester,
    }
    data.update(over)
    return OrderChangeRequest.objects.create(**data)


def test_change_requests_exist_only_for_confirmed_orders_and_after_release_only_due_date_or_hold() -> None:
    draft, _l, creator = f.validated_order(1)
    with refused("ck_commercial_cr_order_state"):
        _change_request(draft, creator, "QTY_CHANGE", base_order_version=1)
    o, _lines, _c = f.validated_order(1)
    f.confirm_order(o.pk, user())
    _immediate()
    o.refresh_from_db()
    with refused("ck_commercial_cr_base_is_current"):
        _change_request(o, creator, "QTY_CHANGE", base_order_version=2)
    with refused("ck_commercial_cr_hold_state"):
        _change_request(o, creator, "RESUME")
    _change_request(o, creator, "QTY_CHANGE")  # allowed before release
    CustomerOrder.objects.filter(pk=o.pk).update(
        status="RELEASED_TO_PLAN", released_by=user(), released_at=Now()
    )
    for kind in ("QTY_CHANGE", "ADD_LINE", "CANCEL_LINE", "CANCEL_ORDER"):
        with refused("ck_commercial_cr_kind_after_release"):
            _change_request(o, creator, kind)
    for kind in ("DUE_DATE_CHANGE", "HOLD"):
        _change_request(o, creator, kind)


def test_change_request_maker_checker_and_due_date_needs_the_planning_approval() -> None:
    o, _lines, creator = f.validated_order(1)
    f.confirm_order(o.pk, user())
    _immediate()
    o.refresh_from_db()
    manager, planner, applier = user(), user(), user()
    cr = _change_request(o, creator, "DUE_DATE_CHANGE", items=[{"field": "requested_due_date"}])
    OrderChangeRequest.objects.filter(pk=cr.pk).update(status="SUBMITTED", submitted_at=Now())
    with refused("ck_commercial_cr_content_frozen"):
        OrderChangeRequest.objects.filter(pk=cr.pk).update(reason="changed reason")
    with refused("ck_commercial_cr_decider_not_requester"):
        OrderChangeRequest.objects.filter(pk=cr.pk).update(
            status="APPROVED", decided_by=creator, decided_at=Now()
        )
    OrderChangeRequest.objects.filter(pk=cr.pk).update(
        status="APPROVED", decided_by=manager, decided_at=Now()
    )

    def apply(planning: bool) -> None:
        CustomerOrder.objects.filter(pk=o.pk).update(requested_due_date=date(2030, 3, 1), current_version=2)
        CustomerOrderVersion.objects.create(
            order=o,
            version=2,
            image={"synthetic": True},
            reason="CHANGE_APPLIED",
            change_request=cr,
            created_by=applier,
        )
        extra: dict[str, Any] = (
            {"planning_approved_by": planner, "planning_approved_at": Now()} if planning else {}
        )
        OrderChangeRequest.objects.filter(pk=cr.pk).update(
            status="APPLIED", applied_by=applier, applied_at=Now(), applied_version=2, **extra
        )

    with refused("ck_commercial_cr_due_date_planning_approved"):
        apply(planning=False)
    with transaction.atomic():
        apply(planning=True)
        _immediate()
    o.refresh_from_db()
    assert (o.current_version, o.requested_due_date) == (2, date(2030, 3, 1))
    assert list(
        CustomerOrderVersion.objects.filter(order=o).order_by("version").values_list("version", flat=True)
    ) == [1, 2]
    with refused("is append-only"):
        CustomerOrderVersion.objects.filter(order=o, version=1).update(image={})
    with refused("terminal_immutable"):
        OrderChangeRequest.objects.filter(pk=cr.pk).update(status="EXPIRED")


def test_released_order_lines_change_only_in_due_date_and_confirmed_lines_only_with_a_version() -> None:
    o, lines, _creator = f.validated_order(1)
    f.confirm_order(o.pk, user())
    _immediate()
    ln = lines[0]
    with refused("ck_commercial_line_change_needs_version"):
        CustomerOrderLine.objects.filter(pk=ln.pk).update(quantity=99)
    CustomerOrder.objects.filter(pk=o.pk).update(
        status="RELEASED_TO_PLAN", released_by=user(), released_at=Now()
    )
    with refused("ck_commercial_line_frozen_after_release"), transaction.atomic():
        CustomerOrder.objects.filter(pk=o.pk).update(requested_due_date=date(2030, 4, 1), current_version=2)
        CustomerOrderLine.objects.filter(pk=ln.pk).update(quantity=99, order_version=2)


def test_approval_request_link_is_a_protected_fk() -> None:
    o, _lines, creator = f.validated_order(1)
    f.confirm_order(o.pk, user())
    _immediate()
    o.refresh_from_db()
    with refused("fk_commercial_order_change_request"):
        _change_request(o, creator, "QTY_CHANGE", approval_id=uuid.uuid4())
    assert ApprovalRequest._meta.db_table == "platform_approval_request"


# ------------------------------------------------------------------------------- matrix v2.0 (DEC-057)
MATRIX_DOC = (
    __import__("pathlib").Path(__file__).resolve().parents[3]
    / "docs"
    / "security"
    / "PERMISSION_MATRIX_DRAFT.md"
)
V20_COLUMNS = {
    "OA": "owner_admin",
    "MGT": "management_viewer",
    "CO": "commercial_officer",
    "CM": "commercial_manager",
    "PO": "planning_officer",
    "PDS": "product_data_steward",
    "CRA": "code_rule_approver",
}


def _matrix_v20_doc() -> dict[str, tuple[set[str], set[str]]]:
    lines = MATRIX_DOC.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## 7. Matrix v2.0"))
    header_idx = next(i for i in range(start, len(lines)) if lines[i].startswith("| Permission"))
    header = [c.strip() for c in lines[header_idx].strip("|").split("|")]
    out = {}
    for ln in lines[header_idx + 2 :]:
        if not ln.startswith(("| identity.", "| commercial.")):
            break
        row = dict(zip(header, [c.strip() for c in ln.strip("|").split("|")], strict=True))
        flags = set(__import__("re").findall(r"\b(MFA|BA|SoD)\b", row["Flags"]))
        holders = {code for col, code in V20_COLUMNS.items() if row[col] == "●"}
        assert all(row[col] in ("●", "—") for col in V20_COLUMNS), ln
        out[row[header[0]]] = (flags, holders)
    return out


def test_matrix_v20_seed_equals_section_7_of_the_matrix_document_cell_by_cell() -> None:
    from platform_core.identity.models import Permission, Role, RolePermission

    doc = _matrix_v20_doc()
    assert len(doc) == 22
    for action, (flags, holders) in doc.items():
        p = Permission.objects.get(action=action)
        assert (p.mfa_step_up, p.business_approval, p.maker_checker) == (
            "MFA" in flags,
            "BA" in flags,
            "SoD" in flags,
        )
        assert (p.matrix_version, p.decision_id) == ("2.0", "DEC-057")
        grants = set(RolePermission.objects.filter(permission=p).values_list("role__code", "grant_mode"))
        assert grants == {(code, "SCOPE") for code in holders}, action  # all customers (DEC-057 answer 3)
    new = {r.code: r for r in Role.objects.filter(code__in=list(V20_COLUMNS.values())[2:])}
    assert {(r.kind, r.status, r.matrix_version, r.decision_id) for r in new.values()} == {
        ("BUSINESS", "ACTIVE", "2.0", "DEC-057")
    }
    # nobody else holds a PHASE_02 permission (employee, technical roles, other business roles)
    others = RolePermission.objects.filter(permission__action__regex=r"^(identity|commercial)[.]").exclude(
        role__code__in=list(V20_COLUMNS.values())
    )
    assert not others.exists()


def test_owner_decides_directly_but_technical_roles_hold_no_other_business_approval() -> None:
    from platform_core.authz import policy as P
    from platform_core.identity.models import RolePermission

    ba_technical = set(
        RolePermission.objects.filter(role__kind="TECHNICAL", permission__business_approval=True).values_list(
            "role__code", "permission_id"
        )
    )
    assert ba_technical == {("owner_admin", a) for a in P.OWNER_BA_ACTIONS}
    assert {
        "identity.code_rule.approve",
        "commercial.order.confirm",
        "commercial.change.decide",
    } <= P.OWNER_BA_ACTIONS
    # the widened DB guard (0022) still refuses the PHASE_02 decisions for any other TECHNICAL role
    from platform_core.identity.models import Role

    tech = Role.objects.create(code="syn_tech_role", name_fa=f"نقش فنی ساختگی {f.SYN}", kind="TECHNICAL")
    for action in ("identity.code_rule.approve", "commercial.order.confirm", "commercial.change.decide"):
        with refused("ck_role_technical_no_business_approval"):
            RolePermission.objects.create(role=tech, permission_id=action, grant_mode="SCOPE")
