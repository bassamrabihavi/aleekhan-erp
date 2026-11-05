"""Server-side sessions (STATE_TRANSITIONS 4.2; DEC-051 + employer answers Q-0101 / Q-0102).

* The cookie value is a random 256-bit token; the database stores only its SHA-256 (``session_key_hash``).
  ``Session.id`` is the public handle. The token is rotated after MFA (new token, same handle).
* Timeouts from parameters: users idle ``session_user_idle_minutes`` (120) / absolute
  ``session_user_absolute_hours`` (12); operators idle ``session_operator_idle_minutes`` (480) / absolute
  ``session_operator_absolute_hours`` (12) and internal network only (``session_operator_internal_only``).
  MFA_PENDING sessions live at most :data:`MFA_PENDING_TTL` (TECH 5 min).
* Concurrent sessions: at most ``session_max_concurrent`` (3) live sessions per user; on the next login the
  OLDEST live session is ended (``session_limit_exceeded_action = END_OLDEST_SESSION``, state REVOKED, reason
  CONCURRENT_LIMIT, audited). Race-safe: the login holds the user row lock (``SELECT ... FOR UPDATE``).
* Every state change is audited (unit of work). Touching ``last_seen_at`` / ``idle_expires_at`` on use is
  technical bookkeeping without an audit row.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from platform_core.authz.policy import Caller
from platform_core.engine.context import RequestContext, db_now
from platform_core.engine.errors import (
    AccessDenied,
    AuthenticationRequired,
    EngineContractError,
    MfaRequired,
    NetworkPolicyDenied,
    NotFound,
    PasswordChangeRequired,
)
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import NothingToDo, UnitOfWork, unit_of_work, unit_of_work_or_nothing
from platform_core.params.values import (
    effective,
    effective_bool,
    effective_hours,
    effective_int,
    effective_minutes,
)
from platform_core.schema_common import NetworkZone

from . import network
from .models import (
    AccountKind,
    Credential,
    Session,
    SessionEndReason,
    SessionState,
    User,
    UserStatus,
)
from .passwords import must_change

MFA_PENDING_TTL: Final = timedelta(minutes=5)  # TECH (STATE_TRANSITIONS 4.2)
TOKEN_BYTES: Final = 32

SESSION_MACHINE: Final = StateMachine(
    name="session",
    states=frozenset(SessionState.values),
    transitions={
        SessionState.MFA_PENDING: frozenset(
            {SessionState.ACTIVE, SessionState.EXPIRED, SessionState.LOGGED_OUT, SessionState.REVOKED}
        ),
        SessionState.ACTIVE: frozenset({SessionState.EXPIRED, SessionState.LOGGED_OUT, SessionState.REVOKED}),
        SessionState.EXPIRED: frozenset(),
        SessionState.REVOKED: frozenset(),
        SessionState.LOGGED_OUT: frozenset(),
    },
)
LIVE: Final = (SessionState.MFA_PENDING, SessionState.ACTIVE)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


@dataclass(frozen=True)
class Timeouts:
    idle: timedelta
    absolute: timedelta

    @classmethod
    def for_user(cls, user: User) -> Timeouts:
        if user.account_kind == AccountKind.OPERATOR:
            return cls(
                effective_minutes("session_operator_idle_minutes"),
                effective_hours("session_operator_absolute_hours"),
            )
        return cls(
            effective_minutes("session_user_idle_minutes"), effective_hours("session_user_absolute_hours")
        )


def operator_zone_refused(user: User, zone: str) -> bool:
    """DEC-042 / DEC-052: INTERNAL_ONLY accounts (all operators) never work from outside."""
    if user.network_policy == "INTERNAL_ONLY" and zone != NetworkZone.INTERNAL:
        return True
    return (
        user.account_kind == AccountKind.OPERATOR
        and effective_bool("session_operator_internal_only")
        and zone != NetworkZone.INTERNAL
    )


def _snapshot(s: Session) -> dict[str, object]:
    return {"state": s.state, "end_reason": s.end_reason, "network_zone": s.network_zone}


_EVENTS: Final = {
    "platform.identity.session.create": "platform.identity.session.created",
    "platform.identity.session.activate": "platform.identity.session.activated",
    "platform.identity.session.expire": "platform.identity.session.expired",
    "platform.identity.session.logout": "platform.identity.session.logged_out",
    "platform.identity.session.revoke": "platform.identity.session.revoked",
}


def _audit(
    uow: UnitOfWork, action: str, s: Session, *, before: dict[str, object] | None, reason: str = ""
) -> None:
    uow.audit(
        action=action,
        resource_type="platform.session",
        resource_id=str(s.pk),
        resource_version=s.row_version,
        before=before,
        after=_snapshot(s),
        reason=reason,
        scope={"user_id": str(s.user_id)},
    )
    uow.emit(
        event_type=_EVENTS[action],
        aggregate_type="platform.session",
        aggregate_id=str(s.pk),
        aggregate_version=s.row_version,
        payload={"id": str(s.pk), "user_id": str(s.user_id), "state": s.state},
    )


# --------------------------------------------------------------------------------------- transitions
def end_session(
    uow: UnitOfWork,
    session: Session,
    state: SessionState,
    reason: SessionEndReason,
    *,
    revoked_by_id: uuid.UUID | None = None,
    note: str = "",
) -> Session:
    """Move a live session to a terminal state (caller holds the row lock inside ``uow``)."""
    SESSION_MACHINE.assert_transition(session.state, state)
    before = _snapshot(session)
    now = db_now()
    Session.objects.filter(pk=session.pk).update(
        state=state, ended_at=now, end_reason=reason, revoked_by_id=revoked_by_id
    )
    session.refresh_from_db()
    action = {
        SessionState.EXPIRED: "platform.identity.session.expire",
        SessionState.LOGGED_OUT: "platform.identity.session.logout",
        SessionState.REVOKED: "platform.identity.session.revoke",
    }[state]
    _audit(uow, action, session, before=before, reason=note or reason)
    return session


def expire_if_due(uow: UnitOfWork, session: Session, now: datetime) -> bool:
    if session.state not in LIVE:
        return False
    if session.absolute_expires_at <= now:
        end_session(uow, session, SessionState.EXPIRED, SessionEndReason.ABSOLUTE_TIMEOUT)
        return True
    if session.idle_expires_at <= now:
        reason = (
            SessionEndReason.MFA_TIMEOUT
            if session.state == SessionState.MFA_PENDING
            else SessionEndReason.IDLE_TIMEOUT
        )
        end_session(uow, session, SessionState.EXPIRED, reason)
        return True
    return False


def open_session(
    uow: UnitOfWork,
    user: User,
    *,
    zone: str,
    client_ip: str | None,
    user_agent: str = "",
    mfa_pending: bool,
    now: datetime,
) -> tuple[Session, str]:
    """Create a session for ``user`` (caller holds the user row lock in ``uow``); applies the session cap."""
    live = list(
        Session.objects.select_for_update().filter(user=user, state__in=LIVE).order_by("created_at", "id")
    )
    for s in live:
        expire_if_due(uow, s, now)
    live = [s for s in live if s.state in LIVE]
    cap = effective_int("session_max_concurrent")
    action = effective("session_limit_exceeded_action")
    if len(live) >= cap:
        if action != "END_OLDEST_SESSION":  # only approved value (Q-0101); anything else is a config error
            raise EngineContractError("unsupported session_limit_exceeded_action")
        for oldest in live[: len(live) - cap + 1]:
            end_session(
                uow,
                oldest,
                SessionState.REVOKED,
                SessionEndReason.CONCURRENT_LIMIT,
                note="END_OLDEST_SESSION (Q-0101)",
            )
    timeouts = Timeouts.for_user(user)
    absolute = now + timeouts.absolute
    idle = min(now + (MFA_PENDING_TTL if mfa_pending else timeouts.idle), absolute)
    token = new_token()
    session = Session.objects.create(
        session_key_hash=hash_token(token),
        user=user,
        state=SessionState.MFA_PENDING if mfa_pending else SessionState.ACTIVE,
        created_at=now,
        last_seen_at=now,
        idle_expires_at=idle,
        absolute_expires_at=absolute,
        network_zone=zone,
        client_ip=network.normalised_ip(client_ip),
        user_agent_hash=hashlib.sha256(user_agent.encode("utf-8")).hexdigest() if user_agent else "",
    )
    _audit(uow, "platform.identity.session.create", session, before=None)
    return session, token


def activate_after_mfa(uow: UnitOfWork, session: Session, now: datetime) -> str:
    """MFA_PENDING -> ACTIVE, mfa_verified_at = now, token rotated (returns the new token)."""
    SESSION_MACHINE.assert_transition(session.state, SessionState.ACTIVE)
    before = _snapshot(session)
    user = User.objects.get(pk=session.user_id)
    token = new_token()
    idle = min(now + Timeouts.for_user(user).idle, session.absolute_expires_at)
    Session.objects.filter(pk=session.pk).update(
        state=SessionState.ACTIVE,
        mfa_verified_at=now,
        session_key_hash=hash_token(token),
        last_seen_at=now,
        idle_expires_at=idle,
    )
    session.refresh_from_db()
    _audit(uow, "platform.identity.session.activate", session, before=before)
    return token


def mark_step_up(uow: UnitOfWork, session: Session, now: datetime) -> None:
    before = {"mfa_verified_at": session.mfa_verified_at.isoformat() if session.mfa_verified_at else None}
    Session.objects.filter(pk=session.pk).update(mfa_verified_at=now)
    session.refresh_from_db()
    uow.audit(
        action="platform.identity.session.step_up",
        resource_type="platform.session",
        resource_id=str(session.pk),
        resource_version=session.row_version,
        before=before,
        after={"mfa_verified_at": now.isoformat()},
        scope={"user_id": str(session.user_id)},
    )
    uow.emit(
        event_type="platform.identity.session.stepped_up",
        aggregate_type="platform.session",
        aggregate_id=str(session.pk),
        aggregate_version=session.row_version,
        payload={"id": str(session.pk), "user_id": str(session.user_id)},
    )


def revoke_user_sessions(
    uow: UnitOfWork,
    user_id: uuid.UUID,
    reason: SessionEndReason,
    *,
    revoked_by_id: uuid.UUID | None,
    keep: uuid.UUID | None = None,
    note: str = "",
) -> int:
    n = 0
    for s in (
        Session.objects.select_for_update().filter(user_id=user_id, state__in=LIVE).order_by("created_at")
    ):
        if s.pk == keep:
            continue
        end_session(uow, s, SessionState.REVOKED, reason, revoked_by_id=revoked_by_id, note=note)
        n += 1
    return n


# ------------------------------------------------------------------------------------- authentication
def _ctx_system(request_id: uuid.UUID | None) -> RequestContext:
    from platform_core.engine.context import Actor

    return RequestContext(Actor.system(), request_id=request_id)


def lookup(token: str) -> Session:
    s = Session.objects.filter(session_key_hash=hash_token(token)).first()
    if s is None:
        raise AuthenticationRequired()
    return s


def authenticate(
    token: str,
    *,
    client_ip: str | None,
    request_id: uuid.UUID | None = None,
    allow_mfa_pending: bool = False,
    allow_password_change: bool = False,
) -> Caller:
    """Validate a session token for one request and return the :class:`Caller`.

    401 ``AUTHENTICATION_REQUIRED`` for unknown/ended/expired sessions (an expired live session is moved to
    EXPIRED, audited); 403 ``NETWORK_POLICY_DENIED`` for internal-only accounts outside; 401 ``MFA_REQUIRED``
    for an MFA_PENDING session (except the MFA ceremony itself) and for a session that moved outside the
    factory network without MFA; 403 ``PASSWORD_CHANGE_REQUIRED`` while the password must be changed.
    """
    session = lookup(token)
    if session.state not in LIVE:
        raise AuthenticationRequired()
    now = db_now()
    if session.absolute_expires_at <= now or session.idle_expires_at <= now:
        with unit_of_work_or_nothing(_ctx_system(request_id)) as uow:
            locked = Session.objects.select_for_update().get(pk=session.pk)
            if not expire_if_due(uow, locked, now):  # someone else ended it meanwhile
                raise NothingToDo()
        raise AuthenticationRequired()
    user = User.objects.get(pk=session.user_id)
    if user.status not in (UserStatus.ACTIVE, UserStatus.CREATED):
        raise AuthenticationRequired()
    zone = network.classify(client_ip)
    if operator_zone_refused(user, zone):
        raise NetworkPolicyDenied()
    if session.state == SessionState.MFA_PENDING and not allow_mfa_pending:
        raise MfaRequired("complete the MFA verification first")
    if (
        zone != NetworkZone.INTERNAL
        and session.mfa_verified_at is None
        and session.state == SessionState.ACTIVE
    ):
        raise MfaRequired("MFA is required outside the factory network (DEC-042)")
    if not allow_password_change and must_change(Credential.objects.filter(user=user).first(), now):
        raise PasswordChangeRequired()
    timeouts = Timeouts.for_user(user)
    if session.state == SessionState.ACTIVE:
        Session.objects.filter(pk=session.pk, state=SessionState.ACTIVE).update(
            last_seen_at=now, idle_expires_at=min(now + timeouts.idle, session.absolute_expires_at)
        )
    return Caller(
        user_id=user.pk, session_id=session.pk, network_zone=zone, mfa_verified_at=session.mfa_verified_at
    )


def logout(caller: Caller, *, request_id: uuid.UUID | None = None) -> None:
    if caller.session_id is None:
        raise AuthenticationRequired()
    with unit_of_work(caller.context(request_id)) as uow:
        s = Session.objects.select_for_update().get(pk=caller.session_id)
        if s.state not in LIVE:
            raise AuthenticationRequired()
        end_session(uow, s, SessionState.LOGGED_OUT, SessionEndReason.LOGOUT)


def revoke_my_session(caller: Caller, session_id: uuid.UUID, *, request_id: uuid.UUID | None = None) -> None:
    """``revokeMySession``: only the caller's own sessions (another user's id -> 404, SEC-01)."""
    with unit_of_work(caller.context(request_id)) as uow:
        s = Session.objects.select_for_update().filter(pk=session_id, user_id=caller.user_id).first()
        if s is None or s.state not in LIVE:
            raise NotFound()
        end_session(uow, s, SessionState.REVOKED, SessionEndReason.SELF_REVOKE, revoked_by_id=caller.user_id)


def revoke_sessions_of(
    caller: Caller, user_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> int:
    """``revokeUserSessions`` (``platform.identity.session.revoke``, MFA step-up, reason)."""
    from platform_core.authz.policy import require_permission, require_step_up

    require_permission(caller, "platform.identity.session.revoke")
    require_step_up(caller, "platform.identity.session.revoke")
    text = reason.strip()
    if len(text) < 3:
        from platform_core.engine.errors import FieldError, ValidationFailed

        raise ValidationFailed("a reason is required", errors=[FieldError("reason", "REQUIRED")])
    if not User.objects.filter(pk=user_id).exists():
        raise NotFound()
    if user_id == caller.user_id:
        raise AccessDenied("use revokeMySession for own sessions")
    with unit_of_work(caller.context(request_id), require_event=False) as uow:
        n = revoke_user_sessions(
            uow, user_id, SessionEndReason.ADMIN_REVOKE, revoked_by_id=caller.user_id, note=text
        )
        uow.audit(
            action="platform.identity.session.revoke_all",
            resource_type="platform.user",
            resource_id=str(user_id),
            reason=text,
            after={"revoked": n},
        )
    return n


def expire_due_sessions(*, limit: int = 1000, request_id: uuid.UUID | None = None) -> int:
    """Housekeeping job function: move timed-out live sessions to EXPIRED (audited)."""
    now = db_now()
    from django.db.models import Q

    ids = list(
        Session.objects.filter(state__in=LIVE)
        .filter(Q(absolute_expires_at__lte=now) | Q(idle_expires_at__lte=now))
        .order_by("idle_expires_at")
        .values_list("pk", flat=True)[:limit]
    )
    n = 0
    for sid in ids:
        with unit_of_work_or_nothing(_ctx_system(request_id)) as uow:
            s = Session.objects.select_for_update(skip_locked=True).filter(pk=sid).first()
            if s is None or not expire_if_due(uow, s, now):
                raise NothingToDo()
            n += 1
    return n
