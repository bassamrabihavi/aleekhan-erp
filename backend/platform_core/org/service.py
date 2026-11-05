"""Org tree services (DEC-043 / DEC-048 APPROVED; STATE_TRANSITIONS 4.10).

Edited only by holders of ``platform.org.manage`` (owner/admin in PHASE_01, MFA step-up). Changes take effect
now (never back-dated: the DB refuses ``effective_from`` / assignment dates older than now - 60 s, migration
0008 for units/positions, 0011 for person-to-position assignments, REV-0107 / REV-0109). Tree invariants
(acyclic, depth <= ``org_tree_max_depth``, no ACTIVE child under an INACTIVE parent, one ACTIVE unit head,
``primary_capacity``, one PRIMARY position per person) are enforced by the DB guards; violations surface as
409
``STATE_TRANSITION_NOT_ALLOWED`` / 400 ``VALIDATION_FAILED`` with the rule name in ``errors[].code``.
Holding a position grants no permission (DEC-049).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from django.db import models

from platform_core.authz.policy import Caller, require_permission, require_step_up
from platform_core.engine.context import db_now
from platform_core.engine.dbrules import db_rules
from platform_core.engine.errors import FieldError, NotFound, StateTransitionNotAllowed, ValidationFailed
from platform_core.engine.uow import UnitOfWork, unit_of_work

from .models import OrgStatus, OrgUnit, Position, PositionAssignment, PositionAssignmentKind

MANAGE: Final = "platform.org.manage"


def _guard(caller: Caller) -> None:
    require_permission(caller, MANAGE)
    require_step_up(caller, MANAGE)


def _reason(text: str) -> str:
    value = text.strip()
    if len(value) < 3:
        raise ValidationFailed("a reason is required", errors=[FieldError("reason", "REQUIRED")])
    return value[:500]


def _audit(
    uow: UnitOfWork,
    action: str,
    event: str,
    rtype: str,
    obj: Any,
    after: dict[str, Any],
    *,
    before: dict[str, Any] | None = None,
    reason: str = "",
) -> None:
    uow.audit(
        action=action,
        resource_type=rtype,
        resource_id=str(obj.pk),
        resource_version=obj.row_version,
        before=before,
        after=after,
        reason=reason,
    )
    uow.emit(
        event_type=event,
        aggregate_type=rtype,
        aggregate_id=str(obj.pk),
        aggregate_version=obj.row_version,
        payload={"id": str(obj.pk)},
    )


def _unit_view(u: OrgUnit) -> dict[str, Any]:
    return {
        "code": u.code,
        "unit_type": u.unit_type_id,
        "parent_id": str(u.parent_id) if u.parent_id else None,
        "status": u.status,
    }


def _position_view(p: Position) -> dict[str, Any]:
    return {
        "code": p.code,
        "unit_id": str(p.unit_id),
        "reports_to_id": str(p.reports_to_id) if p.reports_to_id else None,
        "is_unit_head": p.is_unit_head,
        "primary_capacity": p.primary_capacity,
        "status": p.status,
    }


def _lock[M: models.Model](model: type[M], pk: uuid.UUID) -> M:
    obj = model._default_manager.select_for_update().filter(pk=pk).first()
    if obj is None:
        raise NotFound()
    return obj


# ---------------------------------------------------------------------------------------------- units
def create_unit(
    caller: Caller,
    *,
    code: str,
    name_fa: str,
    unit_type: str,
    parent_id: uuid.UUID | None,
    reason: str,
    request_id: uuid.UUID | None = None,
    provenance: str = "SYS",
) -> OrgUnit:
    _guard(caller)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        if parent_id is not None and not OrgUnit.objects.filter(pk=parent_id).exists():
            raise NotFound()
        with db_rules():
            unit = OrgUnit.objects.create(
                code=code,
                name_fa=name_fa,
                unit_type_id=unit_type,
                parent_id=parent_id,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
                provenance=provenance,
            )
        unit.refresh_from_db()
        _audit(
            uow,
            "platform.org.unit.create",
            "platform.org.unit.created",
            "platform.org_unit",
            unit,
            _unit_view(unit),
            reason=text,
        )
    return unit


def move_unit(
    caller: Caller,
    unit_id: uuid.UUID,
    *,
    new_parent_id: uuid.UUID | None,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> OrgUnit:
    """``moveOrgUnit``: closes the current parent link and opens a new one now (history by trigger)."""
    _guard(caller)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        unit = _lock(OrgUnit, unit_id)
        _check_version(unit, expected_version)
        if new_parent_id is not None and not OrgUnit.objects.filter(pk=new_parent_id).exists():
            raise NotFound()
        before = _unit_view(unit)
        with db_rules():
            OrgUnit.objects.filter(pk=unit.pk).update(parent_id=new_parent_id, updated_by_id=caller.user_id)
        unit.refresh_from_db()
        _audit(
            uow,
            "platform.org.unit.move",
            "platform.org.unit.moved",
            "platform.org_unit",
            unit,
            _unit_view(unit),
            before=before,
            reason=text,
        )
    return unit


def deactivate_unit(
    caller: Caller,
    unit_id: uuid.UUID,
    *,
    expected_version: int,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> OrgUnit:
    _guard(caller)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        unit = _lock(OrgUnit, unit_id)
        _check_version(unit, expected_version)
        if unit.status != OrgStatus.ACTIVE:
            raise StateTransitionNotAllowed("the unit is not ACTIVE")
        before = _unit_view(unit)
        with db_rules():
            OrgUnit.objects.filter(pk=unit.pk).update(status=OrgStatus.INACTIVE, updated_by_id=caller.user_id)
        unit.refresh_from_db()
        _audit(
            uow,
            "platform.org.unit.deactivate",
            "platform.org.unit.deactivated",
            "platform.org_unit",
            unit,
            _unit_view(unit),
            before=before,
            reason=text,
        )
    return unit


def _check_version(obj: Any, expected: int) -> None:
    from platform_core.engine.errors import VersionConflict

    if obj.row_version != expected:
        raise VersionConflict()


# ------------------------------------------------------------------------------------------ positions
def create_position(
    caller: Caller,
    *,
    unit_id: uuid.UUID,
    code: str,
    title_fa: str,
    reports_to_id: uuid.UUID | None = None,
    is_unit_head: bool = False,
    primary_capacity: int = 1,
    reason: str,
    request_id: uuid.UUID | None = None,
    provenance: str = "SYS",
) -> Position:
    _guard(caller)
    text = _reason(reason)
    if is_unit_head and primary_capacity != 1:
        raise ValidationFailed(errors=[FieldError("primary_capacity", "HEAD_CAPACITY_ONE")])
    with unit_of_work(caller.context(request_id)) as uow:
        if not OrgUnit.objects.filter(pk=unit_id).exists():
            raise NotFound()
        if reports_to_id is not None and not Position.objects.filter(pk=reports_to_id).exists():
            raise NotFound()
        with db_rules():
            pos = Position.objects.create(
                unit_id=unit_id,
                code=code,
                title_fa=title_fa,
                reports_to_id=reports_to_id,
                is_unit_head=is_unit_head,
                primary_capacity=primary_capacity,
                created_by_id=caller.user_id,
                updated_by_id=caller.user_id,
                provenance=provenance,
            )
        pos.refresh_from_db()
        _audit(
            uow,
            "platform.org.position.create",
            "platform.org.position.created",
            "platform.position",
            pos,
            _position_view(pos),
            reason=text,
        )
    return pos


def update_position(
    caller: Caller,
    position_id: uuid.UUID,
    *,
    expected_version: int,
    reason: str,
    reports_to_id: uuid.UUID | object | None = ...,
    primary_capacity: int | None = None,
    deactivate: bool = False,
    request_id: uuid.UUID | None = None,
) -> Position:
    _guard(caller)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        pos = _lock(Position, position_id)
        _check_version(pos, expected_version)
        before = _position_view(pos)
        values: dict[str, Any] = {"updated_by_id": caller.user_id}
        if reports_to_id is not ...:
            values["reports_to_id"] = reports_to_id
        if primary_capacity is not None:
            values["primary_capacity"] = primary_capacity
        if deactivate:
            if pos.status != OrgStatus.ACTIVE:
                raise StateTransitionNotAllowed("the position is not ACTIVE")
            values["status"] = OrgStatus.INACTIVE
        with db_rules():
            Position.objects.filter(pk=pos.pk).update(**values)
        pos.refresh_from_db()
        _audit(
            uow,
            "platform.org.position.update",
            "platform.org.position.updated",
            "platform.position",
            pos,
            _position_view(pos),
            before=before,
            reason=text,
        )
    return pos


# -------------------------------------------------------------------------------------- assignments
def assign_position(
    caller: Caller,
    *,
    position_id: uuid.UUID,
    user_id: uuid.UUID,
    kind: str,
    reason: str,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    request_id: uuid.UUID | None = None,
) -> PositionAssignment:
    """PRIMARY (one per person at any instant, up to the position capacity) or ACTING (always ends)."""
    from platform_core.identity.models import User

    _guard(caller)
    text = _reason(reason)
    if kind not in PositionAssignmentKind.values:
        raise ValidationFailed(errors=[FieldError("kind", "INVALID")])
    if kind == PositionAssignmentKind.ACTING and valid_to is None:
        raise ValidationFailed(errors=[FieldError("valid_to", "REQUIRED")])
    with unit_of_work(caller.context(request_id)) as uow:
        if (
            not Position.objects.filter(pk=position_id).exists()
            or not User.objects.filter(pk=user_id).exists()
        ):
            raise NotFound()
        values: dict[str, Any] = {
            "position_id": position_id,
            "user_id": user_id,
            "kind": kind,
            "valid_to": valid_to,
            "reason": text,
            "created_by_id": caller.user_id,
            "updated_by_id": caller.user_id,
        }
        if valid_from is not None:
            values["valid_from"] = valid_from
        with db_rules():
            pa = PositionAssignment.objects.create(**values)
        pa.refresh_from_db()
        _audit(
            uow,
            "platform.org.position_assignment.create",
            "platform.org.position_assignment.created",
            "platform.position_assignment",
            pa,
            {
                "position_id": str(position_id),
                "user_id": str(user_id),
                "kind": kind,
                "valid_from": pa.valid_from.isoformat(),
                "valid_to": pa.valid_to.isoformat() if pa.valid_to else None,
            },
            reason=text,
        )
    return pa


def end_position_assignment(
    caller: Caller,
    assignment_id: uuid.UUID,
    *,
    expected_version: int,
    reason: str,
    valid_to: datetime | None = None,
    request_id: uuid.UUID | None = None,
) -> PositionAssignment:
    """Set the end of an assignment, now or later (never in the past, REV-0109)."""
    _guard(caller)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        pa = _lock(PositionAssignment, assignment_id)
        _check_version(pa, expected_version)
        end = valid_to or db_now()
        before = {"valid_to": pa.valid_to.isoformat() if pa.valid_to else None}
        with db_rules():
            PositionAssignment.objects.filter(pk=pa.pk).update(valid_to=end, updated_by_id=caller.user_id)
        pa.refresh_from_db()
        _audit(
            uow,
            "platform.org.position_assignment.end",
            "platform.org.position_assignment.ended",
            "platform.position_assignment",
            pa,
            {"valid_to": pa.valid_to.isoformat() if pa.valid_to else None},
            before=before,
            reason=text,
        )
    return pa
