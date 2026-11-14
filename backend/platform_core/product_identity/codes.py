"""DEC-005 use cases (PHASE_02 / 02.3): code rule revisions, golden cases, code preview / issue, ERP match.

Code rule revision (``identity_code_rule_revision``; STATE_TRANSITIONS 5.3)::

    create (DRAFT, identity.code_rule.manage) -> add golden cases (DRAFT only)
    submit  DRAFT -> IN_REVIEW      identity.code_rule.manage; every product type of the scope has >= 20
                                    golden cases (Gate) and the engine reproduces every case exactly
    approve IN_REVIEW -> APPROVED   identity.code_rule.approve (code_rule_approver / owner, BA + fresh MFA),
    reject  IN_REVIEW -> REJECTED   approver != maker (DEC-005 Q-A, DEC-032); approve marks the golden cases
                                    verified by the approver
    activate APPROVED -> ACTIVE     identity.code_rule.approve (fresh MFA, != maker); the previous ACTIVE
                                    revision becomes RETIRED in the same transaction

Product code (``identity_product_code``; STATE_TRANSITIONS 5.6)::

    preview        side-effect free (identity.product_code.read): the code an existing or a new style has
    issue          identity.product_code.issue (product_data_steward, fresh MFA): RESERVED / ERP_PENDING
                   (DEC-005 B1, nothing is written to Rahkaran); needs an ACTIVE revision whose spec is the
                   one this engine implements and whose scope covers the style's product type, else 409
                   RULE_NOT_APPROVED (DEC-005); idempotent per key; one live code per style
    mark_erp_matched  RESERVED / ERP_PENDING -> ACTIVE / ERP_MATCHED when the Rahkaran import (02.6) shows the
                   same code (exact match, system actor, import batch recorded)
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any, Final

from django.db.models import Max
from django.db.models.functions import Now

from platform_core.authz.policy import Caller
from platform_core.engine.context import RequestContext, db_now
from platform_core.engine.dbrules import db_rules
from platform_core.engine.errors import EngineContractError, FieldError, NotFound
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import NothingToDo, UnitOfWork, unit_of_work, unit_of_work_or_nothing
from platform_core.models import ActorType
from platform_core.schema_common import ProvenanceKind

from . import coderule
from .master import proposed_product_no, proposed_style_no
from .models import (
    PRODUCT_CODE_NAMESPACE,
    ClassLevel,
    CodeRuleGoldenCase,
    CodeRuleRevision,
    CodeRuleStatus,
    ErpStatus,
    MasterStatus,
    Product,
    ProductClass,
    ProductCode,
    ProductCodeStatus,
    ProductNoScheme,
    Style,
)
from .refusals import Reason, refuse
from .usecase import authorize, check_version, lock, reason_text

RULE_READ: Final = "identity.code_rule.read"
RULE_MANAGE: Final = "identity.code_rule.manage"
RULE_APPROVE: Final = "identity.code_rule.approve"
CODE_READ: Final = "identity.product_code.read"
CODE_ISSUE: Final = "identity.product_code.issue"
DECISION: Final = "DEC-005"
GOLDEN_MIN_PER_FAMILY: Final = 20  # PHASE_02 Gate: "20+ real cases per known family"
MAX_GOLDEN_PER_CALL: Final = 2000
LIVE_CODE_STATES: Final = (ProductCodeStatus.RESERVED, ProductCodeStatus.ACTIVE)

CODE_RULE_MACHINE: Final = StateMachine(
    name="identity.code_rule_revision",
    states=frozenset(CodeRuleStatus.values),
    transitions={
        CodeRuleStatus.DRAFT: frozenset({CodeRuleStatus.IN_REVIEW}),
        CodeRuleStatus.IN_REVIEW: frozenset({CodeRuleStatus.APPROVED, CodeRuleStatus.REJECTED}),
        CodeRuleStatus.APPROVED: frozenset({CodeRuleStatus.ACTIVE}),
        CodeRuleStatus.ACTIVE: frozenset({CodeRuleStatus.RETIRED}),
        CodeRuleStatus.RETIRED: frozenset(),
        CodeRuleStatus.REJECTED: frozenset(),
    },
)
PRODUCT_CODE_MACHINE: Final = StateMachine(
    name="identity.product_code",
    states=frozenset(ProductCodeStatus.values),
    # PHASE_02 engine writes RESERVED (issue) and RESERVED -> ACTIVE (ERP match); DISPUTED / RETIRED come
    # from the import conflict queue (02.6) and are listed so the graph is complete
    transitions={
        ProductCodeStatus.RESERVED: frozenset({ProductCodeStatus.ACTIVE, ProductCodeStatus.DISPUTED}),
        ProductCodeStatus.ACTIVE: frozenset({ProductCodeStatus.RETIRED}),
        ProductCodeStatus.DISPUTED: frozenset(),
        ProductCodeStatus.RETIRED: frozenset(),
    },
)
_PAST: Final = {
    "create": "created",
    "golden": "golden_cases_added",
    "submit": "submitted",
    "approve": "approved",
    "reject": "rejected",
    "activate": "activated",
    "retire": "retired",
}


def _rule_view(r: CodeRuleRevision) -> dict[str, Any]:
    return {
        "revision_no": r.revision_no,
        "status": r.status,
        "scope": r.scope,
        "golden_case_count": r.golden_case_count,
        "source_workbook_sha256": r.source_workbook_sha256,
    }


def _rule_write(
    uow: UnitOfWork,
    verb: str,
    r: CodeRuleRevision,
    *,
    before: Mapping[str, Any] | None,
    reason: str = "",
    scope: Mapping[str, Any] | None = None,
) -> None:
    uow.audit(
        action=f"identity.code_rule.{verb}",
        resource_type="identity.code_rule_revision",
        resource_id=str(r.pk),
        resource_version=r.row_version,
        before=before,
        after=_rule_view(r),
        reason=reason,
        scope=scope,
    )
    uow.emit(
        event_type=f"identity.code_rule.{_PAST[verb]}",
        aggregate_type="identity.code_rule_revision",
        aggregate_id=str(r.pk),
        aggregate_version=r.row_version,
        payload={"id": str(r.pk), "revision_no": r.revision_no, "status": r.status},
    )


def _scope_types(product_type_codes: Iterable[str]) -> list[str]:
    codes = list(product_type_codes)
    if not codes:
        refuse(Reason.REQUIRED, field="product_type_codes")
    for c in codes:
        coderule.CodeParts(c, "00", "0000", "0001")  # validates the 2-digit text segment
    if len(set(codes)) != len(codes):
        refuse(Reason.DUPLICATE_ITEM, field="product_type_codes")
    return sorted(codes)


def scope_types(r: CodeRuleRevision) -> frozenset[str]:
    raw = r.scope.get("product_types") if isinstance(r.scope, dict) else None
    return frozenset(raw) if isinstance(raw, list) else frozenset()


# -------------------------------------------------------------------------------------- rule revisions
def create_rule_revision(
    caller: Caller,
    *,
    product_type_codes: Iterable[str],
    source_workbook_sha256: str,
    evidence_document_id: uuid.UUID | None = None,
    request_id: uuid.UUID | None = None,
) -> CodeRuleRevision:
    """A DRAFT revision of the DEC-005 rule (``rule_spec`` = :data:`coderule.RULE_SPEC_V1`)."""
    authorize(caller, RULE_MANAGE)
    types = _scope_types(product_type_codes)
    with unit_of_work(caller.context(request_id)) as uow:
        last = CodeRuleRevision.objects.aggregate(m=Max("revision_no"))["m"] or 0
        with db_rules():
            r = CodeRuleRevision.objects.create(
                code_namespace=PRODUCT_CODE_NAMESPACE,
                revision_no=last + 1,
                scope={"product_types": types},
                rule_spec=coderule.rule_spec_v1(),
                source_workbook_sha256=source_workbook_sha256,
                evidence_document_id=evidence_document_id,
                decision_id=DECISION,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
            )
        r.refresh_from_db()
        _rule_write(uow, "create", r, before=None)
    return r


def add_golden_cases(
    caller: Caller,
    revision_id: uuid.UUID,
    *,
    cases: Iterable[Mapping[str, Any]],
    request_id: uuid.UUID | None = None,
) -> int:
    """Attach golden cases to a DRAFT revision. Each case: ``inputs`` (``type_code``, ``category_code``,
    ``product_no``, ``style_no`` as text; optional ``buckle_type_code`` / ``belt_width_code``),
    ``expected_code``, ``source_sheet``, ``source_cell_ref``. They are evidence: stored as given and checked
    at submit (a case the engine does not reproduce blocks the submit, it is never "corrected").
    Real cases exist only in the server DB (DEC-028/046, R-38)."""
    authorize(caller, RULE_MANAGE)
    rows = list(cases)
    if not rows or len(rows) > MAX_GOLDEN_PER_CALL:
        refuse(Reason.INVALID, field="cases")
    with unit_of_work(caller.context(request_id)) as uow:
        r = lock(CodeRuleRevision, revision_id)
        if r.status != CodeRuleStatus.DRAFT:
            refuse(
                Reason.STATE_NOT_ALLOWED, field="revision", detail="golden cases are added to a DRAFT only"
            )
        objs = []
        for i, raw in enumerate(rows):
            inputs = raw.get("inputs")
            expected = raw.get("expected_code")
            if not isinstance(inputs, Mapping) or not isinstance(expected, str) or len(expected) != 14:
                refuse(Reason.INVALID, field=f"cases[{i}]")
            for key in ("type_code", "category_code", "product_no", "style_no"):
                if not isinstance(inputs.get(key), str):
                    refuse(Reason.SEGMENT_FORMAT, field=f"cases[{i}].inputs.{key}")
            objs.append(
                CodeRuleGoldenCase(
                    rule_revision=r,
                    product_type_code=expected[2:4],
                    inputs={k: v for k, v in inputs.items() if isinstance(v, str)},
                    expected_code=expected,
                    source_sheet=str(raw.get("source_sheet", ""))[:100],
                    source_cell_ref=str(raw.get("source_cell_ref", ""))[:32],
                    source_workbook_sha256=r.source_workbook_sha256,
                    created_by_id=caller.user_id,
                )
            )
        with db_rules():
            CodeRuleGoldenCase.objects.bulk_create(objs)
        CodeRuleRevision.objects.filter(pk=r.pk).update(updated_by_id=caller.user_id)
        r.refresh_from_db()
        _rule_write(uow, "golden", r, before=None, scope={"added": len(objs)})
    return len(objs)


def belt_type_codes() -> frozenset[str]:
    """Segment values of the product types numbered buckle + width (DEC-005 belt)."""
    return frozenset(
        ProductClass.objects.filter(
            level_key=ClassLevel.PRODUCT_TYPE, product_no_scheme=ProductNoScheme.BELT_BUCKLE_WIDTH
        ).values_list("segment_value", flat=True)
    )


def golden_report(r: CodeRuleRevision) -> tuple[dict[str, int], list[FieldError]]:
    """Per-family counts and the problems (insufficient family, out-of-scope case, case not reproduced).

    02.4 (REV-0230 / REV-0231): a case of a belt type (``BELT_BUCKLE_WIDTH``) must carry both belt segments
    (``BELT_SEGMENTS_REQUIRED``); a case whose ``category_code_order_form`` differs from ``category_code``
    does not reproduce (C-77). A case marked ``legacy_disputed`` is neither checked nor counted (it is
    reported by the harness, DEC-005 Q-D: planning decides it)."""
    types = scope_types(r)
    belts = belt_type_codes()
    counts: Counter[str] = Counter()
    problems: list[FieldError] = []
    for g in CodeRuleGoldenCase.objects.filter(rule_revision=r).order_by("id"):
        if g.inputs.get("legacy_disputed"):
            continue
        counts[g.product_type_code] += 1
        if g.product_type_code in belts and not (
            g.inputs.get("buckle_type_code") and g.inputs.get("belt_width_code")
        ):
            problems.append(FieldError(f"golden_case:{g.pk}", Reason.BELT_SEGMENTS_REQUIRED.value))
            continue
        if g.product_type_code not in types:
            problems.append(FieldError(f"golden_case:{g.pk}", Reason.GOLDEN_CASE_OUT_OF_SCOPE.value))
            continue
        try:
            case = coderule.GoldenCase.from_mapping(
                {**g.inputs, "expected_code": g.expected_code, "family": g.product_type_code}
            )
        except ValueError:
            problems.append(FieldError(f"golden_case:{g.pk}", Reason.SEGMENT_FORMAT.value))
            continue
        bad = coderule.golden_case_problems(case)
        problems.extend(FieldError(f"golden_case:{g.pk}", code) for code in bad)
    for t in sorted(types):
        if counts[t] < GOLDEN_MIN_PER_FAMILY:
            problems.append(FieldError(f"family:{t}", Reason.GOLDEN_CASES_INSUFFICIENT.value))
    return dict(counts), problems


def _refuse_golden(problems: list[FieldError]) -> None:
    if problems:
        first = Reason(problems[0].code)
        refuse(first, field=problems[0].field, extra=tuple(problems[1:]), detail="golden cases do not pass")


def submit_rule_revision(
    caller: Caller, revision_id: uuid.UUID, *, expected_version: int, request_id: uuid.UUID | None = None
) -> CodeRuleRevision:
    authorize(caller, RULE_MANAGE)
    with unit_of_work(caller.context(request_id)) as uow:
        r = lock(CodeRuleRevision, revision_id)
        check_version(r, expected_version)
        CODE_RULE_MACHINE.assert_transition(r.status, CodeRuleStatus.IN_REVIEW)
        counts, problems = golden_report(r)
        _refuse_golden(problems)
        before = _rule_view(r)
        with db_rules():
            CodeRuleRevision.objects.filter(pk=r.pk).update(
                status=CodeRuleStatus.IN_REVIEW,
                golden_case_count=sum(counts.values()),
                updated_by_id=caller.user_id,
            )
        r.refresh_from_db()
        _rule_write(uow, "submit", r, before=before, scope={"golden_per_family": counts})
    return r


def _approver(caller: Caller, r: CodeRuleRevision) -> None:
    if r.created_by_id == caller.user_id:
        refuse(
            Reason.APPROVER_IS_MAKER,
            field="revision",
            detail="the maker of a rule revision never approves it",
        )


def approve_rule_revision(
    caller: Caller,
    revision_id: uuid.UUID,
    *,
    expected_version: int,
    note: str = "",
    request_id: uuid.UUID | None = None,
) -> CodeRuleRevision:
    decision = authorize(caller, RULE_APPROVE)
    with unit_of_work(caller.context(request_id)) as uow:
        r = lock(CodeRuleRevision, revision_id)
        check_version(r, expected_version)
        _approver(caller, r)
        CODE_RULE_MACHINE.assert_transition(r.status, CodeRuleStatus.APPROVED)
        _counts, problems = golden_report(r)  # re-checked: the approver approves what reproduces now
        _refuse_golden(problems)
        before = _rule_view(r)
        with db_rules():
            CodeRuleRevision.objects.filter(pk=r.pk).update(
                status=CodeRuleStatus.APPROVED,
                approved_by_id=caller.user_id,
                approved_at=Now(),
                updated_by_id=caller.user_id,
            )
            CodeRuleGoldenCase.objects.filter(rule_revision=r, verified_by__isnull=True).update(
                verified_by_id=caller.user_id, verified_at=Now()
            )
        r.refresh_from_db()
        _rule_write(
            uow,
            "approve",
            r,
            before=before,
            reason=note.strip()[:500],
            scope={"via_role": decision.grant.role_code if decision.grant else ""},
        )
    return r


def reject_rule_revision(
    caller: Caller,
    revision_id: uuid.UUID,
    *,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> CodeRuleRevision:
    decision = authorize(caller, RULE_APPROVE)
    text = reason_text(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        r = lock(CodeRuleRevision, revision_id)
        check_version(r, expected_version)
        _approver(caller, r)
        CODE_RULE_MACHINE.assert_transition(r.status, CodeRuleStatus.REJECTED)
        before = _rule_view(r)
        CodeRuleRevision.objects.filter(pk=r.pk).update(
            status=CodeRuleStatus.REJECTED, updated_by_id=caller.user_id
        )
        r.refresh_from_db()
        _rule_write(
            uow,
            "reject",
            r,
            before=before,
            reason=text,
            scope={"via_role": decision.grant.role_code if decision.grant else ""},
        )
    return r


def activate_rule_revision(
    caller: Caller,
    revision_id: uuid.UUID,
    *,
    expected_version: int,
    reason: str = "",
    request_id: uuid.UUID | None = None,
) -> CodeRuleRevision:
    decision = authorize(caller, RULE_APPROVE)
    text = reason.strip()[:500]
    with unit_of_work(caller.context(request_id)) as uow:
        r = lock(CodeRuleRevision, revision_id)
        check_version(r, expected_version)
        _approver(caller, r)
        CODE_RULE_MACHINE.assert_transition(r.status, CodeRuleStatus.ACTIVE)
        for old in CodeRuleRevision.objects.select_for_update().filter(
            code_namespace=r.code_namespace, status=CodeRuleStatus.ACTIVE
        ):
            old_before = _rule_view(old)
            CodeRuleRevision.objects.filter(pk=old.pk).update(
                status=CodeRuleStatus.RETIRED, updated_by_id=caller.user_id
            )
            old.refresh_from_db()
            _rule_write(uow, "retire", old, before=old_before, scope={"superseded_by": str(r.pk)})
        before = _rule_view(r)
        with db_rules():
            CodeRuleRevision.objects.filter(pk=r.pk).update(
                status=CodeRuleStatus.ACTIVE, updated_by_id=caller.user_id
            )
        r.refresh_from_db()
        _rule_write(
            uow,
            "activate",
            r,
            before=before,
            reason=text,
            scope={"via_role": decision.grant.role_code if decision.grant else ""},
        )
    return r


def active_rule_for(type_code: str) -> CodeRuleRevision:
    """The ACTIVE revision that may issue codes of ``type_code`` - else 409 RULE_NOT_APPROVED (DEC-005)."""
    r = CodeRuleRevision.objects.filter(
        code_namespace=PRODUCT_CODE_NAMESPACE, status=CodeRuleStatus.ACTIVE
    ).first()
    if r is None:
        refuse(Reason.NO_ACTIVE_CODE_RULE, field="rule_revision", detail="no ACTIVE code rule revision")
    if r.rule_spec != coderule.rule_spec_v1():
        refuse(Reason.RULE_SPEC_NOT_IMPLEMENTED, field="rule_revision")
    if type_code not in scope_types(r):
        refuse(Reason.TYPE_NOT_IN_RULE_SCOPE, field="product_type")
    return r


# ----------------------------------------------------------------------------------------- preview/issue
def _style_parts(s: Style, *, legacy: bool = False) -> coderule.CodeParts:
    """``legacy=False`` (issue) refuses a legacy-only style ``0000`` (DEC-005 amendment 2026-11-13)."""
    return coderule.CodeParts(
        s.product.product_type.segment_value,
        s.category.segment_value,
        s.product.product_no,
        s.style_no,
        legacy=legacy,
    )


def _style(style_id: uuid.UUID) -> Style:
    s = Style.objects.select_related("product__product_type", "category").filter(pk=style_id).first()
    if s is None:
        raise NotFound()
    return s


def live_code_of(style_id: uuid.UUID) -> ProductCode | None:
    return ProductCode.objects.filter(style_id=style_id, status__in=LIVE_CODE_STATES).first()


def preview_style_code(caller: Caller, style_id: uuid.UUID) -> dict[str, Any]:
    """The code of an existing style (no write, no audit). ``issued`` tells whether it is in the registry."""
    authorize(caller, CODE_READ)
    s = _style(style_id)
    parts = _style_parts(s, legacy=True)  # a legacy style 0000 is shown, never issued
    live = live_code_of(s.pk)
    return {
        "code": parts.code,
        "legacy_only": parts.is_legacy_only,
        "style_id": str(s.pk),
        "issued": live is not None,
        "status": live.status if live else None,
        "erp_status": live.erp_status if live else None,
    }


def preview_new_code(
    caller: Caller,
    *,
    product_type_id: uuid.UUID,
    category_id: uuid.UUID,
    product_id: uuid.UUID | None = None,
    buckle_type_code: str | None = None,
    belt_width_code: str | None = None,
) -> dict[str, Any]:
    """The code a NEW style would get - for an existing product (next style) or a new product (next product
    number, style 0001). Side-effect free; the numbers may be taken by someone else before creation."""
    authorize(caller, CODE_READ)
    t = ProductClass.objects.filter(pk=product_type_id, level_key=ClassLevel.PRODUCT_TYPE).first()
    c = ProductClass.objects.filter(pk=category_id, level_key=ClassLevel.CATEGORY).first()
    if t is None or c is None:
        raise NotFound()
    if c.parent_id != t.pk:
        refuse(Reason.INVALID, field="category_id", detail="the category must belong to the product type")
    if product_id is not None:
        p = Product.objects.filter(pk=product_id, product_type=t).first()
        if p is None:
            raise NotFound()
        product_no, style_no, new_product = p.product_no, proposed_style_no(p, c), False
    else:
        product_no = proposed_product_no(
            t, buckle_type_code=buckle_type_code, belt_width_code=belt_width_code
        )
        style_no, new_product = coderule.next_style_no(0), True
        existing = Product.objects.filter(product_type=t, product_no=product_no).first()
        if existing is not None:  # belt with an existing buckle + width: that product's next style
            style_no, new_product = proposed_style_no(existing, c), False
    code = coderule.build_code(t.segment_value, c.segment_value, product_no, style_no)
    return {"code": code, "product_no": product_no, "style_no": style_no, "new_product": new_product}


def _code_view(pc: ProductCode) -> dict[str, Any]:
    return {"code": pc.code, "status": pc.status, "erp_status": pc.erp_status, "style_id": str(pc.style_id)}


def issue_product_code(
    caller: Caller, style_id: uuid.UUID, *, idempotency_key: uuid.UUID, request_id: uuid.UUID | None = None
) -> tuple[ProductCode, bool]:
    """RESERVED / ERP_PENDING code of an ACTIVE style (DEC-005 B1). Returns ``(code, replayed)``."""
    authorize(caller, CODE_ISSUE)
    replayed: list[ProductCode] = []
    with unit_of_work_or_nothing(caller.context(request_id)) as uow:
        lock(Style, style_id)  # serialises issues of one style (and of one key: the key names one style)
        replay = ProductCode.objects.filter(issue_idempotency_key=idempotency_key).first()
        if replay is not None:
            if replay.style_id != style_id or replay.issued_by_id != caller.user_id:
                refuse(Reason.IDEMPOTENCY_PAYLOAD_MISMATCH, field="idempotency_key")
            replayed.append(replay)
            raise NothingToDo()  # same key, same request: the stored result, no second write
        s = _style(style_id)
        if s.status != MasterStatus.ACTIVE:
            refuse(Reason.MASTER_NOT_ACTIVE, field="style_id")
        parts = _style_parts(s)
        rule = active_rule_for(parts.type_code)
        if live_code_of(s.pk) is not None:
            refuse(Reason.CODE_ALREADY_ISSUED, field="style_id")
        if ProductCode.objects.filter(code_namespace=PRODUCT_CODE_NAMESPACE, code=parts.code).exists():
            refuse(
                Reason.CODE_IN_REGISTRY,
                field="code",
                detail="the code exists in the registry; a person links it",
            )
        with db_rules():
            pc = ProductCode.objects.create(
                code=parts.code,
                code_namespace=PRODUCT_CODE_NAMESPACE,
                style=s,
                rule_revision=rule,
                status=ProductCodeStatus.RESERVED,
                erp_status=ErpStatus.ERP_PENDING,
                issue_idempotency_key=idempotency_key,
                issued_by_id=caller.user_id,
                issued_at=db_now(),
                provenance_kind=ProvenanceKind.SYS,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
            )
        pc.refresh_from_db()
        uow.audit(
            action="identity.product_code.issue",
            resource_type="identity.product_code",
            resource_id=str(pc.pk),
            resource_version=pc.row_version,
            after=_code_view(pc),
            scope={"rule_revision_id": str(rule.pk)},
        )
        uow.emit(
            event_type="identity.product_code.reserved",
            aggregate_type="identity.product_code",
            aggregate_id=str(pc.pk),
            aggregate_version=pc.row_version,
            payload={
                "id": str(pc.pk),
                "style_id": str(s.pk),
                "rule_revision_id": str(rule.pk),
                "status": pc.status,
                "erp_status": pc.erp_status,
            },
        )
    if replayed:
        return replayed[0], True
    return pc, False


def mark_erp_matched(ctx: RequestContext, *, code: str, batch_id: uuid.UUID) -> ProductCode:
    """DEC-005 B1: the Rahkaran import (02.6, system actor) shows exactly this code: ACTIVE / ERP_MATCHED."""
    coderule.parse_code(code)
    if ctx.actor.actor_type != ActorType.SYSTEM:
        raise EngineContractError("the ERP match is written by the import (system actor)")
    with unit_of_work(ctx) as uow:
        pc = (
            ProductCode.objects.select_for_update()
            .filter(code_namespace=PRODUCT_CODE_NAMESPACE, code=code)
            .first()
        )
        if pc is None:
            raise NotFound()
        if pc.status != ProductCodeStatus.RESERVED or pc.erp_status != ErpStatus.ERP_PENDING:
            refuse(Reason.CODE_NOT_RESERVED, field="code")
        PRODUCT_CODE_MACHINE.assert_transition(pc.status, ProductCodeStatus.ACTIVE)
        before = _code_view(pc)
        with db_rules():
            ProductCode.objects.filter(pk=pc.pk).update(
                status=ProductCodeStatus.ACTIVE, erp_status=ErpStatus.ERP_MATCHED, erp_seen_batch_id=batch_id
            )
        pc.refresh_from_db()
        uow.audit(
            action="identity.product_code.erp_match",
            resource_type="identity.product_code",
            resource_id=str(pc.pk),
            resource_version=pc.row_version,
            before=before,
            after=_code_view(pc),
            scope={"batch_id": str(batch_id)},
        )
        uow.emit(
            event_type="identity.product_code.erp_matched",
            aggregate_type="identity.product_code",
            aggregate_id=str(pc.pk),
            aggregate_version=pc.row_version,
            payload={
                "id": str(pc.pk),
                "status": pc.status,
                "erp_status": pc.erp_status,
                "batch_id": str(batch_id),
            },
        )
    return pc
