"""User administration (STATE_TRANSITIONS 4.1; DEC-003 / DEC-049 / DEC-051 / DEC-052 / DEC-054).

* Users exist only inside the system: created by a holder of ``platform.identity.user.create`` (owner_admin)
  or, for the very first owner, by the console bootstrap command (no AD/LDAP/SSO, no self-registration).
* The initial password is set by the admin, is one-time (72 h) and must be changed at first login (DEC-051).
* OPERATOR accounts are personal and always INTERNAL_ONLY (DEC-052).
* Disable revokes every session in the same transaction; the last ACTIVE holder of
  ``platform.identity.user.disable`` cannot be disabled (TECH lock-out protection).
* Unlock: ``platform.identity.user.unlock`` (owner_admin, it_ops; DEC-049 item 2) - never changes a password.
* Admin password reset: new one-time password, all sessions revoked; never on oneself (own password: change).
* Owner bootstrap / console recovery (DEC-003 / DEC-054 C): :func:`bootstrap_owner`, :func:`recover_owner`,
  used only by ``manage.py bootstrap_owner`` on the server console; audited as SYSTEM.
"""

from __future__ import annotations

import uuid
from typing import Final

from django.db.models import Q

from platform_core.authz.policy import OWNER_ROLE, Caller, require_permission, require_step_up
from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.engine.errors import (
    AccessDenied,
    FieldError,
    NotFound,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.engine.uow import UnitOfWork, unit_of_work
from platform_core.schema_common import USERNAME_PATTERN

from . import sessions
from .auth import USER_MACHINE, _set_status, _status_after_unlock
from .mfa import reset_factors
from .models import (
    AccountKind,
    AssignmentStatus,
    GrantedVia,
    NetworkPolicy,
    Role,
    RoleAssignment,
    ScopeKind,
    SessionEndReason,
    User,
    UserStatus,
)
from .passwords import validate_new_password, write_credential

DISABLE_ACTION: Final = "platform.identity.user.disable"


def _reason(text: str) -> str:
    value = text.strip()
    if len(value) < 3:
        raise ValidationFailed("a reason is required", errors=[FieldError("reason", "REQUIRED")])
    return value[:500]


def _validate_identity(username: str, display_name: str) -> tuple[str, str]:
    import re

    name = username.strip().lower()
    if not re.fullmatch(USERNAME_PATTERN, name):
        raise ValidationFailed(errors=[FieldError("username", "INVALID")])
    shown = display_name.strip()
    if not shown or len(shown) > 200:
        raise ValidationFailed(errors=[FieldError("display_name", "INVALID")])
    if User.objects.filter(username=name).exists():
        raise ValidationFailed(errors=[FieldError("username", "ALREADY_EXISTS")])
    return name, shown


def _audit_user(
    uow: UnitOfWork,
    action: str,
    event: str,
    user: User,
    *,
    reason: str = "",
    before: dict[str, object] | None = None,
) -> None:
    uow.audit(
        action=action,
        resource_type="platform.user",
        resource_id=str(user.pk),
        resource_version=user.row_version,
        before=before,
        after={"username": user.username, "status": user.status, "account_kind": user.account_kind},
        reason=reason,
    )
    uow.emit(
        event_type=event,
        aggregate_type="platform.user",
        aggregate_id=str(user.pk),
        aggregate_version=user.row_version,
        payload={"id": str(user.pk), "status": user.status},
    )


def create_user(
    caller: Caller,
    *,
    username: str,
    display_name: str,
    account_kind: str,
    initial_password: str,
    network_policy: str | None = None,
    reason: str,
    request_id: uuid.UUID | None = None,
    provenance: str = "SYS",
) -> User:
    require_permission(caller, "platform.identity.user.create")
    require_step_up(caller, "platform.identity.user.create")
    text = _reason(reason)
    if account_kind not in AccountKind.values:
        raise ValidationFailed(errors=[FieldError("account_kind", "INVALID")])
    policy = network_policy or NetworkPolicy.ANY_WITH_MFA_OUTSIDE
    if account_kind == AccountKind.OPERATOR:
        policy = NetworkPolicy.INTERNAL_ONLY  # DEC-052: operators never outside
    if policy not in NetworkPolicy.values:
        raise ValidationFailed(errors=[FieldError("network_policy", "INVALID")])
    name, shown = _validate_identity(username, display_name)
    validate_new_password(None, initial_password)
    with unit_of_work(caller.context(request_id)) as uow:
        now = db_now()
        user = User.objects.create(
            username=name,
            display_name=shown,
            account_kind=account_kind,
            network_policy=policy,
            created_by_id=caller.user_id,
            updated_by_id=caller.user_id,
            status_changed_at=now,
            provenance=provenance,
        )
        write_credential(user, initial_password, now=now, one_time=True, set_by_id=caller.user_id)
        _audit_user(uow, "platform.identity.user.create", "platform.identity.user.created", user, reason=text)
    return user


def _lock_target(user_id: uuid.UUID) -> User:
    target = User.objects.select_for_update().filter(pk=user_id).first()
    if target is None:
        raise NotFound()
    return target


def _last_disabler(user: User) -> bool:
    """True if ``user`` is the only ACTIVE user with a live grant of ``platform.identity.user.disable``."""
    now = db_now()
    holders = (
        RoleAssignment.objects.filter(
            status=AssignmentStatus.ACTIVE,
            role__status="ACTIVE",
            role__grants__permission_id=DISABLE_ACTION,
            user__status=UserStatus.ACTIVE,
            valid_from__lte=now,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=now))
        .values_list("user_id", flat=True)
        .distinct()
    )
    ids = set(holders)
    return ids == {user.pk}


def disable_user(
    caller: Caller, user_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> User:
    require_permission(caller, DISABLE_ACTION)
    require_step_up(caller, DISABLE_ACTION)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        target = _lock_target(user_id)
        if _last_disabler(target):
            raise StateTransitionNotAllowed("the last active administrator cannot be disabled")
        _set_status(uow, target, UserStatus.DISABLED, now=db_now(), locked_until=None, reason=text)
        sessions.revoke_user_sessions(
            uow, target.pk, SessionEndReason.USER_DISABLED, revoked_by_id=caller.user_id, note=text
        )
    return target


def enable_user(
    caller: Caller, user_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> User:
    require_permission(caller, DISABLE_ACTION)
    require_step_up(caller, DISABLE_ACTION)
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        target = _lock_target(user_id)
        USER_MACHINE.assert_transition(target.status, UserStatus.ACTIVE)
        _set_status(uow, target, UserStatus.ACTIVE, now=db_now(), locked_until=None, reason=text)
    return target


def unlock_user(
    caller: Caller, user_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> User:
    """LOCKED -> ACTIVE (or CREATED). ``it_ops`` may do this (DEC-049 item 2); no password is changed."""
    require_permission(caller, "platform.identity.user.unlock")
    require_step_up(caller, "platform.identity.user.unlock")
    text = _reason(reason)
    with unit_of_work(caller.context(request_id)) as uow:
        target = _lock_target(user_id)
        if target.status != UserStatus.LOCKED:
            raise StateTransitionNotAllowed("the user is not locked")
        _set_status(uow, target, _status_after_unlock(target), now=db_now(), locked_until=None, reason=text)
    return target


def reset_password(
    caller: Caller,
    user_id: uuid.UUID,
    *,
    new_one_time_password: str,
    reason: str,
    request_id: uuid.UUID | None = None,
) -> User:
    require_permission(caller, "platform.identity.user.reset_password")
    require_step_up(caller, "platform.identity.user.reset_password")
    text = _reason(reason)
    if user_id == caller.user_id:
        raise AccessDenied("change your own password with changeMyPassword")
    with unit_of_work(caller.context(request_id)) as uow:
        target = _lock_target(user_id)
        validate_new_password(target, new_one_time_password)
        write_credential(target, new_one_time_password, now=db_now(), one_time=True, set_by_id=caller.user_id)
        sessions.revoke_user_sessions(
            uow, target.pk, SessionEndReason.PASSWORD_CHANGED, revoked_by_id=caller.user_id, note=text
        )
        target.refresh_from_db()
        _audit_user(
            uow,
            "platform.identity.user.reset_password",
            "platform.identity.user.password_reset",
            target,
            reason=text,
        )
    return target


# ------------------------------------------------------------------------------- console (DEC-003/054)
def _system_ctx() -> RequestContext:
    return RequestContext(Actor.system(), request_id=uuid.uuid4())


def owner_exists() -> bool:
    now = db_now()
    return (
        RoleAssignment.objects.filter(
            role__code=OWNER_ROLE, status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.PENDING_APPROVAL]
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=now))
        .exists()
    )


def bootstrap_owner(*, username: str, display_name: str, password: str, reason: str) -> User:
    """First owner from the server console: user (CREATED, one-time password) + ``owner_admin`` only
    (DEC-049 item 4) via ``CONSOLE_BOOTSTRAP``. Refused when an owner exists (use :func:`recover_owner`)."""
    text = _reason(reason)
    name, shown = _validate_identity(username, display_name)
    validate_new_password(None, password)
    with unit_of_work(_system_ctx()) as uow:
        role = Role.objects.select_for_update().get(code=OWNER_ROLE)
        if owner_exists():
            raise StateTransitionNotAllowed("an owner already exists; use the recovery mode")
        now = db_now()
        user = User.objects.create(
            username=name,
            display_name=shown,
            account_kind=AccountKind.PERSON,
            network_policy=NetworkPolicy.ANY_WITH_MFA_OUTSIDE,
            status_changed_at=now,
        )
        write_credential(user, password, now=now, one_time=True, set_by_id=None)
        ra = RoleAssignment.objects.create(
            user=user,
            role=role,
            scope_kind=ScopeKind.GLOBAL,
            status=AssignmentStatus.ACTIVE,
            granted_via=GrantedVia.CONSOLE_BOOTSTRAP,
            granted_by=None,
            reason=text,
        )
        _audit_user(
            uow,
            "platform.identity.owner.bootstrap",
            "platform.identity.owner.bootstrapped",
            user,
            reason=text,
        )
        uow.audit(
            action="platform.identity.assignment.grant",
            resource_type="platform.role_assignment",
            resource_id=str(ra.pk),
            after={"role": OWNER_ROLE, "granted_via": GrantedVia.CONSOLE_BOOTSTRAP, "status": ra.status},
            reason=text,
        )
    return user


def recover_owner(*, username: str, password: str, reason: str) -> User:
    """DEC-054 C: console recovery of the owner's password and MFA (one-time password, MFA factors revoked,
    sessions revoked, lock lifted). Only for a user holding ``owner_admin``."""
    text = _reason(reason)
    with unit_of_work(_system_ctx()) as uow:
        target = User.objects.select_for_update().filter(username=username.strip().lower()).first()
        if (
            target is None
            or not RoleAssignment.objects.filter(
                user=target, role__code=OWNER_ROLE, status=AssignmentStatus.ACTIVE
            ).exists()
        ):
            raise NotFound()
        validate_new_password(target, password)
        now = db_now()
        write_credential(target, password, now=now, one_time=True, set_by_id=None)
        reset_factors(uow, target, by=None, reason=text)
        if target.status == UserStatus.LOCKED:
            _set_status(uow, target, _status_after_unlock(target), now=now, locked_until=None, reason=text)
        elif target.status == UserStatus.DISABLED:
            _set_status(uow, target, UserStatus.ACTIVE, now=now, locked_until=None, reason=text)
        target.refresh_from_db()
        _audit_user(
            uow, "platform.identity.owner.recover", "platform.identity.owner.recovered", target, reason=text
        )
    return target
