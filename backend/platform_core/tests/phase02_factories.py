"""Synthetic PHASE_02 builders (02.2). Every value here is SYNTHETIC and labelled «محیط آزمایشی — داده
ساختگی»:
no real product type, category, code, customer, brand, representative or serial (DEC-005 / DEC-028 / DEC-046,
rule R-38). Synthetic type segments use the ``9x`` range and product numbers the ``9xxx`` range so they
read as
test data at a glance; they say nothing about the real ``Sorce`` list.

* :func:`ensure_phase02_catalogue` re-creates the 0021 seed (units, order types, reference types, counter) and
  the matrix v2.0 rows of 0022 after a transactional flush (race tests).
* :func:`confirm_order` is a TEST HARNESS of the confirm transaction (the 02.3 engine owns the real use case):
  Commercial locks its order and lines, Identity's :func:`allocate_serial` draws each serial, Commercial
  writes
  the pairing on its own line rows and the version row - one unit of work.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import date
from importlib import import_module
from typing import Any

from django.db.models.functions import Now

from platform_core.commercial.models import CustomerOrder, CustomerOrderLine, CustomerOrderVersion
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.uow import unit_of_work
from platform_core.identity.models import Permission, Role, RolePermission, User
from platform_core.integration.models import ImportBatch, StagingRow
from platform_core.product_identity.models import (
    CodeRuleRevision,
    Customer,
    CustomerBrand,
    ExternalRefType,
    Product,
    ProductClass,
    SerialCounter,
    Style,
    StyleRevision,
    UnitOfMeasure,
)
from platform_core.product_identity.serials import AllocationRequest, allocate_serial

from .factories import integration_source
from .phase01_factories import SYN, user

__all__ = ["SYN"]

SHA = "0" * 63 + "1"  # synthetic workbook hash (not the registered baseline)
NS_ALLOCATION = uuid.UUID("5f0e2c1a-0000-4000-8000-000000000022")  # synthetic namespace for uuid5 keys


def _n() -> str:
    return secrets.token_hex(4)


def ensure_phase02_catalogue() -> None:
    """After a transactional flush: the 0021 seed rows and the 0022 matrix v2.0 rows (same frozen values)."""
    seed = import_module("platform_core.migrations.0021_phase02_seed_catalogue")
    matrix = import_module("platform_core.migrations.0022_dec057_matrix_v20")
    for code, label in seed.UNITS:
        UnitOfMeasure.objects.get_or_create(
            code=code, defaults={"label_fa": label, "decision_id": "DEC-058", "provenance": seed.SEED}
        )
    from platform_core.commercial.models import OrderType

    for code, label, order in seed.ORDER_TYPES:
        OrderType.objects.get_or_create(
            code=code,
            defaults={
                "label_fa": label,
                "sort_order": order,
                "decision_id": "DEC-058",
                "provenance": seed.SEED,
            },
        )
    for key, label in seed.EXTERNAL_REF_TYPES:
        ExternalRefType.objects.get_or_create(
            key=key, defaults={"label_fa": label, "decision_id": "DEC-058", "provenance": seed.SEED}
        )
    if not SerialCounter.objects.exists():
        SerialCounter.objects.create(**seed.SERIAL_COUNTER)
    if not Permission.objects.filter(action__in=list(matrix.PERMISSIONS)).exists():
        _seed_matrix_v20(matrix)
    _seed_matrix_v21()


def _seed_matrix_v21() -> None:
    """Matrix v2.1 (0024, same frozen values): owner reads + ``commercial.change.planning_approve``."""
    v21 = import_module("platform_core.migrations.0024_dec057_dec059_matrix_v21")
    if Permission.objects.filter(action__in=list(v21.NEW_PERMISSIONS)).exists():
        return
    for action, (desc, mfa, ba, sod, decision) in v21.NEW_PERMISSIONS.items():
        Permission.objects.create(
            action=action,
            module=action.split(".")[0],
            description_fa=desc,
            mfa_step_up=mfa,
            business_approval=ba,
            maker_checker=sod,
            matrix_version=v21.MATRIX_VERSION,
            decision_id=decision,
        )
    roles = {r.code: r for r in Role.objects.filter(code__in=list(v21.CHANGED_ROLES))}
    if len(roles) != len(v21.CHANGED_ROLES):
        return
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard")
        try:
            for action, codes in v21.ADDED_GRANTS.items():
                for code in codes:
                    RolePermission.objects.get_or_create(
                        role=roles[code], permission_id=action, defaults={"grant_mode": "SCOPE"}
                    )
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        finally:
            cur.execute("ALTER TABLE platform_role_permission ENABLE TRIGGER trg_role_permission_guard")
        cur.execute("ALTER TABLE platform_role DISABLE TRIGGER trg_role_kind_guard")
        try:
            Role.objects.filter(code__in=list(roles)).update(matrix_version=v21.MATRIX_VERSION)
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        finally:
            cur.execute("ALTER TABLE platform_role ENABLE TRIGGER trg_role_kind_guard")


def _seed_matrix_v20(matrix: Any) -> None:
    for action, (desc, mfa, ba, sod) in matrix.PERMISSIONS.items():
        Permission.objects.create(
            action=action,
            module=action.split(".")[0],
            description_fa=desc,
            mfa_step_up=mfa,
            business_approval=ba,
            maker_checker=sod,
            matrix_version=matrix.MATRIX_VERSION,
            decision_id=matrix.DECISION,
        )
    roles = {
        code: Role.objects.create(
            code=code, name_fa=name, kind="BUSINESS", status="DRAFT", provenance="MIGRATION_SEED"
        )
        for code, name in matrix.ROLES.items()
    }
    existing = {r.code: r for r in Role.objects.filter(code__in=list(matrix.PREVIOUS_VERSIONS))}
    from django.db import connection

    with connection.cursor() as cur:  # test DB owner: same bypass as the migration for ACTIVE roles
        cur.execute("ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard")
        try:
            for action, codes in matrix.GRANTS.items():
                for code in codes:
                    target = roles.get(code) or existing.get(code)
                    if target is not None:
                        RolePermission.objects.create(role=target, permission_id=action, grant_mode="SCOPE")
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        finally:
            cur.execute("ALTER TABLE platform_role_permission ENABLE TRIGGER trg_role_permission_guard")
        Role.objects.filter(code__in=list(matrix.ROLES)).update(
            status="ACTIVE", matrix_version=matrix.MATRIX_VERSION
        )
        if existing:
            cur.execute("ALTER TABLE platform_role DISABLE TRIGGER trg_role_kind_guard")
            try:
                Role.objects.filter(code__in=list(existing)).update(matrix_version=matrix.MATRIX_VERSION)
                cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
            finally:
                cur.execute("ALTER TABLE platform_role ENABLE TRIGGER trg_role_kind_guard")


# --------------------------------------------------------------------------------------- classification
def product_type(segment: str | None = None, *, uom: str = "PIECE", **over: Any) -> ProductClass:
    data: dict[str, Any] = {
        "level_key": "product_type",
        "segment_value": segment or free_type_segment(),
        "label_fa": f"نوع ساختگی {_n()} {SYN}",
        "uom_id": uom,
        "product_no_scheme": "SEQUENTIAL_PER_TYPE",
        "status": "ACTIVE",
    }
    data.update(over)
    return ProductClass.objects.create(**data)


def free_type_segment() -> str:
    used = set(ProductClass.objects.filter(level_key="product_type").values_list("segment_value", flat=True))
    for i in range(99, -1, -1):
        seg = f"{i:02d}"
        if seg not in used:
            return seg
    raise AssertionError("no free synthetic type segment")


def category(ptype: ProductClass, segment: str = "07", **over: Any) -> ProductClass:
    data: dict[str, Any] = {
        "level_key": "category",
        "parent": ptype,
        "segment_value": segment,
        "label_fa": f"دسته ساختگی {_n()} {SYN}",
        "status": "ACTIVE",
    }
    data.update(over)
    return ProductClass.objects.create(**data)


def product(ptype: ProductClass, product_no: str = "9001", **over: Any) -> Product:
    data: dict[str, Any] = {
        "product_type": ptype,
        "product_no": product_no,
        "name_fa": f"محصول ساختگی {_n()} {SYN}",
        "status": "ACTIVE",
    }
    data.update(over)
    return Product.objects.create(**data)


def style(prod: Product, cat: ProductClass, style_no: str = "0001", **over: Any) -> Style:
    data: dict[str, Any] = {
        "product": prod,
        "category": cat,
        "style_no": style_no,
        "name_fa": f"استایل ساختگی {_n()} {SYN}",
        "status": "ACTIVE",
    }
    data.update(over)
    return Style.objects.create(**data)


def style_revision(sty: Style, revision_no: int = 1, status: str = "ACTIVE", **over: Any) -> StyleRevision:
    data: dict[str, Any] = {
        "style": sty,
        "revision_no": revision_no,
        "attributes": {"colour_fa": f"رنگ ساختگی {SYN}"},
        "status": status,
    }
    data.update(over)
    return StyleRevision.objects.create(**data)


def styled(**over: Any) -> tuple[ProductClass, ProductClass, Product, Style, StyleRevision]:
    """A fresh synthetic type -> category -> product -> style -> ACTIVE revision chain."""
    t = product_type(free_type_segment(), **over)
    c = category(t)
    p = product(t)
    s = style(p, c)
    return t, c, p, s, style_revision(s)


def code_rule(maker: User, **over: Any) -> CodeRuleRevision:
    data: dict[str, Any] = {
        "revision_no": (CodeRuleRevision.objects.count() + 1),
        "scope": {"synthetic": True},
        "rule_spec": {"synthetic": True},
        "source_workbook_sha256": SHA,
        "decision_id": "DEC-005",
        "created_by": maker,
    }
    data.update(over)
    return CodeRuleRevision.objects.create(**data)


def active_code_rule(maker: User, approver: User) -> CodeRuleRevision:
    rule = code_rule(maker)
    for status in ("IN_REVIEW", "APPROVED", "ACTIVE"):
        extra: dict[str, Any] = {"status": status}
        if status == "APPROVED":
            extra.update(approved_by=approver, approved_at=Now())
        CodeRuleRevision.objects.filter(pk=rule.pk).update(**extra)
    rule.refresh_from_db()
    return rule


def code_for(sty: Style) -> str:
    sty = Style.objects.select_related("product__product_type", "category").get(pk=sty.pk)
    return str(
        "02"
        + sty.product.product_type.segment_value
        + sty.category.segment_value
        + sty.product.product_no
        + sty.style_no
    )


def staging(sheet: str = "SyntheticSheet") -> tuple[ImportBatch, StagingRow]:
    src = integration_source()
    batch = ImportBatch.objects.create(
        source=src,
        file_sha256=hashlib.sha256(_n().encode()).hexdigest(),
        byte_size=1,
        original_name="synthetic.xlsx",
        actor_type="SYSTEM",
    )
    row = StagingRow.objects.create(
        batch=batch,
        sheet_name=sheet,
        row_number=1,
        payload={"synthetic": True},
        payload_sha256=hashlib.sha256(b"synthetic").hexdigest(),
    )
    return batch, row


# --------------------------------------------------------------------------------------------- customers
def customer(**over: Any) -> Customer:
    n = _n()
    data: dict[str, Any] = {"customer_no": f"SYN-{n}", "display_name_fa": f"مشتری ساختگی {n} {SYN}"}
    data.update(over)
    return Customer.objects.create(**data)


def brand(cust: Customer, **over: Any) -> CustomerBrand:
    data: dict[str, Any] = {"customer": cust, "brand_name_fa": f"برند ساختگی {_n()} {SYN}"}
    data.update(over)
    return CustomerBrand.objects.create(**data)


# ------------------------------------------------------------------------------------------------ orders
def order(cust: Customer, creator: User, **over: Any) -> CustomerOrder:
    data: dict[str, Any] = {
        "order_no": f"SYN-O-{_n()}",
        "customer": cust,
        "order_type_id": "series_production",
        "order_date": date(2030, 1, 10),
        "created_by": creator,
    }
    data.update(over)
    return CustomerOrder.objects.create(**data)


def line(
    o: CustomerOrder, sty: Style, rev: StyleRevision, line_no: int = 1, **over: Any
) -> CustomerOrderLine:
    uom = Style.objects.select_related("product__product_type").get(pk=sty.pk).product.product_type.uom_id
    data: dict[str, Any] = {
        "order": o,
        "line_no": line_no,
        "style": sty,
        "style_revision": rev,
        "quantity": 10,
        "uom_id": uom,
    }
    data.update(over)
    return CustomerOrderLine.objects.create(**data)


def validated_order(
    n_lines: int = 1, *, chain: tuple[Style, StyleRevision] | None = None, **over: Any
) -> tuple[CustomerOrder, list[CustomerOrderLine], User]:
    """A VALIDATED synthetic order with ``n_lines`` independent lines; returns (order, lines, creator).
    ``chain`` = (style, revision) to reuse (race tests: the 2-digit type segment allows 100 types only)."""
    creator = user()
    if chain is None:
        _t, _c, _p, sty, rev = styled()
    else:
        sty, rev = chain
    o = order(customer(), creator, **over)
    lines = [line(o, sty, rev, line_no=i + 1) for i in range(n_lines)]
    CustomerOrder.objects.filter(pk=o.pk).update(status="VALIDATED")
    o.refresh_from_db()
    return o, lines, creator


def confirm_order(order_id: uuid.UUID, confirmer: User, *, fail_after_allocation: bool = False) -> list[str]:
    """TEST HARNESS of the confirm transaction (DEC-006 L-A): every line gets its serial in ONE unit of
    work."""
    ctx = RequestContext(Actor.user(confirmer.pk), request_id=uuid.uuid4())
    numbers: list[str] = []
    with unit_of_work(ctx) as uow:
        o = CustomerOrder.objects.select_for_update().get(pk=order_id)
        lines = list(
            CustomerOrderLine.objects.select_for_update().filter(order=o, status="OPEN").order_by("line_no")
        )
        for ln in lines:
            result = allocate_serial(
                uow,
                AllocationRequest(
                    idempotency_key=uuid.uuid5(NS_ALLOCATION, f"{o.pk}:{ln.pk}"),
                    allocated_by=confirmer.pk,
                    customer_id=o.customer_id,
                    style_id=ln.style_id,
                    style_revision_id=ln.style_revision_id,
                    product_code_id=ln.product_code_id,
                    order_version=1,
                    snapshot={"order_id": str(o.pk), "line_id": str(ln.pk), "line_no": ln.line_no},
                ),
            )
            CustomerOrderLine.objects.filter(pk=ln.pk).update(
                status="CONFIRMED", serial=result.serial, order_version=1
            )
            numbers.append(result.serial.serial_number)
        CustomerOrderVersion.objects.create(
            order=o, version=1, image={"lines": len(lines)}, reason="CONFIRMED", created_by=confirmer
        )
        CustomerOrder.objects.filter(pk=o.pk).update(
            status="CONFIRMED", current_version=1, confirmed_by=confirmer, confirmed_at=Now()
        )
        uow.audit(
            action="commercial.order.confirm",
            resource_type="commercial.customer_order",
            resource_id=str(o.pk),
        )
        if fail_after_allocation:
            raise RuntimeError("SYNTHETIC failure after allocation (rollback must not consume a number)")
    return numbers
