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
  ``platform_idempotency_record`` (02.4). REV-0220 (02.3): a replay must be the *same* allocation (customer,
  style, style revision, product code, allocating user); the same key with another payload is refused with
  422 ``IDEMPOTENCY_KEY_REUSED`` / ``IDEMPOTENCY_PAYLOAD_MISMATCH`` - no number is drawn, nothing is written.
* 02.3: :func:`add_snapshot` (next snapshot version when a change request is applied, DEC-059) and
  :func:`cancel_serial` (ALLOCATED -> CANCELLED with its line; the number is never re-used).
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
from django.db.models.functions import Now

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
from .refusals import Reason, refuse

AUDIT_ACTION = "identity.serial.allocate"
EVENT_TYPE = "identity.serial.allocated"
AGGREGATE_TYPE = "identity.serial"
CANCEL_EVENT = "identity.serial.cancelled"
SNAPSHOT_EVENT = "identity.serial.snapshot_added"


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
        # REV-0220: a replay must be the same request; the same key for another line/style is refused
        if _identity_of(existing) != _identity_of_request(request):
            refuse(
                Reason.IDEMPOTENCY_PAYLOAD_MISMATCH,
                field="idempotency_key",
                detail="this allocation key was already used for a different line",
            )
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


def _identity_of(serial: Serial) -> tuple[Any, ...]:
    return (
        serial.customer_id,
        serial.style_id,
        serial.style_revision_id,
        serial.product_code_id,
        serial.allocated_by_id,
    )


def _identity_of_request(request: AllocationRequest) -> tuple[Any, ...]:
    return (
        request.customer_id,
        request.style_id,
        request.style_revision_id,
        request.product_code_id,
        request.allocated_by,
    )


def add_snapshot(
    uow: UnitOfWork,
    serial_id: uuid.UUID,
    *,
    snapshot: Mapping[str, Any],
    order_version: int,
    change_request_id: uuid.UUID,
) -> SerialSnapshot:
    """DEC-059: an applied change request writes the next snapshot version of every serial it touches (old
    versions are append-only). Called by the Commercial apply use case inside its unit of work."""
    actor = uow.ctx.actor.actor_id
    if not actor:
        raise EngineContractError("a serial snapshot needs a user actor")
    using = uow.using
    serial = Serial.objects.using(using).select_for_update().get(pk=serial_id)
    last = (
        SerialSnapshot.objects.using(using)
        .filter(serial=serial)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    ) or 0
    snap = SerialSnapshot.objects.using(using).create(
        serial=serial,
        version=last + 1,
        snapshot=dict(snapshot),
        reason=SnapshotReason.CHANGE_APPLIED,
        order_version=order_version,
        change_request_id=change_request_id,
        created_by_id=actor,
    )
    uow.audit(
        action="identity.serial.snapshot",
        resource_type=AGGREGATE_TYPE,
        resource_id=str(serial.pk),
        resource_version=serial.row_version,
        after={"snapshot_version": snap.version, "order_version": order_version},
        scope={"change_request_id": str(change_request_id)},
    )
    uow.emit(
        event_type=SNAPSHOT_EVENT,
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=str(serial.pk),
        aggregate_version=serial.row_version,
        payload={"id": str(serial.pk), "snapshot_version": snap.version, "order_version": order_version},
    )
    return snap


def cancel_serial(uow: UnitOfWork, serial_id: uuid.UUID, *, reason: str) -> Serial:
    """DEC-059: ALLOCATED -> CANCELLED together with its line (the number is never re-used: the counter never
    moves back and the row is never deleted). The DB pairs line and serial cancellation at commit."""
    using = uow.using
    serial = Serial.objects.using(using).select_for_update().get(pk=serial_id)
    if serial.status != SerialStatus.ALLOCATED:
        refuse(Reason.STATE_NOT_ALLOWED, field="serial", detail="only an ALLOCATED serial can be cancelled")
    Serial.objects.using(using).filter(pk=serial.pk).update(
        status=SerialStatus.CANCELLED, cancelled_at=Now(), cancel_reason=reason[:500]
    )
    serial.refresh_from_db(using=using)
    uow.audit(
        action="identity.serial.cancel",
        resource_type=AGGREGATE_TYPE,
        resource_id=str(serial.pk),
        resource_version=serial.row_version,
        before={"status": SerialStatus.ALLOCATED.value},
        after={"status": serial.status},
        reason=reason[:500],
    )
    uow.emit(
        event_type=CANCEL_EVENT,
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=str(serial.pk),
        aggregate_version=serial.row_version,
        payload={"id": str(serial.pk), "status": serial.status},
    )
    return serial
