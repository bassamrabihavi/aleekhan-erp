"""``/identity/...`` endpoints (PHASE_02 / 02.4) over the 02.3 use cases (``product_identity``).

Every operation: session cookie, the contract's ``x-aleekhan-permission`` (403), fresh MFA where the matrix
flags it (401 ``MFA_REQUIRED``), GLOBAL record scope (404), ``Idempotency-Key`` on writes (428/400/422),
``If-Match`` on updates and actions (428/412/400), refusal reasons in ``errors[].code``. The use cases check
permission, version and state again inside their unit of work (defence in depth).

Product types and categories are read-only here (they come from the Planning ``Sorce`` sheet through the
server import, DEC-005 / R-38). A stand-alone serial allocation does not exist (DEC-006 L-A: serials are drawn
by the order confirmation): ``allocateSerial`` answers 409 ``SERIAL_ALLOCATED_AT_CONFIRM``.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from django.db.models import Count, Q
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.authz.policy import Caller
from platform_core.commercial.models import CustomerOrderLine
from platform_core.engine.errors import FieldError, NotFound, ValidationFailed
from platform_core.engine.idempotency import StoredResponse
from platform_core.models import AuditEvent
from platform_core.product_identity import coderule, codes, external, master
from platform_core.product_identity.models import (
    PRODUCT_CODE_NAMESPACE,
    ClassLevel,
    CodeRuleRevision,
    CodeRuleStatus,
    Customer,
    CustomerBrand,
    ExternalRef,
    HistoricalOrderRecord,
    Product,
    ProductClass,
    ProductCode,
    ProductCodeStatus,
    Serial,
    SerialSnapshot,
    SerialStatus,
    Style,
    StyleRevision,
)
from platform_core.product_identity.refusals import Reason, refuse

from ..phase01.common import (
    NO_STORE,
    body_of,
    etag_response,
    if_match,
    paginate,
    query_choice,
    query_pattern,
    query_uuid,
    stored,
    utc_req,
    write,
)
from . import serializers as S
from .common import Phase02View, apply_search, object_or_404, query_date, scoped

CUSTOMER_READ: Final = "identity.customer.read"
CUSTOMER_MANAGE: Final = "identity.customer.manage"
PRODUCT_READ: Final = "identity.product.read"
PRODUCT_MANAGE: Final = "identity.product.manage"
CODE_READ: Final = "identity.product_code.read"
CODE_ISSUE: Final = "identity.product_code.issue"
RULE_READ: Final = "identity.code_rule.read"
RULE_MANAGE: Final = "identity.code_rule.manage"
RULE_APPROVE: Final = "identity.code_rule.approve"
SERIAL_READ: Final = "identity.serial.read"
SERIAL_ALLOCATE: Final = "identity.serial.allocate"
REF_READ: Final = "identity.external_ref.read"
REF_MANAGE: Final = "identity.external_ref.manage"
HISTORICAL_READ: Final = "identity.historical.read"
PARTY: Final = ("ACTIVE", "INACTIVE")
MASTER: Final = ("DRAFT", "ACTIVE", "RETIRED")
ACK_NAME: Final = Reason.DUPLICATE_CUSTOMER_NAME.value


def _acks(data: dict[str, Any], code: str) -> list[str]:
    return [code] if data.get("acknowledge_possible_duplicate") else []


def _clearable(data: dict[str, Any], name: str) -> str | None:
    """``null`` clears an optional text (the engine reads ``""`` as clear and ``None`` as unchanged)."""
    if name not in data:
        return None
    value = data[name]
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------------------------- customers
class CustomersView(Phase02View):
    required_action = CUSTOMER_READ
    write_action = CUSTOMER_MANAGE

    def get(self, request: Request) -> Response:
        qs = scoped(self, Customer.objects.all())
        status = query_choice(request, "status", PARTY)
        if status:
            qs = qs.filter(status=status)
        qs = apply_search(request, qs, "display_name_fa", "legal_name_fa", "customer_no")
        return paginate(request, self, qs, S.customer, ordering="-customer_no")

    def post(self, request: Request) -> Response:
        data = body_of(request, "CustomerCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            c = master.create_customer(
                caller,
                display_name_fa=data["display_name_fa"],
                legal_name_fa=data.get("legal_name_fa"),
                default_required_quality_ref=data.get("default_required_quality_ref"),
                acknowledge_warnings=_acks(data, ACK_NAME),
                request_id=rid,
            )
            return stored(201, S.customer(c), etag_version=c.row_version)

        return write(self, run)


class CustomerView(Phase02View):
    required_action = CUSTOMER_READ
    write_action = CUSTOMER_MANAGE

    def get(self, request: Request, customer_id: uuid.UUID) -> Response:
        c = object_or_404(self, Customer.objects.all(), customer_id)
        return etag_response(S.customer(c), c.row_version)

    def patch(self, request: Request, customer_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "CustomerUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            c = master.update_customer(
                caller,
                customer_id,
                expected_version=expected,
                display_name_fa=data.get("display_name_fa"),
                legal_name_fa=_clearable(data, "legal_name_fa"),
                default_required_quality_ref=_clearable(data, "default_required_quality_ref"),
                status=data.get("status"),
                acknowledge_warnings=_acks(data, ACK_NAME),
                reason=data["reason"],
                request_id=rid,
            )
            return stored(200, S.customer(c), etag_version=c.row_version)

        return write(self, run)


class CustomerBrandsView(Phase02View):
    required_action = CUSTOMER_READ
    write_action = CUSTOMER_MANAGE

    def get(self, request: Request, customer_id: uuid.UUID) -> Response:
        c = object_or_404(self, Customer.objects.all(), customer_id)
        return paginate(request, self, CustomerBrand.objects.filter(customer=c), S.brand)

    def post(self, request: Request, customer_id: uuid.UUID) -> Response:
        data = body_of(request, "CustomerBrandCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            b = master.add_brand(caller, customer_id, brand_name_fa=data["brand_name_fa"], request_id=rid)
            return stored(201, S.brand(b), etag_version=b.row_version)

        return write(self, run)


class CustomerBrandView(Phase02View):
    required_action = CUSTOMER_MANAGE

    def patch(self, request: Request, customer_id: uuid.UUID, brand_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "CustomerBrandUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            if not CustomerBrand.objects.filter(pk=brand_id, customer_id=customer_id).exists():
                raise NotFound()
            b = master.set_brand_status(
                caller,
                brand_id,
                status=data["status"],
                expected_version=expected,
                reason=data["reason"],
                request_id=rid,
            )
            return stored(200, S.brand(b), etag_version=b.row_version)

        return write(self, run)


# ---------------------------------------------------------------------------------- classes and products
class ProductClassesView(Phase02View):
    required_action = PRODUCT_READ

    def get(self, request: Request) -> Response:
        qs = scoped(self, ProductClass.objects.all())
        parent = query_uuid(request, "parent_class_id")
        if parent is not None:
            qs = qs.filter(parent_id=parent)
        level = query_choice(request, "level_key", ClassLevel.values)
        if level:
            qs = qs.filter(level_key=level)
        status = query_choice(request, "status", MASTER)
        if status:
            qs = qs.filter(status=status)
        return paginate(request, self, qs, S.product_class)


class ProductsView(Phase02View):
    required_action = PRODUCT_READ
    write_action = PRODUCT_MANAGE

    def get(self, request: Request) -> Response:
        qs = scoped(self, Product.objects.select_related("product_type"))
        cls = query_uuid(request, "product_class_id")
        if cls is not None:
            qs = qs.filter(product_type_id=cls)
        status = query_choice(request, "status", MASTER)
        if status:
            qs = qs.filter(status=status)
        qs = apply_search(request, qs, "name_fa", "product_no")
        return paginate(request, self, qs, S.product)

    def post(self, request: Request) -> Response:
        data = body_of(request, "ProductCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            p = master.create_product(
                caller,
                product_type_id=data["product_class_id"],
                name_fa=data["name_fa"],
                buckle_type_code=data.get("buckle_type_code"),
                belt_width_code=data.get("belt_width_code"),
                request_id=rid,
            )
            return stored(201, S.product(p), etag_version=p.row_version)

        return write(self, run)


class ProductView(Phase02View):
    required_action = PRODUCT_READ
    write_action = PRODUCT_MANAGE

    def get(self, request: Request, product_id: uuid.UUID) -> Response:
        p = object_or_404(self, Product.objects.select_related("product_type"), product_id)
        return etag_response(S.product(p), p.row_version)

    def patch(self, request: Request, product_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "ProductUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            p = master.set_product_status(
                caller,
                product_id,
                status=data["status"],
                expected_version=expected,
                reason=data["reason"],
                request_id=rid,
            )
            return stored(200, S.product(p), etag_version=p.row_version)

        return write(self, run)


# ------------------------------------------------------------------------------------------------ styles
class ProductStylesView(Phase02View):
    required_action = PRODUCT_READ
    write_action = PRODUCT_MANAGE

    def get(self, request: Request, product_id: uuid.UUID) -> Response:
        p = object_or_404(self, Product.objects.all(), product_id)
        return paginate(request, self, Style.objects.filter(product=p), S.style)

    def post(self, request: Request, product_id: uuid.UUID) -> Response:
        data = body_of(request, "StyleCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            s = master.create_style(
                caller,
                product_id=product_id,
                category_id=data["category_id"],
                name_fa=data["name_fa"],
                request_id=rid,
            )
            if data.get("initial_attributes"):  # revision 1 (DRAFT) in the same transaction
                master.create_style_revision(
                    caller, style_id=s.pk, attributes=data["initial_attributes"], request_id=rid
                )
            s.refresh_from_db()
            return stored(201, S.style(s), etag_version=s.row_version)

        return write(self, run)


class StyleView(Phase02View):
    required_action = PRODUCT_READ
    write_action = PRODUCT_MANAGE

    def get(self, request: Request, style_id: uuid.UUID) -> Response:
        s = object_or_404(self, Style.objects.all(), style_id)
        return etag_response(S.style(s), s.row_version)

    def patch(self, request: Request, style_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "StyleUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            s = master.set_style_status(
                caller,
                style_id,
                status=data["status"],
                expected_version=expected,
                reason=data["reason"],
                request_id=rid,
            )
            return stored(200, S.style(s), etag_version=s.row_version)

        return write(self, run)


class StyleRevisionsView(Phase02View):
    required_action = PRODUCT_READ
    write_action = PRODUCT_MANAGE

    def get(self, request: Request, style_id: uuid.UUID) -> Response:
        s = object_or_404(self, Style.objects.all(), style_id)
        return paginate(request, self, StyleRevision.objects.filter(style=s), S.style_revision)

    def post(self, request: Request, style_id: uuid.UUID) -> Response:
        data = body_of(request, "StyleRevisionCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            r = master.create_style_revision(
                caller, style_id=style_id, attributes=data["attributes"], request_id=rid
            )
            return stored(201, S.style_revision(r), etag_version=r.row_version)

        return write(self, run)


class ActivateStyleRevisionView(Phase02View):
    required_action = PRODUCT_MANAGE

    def post(self, request: Request, style_id: uuid.UUID, style_revision_id: uuid.UUID) -> Response:
        expected = if_match(self)
        body_of(request, "ReasonRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            if not StyleRevision.objects.filter(pk=style_revision_id, style_id=style_id).exists():
                raise NotFound()
            r = master.activate_style_revision(
                caller, style_revision_id, expected_version=expected, request_id=rid
            )
            return stored(200, S.style_revision(r), etag_version=r.row_version)

        return write(self, run)


class StyleTrackingView(Phase02View):
    """Page 4 (Product/Style 360), PHASE_02 part: counts and the serials of the style (server-computed)."""

    required_action = PRODUCT_READ

    def get(self, request: Request, style_id: uuid.UUID) -> Response:
        s = object_or_404(self, Style.objects.all(), style_id)
        serials = Serial.objects.filter(style=s)
        customer = query_uuid(request, "customer_id")
        if customer is not None:
            serials = serials.filter(customer_id=customer)
        status = query_choice(request, "status", SerialStatus.values)
        if status:
            serials = serials.filter(status=status)
        start, end = query_date(request, "from"), query_date(request, "to")
        if start is not None:
            serials = serials.filter(allocated_at__date__gte=start)
        if end is not None:
            serials = serials.filter(allocated_at__date__lte=end)
        page = paginate(request, self, serials, S.serial_summary, ordering="-serial_value")
        orders = CustomerOrderLine.objects.filter(style=s).values("order_id").distinct().count()
        counts = Serial.objects.filter(style=s).aggregate(
            total=Count("pk"), active=Count("pk", filter=~Q(status=SerialStatus.CANCELLED))
        )
        body = {
            "style": S.style(s),
            "counts": {
                "serials_total": counts["total"],
                "serials_active": counts["active"],
                "orders_total": orders,
            },
            "serials": page.data["items"],
            "unavailable_sections": S.UNAVAILABLE,
            "page": page.data["page"],
        }
        return Response(body, headers=NO_STORE)


class StyleSuggestionsView(Phase02View):
    """Ranked suggestions only (C-71: no merge). Score: 0.5 same product + 0.5 normalised name contains."""

    required_action = PRODUCT_READ

    def get(self, request: Request) -> Response:
        if request.query_params.get("q") is None:
            raise ValidationFailed(errors=[FieldError("q", "REQUIRED")])
        product_id = query_uuid(request, "product_id")
        qs = apply_search(request, scoped(self, Style.objects.all()), "name_fa").order_by("product_id", "id")
        items = []
        for s in qs[:200]:
            same = product_id is not None and s.product_id == product_id
            reasons = (["SAME_PRODUCT"] if same else []) + ["NAME_SIMILAR"]
            items.append(
                {
                    "style_id": str(s.pk),
                    "product_id": str(s.product_id),
                    "name_fa": s.name_fa,
                    "score": 1.0 if same else 0.5,
                    "reasons": reasons,
                }
            )
        items.sort(key=lambda x: (-float(str(x["score"])), str(x["style_id"])))
        return Response({"items": items[:20]}, headers=NO_STORE)


# -------------------------------------------------------------------------------------------- product codes
VALIDATION_REASONS: Final = (
    "LENGTH_NOT_14",
    "NON_ASCII_DIGIT",
    "NON_DIGIT_CHARACTER",
    "SURROUNDING_WHITESPACE",
    "NOT_PRODUCT_PREFIX",
    "LEGACY_ONLY_STYLE_0000",
    "NOT_IN_REGISTRY",
    "DISPUTED_IN_REGISTRY",
    "WRONG_NAMESPACE",
)


def _format_reasons(raw: str) -> list[str]:
    reasons: list[str] = []
    if raw != raw.strip():
        reasons.append("SURROUNDING_WHITESPACE")
    if len(raw) != coderule.CODE_LENGTH:
        reasons.append("LENGTH_NOT_14")
    if any(ch.isdigit() and not ("0" <= ch <= "9") for ch in raw):
        reasons.append("NON_ASCII_DIGIT")  # Persian / Arabic-Indic digits are never converted
    if any(not ch.isdigit() and not ch.isspace() for ch in raw):
        reasons.append("NON_DIGIT_CHARACTER")
    return reasons


class ValidateProductCodeView(Phase02View):
    """Side-effect free (no Idempotency-Key, no write, no audit); the code stays out of the URL."""

    required_action = CODE_READ
    idempotent = False

    def post(self, request: Request) -> Response:
        self.in_scope()
        data = body_of(request, "ProductCodeValidateRequest")
        raw: str = data["code"]
        reasons = _format_reasons(raw)
        entry = None
        checked = False
        if data["code_namespace"] != PRODUCT_CODE_NAMESPACE:
            reasons.append("WRONG_NAMESPACE")
        elif not reasons:
            checked = True
            if not raw.startswith(coderule.PRODUCT_PREFIX):
                reasons.append("NOT_PRODUCT_PREFIX")
            elif raw.endswith(coderule.LEGACY_ONLY_STYLE_NO):
                reasons.append("LEGACY_ONLY_STYLE_0000")  # history only, never issued (DEC-005 amendment)
            pc = ProductCode.objects.filter(code_namespace=PRODUCT_CODE_NAMESPACE, code=raw).first()
            if pc is None:
                reasons.append("NOT_IN_REGISTRY")
            else:
                entry = S.product_code(pc)
                if pc.status == ProductCodeStatus.DISPUTED:
                    reasons.append("DISPUTED_IN_REGISTRY")
        body = {
            "input": raw,
            "format_valid": not _format_reasons(raw),
            "code_namespace": data["code_namespace"],
            "registry_entry": entry,
            "segments_checked": checked,
            "segments_decision_id": "DEC-005" if checked else None,
            "reasons": [r for r in VALIDATION_REASONS if r in reasons],
        }
        return Response(body, headers=NO_STORE)


class PreviewProductCodeView(Phase02View):
    """Side-effect free: the code of an existing style (``style_id``) or of a NEW style (type + category, with
    an existing ``product_id`` or a new product; belt types need buckle + width). Nothing is reserved."""

    required_action = CODE_READ
    idempotent = False

    def post(self, request: Request) -> Response:
        caller = self.in_scope()
        data = body_of(request, "ProductCodePreviewRequest")
        if data.get("style_id") is not None:
            extra = set(data) - {"style_id"}
            if extra:
                raise ValidationFailed(errors=[FieldError(sorted(extra)[0], "NOT_ALLOWED_WITH_STYLE")])
            view = codes.preview_style_code(caller, data["style_id"])
            parts = coderule.parse_code(view["code"], legacy=True)
            new_product = False
        else:
            for name in ("product_class_id", "category_id"):
                if data.get(name) is None:
                    raise ValidationFailed(errors=[FieldError(name, "REQUIRED")])
            preview = codes.preview_new_code(
                caller,
                product_type_id=data["product_class_id"],
                category_id=data["category_id"],
                product_id=data.get("product_id"),
                buckle_type_code=data.get("buckle_type_code"),
                belt_width_code=data.get("belt_width_code"),
            )
            parts = coderule.parse_code(preview["code"])
            view = {"code": preview["code"], "legacy_only": False, "issued": False}
            new_product = bool(preview["new_product"])
        active = CodeRuleRevision.objects.filter(
            code_namespace=PRODUCT_CODE_NAMESPACE, status=CodeRuleStatus.ACTIVE
        ).first()
        body = {
            "code": view["code"],
            "rule_revision_id": str(active.pk) if active else None,
            "segments": [
                {"level_key": "product_type", "value": parts.type_code},
                {"level_key": "category", "value": parts.category_code},
                {"level_key": "product_no", "value": parts.product_no},
                {"level_key": "style_no", "value": parts.style_no},
            ],
            "new_product": new_product,
            "legacy_only": bool(view["legacy_only"]),
            "issued": bool(view["issued"]),
        }
        return Response(body, headers=NO_STORE)


class ProductCodesView(Phase02View):
    required_action = CODE_READ
    write_action = CODE_ISSUE

    def get(self, request: Request) -> Response:
        qs = scoped(self, ProductCode.objects.all())
        for name, field in (("style_id", "style_id"), ("product_id", "style__product_id")):
            value = query_uuid(request, name)
            if value is not None:
                qs = qs.filter(**{field: value})
        status = query_choice(request, "status", ProductCodeStatus.values)
        if status:
            qs = qs.filter(status=status)
        erp = query_choice(request, "erp_status", ("ERP_PENDING", "ERP_MATCHED", "ERP_MISSING"))
        if erp:
            qs = qs.filter(erp_status=erp)
        return paginate(request, self, qs, S.product_code, ordering="code")

    def post(self, request: Request) -> Response:
        data = body_of(request, "ProductCodeIssueRequest")
        key = uuid.UUID(str(request.headers.get("Idempotency-Key")))

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            expected_rule = data.get("rule_revision_id")
            if expected_rule is not None:
                active = CodeRuleRevision.objects.filter(
                    code_namespace=PRODUCT_CODE_NAMESPACE, status=CodeRuleStatus.ACTIVE
                ).first()
                if active is not None and active.pk != expected_rule:
                    refuse(Reason.RULE_REVISION_NOT_ACTIVE, field="rule_revision_id")
            pc, _replayed = codes.issue_product_code(
                caller, data["style_id"], idempotency_key=key, request_id=rid
            )
            return stored(201, S.product_code(pc), etag_version=pc.row_version)

        return write(self, run)


class ProductCodeView(Phase02View):
    required_action = CODE_READ

    def get(self, request: Request, product_code_id: uuid.UUID) -> Response:
        pc = object_or_404(self, ProductCode.objects.all(), product_code_id)
        return etag_response(S.product_code(pc), pc.row_version)


# --------------------------------------------------------------------------------------- code rule revisions
class CodeRulesView(Phase02View):
    required_action = RULE_READ
    write_action = RULE_MANAGE

    def get(self, request: Request) -> Response:
        qs = scoped(self, CodeRuleRevision.objects.all())
        status = query_choice(request, "status", CodeRuleStatus.values)
        if status:
            qs = qs.filter(status=status)
        return paginate(request, self, qs, S.code_rule, ordering="-revision_no")

    def post(self, request: Request) -> Response:
        data = body_of(request, "CodeRuleRevisionCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            r = codes.create_rule_revision(
                caller,
                product_type_codes=data["product_type_codes"],
                source_workbook_sha256=data["source_workbook_sha256"],
                evidence_document_id=data.get("evidence_document_id"),
                request_id=rid,
            )
            return stored(201, S.code_rule(r), etag_version=r.row_version)

        return write(self, run)


class CodeRuleView(Phase02View):
    required_action = RULE_READ

    def get(self, request: Request, rule_revision_id: uuid.UUID) -> Response:
        r = object_or_404(self, CodeRuleRevision.objects.all(), rule_revision_id)
        return etag_response(S.code_rule(r), r.row_version)


class CodeRuleGoldenCasesView(Phase02View):
    """Attach golden cases to a DRAFT revision (evidence, checked at submit). Real cases are entered on the
    server only (DEC-028 / DEC-046); the response carries counts only, never a case value."""

    required_action = RULE_MANAGE

    def post(self, request: Request, rule_revision_id: uuid.UUID) -> Response:
        data = body_of(request, "GoldenCasesAddRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            added = codes.add_golden_cases(caller, rule_revision_id, cases=data["cases"], request_id=rid)
            r = CodeRuleRevision.objects.get(pk=rule_revision_id)
            body = {"rule_revision_id": str(r.pk), "added": added, "revision": S.code_rule(r)}
            return stored(201, body, etag_version=r.row_version)

        return write(self, run)


def _rule_action(action: str, schema: str, call: Any) -> type[Phase02View]:
    class _View(Phase02View):
        required_action = action

        def post(self, request: Request, rule_revision_id: uuid.UUID) -> Response:
            expected = if_match(self)
            data = body_of(request, schema)

            def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
                r = call(caller, rule_revision_id, expected, data, rid)
                return stored(200, S.code_rule(r), etag_version=r.row_version)

            return write(self, run)

    return _View


def _approve(caller: Caller, pk: uuid.UUID, expected: int, data: dict[str, Any], rid: uuid.UUID) -> Any:
    r = CodeRuleRevision.objects.filter(pk=pk).first()
    if r is not None and data["resource_revision"] != r.revision_no:
        refuse(Reason.STALE_BASE_VERSION, field="resource_revision", detail="not the revision being approved")
    return codes.approve_rule_revision(
        caller, pk, expected_version=expected, note=data["note"], request_id=rid
    )


SubmitCodeRuleView = _rule_action(
    RULE_MANAGE,
    "ReasonRequest",
    lambda c, pk, v, d, rid: codes.submit_rule_revision(c, pk, expected_version=v, request_id=rid),
)
ApproveCodeRuleView = _rule_action(RULE_APPROVE, "ApprovalDecisionRequest", _approve)
RejectCodeRuleView = _rule_action(
    RULE_APPROVE,
    "ReasonRequest",
    lambda c, pk, v, d, rid: codes.reject_rule_revision(
        c, pk, expected_version=v, reason=d["reason"], request_id=rid
    ),
)
ActivateCodeRuleView = _rule_action(
    RULE_APPROVE,
    "ReasonRequest",
    lambda c, pk, v, d, rid: codes.activate_rule_revision(
        c, pk, expected_version=v, reason=d["reason"], request_id=rid
    ),
)


# ------------------------------------------------------------------------------------------------- serials
class SerialsView(Phase02View):
    required_action = SERIAL_READ
    write_action = SERIAL_ALLOCATE

    def get(self, request: Request) -> Response:
        qs = scoped(self, Serial.objects.select_related("serial_counter"))
        number = query_pattern(request, "q", r"^[0-9]{1,32}$", max_len=32)
        if number is not None:
            qs = qs.filter(serial_number__startswith=number)
        for name, field in (("customer_id", "customer_id"), ("style_id", "style_id")):
            value = query_uuid(request, name)
            if value is not None:
                qs = qs.filter(**{field: value})
        order = query_uuid(request, "order_id")
        if order is not None:
            qs = qs.filter(
                pk__in=CustomerOrderLine.objects.filter(order_id=order, serial__isnull=False).values(
                    "serial_id"
                )
            )
        status = query_choice(request, "status", SerialStatus.values)
        if status:
            qs = qs.filter(status=status)
        return paginate(request, self, qs, S.serial, ordering="-serial_value")

    def post(self, request: Request) -> Response:
        body_of(request, "SerialAllocateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            refuse(
                Reason.SERIAL_ALLOCATED_AT_CONFIRM,
                field="order_line_id",
                detail="serials are allocated by the order confirmation (DEC-006 L-A)",
            )

        return write(self, run)


class SerialView(Phase02View):
    required_action = SERIAL_READ

    def get(self, request: Request, serial_id: uuid.UUID) -> Response:
        s = object_or_404(self, Serial.objects.select_related("serial_counter"), serial_id)
        return etag_response(S.serial(s), s.row_version)


class SerialSnapshotsView(Phase02View):
    required_action = SERIAL_READ

    def get(self, request: Request, serial_id: uuid.UUID) -> Response:
        s = object_or_404(self, Serial.objects.all(), serial_id)
        return paginate(
            request, self, SerialSnapshot.objects.filter(serial=s), S.snapshot, ordering="version"
        )


TRACKING_KINDS: Final = {
    "commercial.order.create": "ORDER_DRAFTED",
    "commercial.order.validate": "ORDER_VALIDATED",
    "commercial.order.confirm": "ORDER_CONFIRMED",
    "identity.serial.allocate": "SERIAL_ALLOCATED",
    "commercial.order.release": "ORDER_RELEASED_TO_PLAN",
    "commercial.change_request.create": "CHANGE_REQUESTED",
    "commercial.change_request.decide": "CHANGE_DECIDED",
    "commercial.change_request.planning_approve": "CHANGE_DECIDED",
    "commercial.change_request.planning_reject": "CHANGE_DECIDED",
    "commercial.change_request.apply": "CHANGE_APPLIED",
    "commercial.order.cancel": "ORDER_CANCELLED",
    "identity.serial.cancel": "SERIAL_CANCELLED",
}
_REF_TYPE: Final = {
    "commercial.customer_order": "customer_order",
    "commercial.change_request": "change_request",
    "identity.serial": "serial",
}


class SerialTrackingView(Phase02View):
    """Pages 1/2 (serial 360), PHASE_02 part: the serial, its order versions and the audited events of the
    serial, its order and the order's change requests (newest 200)."""

    required_action = SERIAL_READ

    def get(self, request: Request, serial_id: uuid.UUID) -> Response:
        from platform_core.commercial.models import CustomerOrderVersion, OrderChangeRequest

        s = object_or_404(self, Serial.objects.select_related("serial_counter"), serial_id)
        ln = CustomerOrderLine.objects.filter(serial_id=s.pk).first()
        versions = (
            CustomerOrderVersion.objects.filter(order_id=ln.order_id).order_by("version")[:200] if ln else []
        )
        ids = [str(s.pk)]
        if ln is not None:
            ids.append(str(ln.order_id))
            ids += [
                str(x)
                for x in OrderChangeRequest.objects.filter(order_id=ln.order_id).values_list("pk", flat=True)
            ]
        events = (
            AuditEvent.objects.filter(resource_id__in=ids, action__in=list(TRACKING_KINDS))
            .order_by("-occurred_at")
            .values("id", "occurred_at", "action", "resource_type", "resource_id", "resource_version")[:200]
        )
        body = {
            "serial": S.serial(s),
            "order_versions": [S.version_summary(v) for v in versions],
            "events": [
                {
                    "occurred_at": utc_req(e["occurred_at"]),
                    "kind": TRACKING_KINDS[e["action"]],
                    "ref": {
                        "entity_type": _REF_TYPE.get(e["resource_type"], "serial"),
                        "entity_id": e["resource_id"],
                        "revision": e["resource_version"],
                    },
                    "audit_event_id": str(e["id"]),
                }
                for e in events
            ],
            "unavailable_sections": S.UNAVAILABLE,
        }
        return Response(body, headers=NO_STORE)


# ------------------------------------------------------------------------------------ external references
class ExternalRefsView(Phase02View):
    required_action = REF_READ
    write_action = REF_MANAGE

    def get(self, request: Request) -> Response:
        qs = scoped(self, ExternalRef.objects.all())
        target_type = query_choice(
            request, "target_type", ("customer", "product", "style", "customer_order", "order_line", "serial")
        )
        if target_type:
            qs = qs.filter(target_type=target_type)
        target = query_uuid(request, "target_id")
        if target is not None:
            qs = qs.filter(target_id=target)
        system = query_choice(request, "system", ("RAHKARAN", "CUSTOMER", "LEGACY_PLANNING", "OTHER"))
        if system:
            qs = qs.filter(system=system)
        namespace = query_pattern(request, "namespace", r"^[a-z][a-z0-9_]{2,63}$", max_len=64)
        if namespace:
            qs = qs.filter(ref_type_id=namespace)
        value = request.query_params.get("value")
        if value is not None:
            if not 1 <= len(value) <= 64:
                raise ValidationFailed(errors=[FieldError("value", "PATTERN_MISMATCH")])
            qs = qs.filter(value=value)  # exact raw text, never parsed
        return paginate(request, self, qs, S.external_ref)

    def post(self, request: Request) -> Response:
        data = body_of(request, "ExternalRefCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            r = external.create_external_ref(
                caller,
                target_type=data["target_type"],
                target_id=data["target_id"],
                system=data["system"],
                namespace=data["namespace"],
                value=data["value"],
                reason=data["reason"],
                request_id=rid,
            )
            return stored(201, S.external_ref(r), etag_version=r.row_version)

        return write(self, run)


class EndExternalRefView(Phase02View):
    required_action = REF_MANAGE

    def post(self, request: Request, external_ref_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "ReasonRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            r = external.end_external_ref(
                caller, external_ref_id, expected_version=expected, reason=data["reason"], request_id=rid
            )
            return stored(200, S.external_ref(r), etag_version=r.row_version)

        return write(self, run)


class HistoricalRecordsView(Phase02View):
    """Read-only legacy evidence (never an official order); rows come from the 02.6 import."""

    required_action = HISTORICAL_READ

    def get(self, request: Request) -> Response:
        qs = scoped(self, HistoricalOrderRecord.objects.all())
        batch = query_uuid(request, "import_batch_id")
        if batch is not None:
            qs = qs.filter(import_batch_id=batch)
        status = query_choice(request, "status", ("UNMATCHED", "SUGGESTED", "CONFIRMED", "REJECTED"))
        if status:
            qs = qs.filter(match_status=status)
        flag = query_choice(request, "code_flag", ("OK", "DISPUTED", "ABSENT"))
        if flag:
            qs = qs.filter(code_flag=flag)
        return paginate(request, self, qs, S.historical)
