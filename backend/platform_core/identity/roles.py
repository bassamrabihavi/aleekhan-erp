"""Roles and role assignments (STATE_TRANSITIONS 4.8; DEC-003 / DEC-032 / DEC-049 APPROVED).

Role lifecycle DRAFT -> ACTIVE -> RETIRED (DB-enforced since REV-0105); grants change only while DRAFT; a
TECHNICAL role never holds a business-approval permission (DB). Activation needs an approved permission
matrix version: matrix v1.0 (DEC-049) is exactly the seeded catalogue, so a role created at runtime has no
approved permission set and its activation is refused with ``RULE_NOT_APPROVED`` (DEC-049) until a new matrix
version is approved and shipped as a reviewed migration (PERMISSION_MATRIX section 6).

Assignments (``platform.identity.assignment.grant``, MFA step-up, reason):

* role ACTIVE; scope GLOBAL / ORG_UNIT / ORG_UNIT_SUBTREE; optional end; no overlapping live duplicate (DB).
* Self-assignment only with ``allow_self=True`` - always flagged (``self_assignment``, generated column) and
  audited (DEC-003).
* A role holding a business-approval permission -> ``PENDING_APPROVAL`` + an approval request
  (``platform.identity.assignment.grant`` / ``role_assignment``), decided by a third person holding
  ``platform.workflow.approval.decide`` in scope (never the grantor, never the grantee; DB guard
  ``ck_role_assignment_second_approval``). Approved -> ACTIVE; rejected/withdrawn/expired -> REVOKED.
* Revoke (reason): ACTIVE / PENDING_APPROVAL -> REVOKED (a pending request is withdrawn). Expiry sweep:
  ACTIVE past ``valid_to`` -> EXPIRED.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from django.db.models import Q

from platform_core.authz.policy import Caller, require_permission, require_step_up
from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.engine.dbrules import db_rules
from platform_core.engine.errors import (
    FieldError,
    NotFound,
    RuleNotApproved,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import NothingToDo, UnitOfWork, unit_of_work, unit_of_work_or_nothing
from platform_core.workflow import approvals
from platform_core.workflow.models import ApprovalRequest, ApprovalStatus

from .models import (
    AssignmentStatus,
    GrantedVia,
    Permission,
    Role,
    RoleAssignment,
    RoleKind,
    RolePermission,
    RoleStatus,
    ScopeKind,
    User,
)

GRANT: Final = "platform.identity.assignment.grant"
MANAGE: Final = "platform.identity.role.manage"
RESOURCE: Final = "role_assignment"

ROLE_MACHINE: Final = StateMachine(
    name="role",
    states=frozenset(RoleStatus.values),
    transitions={
        RoleStatus.DRAFT: frozenset({RoleStatus.ACTIVE}),
        RoleStatus.ACTIVE: frozenset({RoleStatus.RETIRED}),
        RoleStatus.RETIRED: frozenset(),
    },
)
ASSIGNMENT_MACHINE: Final = StateMachine(
    name="role_assignment",
    states=frozenset(AssignmentStatus.values),
    transitions={
        AssignmentStatus.PENDING_APPROVAL: frozenset({AssignmentStatus.ACTIVE, AssignmentStatus.REVOKED}),
        AssignmentStatus.ACTIVE: frozenset({AssignmentStatus.EXPIRED, AssignmentStatus.REVOKED}),
        AssignmentStatus.EXPIRED: frozenset(),
        AssignmentStatus.REVOKED: frozenset(),
    },
)


def _reason(text: str) -> str:
    value = text.strip()
    if len(value) < 3:
        raise ValidationFailed("a reason is required", errors=[FieldError("reason", "REQUIRED")])
    return value[:500]


def approved_matrix_grants() -> dict[str, frozenset[tuple[str, str, str]]]:
    """Role code -> set of (action, grant_mode, max_sensitivity) of the approved matrix v1.0 (frozen seed)."""
    from importlib import import_module

    seed = import_module("platform_core.migrations.0010_seed_phase01_catalogue")
    out: dict[str, set[tuple[str, str, str]]] = {code: set() for code in seed.ROLES}
    for action, cells in seed.GRANTS.items():
        for code, cell in cells.items():
            mode, max_sens = cell if isinstance(cell, tuple) else (cell, "")
            out[code].add((action, mode, max_sens))
    return {k: frozenset(v) for k, v in out.items()}


def role_holds_business_approval(role_id: uuid.UUID) -> bool:
    return RolePermission.objects.filter(role_id=role_id, permission__business_approval=True).exists()


def _audit_role(
    uow: UnitOfWork, verb: str, role: Role, *, before: dict[str, object] | None, reason: str = ""
) -> None:
    uow.audit(
        action=f"platform.identity.role.{verb}",
        resource_type="platform.role",
        resource_id=str(role.pk),
        resource_version=role.row_version,
        before=before,
        after={"code": role.code, "kind": role.kind, "status": role.status},
        reason=reason,
    )
    uow.emit(
        event_type="platform.identity.role.changed",
        aggregate_type="platform.role",
        aggregate_id=str(role.pk),
        aggregate_version=role.row_version,
        payload={"id": str(role.pk), "status": role.status},
    )


# --------------------------------------------------------------------------------------------- roles
def create_role(
    caller: Caller, *, code: str, name_fa: str, kind: str, reason: str, request_id: uuid.UUID | None = None
) -> Role:
    require_permission(caller, MANAGE)
    require_step_up(caller, MANAGE)
    text = _reason(reason)
    if kind not in RoleKind.values:
        raise ValidationFailed(errors=[FieldError("kind", "INVALID")])
    with unit_of_work(caller.context(request_id)) as uow:
        if Role.objects.filter(code=code).exists():
            raise ValidationFailed(errors=[FieldError("code", "ALREADY_EXISTS")])
        role = Role.objects.create(
            code=code,
            name_fa=name_fa,
            kind=kind,
            status=RoleStatus.DRAFT,
            created_by_id=caller.user_id,
            updated_by_id=caller.user_id,
        )
        role.refresh_from_db()
        _audit_role(uow, "create", role, before=None, reason=text)
    return role


def grant_permission(
    caller: Caller,
    role_id: uuid.UUID,
    *,
    action: str,
    mode: str,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> RolePermission:
    """Only while the role is DRAFT (DB); TECHNICAL + business-approval refused (DB, DEC-003)."""
    require_permission(caller, MANAGE)
    require_step_up(caller, MANAGE)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        role = Role.objects.select_for_update().filter(pk=role_id).first()
        if role is None or not Permission.objects.filter(action=action).exists():
            raise NotFound()
        if role.status != RoleStatus.DRAFT:
            raise StateTransitionNotAllowed("permissions change only while the role is DRAFT")
        if role.kind == RoleKind.TECHNICAL and Permission.objects.get(action=action).business_approval:
            raise StateTransitionNotAllowed(
                "a TECHNICAL role never holds a business-approval permission (DEC-003)"
            )
        with db_rules():
            rp = RolePermission.objects.create(role=role, permission_id=action, grant_mode=mode)
        _audit_role(uow, "grant_permission", role, before=None, reason=text)
    return rp


def activate_role(
    caller: Caller, role_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> Role:
    require_permission(caller, MANAGE)
    require_step_up(caller, MANAGE)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        role = Role.objects.select_for_update().filter(pk=role_id).first()
        if role is None:
            raise NotFound()
        ROLE_MACHINE.assert_transition(role.status, RoleStatus.ACTIVE)
        grants = frozenset(
            RolePermission.objects.filter(role=role).values_list(
                "permission_id", "grant_mode", "max_sensitivity"
            )
        )
        if approved_matrix_grants().get(role.code) != grants:
            raise RuleNotApproved(
                "DEC-049", "the permission set of this role is not in an approved matrix version"
            )
        before: dict[str, object] = {"status": role.status}
        Role.objects.filter(pk=role.pk).update(
            status=RoleStatus.ACTIVE, matrix_version="1.0", updated_by_id=caller.user_id
        )
        role.refresh_from_db()
        _audit_role(uow, "activate", role, before=before, reason=text)
    return role


def retire_role(
    caller: Caller, role_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> Role:
    require_permission(caller, MANAGE)
    require_step_up(caller, MANAGE)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        role = Role.objects.select_for_update().filter(pk=role_id).first()
        if role is None:
            raise NotFound()
        ROLE_MACHINE.assert_transition(role.status, RoleStatus.RETIRED)
        if RoleAssignment.objects.filter(
            role=role, status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.PENDING_APPROVAL]
        ).exists():
            raise StateTransitionNotAllowed("the role still has live assignments")
        before: dict[str, object] = {"status": role.status}
        with db_rules():
            Role.objects.filter(pk=role.pk).update(status=RoleStatus.RETIRED, updated_by_id=caller.user_id)
        role.refresh_from_db()
        _audit_role(uow, "retire", role, before=before, reason=text)
    return role


# --------------------------------------------------------------------------------------- assignments
def _assignment_view(ra: RoleAssignment) -> dict[str, object]:
    return {
        "user_id": str(ra.user_id),
        "role_id": str(ra.role_id),
        "scope_kind": ra.scope_kind,
        "scope_unit_id": str(ra.scope_unit_id) if ra.scope_unit_id else None,
        "status": ra.status,
        "self_assignment": bool(ra.self_assignment),
        "requires_second_approval": ra.requires_second_approval,
    }


def _audit_assignment(
    uow: UnitOfWork, verb: str, ra: RoleAssignment, *, before: dict[str, object] | None, reason: str
) -> None:
    uow.audit(
        action=f"platform.identity.assignment.{verb}",
        resource_type="platform.role_assignment",
        resource_id=str(ra.pk),
        resource_version=ra.row_version,
        before=before,
        after=_assignment_view(ra),
        reason=reason,
        scope={"self_assignment": bool(ra.self_assignment)},
    )
    uow.emit(
        event_type="platform.identity.assignment.changed",
        aggregate_type="platform.role_assignment",
        aggregate_id=str(ra.pk),
        aggregate_version=ra.row_version,
        payload={"id": str(ra.pk), "status": ra.status},
    )


def grant_role(
    caller: Caller,
    *,
    user_id: uuid.UUID,
    role_code: str,
    scope_kind: str = ScopeKind.GLOBAL,
    scope_unit_id: uuid.UUID | None = None,
    valid_to: datetime | None = None,
    reason: str,
    allow_self: bool = False,
    request_id: uuid.UUID | None = None,
) -> RoleAssignment:
    from platform_core.org.models import OrgUnit

    require_permission(caller, GRANT)
    require_step_up(caller, GRANT)
    text = _reason(reason)
    if user_id == caller.user_id and not allow_self:
        raise ValidationFailed(
            "self-assignment must be explicit (DEC-003)",
            errors=[FieldError("user_id", "SELF_ASSIGNMENT_NOT_CONFIRMED")],
        )
    if scope_kind not in ScopeKind.values or (scope_kind == ScopeKind.GLOBAL) != (scope_unit_id is None):
        raise ValidationFailed(errors=[FieldError("scope", "INVALID")])
    with unit_of_work(caller.context(request_id)) as uow:
        role = Role.objects.filter(code=role_code).first()
        if role is None or not User.objects.filter(pk=user_id).exists():
            raise NotFound()
        if scope_unit_id is not None and not OrgUnit.objects.filter(pk=scope_unit_id).exists():
            raise NotFound()
        if role.status != RoleStatus.ACTIVE:
            raise StateTransitionNotAllowed("the role is not ACTIVE")
        needs_second = role_holds_business_approval(role.pk)
        with db_rules():
            ra = RoleAssignment.objects.create(
                user_id=user_id,
                role=role,
                scope_kind=scope_kind,
                scope_unit_id=scope_unit_id,
                valid_to=valid_to,
                status=AssignmentStatus.PENDING_APPROVAL if needs_second else AssignmentStatus.ACTIVE,
                granted_via=GrantedVia.ADMIN,
                granted_by_id=caller.user_id,
                updated_by_id=caller.user_id,
                reason=text,
            )
        ra.refresh_from_db()
        if needs_second:
            req = approvals.raise_request(
                uow,
                action=GRANT,
                resource_type=RESOURCE,
                resource_id=str(ra.pk),
                resource_revision=ra.row_version,
                requested_by=caller.user_id,
                route_scope_unit_id=scope_unit_id,
            )
            RoleAssignment.objects.filter(pk=ra.pk).update(approval_request=req)
            ra.refresh_from_db()
        _audit_assignment(uow, "grant", ra, before=None, reason=text)
    return ra


def revoke_assignment(
    caller: Caller, assignment_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> RoleAssignment:
    require_permission(caller, GRANT)
    require_step_up(caller, GRANT)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        ra = RoleAssignment.objects.select_for_update().filter(pk=assignment_id).first()
        if ra is None:
            raise NotFound()
        ASSIGNMENT_MACHINE.assert_transition(ra.status, AssignmentStatus.REVOKED)
        was_pending = ra.status == AssignmentStatus.PENDING_APPROVAL
        _revoke(uow, ra, by=caller.user_id, reason=text)
        if was_pending:
            approvals.close_pending_for(
                uow, RESOURCE, str(ra.pk), ApprovalStatus.WITHDRAWN, note="assignment revoked"
            )
    return ra


def _revoke(uow: UnitOfWork, ra: RoleAssignment, *, by: uuid.UUID | None, reason: str) -> None:
    before = _assignment_view(ra)
    RoleAssignment.objects.filter(pk=ra.pk).update(
        status=AssignmentStatus.REVOKED,
        revoked_at=db_now(),
        revoked_by_id=by,
        revoke_reason=reason[:500],
        updated_by_id=by,
    )
    ra.refresh_from_db()
    _audit_assignment(uow, "revoke", ra, before=before, reason=reason)


# approval handler: the decision on the request acts on the assignment in the same transaction
def _on_approved(uow: UnitOfWork, req: ApprovalRequest, decided_by: uuid.UUID | None) -> None:
    ra = RoleAssignment.objects.select_for_update().get(pk=uuid.UUID(req.resource_id))
    ASSIGNMENT_MACHINE.assert_transition(ra.status, AssignmentStatus.ACTIVE)
    before = _assignment_view(ra)
    RoleAssignment.objects.filter(pk=ra.pk).update(
        status=AssignmentStatus.ACTIVE, approval_request=req, updated_by_id=decided_by
    )
    ra.refresh_from_db()
    _audit_assignment(uow, "activate", ra, before=before, reason=f"approved by request {req.pk}")


def _on_closed(uow: UnitOfWork, req: ApprovalRequest, by: uuid.UUID | None) -> None:
    ra = RoleAssignment.objects.select_for_update().filter(pk=uuid.UUID(req.resource_id)).first()
    if ra is not None and ra.status == AssignmentStatus.PENDING_APPROVAL:
        _revoke(uow, ra, by=None, reason=f"approval request {req.status.lower()}")


def _makers(req: ApprovalRequest) -> set[uuid.UUID]:
    ra = RoleAssignment.objects.filter(pk=uuid.UUID(req.resource_id)).first()
    out: set[uuid.UUID] = set()
    if ra is not None:
        out.add(ra.user_id)  # the grantee never confirms his own role (DEC-032)
        if ra.granted_by_id is not None:
            out.add(ra.granted_by_id)
    return out


approvals.register_resource_handler(RESOURCE, approvals.ResourceHandler(_on_approved, _on_closed, _makers))


def expire_due_assignments(*, limit: int = 500, request_id: uuid.UUID | None = None) -> int:
    """Housekeeping job function: ACTIVE assignments whose ``valid_to`` has passed -> EXPIRED."""
    now = db_now()
    ids = list(
        RoleAssignment.objects.filter(
            status=AssignmentStatus.ACTIVE, valid_to__isnull=False, valid_to__lte=now
        ).values_list("pk", flat=True)[:limit]
    )
    n = 0
    for aid in ids:
        with unit_of_work_or_nothing(RequestContext(Actor.system(), request_id=request_id)) as uow:
            ra = (
                RoleAssignment.objects.select_for_update(skip_locked=True)
                .filter(Q(pk=aid), status=AssignmentStatus.ACTIVE, valid_to__lte=now)
                .first()
            )
            if ra is None:
                raise NothingToDo()
            before = _assignment_view(ra)
            RoleAssignment.objects.filter(pk=ra.pk).update(status=AssignmentStatus.EXPIRED)
            ra.refresh_from_db()
            _audit_assignment(uow, "expire", ra, before=before, reason="valid_to reached")
            n += 1
    return n


def update_role(
    caller: Caller,
    role_id: uuid.UUID,
    *,
    reason: str,
    name_fa: str | None = None,
    permissions: list[str] | None = None,
    request_id: uuid.UUID | None = None,
) -> Role:
    """``updateRole`` (01.4): name and permission set of a DRAFT role only (grants never change after
    activation, DEC-049; the DB refuses it too). New grants use mode SCOPE; a TECHNICAL role never receives a
    business-approval permission (DEC-003). Activation still needs an approved matrix version."""
    require_permission(caller, MANAGE)
    require_step_up(caller, MANAGE)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        role = Role.objects.select_for_update().filter(pk=role_id).first()
        if role is None:
            raise NotFound()
        if role.status != RoleStatus.DRAFT:
            raise StateTransitionNotAllowed("a role changes only while it is DRAFT")
        before: dict[str, object] = {
            "permissions": sorted(
                RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)
            )
        }
        if name_fa is not None:
            if not name_fa.strip():
                raise ValidationFailed(errors=[FieldError("name_fa", "REQUIRED")])
            Role.objects.filter(pk=role.pk).update(
                name_fa=name_fa.strip()[:200], updated_by_id=caller.user_id
            )
        if permissions is not None:
            wanted = set(permissions)
            known = dict(
                Permission.objects.filter(action__in=wanted).values_list("action", "business_approval")
            )
            unknown = sorted(wanted - set(known))
            if unknown:
                raise ValidationFailed(errors=[FieldError("permissions", "UNKNOWN_PERMISSION")])
            if role.kind == RoleKind.TECHNICAL and any(known.values()):
                raise StateTransitionNotAllowed(
                    "a TECHNICAL role never holds a business-approval permission (DEC-003)"
                )
            current = set(RolePermission.objects.filter(role=role).values_list("permission_id", flat=True))
            with db_rules():
                RolePermission.objects.filter(role=role, permission_id__in=current - wanted).delete()
                for action in sorted(wanted - current):
                    RolePermission.objects.create(role=role, permission_id=action, grant_mode="SCOPE")
            Role.objects.filter(pk=role.pk).update(updated_by_id=caller.user_id)
        role.refresh_from_db()
        _audit_role(uow, "update", role, before=before, reason=text)
    return role
