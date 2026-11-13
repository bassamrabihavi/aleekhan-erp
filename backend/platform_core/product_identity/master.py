"""Identity master data use cases (PHASE_02 / 02.3): customers, brands, products, styles, style revisions.

Permissions (matrix v2.0, DEC-057): ``identity.customer.manage`` (commercial_officer) for customers and
brands; ``identity.product.manage`` (product_data_steward) for products, styles and style revisions. Product
types and categories (code segments 2 and 3) are NOT created here: they come from the Planning ``Sorce`` sheet
through the server import only (DEC-005, R-38).

Numbering (DEC-005, ``coderule``): a new product of a sequential type gets ``max(product_no of the type) + 1``
and a belt product ``buckle + width``; a new style gets ``count(styles of the product and category) + 1``. The
counting row (product type, product) is locked ``FOR UPDATE`` first, so two concurrent creations never compute
the same number; a collision with an existing number is refused, never re-numbered.

Lifecycle of products and styles (``MASTER_MACHINE``): DRAFT -> ACTIVE -> RETIRED (never deleted). Customers
and brands: ACTIVE <-> INACTIVE. Style revisions: DRAFT -> ACTIVE (the previous ACTIVE one becomes SUPERSEDED
in the same transaction); an ACTIVE revision never changes (DB guard 0020).

Customer duplicate names are a warning (index ``ix_icus_name_lower``): the caller must acknowledge
``DUPLICATE_CUSTOMER_NAME``; the acknowledgement is audited.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from typing import Any, Final

from django.db.models.functions import Lower

from platform_core.authz.policy import Caller
from platform_core.engine.dbrules import db_rules
from platform_core.engine.redaction import sensitive_paths
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import UnitOfWork, unit_of_work

from . import coderule
from .models import (
    ClassLevel,
    Customer,
    CustomerBrand,
    MasterStatus,
    PartyStatus,
    Product,
    ProductClass,
    ProductNoScheme,
    Style,
    StyleRevision,
    StyleRevisionStatus,
)
from .refusals import Reason, refuse
from .usecase import (
    acknowledged,
    authorize,
    check_version,
    lock,
    next_number,
    optional_text,
    reason_text,
    required_text,
)

CUSTOMER_MANAGE: Final = "identity.customer.manage"
PRODUCT_MANAGE: Final = "identity.product.manage"
WARN_DUPLICATE_NAME: Final = Reason.DUPLICATE_CUSTOMER_NAME.value

MASTER_MACHINE: Final = StateMachine(
    name="identity.master",
    states=frozenset(MasterStatus.values),
    transitions={
        MasterStatus.DRAFT: frozenset({MasterStatus.ACTIVE}),
        MasterStatus.ACTIVE: frozenset({MasterStatus.RETIRED}),
        MasterStatus.RETIRED: frozenset(),
    },
)
PARTY_MACHINE: Final = StateMachine(
    name="identity.party",
    states=frozenset(PartyStatus.values),
    transitions={
        PartyStatus.ACTIVE: frozenset({PartyStatus.INACTIVE}),
        PartyStatus.INACTIVE: frozenset({PartyStatus.ACTIVE}),
    },
)
STYLE_REVISION_MACHINE: Final = StateMachine(
    name="identity.style_revision",
    states=frozenset(StyleRevisionStatus.values),
    transitions={
        StyleRevisionStatus.DRAFT: frozenset({StyleRevisionStatus.ACTIVE}),
        StyleRevisionStatus.ACTIVE: frozenset({StyleRevisionStatus.SUPERSEDED}),
        StyleRevisionStatus.SUPERSEDED: frozenset(),
    },
)
MAX_ATTRIBUTES: Final = 30
MAX_ATTRIBUTE_LEN: Final = 200


def _write(
    uow: UnitOfWork,
    *,
    verb: str,
    rtype: str,
    obj: Any,
    after: Mapping[str, Any],
    payload: Mapping[str, Any],
    before: Mapping[str, Any] | None = None,
    reason: str = "",
    scope: Mapping[str, Any] | None = None,
) -> None:
    past = {"create": "created", "update": "updated", "activate": "activated", "status": "status_changed"}[
        verb
    ]
    uow.audit(
        action=f"{rtype}.{verb}",
        resource_type=rtype,
        resource_id=str(obj.pk),
        resource_version=obj.row_version,
        before=before,
        after=dict(after),
        reason=reason,
        scope=scope,
    )
    uow.emit(
        event_type=f"{rtype}.{past}",
        aggregate_type=rtype,
        aggregate_id=str(obj.pk),
        aggregate_version=obj.row_version,
        payload=dict(payload),
    )


# ----------------------------------------------------------------------------------------------- customers
def _customer_view(c: Customer) -> dict[str, Any]:
    # names are business master data (not personal data); still kept out of event payloads (S1)
    return {"customer_no": c.customer_no, "status": c.status, "has_legal_name": bool(c.legal_name_fa)}


def customer_name_duplicates(display_name_fa: str, *, exclude: uuid.UUID | None = None) -> int:
    qs = Customer.objects.annotate(n=Lower("display_name_fa")).filter(n=display_name_fa.strip().lower())
    if exclude is not None:
        qs = qs.exclude(pk=exclude)
    return qs.count()


def create_customer(
    caller: Caller,
    *,
    display_name_fa: str,
    legal_name_fa: str | None = None,
    default_required_quality_ref: str | None = None,
    acknowledge_warnings: Iterable[str] = (),
    request_id: uuid.UUID | None = None,
) -> Customer:
    authorize(caller, CUSTOMER_MANAGE)
    name = required_text(display_name_fa, max_len=200, field="display_name_fa")
    legal = optional_text(legal_name_fa, max_len=300, field="legal_name_fa")
    quality = optional_text(default_required_quality_ref, max_len=64, field="default_required_quality_ref")
    acks = acknowledged(acknowledge_warnings, [WARN_DUPLICATE_NAME])
    with unit_of_work(caller.context(request_id)) as uow:
        duplicates = customer_name_duplicates(name)
        if duplicates and WARN_DUPLICATE_NAME not in acks:
            refuse(
                Reason.DUPLICATE_CUSTOMER_NAME,
                field="display_name_fa",
                detail="a customer with this name exists",
            )
        with db_rules():
            c = Customer.objects.create(
                customer_no=next_number("customer"),
                display_name_fa=name,
                legal_name_fa=legal,
                default_required_quality_ref=quality,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
            )
        c.refresh_from_db()
        _write(
            uow,
            verb="create",
            rtype="identity.customer",
            obj=c,
            after=_customer_view(c),
            payload={"id": str(c.pk), "status": c.status},
            scope={"acknowledged_warnings": sorted(acks & {WARN_DUPLICATE_NAME}) if duplicates else []},
        )
    return c


def update_customer(
    caller: Caller,
    customer_id: uuid.UUID,
    *,
    expected_version: int,
    display_name_fa: str | None = None,
    legal_name_fa: str | None = None,
    default_required_quality_ref: str | None = None,
    status: str | None = None,
    acknowledge_warnings: Iterable[str] = (),
    reason: str = "",
    request_id: uuid.UUID | None = None,
) -> Customer:
    authorize(caller, CUSTOMER_MANAGE)
    acks = acknowledged(acknowledge_warnings, [WARN_DUPLICATE_NAME])
    with unit_of_work(caller.context(request_id)) as uow:
        c = lock(Customer, customer_id)
        check_version(c, expected_version)
        before = _customer_view(c)
        values: dict[str, Any] = {}
        if display_name_fa is not None:
            name = required_text(display_name_fa, max_len=200, field="display_name_fa")
            if name.lower() != c.display_name_fa.lower() and customer_name_duplicates(name, exclude=c.pk):
                if WARN_DUPLICATE_NAME not in acks:
                    refuse(Reason.DUPLICATE_CUSTOMER_NAME, field="display_name_fa")
            values["display_name_fa"] = name
        if legal_name_fa is not None:
            values["legal_name_fa"] = optional_text(legal_name_fa, max_len=300, field="legal_name_fa")
        if default_required_quality_ref is not None:
            values["default_required_quality_ref"] = optional_text(
                default_required_quality_ref, max_len=64, field="default_required_quality_ref"
            )
        text = ""
        if status is not None and status != c.status:
            PARTY_MACHINE.assert_transition(c.status, status)
            text = reason_text(reason)
            values["status"] = status
        if not values:
            refuse(Reason.REQUIRED, field="", detail="nothing to change")
        with db_rules():
            Customer.objects.filter(pk=c.pk).update(updated_by_id=caller.user_id, **values)
        c.refresh_from_db()
        _write(
            uow,
            verb="update",
            rtype="identity.customer",
            obj=c,
            before=before,
            after={**_customer_view(c), "changed": sorted(values)},
            payload={"id": str(c.pk), "status": c.status},
            reason=text,
        )
    return c


def add_brand(
    caller: Caller, customer_id: uuid.UUID, *, brand_name_fa: str, request_id: uuid.UUID | None = None
) -> CustomerBrand:
    """DEC-058 B-A: one customer, many brands (unique name per customer, case-insensitive)."""
    authorize(caller, CUSTOMER_MANAGE)
    name = required_text(brand_name_fa, max_len=200, field="brand_name_fa")
    with unit_of_work(caller.context(request_id)) as uow:
        c = lock(Customer, customer_id)
        if c.status != PartyStatus.ACTIVE:
            refuse(Reason.MASTER_NOT_ACTIVE, field="customer_id")
        with db_rules():
            b = CustomerBrand.objects.create(
                customer=c, brand_name_fa=name, created_by_id=caller.user_id, updated_by_id=caller.user_id
            )
        b.refresh_from_db()
        _write(
            uow,
            verb="create",
            rtype="identity.customer_brand",
            obj=b,
            after={"customer_id": str(c.pk), "status": b.status},
            payload={"id": str(b.pk), "customer_id": str(c.pk), "status": b.status},
        )
    return b


def set_brand_status(
    caller: Caller,
    brand_id: uuid.UUID,
    *,
    status: str,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> CustomerBrand:
    authorize(caller, CUSTOMER_MANAGE)
    text = reason_text(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        b = lock(CustomerBrand, brand_id)
        check_version(b, expected_version)
        PARTY_MACHINE.assert_transition(b.status, status)
        before = {"status": b.status}
        CustomerBrand.objects.filter(pk=b.pk).update(status=status, updated_by_id=caller.user_id)
        b.refresh_from_db()
        _write(
            uow,
            verb="update",
            rtype="identity.customer_brand",
            obj=b,
            before=before,
            after={"customer_id": str(b.customer_id), "status": b.status},
            payload={"id": str(b.pk), "customer_id": str(b.customer_id), "status": b.status},
            reason=text,
        )
    return b


# ------------------------------------------------------------------------------------------------ products
def _active_type(type_id: uuid.UUID) -> ProductClass:
    t = lock(ProductClass, type_id)
    if t.level_key != ClassLevel.PRODUCT_TYPE:
        refuse(Reason.INVALID, field="product_type_id", detail="not a product type")
    if t.status != MasterStatus.ACTIVE:
        refuse(Reason.MASTER_NOT_ACTIVE, field="product_type_id")
    return t


def proposed_product_no(
    t: ProductClass, *, buckle_type_code: str | None = None, belt_width_code: str | None = None
) -> str:
    """The product number a new product of type ``t`` gets (pure read; preview and create use it)."""
    belt = t.product_no_scheme == ProductNoScheme.BELT_BUCKLE_WIDTH
    if belt:
        if buckle_type_code is None or belt_width_code is None:
            refuse(Reason.BELT_SEGMENTS_REQUIRED, field="buckle_type_code")
        return coderule.belt_product_no(buckle_type_code, belt_width_code)
    if buckle_type_code is not None or belt_width_code is not None:
        refuse(Reason.BELT_SEGMENTS_NOT_ALLOWED, field="buckle_type_code")
    return coderule.next_product_no(
        Product.objects.filter(product_type=t).values_list("product_no", flat=True)
    )


def create_product(
    caller: Caller,
    *,
    product_type_id: uuid.UUID,
    name_fa: str,
    buckle_type_code: str | None = None,
    belt_width_code: str | None = None,
    request_id: uuid.UUID | None = None,
) -> Product:
    authorize(caller, PRODUCT_MANAGE)
    name = required_text(name_fa, max_len=200, field="name_fa")
    with unit_of_work(caller.context(request_id)) as uow:
        t = _active_type(product_type_id)  # row lock: serialises numbering within the type
        product_no = proposed_product_no(
            t, buckle_type_code=buckle_type_code, belt_width_code=belt_width_code
        )
        if Product.objects.filter(product_type=t, product_no=product_no).exists():
            refuse(Reason.PRODUCT_NO_TAKEN, field="product_no", detail="this product number already exists")
        with db_rules():
            p = Product.objects.create(
                product_type=t,
                product_no=product_no,
                name_fa=name,
                buckle_type_code=buckle_type_code,
                belt_width_code=belt_width_code,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
            )
        p.refresh_from_db()
        _write(
            uow,
            verb="create",
            rtype="identity.product",
            obj=p,
            after={"product_type_id": str(t.pk), "product_no": p.product_no, "status": p.status},
            payload={"id": str(p.pk), "product_type_id": str(t.pk), "status": p.status},
        )
    return p


def _set_master_status(
    caller: Caller,
    model: type[Product] | type[Style],
    rtype: str,
    pk: uuid.UUID,
    *,
    status: str,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None,
) -> Any:
    authorize(caller, PRODUCT_MANAGE)
    text = reason_text(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        obj = lock(model, pk)
        check_version(obj, expected_version)
        MASTER_MACHINE.assert_transition(obj.status, status)
        before = {"status": obj.status}
        model._default_manager.filter(pk=obj.pk).update(status=status, updated_by_id=caller.user_id)
        obj.refresh_from_db()
        _write(
            uow,
            verb="status",
            rtype=rtype,
            obj=obj,
            before=before,
            after={"status": obj.status},
            payload={"id": str(obj.pk), "status": obj.status},
            reason=text,
        )
    return obj


def set_product_status(
    caller: Caller,
    product_id: uuid.UUID,
    *,
    status: str,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> Product:
    obj: Product = _set_master_status(
        caller,
        Product,
        "identity.product",
        product_id,
        status=status,
        expected_version=expected_version,
        reason=reason,
        request_id=request_id,
    )
    return obj


# -------------------------------------------------------------------------------------------------- styles
def proposed_style_no(product: Product, category: ProductClass) -> str:
    return coderule.next_style_no(Style.objects.filter(product=product, category=category).count())


def _category_of_type(category_id: uuid.UUID, product: Product) -> ProductClass:
    c = ProductClass.objects.filter(pk=category_id).first()
    if c is None or c.level_key != ClassLevel.CATEGORY or c.parent_id != product.product_type_id:
        refuse(Reason.INVALID, field="category_id", detail="the category must belong to the product's type")
    if c.status != MasterStatus.ACTIVE:
        refuse(Reason.MASTER_NOT_ACTIVE, field="category_id")
    return c


def create_style(
    caller: Caller,
    *,
    product_id: uuid.UUID,
    category_id: uuid.UUID,
    name_fa: str,
    request_id: uuid.UUID | None = None,
) -> Style:
    authorize(caller, PRODUCT_MANAGE)
    name = required_text(name_fa, max_len=200, field="name_fa")
    with unit_of_work(caller.context(request_id)) as uow:
        p = lock(Product, product_id)  # row lock: serialises style numbering of the product
        if p.status == MasterStatus.RETIRED:
            refuse(Reason.MASTER_NOT_ACTIVE, field="product_id")
        c = _category_of_type(category_id, p)
        style_no = proposed_style_no(p, c)
        if Style.objects.filter(product=p, category=c, style_no=style_no).exists():
            # legacy styles of this product/category are not contiguous: the employer decides (open item)
            refuse(Reason.STYLE_NO_COLLISION, field="style_no", detail="count + 1 is already used")
        with db_rules():
            s = Style.objects.create(
                product=p,
                category=c,
                style_no=style_no,
                name_fa=name,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
            )
        s.refresh_from_db()
        _write(
            uow,
            verb="create",
            rtype="identity.style",
            obj=s,
            after={
                "product_id": str(p.pk),
                "category_id": str(c.pk),
                "style_no": s.style_no,
                "status": s.status,
            },
            payload={"id": str(s.pk), "product_id": str(p.pk), "category_id": str(c.pk), "status": s.status},
        )
    return s


def set_style_status(
    caller: Caller,
    style_id: uuid.UUID,
    *,
    status: str,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> Style:
    obj: Style = _set_master_status(
        caller,
        Style,
        "identity.style",
        style_id,
        status=status,
        expected_version=expected_version,
        reason=reason,
        request_id=request_id,
    )
    return obj


def _attributes(raw: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(raw, Mapping) or len(raw) > MAX_ATTRIBUTES:
        refuse(Reason.INVALID, field="attributes")
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not k.strip() or len(k) > 64:
            refuse(Reason.INVALID, field="attributes")
        if not isinstance(v, str) or len(v) > MAX_ATTRIBUTE_LEN:
            refuse(Reason.INVALID, field=f"attributes.{k}")
        out[k.strip()] = v.strip()
    if list(sensitive_paths(out)):
        refuse(Reason.INVALID, field="attributes", detail="attribute names must not be sensitive fields")
    return out


def create_style_revision(
    caller: Caller,
    *,
    style_id: uuid.UUID,
    attributes: Mapping[str, Any],
    request_id: uuid.UUID | None = None,
) -> StyleRevision:
    """A new DRAFT revision (number = last + 1; text attributes only: colour, material, ... - PHASE_04/06 own
    the master lists)."""
    authorize(caller, PRODUCT_MANAGE)
    attrs = _attributes(attributes)
    with unit_of_work(caller.context(request_id)) as uow:
        s = lock(Style, style_id)
        if s.status == MasterStatus.RETIRED:
            refuse(Reason.MASTER_NOT_ACTIVE, field="style_id")
        last = (
            StyleRevision.objects.filter(style=s)
            .order_by("-revision_no")
            .values_list("revision_no", flat=True)
            .first()
        ) or 0
        with db_rules():
            r = StyleRevision.objects.create(
                style=s,
                revision_no=last + 1,
                attributes=attrs,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
            )
        r.refresh_from_db()
        _write(
            uow,
            verb="create",
            rtype="identity.style_revision",
            obj=r,
            after={"style_id": str(s.pk), "revision_no": r.revision_no, "status": r.status},
            payload={
                "id": str(r.pk),
                "style_id": str(s.pk),
                "revision_no": r.revision_no,
                "status": r.status,
            },
        )
    return r


def activate_style_revision(
    caller: Caller, revision_id: uuid.UUID, *, expected_version: int, request_id: uuid.UUID | None = None
) -> StyleRevision:
    authorize(caller, PRODUCT_MANAGE)
    with unit_of_work(caller.context(request_id)) as uow:
        r = lock(StyleRevision, revision_id)
        lock(Style, r.style_id)  # one activation per style at a time
        check_version(r, expected_version)
        STYLE_REVISION_MACHINE.assert_transition(r.status, StyleRevisionStatus.ACTIVE)
        for old in StyleRevision.objects.select_for_update().filter(
            style_id=r.style_id, status=StyleRevisionStatus.ACTIVE
        ):
            StyleRevision.objects.filter(pk=old.pk).update(
                status=StyleRevisionStatus.SUPERSEDED, updated_by_id=caller.user_id
            )
            old.refresh_from_db()
            _write(
                uow,
                verb="status",
                rtype="identity.style_revision",
                obj=old,
                before={"status": StyleRevisionStatus.ACTIVE.value},
                after={"status": old.status},
                payload={
                    "id": str(old.pk),
                    "style_id": str(old.style_id),
                    "revision_no": old.revision_no,
                    "status": old.status,
                },
            )
        with db_rules():
            StyleRevision.objects.filter(pk=r.pk).update(
                status=StyleRevisionStatus.ACTIVE, updated_by_id=caller.user_id
            )
        r.refresh_from_db()
        _write(
            uow,
            verb="activate",
            rtype="identity.style_revision",
            obj=r,
            before={"status": StyleRevisionStatus.DRAFT.value},
            after={"status": r.status, "revision_no": r.revision_no},
            payload={
                "id": str(r.pk),
                "style_id": str(r.style_id),
                "revision_no": r.revision_no,
                "status": r.status,
            },
        )
    return r
