"""Login ceremony, MFA verification, step-up, password change and lockout (STATE_TRANSITIONS 4.1 / 4.2).

Login (``login``): credentials -> network zone -> MFA decision -> session.

1. Unknown user, wrong password, DISABLED, LOCKED (lock still running) and an expired one-time password all
   answer the same 401 ``INVALID_CREDENTIALS`` (no account enumeration); an unknown user costs the same hasher
   work as a real one.
2. Correct credentials of an INTERNAL_ONLY / operator account from outside the factory network (EXTERNAL or
   UNKNOWN, VPN = outside) -> 403 ``NETWORK_POLICY_DENIED`` and no session (DEC-042 / DEC-052).
3. MFA applies when the login comes from outside the factory network (DEC-042) or the user holds a role of the
   DEC-003 list, bound to the approved matrix (``authz.policy.requires_login_mfa``). Enrolled -> session
   ``MFA_PENDING``. Not enrolled: inside the network -> ACTIVE session flagged ``mfa_enrolment_required``
   (every
   MFA step-up action stays refused until enrolment); outside -> 401 ``MFA_REQUIRED`` (enrol inside first).
4. Session created under the concurrency cap (``sessions.open_session``).

Lockout (DEC-051: ``lockout_max_failures`` 5 in ``lockout_window_minutes`` 15 -> LOCKED for
``lockout_duration_minutes`` 15 + security event): failed passwords and failed MFA codes count; counting runs
under the user row lock (``SELECT ... FOR UPDATE``) so concurrent attempts cannot under-count. Failures before
the last status change (lock/unlock) or the last successful login do not count. An expired lock is lifted at
the next attempt (LOCKED -> ACTIVE, or CREATED while the initial one-time password is unchanged).

Every attempt is a ``platform_login_attempt`` row (never the password) and an audit event; failures are
committed before the error is raised, so they survive (the business write of a failed request rolls back, the
security record does not). Authentication ceremonies are exempt from Idempotency-Key (C-27).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from platform_core.authz.policy import Caller, requires_login_mfa
from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.engine.errors import (
    AleekhanError,
    AuthenticationRequired,
    FieldError,
    InvalidCredentials,
    MfaRequired,
    NetworkPolicyDenied,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import UnitOfWork, unit_of_work
from platform_core.models import ActorType, AuditOutcome
from platform_core.params.values import effective_int, effective_minutes
from platform_core.schema_common import NetworkZone

from . import crypto, network, sessions, totp
from .models import (
    Credential,
    LoginAttempt,
    LoginOutcome,
    MfaFactor,
    MfaFactorStatus,
    RecoveryCode,
    Session,
    SessionEndReason,
    SessionState,
    User,
    UserStatus,
)
from .passwords import one_time_expired, validate_new_password, verify_password, write_credential

FAILURE_OUTCOMES: Final = (LoginOutcome.INVALID_CREDENTIALS, LoginOutcome.MFA_FAILED)
MAX_USERNAME: Final = 64

# User account machine (STATE_TRANSITIONS 4.1). Engine additions, documented in docs/engine/PHASE01_ENGINE.md:
# CREATED -> LOCKED (failed logins before the first password change are locked too) and LOCKED -> CREATED
# (lock lifted while the one-time password is still unchanged).
USER_MACHINE: Final = StateMachine(
    name="user",
    states=frozenset(UserStatus.values),
    transitions={
        UserStatus.CREATED: frozenset({UserStatus.ACTIVE, UserStatus.LOCKED, UserStatus.DISABLED}),
        UserStatus.ACTIVE: frozenset({UserStatus.LOCKED, UserStatus.DISABLED}),
        UserStatus.LOCKED: frozenset({UserStatus.ACTIVE, UserStatus.CREATED, UserStatus.DISABLED}),
        UserStatus.DISABLED: frozenset({UserStatus.ACTIVE}),
    },
)


@dataclass(frozen=True)
class LoginResult:
    session_id: uuid.UUID
    token: str  # shown once (cookie value); only its SHA-256 is stored
    state: str
    network_zone: str
    must_change_password: bool
    mfa_enrolment_required: bool


def normalise_username(raw: str) -> str:
    return raw.strip().lower()[:MAX_USERNAME]


def anonymous_ctx(request_id: uuid.UUID | None, zone: str) -> RequestContext:
    return RequestContext(Actor(ActorType.ANONYMOUS), request_id=request_id, network_zone=zone)


def _user_ctx(
    user_id: uuid.UUID, request_id: uuid.UUID | None, zone: str, session_id: uuid.UUID | None = None
) -> RequestContext:
    return RequestContext(
        Actor.user(user_id), request_id=request_id, network_zone=zone, session_id=session_id
    )


@dataclass(frozen=True)
class Attempt:
    """Where an authentication attempt comes from (copied into ``platform_login_attempt``)."""

    username: str
    client_ip: str | None
    zone: str
    request_id: uuid.UUID | None
    now: datetime


def _record_attempt(
    uow: UnitOfWork,
    att: Attempt,
    *,
    user: User | None,
    outcome: LoginOutcome,
    session: Session | None = None,
) -> None:
    username = att.username
    LoginAttempt.objects.create(
        occurred_at=att.now,
        username_attempted=username,
        user=user,
        outcome=outcome,
        client_ip=network.normalised_ip(att.client_ip),
        network_zone=att.zone,
        request_id=att.request_id,
        session=session,
    )
    ok = outcome in (LoginOutcome.OK, LoginOutcome.MFA_OK, LoginOutcome.RECOVERY_CODE_USED)
    uow.audit(
        action="platform.identity.login.attempt",
        resource_type="platform.user",
        resource_id=str(user.pk) if user else "",
        outcome=AuditOutcome.SUCCESS if ok else AuditOutcome.DENIED,
        scope={"outcome": outcome, "username_hash": hashlib.sha256(username.encode("utf-8")).hexdigest()},
    )


def _set_status(
    uow: UnitOfWork,
    user: User,
    status: UserStatus,
    *,
    now: datetime,
    locked_until: datetime | None,
    reason: str,
) -> None:
    USER_MACHINE.assert_transition(user.status, status)
    before = {"status": user.status}
    action = _status_action(user.status, status)
    User.objects.filter(pk=user.pk).update(
        status=status, status_changed_at=now, locked_until=locked_until, failed_login_count=0
    )
    user.refresh_from_db()
    uow.audit(
        action=action,
        resource_type="platform.user",
        resource_id=str(user.pk),
        resource_version=user.row_version,
        before=before,
        after={"status": user.status, "locked_until": locked_until.isoformat() if locked_until else None},
        reason=reason,
    )
    uow.emit(
        event_type="platform.identity.user.status_changed",
        aggregate_type="platform.user",
        aggregate_id=str(user.pk),
        aggregate_version=user.row_version,
        payload={"id": str(user.pk), "status": user.status},
    )


def _status_action(old: str, new: str) -> str:
    if new == UserStatus.LOCKED:
        return "platform.identity.user.lock"
    if new == UserStatus.DISABLED:
        return "platform.identity.user.disable"
    if old == UserStatus.LOCKED:
        return "platform.identity.user.unlock"
    if old == UserStatus.DISABLED:
        return "platform.identity.user.enable"
    return "platform.identity.user.activate"


def _status_after_unlock(user: User) -> UserStatus:
    cred = Credential.objects.filter(user=user).first()
    return UserStatus.CREATED if cred is None or cred.is_one_time else UserStatus.ACTIVE


def lift_expired_lock(uow: UnitOfWork, user: User, now: datetime) -> None:
    if user.status == UserStatus.LOCKED and user.locked_until is not None and user.locked_until <= now:
        _set_status(
            uow, user, _status_after_unlock(user), now=now, locked_until=None, reason="lock expired (DEC-051)"
        )


def _count_failure(uow: UnitOfWork, user: User, now: datetime) -> bool:
    """After recording a failure: lock the account when the threshold is reached. Returns True if locked."""
    window = effective_minutes("lockout_window_minutes")
    since = max(now - window, user.status_changed_at)
    last_ok = (
        LoginAttempt.objects.filter(
            user=user, outcome__in=[LoginOutcome.MFA_OK, LoginOutcome.OK, LoginOutcome.RECOVERY_CODE_USED]
        )
        .order_by("-occurred_at")
        .values_list("occurred_at", flat=True)
        .first()
    )
    if last_ok is not None:
        since = max(since, last_ok)
    failures = LoginAttempt.objects.filter(
        user=user, outcome__in=FAILURE_OUTCOMES, occurred_at__gte=since
    ).count()
    User.objects.filter(pk=user.pk).update(failed_login_count=failures)
    user.refresh_from_db()
    if failures >= effective_int("lockout_max_failures") and user.status in (
        UserStatus.ACTIVE,
        UserStatus.CREATED,
    ):
        until = now + effective_minutes("lockout_duration_minutes")
        _set_status(
            uow, user, UserStatus.LOCKED, now=now, locked_until=until, reason="lockout threshold (DEC-051)"
        )
        uow.audit(
            action="platform.security.lockout",
            resource_type="platform.user",
            resource_id=str(user.pk),
            outcome=AuditOutcome.DENIED,
            after={"failures": failures, "locked_until": until.isoformat()},
            reason="security event: account locked automatically (DEC-051)",
        )
        return True
    return False


# --------------------------------------------------------------------------------------------- login
def login(
    username: str,
    password: str,
    *,
    client_ip: str | None,
    user_agent: str = "",
    request_id: uuid.UUID | None = None,
) -> LoginResult:
    name = normalise_username(username)
    zone = network.classify(client_ip)
    if not name or not password:
        raise ValidationFailed(errors=[FieldError("username" if not name else "password", "REQUIRED")])
    failure: AleekhanError | None = None
    result: LoginResult | None = None
    with unit_of_work(anonymous_ctx(request_id, zone), require_event=False) as uow:
        user = User.objects.select_for_update().filter(username=name).first()
        now = db_now()
        att = Attempt(name, client_ip, zone, request_id, now)
        if user is None:
            verify_password(password, None)  # same work as a real check
            _record_attempt(uow, att, user=None, outcome=LoginOutcome.INVALID_CREDENTIALS)
            failure = InvalidCredentials()
        else:
            lift_expired_lock(uow, user, now)
            cred = Credential.objects.filter(user=user).first()
            if user.status == UserStatus.DISABLED:
                verify_password(password, None)
                _record_attempt(uow, att, user=user, outcome=LoginOutcome.DISABLED)
                failure = InvalidCredentials()
            elif user.status == UserStatus.LOCKED:
                verify_password(password, None)
                _record_attempt(uow, att, user=user, outcome=LoginOutcome.LOCKED)
                failure = InvalidCredentials()
            elif not verify_password(password, cred.password_hash if cred else None):
                _record_attempt(uow, att, user=user, outcome=LoginOutcome.INVALID_CREDENTIALS)
                _count_failure(uow, user, now)
                failure = InvalidCredentials()
            elif one_time_expired(cred, now):
                _record_attempt(uow, att, user=user, outcome=LoginOutcome.ONE_TIME_EXPIRED)
                failure = InvalidCredentials()
            elif sessions.operator_zone_refused(user, zone):
                _record_attempt(uow, att, user=user, outcome=LoginOutcome.NETWORK_POLICY_DENIED)
                failure = NetworkPolicyDenied()
            else:
                result, failure = _open(uow, user, cred, att, user_agent=user_agent)
    if failure is not None:
        raise failure
    assert result is not None
    return result


def _active_factor(user: User) -> MfaFactor | None:
    return MfaFactor.objects.filter(user=user, status=MfaFactorStatus.ACTIVE).first()


def _open(
    uow: UnitOfWork,
    user: User,
    cred: Credential | None,
    att: Attempt,
    *,
    user_agent: str,
) -> tuple[LoginResult | None, AleekhanError | None]:
    from .passwords import must_change

    now, zone = att.now, att.zone
    outside = zone != NetworkZone.INTERNAL
    needs_mfa = outside or requires_login_mfa(user.pk)
    factor = _active_factor(user)
    if needs_mfa and factor is None and outside:
        _record_attempt(uow, att, user=user, outcome=LoginOutcome.OK)
        return None, MfaRequired("MFA enrolment is required; enrol from inside the factory network first")
    pending = needs_mfa and factor is not None
    session, token = sessions.open_session(
        uow, user, zone=zone, client_ip=att.client_ip, user_agent=user_agent, mfa_pending=pending, now=now
    )
    _record_attempt(uow, att, user=user, outcome=LoginOutcome.OK, session=session)
    User.objects.filter(pk=user.pk).update(last_login_at=now, failed_login_count=0)
    return (
        LoginResult(
            session_id=session.pk,
            token=token,
            state=session.state,
            network_zone=zone,
            must_change_password=must_change(cred, now),
            mfa_enrolment_required=needs_mfa and factor is None,
        ),
        None,
    )


# ----------------------------------------------------------------------------------------------- MFA
def _check_second_factor(
    user: User, code: str, now: datetime
) -> tuple[LoginOutcome, int | None, RecoveryCode | None]:
    """(MFA_OK, step, None) | (RECOVERY_CODE_USED, None, code row) | (MFA_FAILED, None, None)."""
    factor = MfaFactor.objects.select_for_update().filter(user=user, status=MfaFactorStatus.ACTIVE).first()
    if factor is None or factor.secret_ciphertext is None:
        return LoginOutcome.MFA_FAILED, None, None
    clean = code.strip().replace(" ", "")
    if clean.isdigit() and len(clean) == totp.DIGITS:
        secret = crypto.decrypt(
            bytes(factor.secret_ciphertext), key_ref=factor.key_ref, aad=b"mfa:" + user.pk.bytes
        )
        step = totp.match_step(secret, clean, now.timestamp(), last_used_step=factor.last_used_step)
        if step is None:
            return LoginOutcome.MFA_FAILED, None, None
        MfaFactor.objects.filter(pk=factor.pk).update(last_used_step=step)
        return LoginOutcome.MFA_OK, step, None
    from .mfa import recovery_hash

    row = (
        RecoveryCode.objects.select_for_update()
        .filter(user=user, code_hash=recovery_hash(user.pk, clean), used_at__isnull=True)
        .first()
    )
    if row is None:
        return LoginOutcome.MFA_FAILED, None, None
    RecoveryCode.objects.filter(pk=row.pk).update(used_at=now)
    return LoginOutcome.RECOVERY_CODE_USED, None, row


def verify_mfa(
    token: str, code: str, *, client_ip: str | None, request_id: uuid.UUID | None = None
) -> LoginResult:
    """MFA_PENDING -> ACTIVE (token rotated). A wrong code counts towards the lockout (DEC-051)."""
    caller = sessions.authenticate(
        token, client_ip=client_ip, request_id=request_id, allow_mfa_pending=True, allow_password_change=True
    )
    failure: AleekhanError | None = None
    result: LoginResult | None = None
    with unit_of_work(_ctx(caller, request_id), require_event=False) as uow:
        user = User.objects.select_for_update().get(pk=caller.user_id)
        session = Session.objects.select_for_update().get(pk=_session_id(caller))
        now = db_now()
        if session.state != SessionState.MFA_PENDING:
            raise StateTransitionNotAllowed("the session is not waiting for MFA")
        att = Attempt(user.username, client_ip, caller.network_zone, request_id, now)
        lift_expired_lock(uow, user, now)
        if user.status not in (UserStatus.ACTIVE, UserStatus.CREATED):
            _record_attempt(uow, att, user=user, outcome=LoginOutcome.LOCKED, session=session)
            failure = InvalidCredentials()
        else:
            outcome, _step, _row = _check_second_factor(user, code, now)
            _record_attempt(uow, att, user=user, outcome=outcome, session=session)
            if outcome == LoginOutcome.MFA_FAILED:
                _count_failure(uow, user, now)  # a LOCKED user's sessions are refused by authenticate()
                failure = InvalidCredentials()
            else:
                new_token = sessions.activate_after_mfa(uow, session, now)
                from .passwords import must_change

                result = LoginResult(
                    session_id=session.pk,
                    token=new_token,
                    state=session.state,
                    network_zone=caller.network_zone,
                    must_change_password=must_change(Credential.objects.filter(user=user).first(), now),
                    mfa_enrolment_required=False,
                )
    if failure is not None:
        raise failure
    assert result is not None
    return result


def step_up(
    caller: Caller, code: str, *, client_ip: str | None, request_id: uuid.UUID | None = None
) -> datetime:
    """Fresh MFA verification on an ACTIVE session (window ``mfa_step_up_window_minutes``)."""
    if caller.session_id is None:
        raise AuthenticationRequired()
    failure: AleekhanError | None = None
    with unit_of_work(_ctx(caller, request_id), require_event=False) as uow:
        user = User.objects.select_for_update().get(pk=caller.user_id)
        session = Session.objects.select_for_update().get(pk=_session_id(caller))
        now = db_now()
        if session.state != SessionState.ACTIVE:
            raise AuthenticationRequired()
        outcome, _s, _r = _check_second_factor(user, code, now)
        att = Attempt(user.username, client_ip, caller.network_zone, request_id, now)
        _record_attempt(uow, att, user=user, outcome=outcome, session=session)
        if outcome == LoginOutcome.MFA_FAILED:
            _count_failure(uow, user, now)  # a LOCKED user's sessions are refused by authenticate()
            failure = InvalidCredentials()
        else:
            sessions.mark_step_up(uow, session, now)
    if failure is not None:
        raise failure
    return now


def _session_id(caller: Caller) -> uuid.UUID:
    if caller.session_id is None:
        raise AuthenticationRequired()
    return caller.session_id


def _ctx(caller: Caller, request_id: uuid.UUID | None) -> RequestContext:
    return _user_ctx(caller.user_id, request_id, caller.network_zone, caller.session_id)


# ------------------------------------------------------------------------------------ password change
def change_my_password(
    caller: Caller, current_password: str, new_password: str, *, request_id: uuid.UUID | None = None
) -> None:
    """``changeMyPassword`` (DEC-051): current password required; policy + last-5 reuse check; the other
    sessions of the user are revoked; CREATED -> ACTIVE at the first change."""
    failure: AleekhanError | None = None
    with unit_of_work(_ctx(caller, request_id), require_event=False) as uow:
        user = User.objects.select_for_update().get(pk=caller.user_id)
        now = db_now()
        cred = Credential.objects.filter(user=user).first()
        if not verify_password(current_password, cred.password_hash if cred else None):
            att = Attempt(user.username, None, caller.network_zone, request_id, now)
            _record_attempt(uow, att, user=user, outcome=LoginOutcome.INVALID_CREDENTIALS)
            _count_failure(uow, user, now)
            failure = InvalidCredentials()
        else:
            validate_new_password(user, new_password)
            write_credential(user, new_password, now=now, one_time=False, set_by_id=user.pk)
            sessions.revoke_user_sessions(
                uow, user.pk, SessionEndReason.PASSWORD_CHANGED, revoked_by_id=user.pk, keep=caller.session_id
            )
            if user.status == UserStatus.CREATED:
                _set_status(
                    uow,
                    user,
                    UserStatus.ACTIVE,
                    now=now,
                    locked_until=None,
                    reason="first password change (DEC-051)",
                )
            uow.audit(
                action="platform.identity.password.change",
                resource_type="platform.user",
                resource_id=str(user.pk),
                resource_version=user.row_version,
                after={"credential": "replaced"},
            )
    if failure is not None:
        raise failure
