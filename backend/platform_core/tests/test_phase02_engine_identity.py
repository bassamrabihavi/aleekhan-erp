"""PHASE_02 / 02.3 Identity engine (DEC-005 / DEC-057 / DEC-058) against PostgreSQL: customers and brands,
product / style numbering, the code rule revision lifecycle (maker != checker, fresh MFA, >= 20 golden cases
per family), code preview and issue (RULE_NOT_APPROVED without an ACTIVE revision), the ERP match (B1).
Synthetic data only (``9x`` types, ``9xxx`` products, R-38).
"""

from __future__ import annotations

import uuid
from itertools import product
from typing import Any

import pytest

from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import (
    AccessDenied,
    AleekhanError,
    EngineContractError,
    IdempotencyKeyReused,
    MfaRequired,
    NotFound,
    RuleNotApproved,
    SelfApprovalForbidden,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.models import AuditEvent, OutboxEvent
from platform_core.product_identity import coderule, codes, master
from platform_core.product_identity.models import (
    CodeRuleGoldenCase,
    CodeRuleRevision,
    CodeRuleStatus,
    Customer,
    ProductCode,
    StyleRevision,
)

from . import phase02_engine as e
from . import phase02_factories as f
from .phase02_engine import deferred_checks  # noqa: F401 - fixture

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("deferred_checks")]
SHA = "a" * 64  # synthetic workbook hash


def _reason(exc: AleekhanError) -> str:
    return exc.errors[0].code


@pytest.fixture
def p() -> e.People:
    return e.people()


# ------------------------------------------------------------------------------------------- customers
def test_customer_number_and_duplicate_name_warning(p: e.People) -> None:
    name = f"مشتری ساختگی یکتا {uuid.uuid4().hex[:6]} {f.SYN}"
    a = master.create_customer(p.co.caller, display_name_fa=name)
    assert a.customer_no.startswith("CU-") and len(a.customer_no) >= 9
    with pytest.raises(ValidationFailed) as exc:
        master.create_customer(p.co.caller, display_name_fa=name.upper())
    assert _reason(exc.value) == "DUPLICATE_CUSTOMER_NAME"
    b = master.create_customer(
        p.co.caller, display_name_fa=name, acknowledge_warnings=["DUPLICATE_CUSTOMER_NAME"]
    )
    assert b.customer_no != a.customer_no
    audit = AuditEvent.objects.get(action="identity.customer.create", resource_id=str(b.pk))
    assert audit.scope == {"acknowledged_warnings": ["DUPLICATE_CUSTOMER_NAME"]}
    ev = OutboxEvent.objects.get(event_type="identity.customer.created", aggregate_id=str(b.pk))
    assert ev.payload == {"id": str(b.pk), "status": "ACTIVE"}  # no name in the event (S1)
    b = master.update_customer(
        p.co.caller, b.pk, expected_version=b.row_version, status="INACTIVE", reason="synthetic deactivation"
    )
    assert b.status == "INACTIVE"
    with pytest.raises(StateTransitionNotAllowed):  # an inactive customer takes no new brand
        master.add_brand(p.co.caller, b.pk, brand_name_fa=f"برند ساختگی {f.SYN}")


def test_brands_are_unique_per_customer(p: e.People) -> None:
    c = master.create_customer(p.co.caller, display_name_fa=f"مشتری ساختگی {uuid.uuid4().hex[:6]} {f.SYN}")
    b = master.add_brand(p.co.caller, c.pk, brand_name_fa=f"برند ساختگی {f.SYN}")
    with pytest.raises(ValidationFailed):
        master.add_brand(p.co.caller, c.pk, brand_name_fa=f"برند ساختگی {f.SYN}")
    b = master.set_brand_status(
        p.co.caller, b.pk, status="INACTIVE", expected_version=b.row_version, reason="syn"
    )
    assert b.status == "INACTIVE"


@pytest.mark.parametrize(
    "role",
    [
        "commercial_manager",
        "planning_officer",
        "product_data_steward",
        "management_viewer",
        "owner_admin",
        "employee",
    ],
)
def test_only_commercial_officers_manage_customers(role: str) -> None:
    who = e.holder(role)
    with pytest.raises(AccessDenied):
        master.create_customer(who.caller, display_name_fa=f"مشتری ساختگی {f.SYN}")
    assert not Customer.objects.filter(created_by_id=who.pk).exists()


# ---------------------------------------------------------------------------------- products / styles
def test_product_number_is_max_of_the_type_plus_one_with_leading_zeros(p: e.People) -> None:
    t = f.product_type()
    f.product(t, "0007")
    f.product(t, "0003")
    a = master.create_product(p.pds.caller, product_type_id=t.pk, name_fa=f"محصول ساختگی {f.SYN}")
    b = master.create_product(p.pds.caller, product_type_id=t.pk, name_fa=f"محصول ساختگی {f.SYN}")
    assert (a.product_no, b.product_no, a.status) == ("0008", "0009", "DRAFT")
    empty = f.product_type()
    assert (
        master.create_product(p.pds.caller, product_type_id=empty.pk, name_fa=f"م {f.SYN}").product_no
        == "0001"
    )
    with pytest.raises(ValidationFailed) as exc:
        master.create_product(
            p.pds.caller, product_type_id=t.pk, name_fa="x", buckle_type_code="12", belt_width_code="35"
        )
    assert _reason(exc.value) == "BELT_SEGMENTS_NOT_ALLOWED"
    f.product(t, "9999")
    with pytest.raises(ValidationFailed) as exc:
        master.create_product(p.pds.caller, product_type_id=t.pk, name_fa=f"م {f.SYN}")
    assert _reason(exc.value) == "PRODUCT_NO_EXHAUSTED"


def test_belt_product_number_is_buckle_and_width(p: e.People) -> None:
    belt = f.product_type(product_no_scheme="BELT_BUCKLE_WIDTH")
    prod = master.create_product(
        p.pds.caller,
        product_type_id=belt.pk,
        name_fa=f"کمربند ساختگی {f.SYN}",
        buckle_type_code="07",
        belt_width_code="35",
    )
    assert (prod.product_no, prod.buckle_type_code, prod.belt_width_code) == ("0735", "07", "35")
    with pytest.raises(ValidationFailed) as exc:
        master.create_product(p.pds.caller, product_type_id=belt.pk, name_fa="x")
    assert _reason(exc.value) == "BELT_SEGMENTS_REQUIRED"
    with pytest.raises(StateTransitionNotAllowed) as exc2:
        master.create_product(
            p.pds.caller, product_type_id=belt.pk, name_fa="x", buckle_type_code="07", belt_width_code="35"
        )
    assert _reason(exc2.value) == "PRODUCT_NO_TAKEN"
    with pytest.raises(ValidationFailed):
        master.create_product(
            p.pds.caller, product_type_id=belt.pk, name_fa="x", buckle_type_code="7", belt_width_code="35"
        )


def test_style_number_is_count_of_product_and_category_plus_one(p: e.People) -> None:
    t = f.product_type()
    c1, c2 = f.category(t, "01"), f.category(t, "02")
    prod = f.product(t, "9001")
    s1 = master.create_style(p.pds.caller, product_id=prod.pk, category_id=c1.pk, name_fa=f"استایل {f.SYN}")
    s2 = master.create_style(p.pds.caller, product_id=prod.pk, category_id=c1.pk, name_fa=f"استایل {f.SYN}")
    s3 = master.create_style(p.pds.caller, product_id=prod.pk, category_id=c2.pk, name_fa=f"استایل {f.SYN}")
    assert (s1.style_no, s2.style_no, s3.style_no) == ("0001", "0002", "0001")  # per (product, category)
    other_type_cat = f.category(f.product_type(), "03")
    with pytest.raises(ValidationFailed):  # the category belongs to the product's type
        master.create_style(p.pds.caller, product_id=prod.pk, category_id=other_type_cat.pk, name_fa="x")


def test_rev0232_style_collision_takes_the_first_free_number_after_count_plus_one(p: e.People) -> None:
    """DEC-005 amendment 2026-11-14: count + 1 taken -> first free number after it, audited; never refused."""
    from platform_core.models import AuditEvent

    t = f.product_type()
    c = f.category(t, "01")
    prod = f.product(t, "9001")
    f.style(prod, c, "0001")
    f.style(prod, c, "0003")  # legacy gap: count + 1 = 0003 already exists
    f.style(prod, c, "0004")  # ... and so does the next one
    s = master.create_style(p.pds.caller, product_id=prod.pk, category_id=c.pk, name_fa=f"س {f.SYN}")
    assert s.style_no == "0005"  # count (3) + 1 = 0004 is taken -> first free after it
    audit = AuditEvent.objects.get(action="identity.style.create", resource_id=str(s.pk))
    assert "first free number" in audit.reason
    assert audit.scope["style_no_collision"] == {"count_plus_one": "0004", "assigned": "0005"}
    s2 = master.create_style(p.pds.caller, product_id=prod.pk, category_id=c.pk, name_fa=f"س {f.SYN}")
    assert s2.style_no == "0006"  # count (4) + 1 = 0005 is taken -> 0006; the gap 0002 is never back-filled
    f.style(prod, f.category(t, "02"), "0001")
    s3 = master.create_style(p.pds.caller, product_id=prod.pk, category_id=c.pk, name_fa=f"س {f.SYN}")
    assert s3.style_no == "0007"
    clean = master.create_style(
        p.pds.caller, product_id=prod.pk, category_id=f.category(t, "03").pk, name_fa=f"س {f.SYN}"
    )
    assert clean.style_no == "0001"
    assert AuditEvent.objects.get(action="identity.style.create", resource_id=str(clean.pk)).reason == ""


def test_master_status_and_style_revisions(p: e.People) -> None:
    t = f.product_type()
    c = f.category(t, "01")
    prod = master.create_product(p.pds.caller, product_type_id=t.pk, name_fa=f"م {f.SYN}")
    prod = master.set_product_status(
        p.pds.caller, prod.pk, status="ACTIVE", expected_version=prod.row_version, reason="syn"
    )
    with pytest.raises(StateTransitionNotAllowed):
        master.set_product_status(
            p.pds.caller, prod.pk, status="DRAFT", expected_version=prod.row_version, reason="syn"
        )
    s = master.create_style(p.pds.caller, product_id=prod.pk, category_id=c.pk, name_fa=f"س {f.SYN}")
    r1 = master.create_style_revision(p.pds.caller, style_id=s.pk, attributes={"colour_fa": f"رنگ {f.SYN}"})
    r2 = master.create_style_revision(
        p.pds.caller, style_id=s.pk, attributes={"colour_fa": f"رنگ دوم {f.SYN}"}
    )
    assert (r1.revision_no, r2.revision_no, r1.status) == (1, 2, "DRAFT")
    r1 = master.activate_style_revision(p.pds.caller, r1.pk, expected_version=r1.row_version)
    r2 = master.activate_style_revision(p.pds.caller, r2.pk, expected_version=r2.row_version)
    assert StyleRevision.objects.get(pk=r1.pk).status == "SUPERSEDED" and r2.status == "ACTIVE"
    with pytest.raises(StateTransitionNotAllowed):
        master.activate_style_revision(
            p.pds.caller, r1.pk, expected_version=StyleRevision.objects.get(pk=r1.pk).row_version
        )
    with pytest.raises(ValidationFailed):
        master.create_style_revision(p.pds.caller, style_id=s.pk, attributes={"password": "x"})
    with pytest.raises(AccessDenied):
        master.create_style_revision(p.co.caller, style_id=s.pk, attributes={})


MASTER_STATES = ["DRAFT", "ACTIVE", "RETIRED"]


@pytest.mark.parametrize(("src", "dst"), list(product(MASTER_STATES, MASTER_STATES)))
def test_master_machine(src: str, dst: str) -> None:
    assert master.MASTER_MACHINE.can(src, dst) is ((src, dst) in {("DRAFT", "ACTIVE"), ("ACTIVE", "RETIRED")})


# --------------------------------------------------------------------------------------------- code rule
def _golden(types: list[str], n: int = 20) -> list[dict[str, Any]]:
    out = []
    for t in types:
        for i in range(n):
            inputs = {
                "type_code": t,
                "category_code": "07",
                "product_no": f"{9000 + i:04d}",
                "style_no": "0001",
            }
            out.append(
                {
                    "inputs": inputs,
                    "expected_code": "02" + t + "07" + inputs["product_no"] + "0001",
                    "source_sheet": "SyntheticSheet",
                    "source_cell_ref": f"{t}{i}",
                }
            )
    return out


def _active_rule(p: e.People, types: list[str]) -> CodeRuleRevision:
    r = codes.create_rule_revision(p.pds.caller, product_type_codes=types, source_workbook_sha256=SHA)
    codes.add_golden_cases(p.pds.caller, r.pk, cases=_golden(types))
    r.refresh_from_db()
    r = codes.submit_rule_revision(p.pds.caller, r.pk, expected_version=r.row_version)
    r = codes.approve_rule_revision(p.cra.caller, r.pk, expected_version=r.row_version)
    return codes.activate_rule_revision(p.cra.caller, r.pk, expected_version=r.row_version)


def test_code_rule_lifecycle_with_maker_checker_and_golden_gate(p: e.People) -> None:
    r = codes.create_rule_revision(p.pds.caller, product_type_codes=["92", "91"], source_workbook_sha256=SHA)
    assert (r.status, r.scope, r.rule_spec, r.decision_id) == (
        "DRAFT",
        {"product_types": ["91", "92"]},
        coderule.rule_spec_v1(),
        "DEC-005",
    )
    codes.add_golden_cases(p.pds.caller, r.pk, cases=_golden(["91"], 20) + _golden(["92"], 19))
    r.refresh_from_db()
    with pytest.raises(StateTransitionNotAllowed) as exc:  # family 92 has only 19 cases (Gate: >= 20)
        codes.submit_rule_revision(p.pds.caller, r.pk, expected_version=r.row_version)
    assert _reason(exc.value) == "GOLDEN_CASES_INSUFFICIENT"
    bad = _golden(["92"], 1)
    bad[0].update(expected_code="02920790000002", source_cell_ref="bad0")  # the engine does not reproduce it
    codes.add_golden_cases(p.pds.caller, r.pk, cases=bad)
    r.refresh_from_db()
    with pytest.raises(StateTransitionNotAllowed) as exc:
        codes.submit_rule_revision(p.pds.caller, r.pk, expected_version=r.row_version)
    assert {x.code for x in exc.value.errors} == {"GOLDEN_CASE_MISMATCH"}
    fresh = codes.create_rule_revision(
        p.pds.caller, product_type_codes=["91", "92"], source_workbook_sha256=SHA
    )
    codes.add_golden_cases(p.pds.caller, fresh.pk, cases=_golden(["91", "92"]) + _golden(["93"], 1))
    fresh.refresh_from_db()
    with pytest.raises(StateTransitionNotAllowed) as exc:
        codes.submit_rule_revision(p.pds.caller, fresh.pk, expected_version=fresh.row_version)
    assert _reason(exc.value) == "GOLDEN_CASE_OUT_OF_SCOPE"
    good = codes.create_rule_revision(
        p.pds.caller, product_type_codes=["91", "92"], source_workbook_sha256=SHA
    )
    codes.add_golden_cases(p.pds.caller, good.pk, cases=_golden(["91", "92"]))
    good.refresh_from_db()
    good = codes.submit_rule_revision(p.pds.caller, good.pk, expected_version=good.row_version)
    assert (good.status, good.golden_case_count) == ("IN_REVIEW", 40)
    with pytest.raises(StateTransitionNotAllowed):  # no golden case is added after DRAFT
        codes.add_golden_cases(p.pds.caller, good.pk, cases=_golden(["91"], 1))
    with pytest.raises(AccessDenied):  # the maker's role cannot approve
        codes.approve_rule_revision(p.pds.caller, good.pk, expected_version=good.row_version)
    maker_approver = e.holder("product_data_steward", "code_rule_approver")
    own = codes.create_rule_revision(
        maker_approver.caller, product_type_codes=["91"], source_workbook_sha256=SHA
    )
    codes.add_golden_cases(maker_approver.caller, own.pk, cases=_golden(["91"]))
    own.refresh_from_db()
    own = codes.submit_rule_revision(maker_approver.caller, own.pk, expected_version=own.row_version)
    with pytest.raises(SelfApprovalForbidden) as exc2:
        codes.approve_rule_revision(maker_approver.caller, own.pk, expected_version=own.row_version)
    assert _reason(exc2.value) == "APPROVER_IS_MAKER"
    stale_mfa = e.holder("code_rule_approver", mfa=False)
    with pytest.raises(MfaRequired):
        codes.approve_rule_revision(stale_mfa.caller, good.pk, expected_version=good.row_version)
    good = codes.approve_rule_revision(
        p.owner.caller, good.pk, expected_version=good.row_version
    )  # DEC-005 Q-A
    assert (good.status, good.approved_by_id) == ("APPROVED", p.owner.pk)
    assert not CodeRuleGoldenCase.objects.filter(rule_revision=good, verified_by__isnull=True).exists()
    good = codes.activate_rule_revision(p.cra.caller, good.pk, expected_version=good.row_version)
    assert good.status == "ACTIVE"
    own = codes.reject_rule_revision(
        p.cra.caller, own.pk, expected_version=own.row_version, reason="synthetic"
    )
    assert own.status == "REJECTED"
    newer = _active_rule(p, ["91", "92", "93"])
    assert newer.status == "ACTIVE" and CodeRuleRevision.objects.get(pk=good.pk).status == "RETIRED"
    kinds = set(
        OutboxEvent.objects.filter(aggregate_type="identity.code_rule_revision").values_list(
            "event_type", flat=True
        )
    )
    assert {"identity.code_rule.created", "identity.code_rule.submitted", "identity.code_rule.approved",
            "identity.code_rule.activated", "identity.code_rule.retired", "identity.code_rule.rejected",
            "identity.code_rule.golden_cases_added"} <= kinds  # fmt: skip


RULE_STATES = sorted(CodeRuleStatus.values)
RULE_ALLOWED = {
    ("DRAFT", "IN_REVIEW"),
    ("IN_REVIEW", "APPROVED"),
    ("IN_REVIEW", "REJECTED"),
    ("APPROVED", "ACTIVE"),
    ("ACTIVE", "RETIRED"),
}


@pytest.mark.parametrize(("src", "dst"), list(product(RULE_STATES, RULE_STATES)))
def test_code_rule_machine_equals_the_db_lifecycle(src: str, dst: str) -> None:
    assert codes.CODE_RULE_MACHINE.can(src, dst) is ((src, dst) in RULE_ALLOWED)


# ------------------------------------------------------------------------------------------ issue code
def test_issue_needs_an_active_rule_covering_the_type(p: e.People) -> None:
    t = f.product_type("91")
    s = f.style(f.product(t, "9001"), f.category(t, "07"), "0001")
    with pytest.raises(RuleNotApproved) as exc:
        codes.issue_product_code(p.pds.caller, s.pk, idempotency_key=uuid.uuid4())
    assert (exc.value.decision_id, _reason(exc.value)) == ("DEC-005", "NO_ACTIVE_CODE_RULE")
    _active_rule(p, ["92"])
    with pytest.raises(RuleNotApproved) as exc:
        codes.issue_product_code(p.pds.caller, s.pk, idempotency_key=uuid.uuid4())
    assert _reason(exc.value) == "TYPE_NOT_IN_RULE_SCOPE"
    assert not ProductCode.objects.exists()


def test_issue_reserves_the_code_once_and_replays_by_key(p: e.People) -> None:
    rule = _active_rule(p, ["91"])
    t = f.product_type("91")
    s = f.style(f.product(t, "9001"), f.category(t, "07"), "0042")
    preview = codes.preview_style_code(p.co.caller, s.pk)
    assert preview == {
        "code": "02910790010042",
        "legacy_only": False,
        "style_id": str(s.pk),
        "issued": False,
        "status": None,
        "erp_status": None,
    }
    assert not AuditEvent.objects.filter(
        action__startswith="identity.product_code"
    ).exists()  # side-effect free
    key = uuid.uuid4()
    pc, replayed = codes.issue_product_code(p.pds.caller, s.pk, idempotency_key=key)
    assert (pc.code, pc.status, pc.erp_status, pc.rule_revision_id, replayed) == (
        "02910790010042",
        "RESERVED",
        "ERP_PENDING",
        rule.pk,
        False,
    )
    again, replayed2 = codes.issue_product_code(p.pds.caller, s.pk, idempotency_key=key)
    assert (again.pk, replayed2) == (pc.pk, True)
    assert OutboxEvent.objects.filter(event_type="identity.product_code.reserved").count() == 1
    with pytest.raises(StateTransitionNotAllowed) as exc:
        codes.issue_product_code(p.pds.caller, s.pk, idempotency_key=uuid.uuid4())
    assert _reason(exc.value) == "CODE_ALREADY_ISSUED"
    other = f.style(s.product, s.category, "0043")
    with pytest.raises(IdempotencyKeyReused):
        codes.issue_product_code(p.pds.caller, other.pk, idempotency_key=key)
    with pytest.raises(AccessDenied):  # management_viewer holds no identity.product_code.read
        codes.preview_style_code(p.viewer.caller, s.pk)
    with pytest.raises(AccessDenied):
        codes.issue_product_code(p.co.caller, other.pk, idempotency_key=uuid.uuid4())
    stale = e.holder("product_data_steward", mfa=False)
    with pytest.raises(MfaRequired):
        codes.issue_product_code(stale.caller, other.pk, idempotency_key=uuid.uuid4())


def test_issue_refuses_a_code_value_already_in_the_registry(p: e.People) -> None:
    _active_rule(p, ["91"])
    t = f.product_type("91")
    s = f.style(f.product(t, "9001"), f.category(t, "07"), "0005")
    batch, _row = f.staging()
    ProductCode.objects.create(
        code=f.code_for(s),
        status="ACTIVE",
        erp_status="ERP_MATCHED",
        erp_seen_batch=batch,
        provenance_kind="IMP",
        import_batch=batch,
        staging_row=_row,
    )
    with pytest.raises(StateTransitionNotAllowed) as exc:
        codes.issue_product_code(p.pds.caller, s.pk, idempotency_key=uuid.uuid4())
    assert _reason(exc.value) == "CODE_IN_REGISTRY"


def test_preview_of_a_new_style_or_product_writes_nothing(p: e.People) -> None:
    t = f.product_type("91")
    c = f.category(t, "07")
    prod = f.product(t, "9004")
    f.style(prod, c, "0001")
    assert codes.preview_new_code(
        p.co.caller, product_type_id=t.pk, category_id=c.pk, product_id=prod.pk
    ) == {
        "code": "02910790040002",
        "product_no": "9004",
        "style_no": "0002",
        "new_product": False,
    }
    assert (
        codes.preview_new_code(p.co.caller, product_type_id=t.pk, category_id=c.pk)["code"]
        == "02910790050001"
    )
    belt = f.product_type("90", product_no_scheme="BELT_BUCKLE_WIDTH")
    bc = f.category(belt, "02")
    out = codes.preview_new_code(
        p.co.caller, product_type_id=belt.pk, category_id=bc.pk, buckle_type_code="03", belt_width_code="40"
    )
    assert out == {"code": "02900203400001", "product_no": "0340", "style_no": "0001", "new_product": True}
    assert (
        not ProductCode.objects.exists()
        and not AuditEvent.objects.filter(action__startswith="identity.product").exists()
    )


def test_erp_match_turns_a_reserved_code_active(p: e.People) -> None:
    _active_rule(p, ["91"])
    t = f.product_type("91")
    s = f.style(f.product(t, "9001"), f.category(t, "07"), "0009")
    pc, _r = codes.issue_product_code(p.pds.caller, s.pk, idempotency_key=uuid.uuid4())
    batch, _row = f.staging()
    with pytest.raises(EngineContractError):  # only the import (system actor) records an ERP match
        codes.mark_erp_matched(p.po.caller.context(), code=pc.code, batch_id=batch.pk)
    sys = RequestContext(Actor.system())
    done = codes.mark_erp_matched(sys, code=pc.code, batch_id=batch.pk)
    assert (done.status, done.erp_status, done.erp_seen_batch_id) == ("ACTIVE", "ERP_MATCHED", batch.pk)
    with pytest.raises(StateTransitionNotAllowed) as exc:
        codes.mark_erp_matched(sys, code=pc.code, batch_id=batch.pk)
    assert _reason(exc.value) == "CODE_NOT_RESERVED"
    with pytest.raises(NotFound):
        codes.mark_erp_matched(sys, code="02919999990001", batch_id=batch.pk)
    with pytest.raises(ValidationFailed):
        codes.mark_erp_matched(sys, code="2919999990001", batch_id=batch.pk)


# ------------------------------------------------------------- legacy style 0000 (DEC-005 amendment 11-13)
def test_legacy_style_0000_is_stored_and_matched_but_never_issued(p: e.People) -> None:
    from .phase01_factories import db_refuses

    _active_rule(p, ["91"])
    t = f.product_type("91")
    c = f.category(t, "07")
    prod = f.product(t, "9001")
    with db_refuses("ck_identity_style_no_fmt"):  # a system style is never 0000
        f.style(prod, c, "0000")
    batch, row = f.staging()
    legacy_style = f.style(prod, c, "0000", provenance_kind="LEG", import_batch=batch, staging_row=row)
    _b2, row2 = f.staging()
    legacy_code = ProductCode.objects.create(  # a legacy code registered and linked to its legacy style
        code="02910790010000",
        style=legacy_style,
        status="RESERVED",
        erp_status="ERP_PENDING",
        provenance_kind="LEG",
        import_batch=_b2,
        staging_row=row2,
    )
    assert legacy_code.code == "02910790010000"
    preview = codes.preview_style_code(p.co.caller, legacy_style.pk)
    assert (preview["code"], preview["legacy_only"], preview["issued"]) == ("02910790010000", True, True)
    other = f.style(prod, c, "0002")
    with pytest.raises(ValidationFailed):  # never issued for a legacy 0000 style, linked or not
        codes.issue_product_code(p.pds.caller, legacy_style.pk, idempotency_key=uuid.uuid4())
    bare_legacy = f.style(
        prod, f.category(t, "08"), "0000", provenance_kind="IMP", import_batch=batch, staging_row=row
    )
    with pytest.raises(ValidationFailed) as exc:  # the system never issues style 0000
        codes.issue_product_code(p.pds.caller, bare_legacy.pk, idempotency_key=uuid.uuid4())
    assert _reason(exc.value) == "STYLE_0000_LEGACY_ONLY"
    pc, _r = codes.issue_product_code(p.pds.caller, other.pk, idempotency_key=uuid.uuid4())
    assert pc.code == "02910790010002"
    rule = CodeRuleRevision.objects.get(status="ACTIVE")
    with db_refuses("ck_identity_product_code_sys_no_style_0000"):  # the DB refuses a system 0000 code too
        ProductCode.objects.create(
            code="02910890010000",
            style=bare_legacy,
            rule_revision=rule,
            status="RESERVED",
            erp_status="ERP_PENDING",
            provenance_kind="SYS",
            issue_idempotency_key=uuid.uuid4(),
            issued_by_id=p.pds.pk,
            issued_at=__import__("django.db.models.functions", fromlist=["Now"]).Now(),
        )


def test_golden_cases_with_style_0000_pass_as_legacy_only(p: e.People) -> None:
    cases = _golden(["91"])
    cases[0]["inputs"] = {**cases[0]["inputs"], "style_no": "0000"}
    cases[0]["expected_code"] = cases[0]["expected_code"][:10] + "0000"
    r = codes.create_rule_revision(p.pds.caller, product_type_codes=["91"], source_workbook_sha256=SHA)
    codes.add_golden_cases(p.pds.caller, r.pk, cases=cases)
    r.refresh_from_db()
    r = codes.submit_rule_revision(p.pds.caller, r.pk, expected_version=r.row_version)
    assert (r.status, r.golden_case_count) == ("IN_REVIEW", 20)


def test_rev0231_rev0230_submit_refuses_belt_cases_without_segments_and_c77_disagreement(p: e.People) -> None:
    belt = f.product_type(product_no_scheme="BELT_BUCKLE_WIDTH")
    t = belt.segment_value
    plain = _golden([t])  # belt-type cases WITHOUT buckle / width
    r = codes.create_rule_revision(p.pds.caller, product_type_codes=[t], source_workbook_sha256=SHA)
    codes.add_golden_cases(p.pds.caller, r.pk, cases=plain)
    r.refresh_from_db()
    with pytest.raises(ValidationFailed) as exc:  # BELT_SEGMENTS_REQUIRED is an input refusal (400)
        codes.submit_rule_revision(p.pds.caller, r.pk, expected_version=r.row_version)
    assert _reason(exc.value) == "BELT_SEGMENTS_REQUIRED"
    with_segments = _golden([t])
    for i, case in enumerate(with_segments):
        buckle, width = f"{10 + i % 5:02d}", f"{30 + i // 5:02d}"
        case["inputs"] = {
            **case["inputs"],
            "product_no": buckle + width,
            "buckle_type_code": buckle,
            "belt_width_code": width,
            "category_code_order_form": "07",
        }
        case["expected_code"] = "02" + t + "07" + buckle + width + "0001"
    good = codes.create_rule_revision(p.pds.caller, product_type_codes=[t], source_workbook_sha256=SHA)
    codes.add_golden_cases(p.pds.caller, good.pk, cases=with_segments)
    good.refresh_from_db()
    good = codes.submit_rule_revision(p.pds.caller, good.pk, expected_version=good.row_version)
    assert good.status == "IN_REVIEW"
    c77 = [dict(c, inputs=dict(c["inputs"])) for c in with_segments]
    c77[3]["inputs"]["category_code_order_form"] = "08"  # the Order form lookup disagrees (C-77)
    bad = codes.create_rule_revision(p.pds.caller, product_type_codes=[t], source_workbook_sha256=SHA)
    codes.add_golden_cases(p.pds.caller, bad.pk, cases=c77)
    bad.refresh_from_db()
    with pytest.raises(StateTransitionNotAllowed) as exc2:
        codes.submit_rule_revision(p.pds.caller, bad.pk, expected_version=bad.row_version)
    assert _reason(exc2.value) == "GOLDEN_CASE_MISMATCH"
