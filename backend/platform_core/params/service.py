"""Parameter engine (PHASE_01 / 01.3; STATE_TRANSITIONS 4.9, page 42).

Reading effective values: ``params/values.py``. Writing (proposal / publication):

* ``TECHNICAL``      propose -> publish by a holder of ``platform.config.parameter.publish`` (no second
  person,
  DEC-032 asks maker-checker only for BUSINESS_RULE).
* ``OWNER_POLICY``   proposed **and** published by the owner alone (Q-0103, employer answer 2026-11-05): only
  a
  holder of ``owner_admin`` (DB: ``ck_parameter_value_owner_policy``), fresh MFA step-up, reason, audit.
* ``BUSINESS_RULE``  maker-checker (publisher != proposer, DB trigger) **and** blocked by the definition's own
  decision until that decision is in the reviewed approved-rule registry: ``RULE_NOT_APPROVED``.

``effective_from`` in the past is refused (TECH clock tolerance 60 s, same as the org tree guard); a published
value is immutable; a newer published revision supersedes the previous one (history is never rewritten).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Final

from platform_core.authz.policy import Caller, require_owner_admin, require_permission, require_step_up
from platform_core.engine.context import db_now
from platform_core.engine.errors import (
    FieldError,
    NotFound,
    SelfApprovalForbidden,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.engine.rules import require_approved_rule
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import UnitOfWork, unit_of_work

from .models import Classification, ParameterDefinition, ParameterValue, ValueStatus

CLOCK_TOLERANCE: Final = timedelta(seconds=60)  # TECHNICAL (app/DB clock skew), not a business rule

PARAMETER_VALUE_MACHINE: Final = StateMachine(
    name="parameter_value",
    states=frozenset(ValueStatus.values),
    transitions={
        ValueStatus.DRAFT: frozenset({ValueStatus.PENDING_APPROVAL, ValueStatus.PUBLISHED}),
        ValueStatus.PENDING_APPROVAL: frozenset({ValueStatus.PUBLISHED, ValueStatus.REJECTED}),
        ValueStatus.PUBLISHED: frozenset({ValueStatus.SUPERSEDED}),
        ValueStatus.SUPERSEDED: frozenset(),
        ValueStatus.REJECTED: frozenset(),
    },
)


# ----------------------------------------------------------------------------------------------- write
def _definition(key: str) -> ParameterDefinition:
    try:
        return ParameterDefinition.objects.get(key=key)
    except ParameterDefinition.DoesNotExist:
        raise NotFound() from None


def _check_effective_from(value: datetime | None) -> datetime:
    now = db_now()
    if value is None:
        return now
    if value < now - CLOCK_TOLERANCE:
        raise ValidationFailed(
            "effective_from cannot be in the past", errors=[FieldError("effective_from", "PAST_DATE")]
        )
    return value


def _reason(reason: str) -> str:
    text = reason.strip()
    if len(text) < 3:
        raise ValidationFailed("a reason is required", errors=[FieldError("reason", "REQUIRED")])
    return text


def propose(
    caller: Caller,
    *,
    key: str,
    value: str,
    reason: str,
    effective_from: datetime | None = None,
    request_id: uuid.UUID | None = None,
) -> ParameterValue:
    """New value revision. OWNER_POLICY values are published at once by the owner (Q-0103)."""
    definition = _definition(key)
    if definition.classification == Classification.OWNER_POLICY:
        return publish_owner_policy(
            caller, key=key, value=value, reason=reason, effective_from=effective_from, request_id=request_id
        )
    require_permission(caller, "platform.config.parameter.propose")
    if definition.classification == Classification.BUSINESS_RULE:
        require_approved_rule(definition.decision_id, rule=f"parameter {key}")
    ctx = caller.context(request_id)
    actor = caller.user_id
    start = _check_effective_from(effective_from)
    with unit_of_work(ctx) as uow:
        pv = ParameterValue.objects.create(
            definition=definition,
            value=value,
            status=ValueStatus.PENDING_APPROVAL,
            effective_from=start,
            decision_id=definition.decision_id,
            reason=_reason(reason),
            proposed_by_id=actor,
        )
        _audit(
            uow, "platform.config.parameter.propose", "platform.config.parameter.proposed", pv, before=None
        )
    return pv


def publish(caller: Caller, value_id: uuid.UUID, *, request_id: uuid.UUID | None = None) -> ParameterValue:
    """PENDING_APPROVAL -> PUBLISHED (TECHNICAL / BUSINESS_RULE)."""
    require_permission(caller, "platform.config.parameter.publish")
    require_step_up(caller, "platform.config.parameter.publish")
    ctx = caller.context(request_id)
    actor = caller.user_id
    with unit_of_work(ctx) as uow:
        pv = _lock_value(value_id)
        definition = pv.definition
        if definition.classification == Classification.OWNER_POLICY:
            raise StateTransitionNotAllowed("OWNER_POLICY values are published by the owner directly")
        if definition.classification == Classification.BUSINESS_RULE:
            require_approved_rule(definition.decision_id, rule=f"parameter {definition.key}")
            if pv.proposed_by_id == actor:
                raise SelfApprovalForbidden()
        PARAMETER_VALUE_MACHINE.assert_transition(pv.status, ValueStatus.PUBLISHED)
        before = _snapshot(pv)
        now = db_now()
        _supersede_previous(definition, now)
        ParameterValue.objects.filter(pk=pv.pk).update(
            status=ValueStatus.PUBLISHED, published_by_id=actor, published_at=now
        )
        pv.refresh_from_db()
        _audit(
            uow, "platform.config.parameter.publish", "platform.config.parameter.published", pv, before=before
        )
    return pv


def publish_owner_policy(
    caller: Caller,
    *,
    key: str,
    value: str,
    reason: str,
    effective_from: datetime | None = None,
    request_id: uuid.UUID | None = None,
) -> ParameterValue:
    """Q-0103: OWNER_POLICY value proposed and published in one step by an ``owner_admin`` holder."""
    definition = _definition(key)
    if definition.classification != Classification.OWNER_POLICY:
        raise StateTransitionNotAllowed("only OWNER_POLICY parameters are published by the owner directly")
    require_owner_admin(caller)
    require_step_up(caller, "platform.config.parameter.publish")
    ctx = caller.context(request_id)
    actor = caller.user_id
    start = _check_effective_from(effective_from)
    text = _reason(reason)
    with unit_of_work(ctx) as uow:
        now = db_now()
        _supersede_previous(definition, now)
        pv = ParameterValue.objects.create(
            definition=definition,
            value=value,
            status=ValueStatus.PUBLISHED,
            effective_from=start,
            decision_id=definition.decision_id,
            reason=text,
            proposed_by_id=actor,
            published_by_id=actor,
            published_at=now,
        )
        _audit(
            uow, "platform.config.parameter.publish", "platform.config.parameter.published", pv, before=None
        )
    return pv


def reject(
    caller: Caller, value_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> ParameterValue:
    require_permission(caller, "platform.config.parameter.publish")
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        pv = _lock_value(value_id)
        PARAMETER_VALUE_MACHINE.assert_transition(pv.status, ValueStatus.REJECTED)
        before = _snapshot(pv)
        ParameterValue.objects.filter(pk=pv.pk).update(status=ValueStatus.REJECTED)
        pv.refresh_from_db()
        _audit(
            uow,
            "platform.config.parameter.reject",
            "platform.config.parameter.rejected",
            pv,
            before=before,
            reason=text,
        )
    return pv


# ---------------------------------------------------------------------------------------------- helpers
def _lock_value(value_id: uuid.UUID) -> ParameterValue:
    try:
        return ParameterValue.objects.select_for_update().select_related("definition").get(pk=value_id)
    except ParameterValue.DoesNotExist:
        raise NotFound() from None


def _supersede_previous(definition: ParameterDefinition, now: datetime) -> None:
    ParameterValue.objects.filter(definition=definition, status=ValueStatus.PUBLISHED).update(
        status=ValueStatus.SUPERSEDED, superseded_at=now
    )


def _snapshot(pv: ParameterValue) -> dict[str, object]:
    return {
        "key": pv.definition_id,
        "value": pv.value,
        "status": pv.status,
        "effective_from": pv.effective_from.isoformat(),
    }


def _audit(
    uow: UnitOfWork,
    action: str,
    event_type: str,
    pv: ParameterValue,
    *,
    before: dict[str, object] | None,
    reason: str = "",
) -> None:
    uow.audit(
        action=action,
        resource_type="platform.parameter_value",
        resource_id=str(pv.pk),
        resource_version=pv.row_version,
        before=before,
        after=_snapshot(pv),
        reason=reason or pv.reason,
        scope={"parameter_key": pv.definition_id, "classification": pv.definition.classification},
    )
    uow.emit(
        event_type=event_type,
        aggregate_type="platform.parameter_value",
        aggregate_id=str(pv.pk),
        aggregate_version=pv.row_version,
        payload={"id": str(pv.pk), "parameter_key": pv.definition_id, "status": pv.status},
    )
