"""External references (PHASE_02 / 02.4; DEC-058): Rahkaran project code, contract number, customer style
code, customer serial, ... attached to a customer, product, style, order, order line or serial.

* ``identity.external_ref.manage`` (commercial_officer, product_data_steward) creates and ends references;
  ``identity.external_ref.read`` lists them.
* The value is raw text exactly as given (never parsed as a number, never our serial, DEC-006); it is unique
  only per (system, type, value, target) - never globally (C-56). An existing identical live reference is
  refused (``EXTERNAL_REF_EXISTS``), never merged.
* The type must be an ACTIVE row of ``identity_external_ref_type`` (seed 0021; steward-extensible).
* Ending a reference sets ``valid_to`` (never deleted); an ended reference cannot be ended again.
* The value is S2 business data: it is not in the outbox payload (identifiers and codes only).
"""

from __future__ import annotations

import uuid
from typing import Final

from django.db import models
from django.db.models.functions import Now

from platform_core.authz.policy import Caller
from platform_core.commercial.models import CustomerOrder, CustomerOrderLine
from platform_core.engine.dbrules import db_rules
from platform_core.engine.errors import NotFound
from platform_core.engine.uow import UnitOfWork, unit_of_work

from .models import (
    Customer,
    ExternalRef,
    ExternalRefType,
    ExternalSystem,
    ExternalTargetType,
    PartyStatus,
    Product,
    Serial,
    Style,
)
from .refusals import Reason, refuse
from .usecase import authorize, check_version, lock, reason_text, required_text

REF_READ: Final = "identity.external_ref.read"
REF_MANAGE: Final = "identity.external_ref.manage"
RESOURCE: Final = "identity.external_ref"
_TARGETS: Final[dict[str, type[models.Model]]] = {
    ExternalTargetType.CUSTOMER: Customer,
    ExternalTargetType.PRODUCT: Product,
    ExternalTargetType.STYLE: Style,
    ExternalTargetType.CUSTOMER_ORDER: CustomerOrder,
    ExternalTargetType.ORDER_LINE: CustomerOrderLine,
    ExternalTargetType.SERIAL: Serial,
}


def _write(uow: UnitOfWork, verb: str, past: str, ref: ExternalRef, *, reason: str) -> None:
    uow.audit(
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(ref.pk),
        resource_version=ref.row_version,
        after={
            "target_type": ref.target_type,
            "target_id": str(ref.target_id),
            "system": ref.system,
            "namespace": ref.ref_type_id,
            "ended": ref.valid_to is not None,
        },
        reason=reason,
    )
    uow.emit(
        event_type=f"{RESOURCE}.{past}",
        aggregate_type=RESOURCE,
        aggregate_id=str(ref.pk),
        aggregate_version=ref.row_version,
        payload={"id": str(ref.pk), "target_type": ref.target_type, "system": ref.system},
    )


def create_external_ref(
    caller: Caller,
    *,
    target_type: str,
    target_id: uuid.UUID,
    system: str,
    namespace: str,
    value: str,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> ExternalRef:
    authorize(caller, REF_MANAGE)
    text = reason_text(reason)
    if target_type not in ExternalTargetType.values:
        refuse(Reason.INVALID, field="target_type")
    if system not in ExternalSystem.values:
        refuse(Reason.INVALID, field="system")
    raw = required_text(value, max_len=64, field="value")
    if raw != value:  # kept exactly as typed: no trimming, no normalisation
        refuse(
            Reason.INVALID, field="value", detail="the value is stored exactly as given (no spaces around)"
        )
    with unit_of_work(caller.context(request_id)) as uow:
        if not _TARGETS[ExternalTargetType(target_type)]._default_manager.filter(pk=target_id).exists():
            raise NotFound()
        rtype = ExternalRefType.objects.filter(pk=namespace).first()
        if rtype is None:
            refuse(Reason.INVALID, field="namespace")
        if rtype.status != PartyStatus.ACTIVE:
            refuse(Reason.MASTER_NOT_ACTIVE, field="namespace")
        if ExternalRef.objects.filter(
            system=system, ref_type=rtype, value=value, target_type=target_type, target_id=target_id
        ).exists():
            refuse(Reason.EXTERNAL_REF_EXISTS, field="value", detail="this reference is already recorded")
        with db_rules():
            ref = ExternalRef.objects.create(
                target_type=target_type,
                target_id=target_id,
                system=system,
                ref_type=rtype,
                value=value,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
            )
        ref.refresh_from_db()
        _write(uow, "create", "created", ref, reason=text)
    return ref


def end_external_ref(
    caller: Caller,
    ref_id: uuid.UUID,
    *,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> ExternalRef:
    authorize(caller, REF_MANAGE)
    text = reason_text(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        ref = lock(ExternalRef, ref_id)
        check_version(ref, expected_version)
        if ref.valid_to is not None:
            refuse(Reason.STATE_NOT_ALLOWED, field="valid_to", detail="the reference has already ended")
        with db_rules():
            ExternalRef.objects.filter(pk=ref.pk).update(valid_to=Now(), updated_by_id=caller.user_id)
        ref.refresh_from_db()
        _write(uow, "end", "ended", ref, reason=text)
    return ref
