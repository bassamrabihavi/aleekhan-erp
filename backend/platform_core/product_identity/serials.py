"""Gapless serial allocation primitive (DEC-006, PHASE_02 / 02.2). Owned by the Identity module.

Contract (DEC-006 S-A + L-A + G-B + P-A, DECISION_LOG 2026-11-11/12)::

    with unit_of_work(ctx) as uow:              # the confirm transaction (02.3 engine)
        ...                                     # Commercial locks and confirms its order
        serial = allocate_serial(uow, request)  # Identity: number + serial + snapshot v1 + audit + outbox
        ...                                     # Commercial writes line.serial_id (its own table)

* The number comes from the single factory counter row, locked with ``SELECT ... FOR UPDATE`` inside the
  caller's
  transaction and moved by +1. It is never a database sequence and never ``MAX()+1``: a rolled back confirm
  rolls the counter back too, so no number is consumed (gapless, G-B). The database proves it at commit
  (``trg_identity_serial_counter_gapless``, migration 0020).
* Exactly one snapshot v1 and one ``identity.serial.allocated`` outbox event are written in the same
  transaction
  (ID-02, INV-02-04). The commit fails unless one Commercial line points to the new serial (REV-0201 pairing).
* Idempotent (ID-04): the same ``idempotency_key`` returns the serial it already produced, without drawing
  a new
  number and without a second audit/outbox row. The API-level replay (same response) is
  ``platform_idempotency_record`` (02.4).
* The caller must hold an open unit of work (lock order: audit chain first, then the counter row).

The serial number format is a plain integer as text, from 63001 (seed 0021). Who may call this (the order
confirm of ``planning_officer`` / the owner, DEC-057) is checked by the 02.3/02.4 use case, not here.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from django.db.models import F

from platform_core.engine.errors import EngineContractError
from platform_core.engine.uow import UnitOfWork

from .models import (
    FACTORY_SERIAL_NAMESPACE,
    Serial,
    SerialCounter,
    SerialSnapshot,
    SerialStatus,
    SnapshotReason,
)

AUDIT_ACTION = "identity.serial.allocate"
EVENT_TYPE = "identity.serial.allocated"
AGGREGATE_TYPE = "identity.serial"


@dataclass(frozen=True)
class AllocationRequest:
    """What the confirm transaction knows about one line (identifiers only; the image is the snapshot v1)."""

    idempotency_key: uuid.UUID
    allocated_by: uuid.UUID
    customer_id: uuid.UUID
    style_id: uuid.UUID
    style_revision_id: uuid.UUID
    product_code_id: uuid.UUID | None
    order_version: int
    snapshot: Mapping[str, Any]


@dataclass(frozen=True)
class AllocationResult:
    serial: Serial
    replayed: bool


def allocate_serial(uow: UnitOfWork, request: AllocationRequest) -> AllocationResult:
    if not uow.ctx.actor.actor_id:
        raise EngineContractError("serial allocation needs a user actor")
    using = uow.using
    existing = Serial.objects.using(using).filter(allocation_idempotency_key=request.idempotency_key).first()
    if existing is not None:
        return AllocationResult(existing, replayed=True)
    counter = (
        SerialCounter.objects.using(using).select_for_update().get(namespace_key=FACTORY_SERIAL_NAMESPACE)
    )
    value = counter.next_value
    SerialCounter.objects.using(using).filter(pk=counter.pk).update(next_value=F("next_value") + 1)
    serial = Serial.objects.using(using).create(
        serial_counter=counter,
        serial_number=str(value),
        serial_value=value,
        customer_id=request.customer_id,
        style_id=request.style_id,
        style_revision_id=request.style_revision_id,
        product_code_id=request.product_code_id,
        status=SerialStatus.ALLOCATED,
        allocation_idempotency_key=request.idempotency_key,
        allocated_by_id=request.allocated_by,
    )
    SerialSnapshot.objects.using(using).create(
        serial=serial,
        version=1,
        snapshot=dict(request.snapshot),
        reason=SnapshotReason.ALLOCATED,
        order_version=request.order_version,
        created_by_id=request.allocated_by,
    )
    uow.audit(
        action=AUDIT_ACTION,
        resource_type=AGGREGATE_TYPE,
        resource_id=str(serial.pk),
        resource_version=1,
        after={
            "serial_number": serial.serial_number,
            "status": SerialStatus.ALLOCATED,
            "snapshot_version": 1,
        },
    )
    uow.emit(
        event_type=EVENT_TYPE,
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=str(serial.pk),
        aggregate_version=1,
        payload={"id": str(serial.pk), "status": SerialStatus.ALLOCATED.value, "snapshot_version": 1},
    )
    return AllocationResult(serial, replayed=False)
