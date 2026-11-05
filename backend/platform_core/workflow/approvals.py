"""Maker-checker approval requests (STATE_TRANSITIONS 4.4; DEC-032 / DEC-048 / DEC-049 APPROVED).

* Raised by the owning use case (role assignment of a business-approval role, document revision approval,
  BUSINESS_RULE parameter publish). One PENDING request per (resource, revision, action) - DB unique index.
* Route (DEC-048, PHASE_01): role + org-unit scope only. The decider needs :func:`decider_permission` of the
  request's action within the request's ``route_scope_unit`` (NULL route = GLOBAL scope), from a BUSINESS role
  (technical/admin roles never qualify, DEC-003), and a fresh MFA step-up.
* Never self-approved (DEC-032 D1): the requester - and for role assignments also the grantee - gets 403
  ``SELF_APPROVAL_FORBIDDEN``; a single-person deadlock stays PENDING until it expires. No auto-approval.
* Decided exactly once: the decision locks the request row; a concurrent second decision finds it decided ->
  409 ``STATE_TRANSITION_NOT_ALLOWED``. An expired request (``expires_at`` reached, 30 days) cannot be
  decided;
  the sweep :func:`expire_due` moves it to EXPIRED.
* The effect on the resource runs in the same transaction through a handler registered per resource type
  (:func:`register_resource_handler`): approval of a role assignment activates it, etc.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from platform_core.authz.policy import (
    Caller,
    RecordScope,
    decide,
    decider_permission,
    permission_flags,
    require_permission,
    require_step_up,
)
from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.engine.errors import (
    AccessDenied,
    FieldError,
    NotFound,
    SelfApprovalForbidden,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import NothingToDo, UnitOfWork, unit_of_work, unit_of_work_or_nothing
from platform_core.params.values import effective_days

from .models import ApprovalRequest, ApprovalStatus, RouteKind

APPROVAL_MACHINE: Final = StateMachine(
    name="approval_request",
    states=frozenset(ApprovalStatus.values),
    transitions={
        ApprovalStatus.PENDING: frozenset(
            {
                ApprovalStatus.APPROVED,
                ApprovalStatus.REJECTED,
                ApprovalStatus.WITHDRAWN,
                ApprovalStatus.SUPERSEDED,
                ApprovalStatus.EXPIRED,
            }
        ),
        **{s: frozenset() for s in ApprovalStatus.values if s != ApprovalStatus.PENDING},
    },
)


@dataclass(frozen=True)
class Outcome:
    request: ApprovalRequest
    via_self_assignment: bool = False


# resource_type -> (on_approved, on_closed_without_approval, extra makers that may not decide)
Handler = Callable[[UnitOfWork, ApprovalRequest, uuid.UUID | None], None]
MakersOf = Callable[[ApprovalRequest], set[uuid.UUID]]


@dataclass(frozen=True)
class ResourceHandler:
    on_approved: Handler
    on_closed: Handler
    makers_of: MakersOf


_HANDLERS: dict[str, ResourceHandler] = {}


def register_resource_handler(resource_type: str, handler: ResourceHandler) -> None:
    _HANDLERS[resource_type] = handler


def _handler(resource_type: str) -> ResourceHandler | None:
    _load_handlers()
    return _HANDLERS.get(resource_type)


def _load_handlers() -> None:
    # owning modules register on import (no import cycle at module load)
    import platform_core.documents.service
    import platform_core.identity.roles  # noqa: F401


_PAST: Final = {
    "raise": "raised",
    "approve": "approved",
    "reject": "rejected",
    "withdraw": "withdrawn",
    "supersede": "superseded",
    "expire": "expired",
}


def _snapshot(r: ApprovalRequest) -> dict[str, object]:
    return {
        "action": r.action_id,
        "resource_type": r.resource_type,
        "resource_id": r.resource_id,
        "resource_revision": r.resource_revision,
        "status": r.status,
    }


def _audit(
    uow: UnitOfWork,
    verb: str,
    r: ApprovalRequest,
    *,
    before: dict[str, object] | None,
    reason: str = "",
    scope: dict[str, object] | None = None,
) -> None:
    uow.audit(
        action=f"platform.workflow.approval.{verb}",
        resource_type="platform.approval_request",
        resource_id=str(r.pk),
        resource_version=r.row_version,
        before=before,
        after=_snapshot(r),
        reason=reason,
        scope=scope or {},
    )
    uow.emit(
        event_type=f"platform.workflow.approval.{_PAST[verb]}",
        aggregate_type="platform.approval_request",
        aggregate_id=str(r.pk),
        aggregate_version=r.row_version,
        payload={
            "id": str(r.pk),
            "status": r.status,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
        },
    )


def raise_request(
    uow: UnitOfWork,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    resource_revision: int,
    requested_by: uuid.UUID,
    route_scope_unit_id: uuid.UUID | None = None,
) -> ApprovalRequest:
    """Owning use cases call this inside their unit of work (expiry: ``approval_request_expiry_days``)."""
    permission_flags(action)  # must be a catalogue action
    now = db_now()
    req = ApprovalRequest.objects.create(
        action_id=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_revision=resource_revision,
        requested_by_id=requested_by,
        requested_at=now,
        expires_at=now + effective_days("approval_request_expiry_days"),
        route_kind=RouteKind.ROLE_UNIT_SCOPE,
        route_scope_unit_id=route_scope_unit_id,
    )
    _audit(uow, "raise", req, before=None)
    return req


def record_scope(r: ApprovalRequest) -> RecordScope:
    return RecordScope(
        units=frozenset({r.route_scope_unit_id}) if r.route_scope_unit_id else frozenset(),
        owners=frozenset({r.requested_by_id}),
    )


def _lock(request_id: uuid.UUID) -> ApprovalRequest:
    r = ApprovalRequest.objects.select_for_update().filter(pk=request_id).first()
    if r is None:
        raise NotFound()
    return r


def _check_decider(caller: Caller, r: ApprovalRequest) -> bool:
    """Returns ``via_self_assignment``. Order: scope (404) -> SoD (403) -> MFA (401)."""
    perm = decider_permission(r.action_id)
    require_permission(caller, perm)
    decision = decide(caller, perm, record_scope(r))
    if not decision.allowed:
        raise NotFound()
    makers = {r.requested_by_id}
    handler = _handler(r.resource_type)
    if handler is not None:
        makers |= handler.makers_of(r)
    if caller.user_id in makers:
        raise SelfApprovalForbidden()
    require_step_up(caller, perm)
    return decision.via_self_assignment


def _decide(
    caller: Caller,
    request_id: uuid.UUID,
    status: ApprovalStatus,
    *,
    note: str,
    expected_revision: int | None,
    request_ctx_id: uuid.UUID | None,
) -> Outcome:
    with unit_of_work(caller.context(request_ctx_id)) as uow:
        r = _lock(request_id)
        via_self = _check_decider(caller, r)
        APPROVAL_MACHINE.assert_transition(r.status, status)
        if r.expires_at <= db_now():
            raise StateTransitionNotAllowed("the approval request has expired")
        if expected_revision is not None and expected_revision != r.resource_revision:
            raise StateTransitionNotAllowed("the resource has a newer revision; approval never carries over")
        before = _snapshot(r)
        ApprovalRequest.objects.filter(pk=r.pk).update(
            status=status, decided_by_id=caller.user_id, decision_note=note, closed_at=db_now()
        )
        r.refresh_from_db()
        _audit(
            uow,
            "approve" if status == ApprovalStatus.APPROVED else "reject",
            r,
            before=before,
            reason=note,
            scope={"via_self_assigned_role": via_self},
        )
        handler = _handler(r.resource_type)
        if handler is not None:
            (handler.on_approved if status == ApprovalStatus.APPROVED else handler.on_closed)(
                uow, r, caller.user_id
            )
    return Outcome(r, via_self)


def approve(
    caller: Caller,
    request_id: uuid.UUID,
    *,
    note: str = "",
    expected_revision: int | None = None,
    request_ctx_id: uuid.UUID | None = None,
) -> Outcome:
    return _decide(
        caller,
        request_id,
        ApprovalStatus.APPROVED,
        note=note.strip()[:500],
        expected_revision=expected_revision,
        request_ctx_id=request_ctx_id,
    )


def reject(
    caller: Caller,
    request_id: uuid.UUID,
    *,
    note: str,
    expected_revision: int | None = None,
    request_ctx_id: uuid.UUID | None = None,
) -> Outcome:
    text = note.strip()
    if len(text) < 3:
        raise ValidationFailed("a note is required to reject", errors=[FieldError("note", "REQUIRED")])
    return _decide(
        caller,
        request_id,
        ApprovalStatus.REJECTED,
        note=text[:500],
        expected_revision=expected_revision,
        request_ctx_id=request_ctx_id,
    )


def withdraw(
    caller: Caller, request_id: uuid.UUID, *, request_ctx_id: uuid.UUID | None = None
) -> ApprovalRequest:
    """``withdrawRequest``: only the requester (``platform.workflow.approval.request`` ○ own requests)."""
    require_permission(caller, "platform.workflow.approval.request")
    with unit_of_work(caller.context(request_ctx_id)) as uow:
        r = _lock(request_id)
        if r.requested_by_id != caller.user_id:
            raise NotFound()
        close(uow, r, ApprovalStatus.WITHDRAWN, by=caller.user_id)
    return r


def close(
    uow: UnitOfWork, r: ApprovalRequest, status: ApprovalStatus, *, by: uuid.UUID | None, note: str = ""
) -> None:
    """System closures (WITHDRAWN / SUPERSEDED / EXPIRED); caller holds the row lock."""
    if status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
        raise AccessDenied("decisions go through approve/reject")
    APPROVAL_MACHINE.assert_transition(r.status, status)
    before = _snapshot(r)
    ApprovalRequest.objects.filter(pk=r.pk).update(
        status=status, closed_at=db_now(), decision_note=note[:500]
    )
    r.refresh_from_db()
    verb = {
        ApprovalStatus.WITHDRAWN: "withdraw",
        ApprovalStatus.SUPERSEDED: "supersede",
        ApprovalStatus.EXPIRED: "expire",
    }[status]
    _audit(uow, verb, r, before=before, reason=note)
    handler = _handler(r.resource_type)
    if handler is not None:
        handler.on_closed(uow, r, by)


def close_pending_for(
    uow: UnitOfWork, resource_type: str, resource_id: str, status: ApprovalStatus, *, note: str = ""
) -> int:
    n = 0
    for r in ApprovalRequest.objects.select_for_update().filter(
        resource_type=resource_type, resource_id=resource_id, status=ApprovalStatus.PENDING
    ):
        close(uow, r, status, by=None, note=note)
        n += 1
    return n


def expire_due(*, limit: int = 500, request_id: uuid.UUID | None = None) -> int:
    """Housekeeping job function (DEC-032: 30 days): PENDING requests past ``expires_at`` -> EXPIRED."""
    now = db_now()
    ids = list(
        ApprovalRequest.objects.filter(status=ApprovalStatus.PENDING, expires_at__lte=now)
        .order_by("expires_at")
        .values_list("pk", flat=True)[:limit]
    )
    n = 0
    for rid in ids:
        with unit_of_work_or_nothing(RequestContext(Actor.system(), request_id=request_id)) as uow:
            r = (
                ApprovalRequest.objects.select_for_update(skip_locked=True)
                .filter(pk=rid, status=ApprovalStatus.PENDING)
                .first()
            )
            if r is None:
                raise NothingToDo()
            close(
                uow,
                r,
                ApprovalStatus.EXPIRED,
                by=None,
                note="expired (DEC-032: approval_request_expiry_days)",
            )
            n += 1
    return n
