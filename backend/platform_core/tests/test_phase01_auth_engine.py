"""Login ceremony, network zones, MFA (TOTP + recovery codes), step-up, sessions, lockout, password change and
user administration (DEC-003 / 042 / 049 / 050 / 051 / 052) at service level, plus the race tests."""

from __future__ import annotations

import time
from datetime import timedelta

import pytest

from platform_core.engine.context import db_now
from platform_core.engine.errors import (
    AccessDenied,
    AuthenticationRequired,
    InvalidCredentials,
    MfaRequired,
    NetworkPolicyDenied,
    PasswordChangeRequired,
    PasswordPolicyViolation,
    StateTransitionNotAllowed,
)
from platform_core.identity import auth, mfa, network, sessions, totp, users
from platform_core.identity.models import LoginAttempt, MfaFactor, RecoveryCode, Session, User
from platform_core.models import AuditEvent

from .engine_fixtures import (
    EXTERNAL_IP,
    INTERNAL_IP,
    PASSWORD,
    SYN_PW_NEW,
    SYN_PW_WEAK,
    VPN_IP,
    caller,
    ensure_catalogue,
    give_role,
    person,
    with_role,
)
from .engine_fixtures import (
    network as set_network,
)
from .threads import run_concurrently


@pytest.fixture(autouse=True)
def _zones(settings) -> None:
    set_network(settings)


def _enrol(u: User) -> bytes:
    """Enrol TOTP for ``u`` through the service; returns the seed (test only: read back from the URI)."""
    import base64
    from urllib.parse import parse_qs, urlparse

    c = caller(u, mfa=False)
    start = mfa.start_enrolment(c)
    secret_b32 = parse_qs(urlparse(start.provisioning_uri).query)["secret"][0]
    secret = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    _RECOVERY[u.pk] = mfa.confirm_enrolment(c, totp.totp(secret, time.time()))
    return secret


_RECOVERY: dict[object, list[str]] = {}


def _next_code(secret: bytes) -> str:
    """A code for the next time step (the current one was consumed by the replay guard)."""
    return totp.totp(secret, time.time() + totp.STEP_SECONDS)


# ---------------------------------------------------------------------------------------- network zones
def test_network_zone_classification() -> None:
    assert network.classify(INTERNAL_IP) == "INTERNAL"
    assert network.classify(VPN_IP) == "EXTERNAL"  # VPN = outside (DEC-052)
    assert network.classify(EXTERNAL_IP) == "EXTERNAL"
    assert network.classify(None) == "UNKNOWN" and network.classify("not-an-ip") == "UNKNOWN"
    assert network.classify("::ffff:10.20.1.10") == "INTERNAL"


# ---------------------------------------------------------------------------------------------- login
@pytest.mark.django_db
def test_same_answer_for_unknown_user_wrong_password_disabled_and_locked() -> None:
    active = person()
    disabled = person(status="DISABLED")
    locked = person(status="LOCKED")
    for name, pw in (
        ("syn.nobody", PASSWORD),
        (active.username, "Wrong-Pass-1!"),
        (disabled.username, PASSWORD),
        (locked.username, PASSWORD),
    ):
        with pytest.raises(InvalidCredentials) as exc:
            auth.login(name, pw, client_ip=INTERNAL_IP)
        assert exc.value.code == "INVALID_CREDENTIALS" and exc.value.detail == ""
    outcomes = set(LoginAttempt.objects.values_list("outcome", flat=True))
    assert {"INVALID_CREDENTIALS", "DISABLED", "LOCKED"} <= outcomes
    assert not AuditEvent.objects.filter(scope__icontains=PASSWORD).exists()


@pytest.mark.django_db
def test_plain_employee_inside_gets_an_active_session_without_mfa() -> None:
    u = person()
    give_role(u, "employee")
    res = auth.login(u.username, PASSWORD, client_ip=INTERNAL_IP, user_agent="synthetic-agent")
    assert res.state == "ACTIVE" and not res.must_change_password and not res.mfa_enrolment_required
    s = Session.objects.get(pk=res.session_id)
    assert s.session_key_hash == sessions.hash_token(res.token) and res.token not in s.session_key_hash
    c = sessions.authenticate(res.token, client_ip=INTERNAL_IP)
    assert c.user_id == u.pk and c.session_id == s.pk and c.network_zone == "INTERNAL"
    sessions.logout(c)
    with pytest.raises(AuthenticationRequired):
        sessions.authenticate(res.token, client_ip=INTERNAL_IP)


@pytest.mark.django_db
def test_operator_refused_outside_and_vpn() -> None:
    op = person(account_kind="OPERATOR", network_policy="INTERNAL_ONLY")
    for ip in (EXTERNAL_IP, VPN_IP, None):
        with pytest.raises(NetworkPolicyDenied):
            auth.login(op.username, PASSWORD, client_ip=ip)
    assert not Session.objects.filter(user=op).exists()
    res = auth.login(op.username, PASSWORD, client_ip=INTERNAL_IP)
    with pytest.raises(NetworkPolicyDenied):  # the same session used from outside
        sessions.authenticate(res.token, client_ip=EXTERNAL_IP)


@pytest.mark.django_db
def test_outside_login_needs_mfa_and_unenrolled_users_are_refused_outside() -> None:
    u = person()
    with pytest.raises(MfaRequired):
        auth.login(u.username, PASSWORD, client_ip=EXTERNAL_IP)
    secret = _enrol(u)
    res = auth.login(u.username, PASSWORD, client_ip=EXTERNAL_IP)
    assert res.state == "MFA_PENDING"
    with pytest.raises(MfaRequired):  # only verifyMfa / logout accept a pending session
        sessions.authenticate(res.token, client_ip=EXTERNAL_IP)
    with pytest.raises(InvalidCredentials):
        auth.verify_mfa(res.token, "000000", client_ip=EXTERNAL_IP)
    ok = auth.verify_mfa(res.token, _next_code(secret), client_ip=EXTERNAL_IP)
    assert ok.state == "ACTIVE" and ok.token != res.token and ok.session_id == res.session_id  # rotated
    with pytest.raises(AuthenticationRequired):
        sessions.authenticate(res.token, client_ip=EXTERNAL_IP)  # old token is dead
    c = sessions.authenticate(ok.token, client_ip=EXTERNAL_IP)
    assert c.mfa_verified_at is not None


@pytest.mark.django_db
def test_mfa_role_inside_without_enrolment_is_flagged_and_step_up_refused() -> None:
    u = person()
    give_role(u, "owner_admin")
    res = auth.login(u.username, PASSWORD, client_ip=INTERNAL_IP)
    assert res.state == "ACTIVE" and res.mfa_enrolment_required
    c = sessions.authenticate(res.token, client_ip=INTERNAL_IP)
    with pytest.raises(MfaRequired):
        users.create_user(
            c,
            username="syn.new.user",
            display_name="کاربر ساختگی",
            account_kind="PERSON",
            initial_password=PASSWORD,
            reason="test",
        )


@pytest.mark.django_db
def test_totp_replay_and_recovery_codes_single_use() -> None:
    u = person()
    c = caller(u, mfa=False)
    start = mfa.start_enrolment(c)
    import base64
    from urllib.parse import parse_qs, urlparse

    b32 = parse_qs(urlparse(start.provisioning_uri).query)["secret"][0]
    secret = base64.b32decode(b32 + "=" * (-len(b32) % 8))
    codes = mfa.confirm_enrolment(c, totp.totp(secret, time.time()))
    assert len(codes) == 10 and len(set(codes)) == 10
    stored = list(RecoveryCode.objects.filter(user=u).values_list("code_hash", flat=True))
    assert all(h.startswith("sha256$") for h in stored) and not any(
        code in h for code in codes for h in stored
    )
    factor = MfaFactor.objects.get(user=u, status="ACTIVE")
    assert factor.secret_ciphertext is not None
    blob = bytes(factor.secret_ciphertext)
    assert blob != secret and secret not in blob
    res = auth.login(u.username, PASSWORD, client_ip=EXTERNAL_IP)
    with pytest.raises(InvalidCredentials):  # the enrolment code's step is already used (replay)
        auth.verify_mfa(res.token, totp.totp(secret, time.time()), client_ip=EXTERNAL_IP)
    assert auth.verify_mfa(res.token, codes[0], client_ip=EXTERNAL_IP).state == "ACTIVE"
    res2 = auth.login(u.username, PASSWORD, client_ip=EXTERNAL_IP)
    with pytest.raises(InvalidCredentials):  # single use
        auth.verify_mfa(res2.token, codes[0], client_ip=EXTERNAL_IP)
    assert LoginAttempt.objects.filter(user=u, outcome="RECOVERY_CODE_USED").count() == 1
    with pytest.raises(StateTransitionNotAllowed):  # re-enrolment needs a reset
        mfa.start_enrolment(c)


@pytest.mark.django_db
def test_step_up_refreshes_mfa_window() -> None:
    u = person()
    give_role(u, "owner_admin")
    secret = _enrol(u)
    res = auth.login(u.username, PASSWORD, client_ip=EXTERNAL_IP)
    ok = auth.verify_mfa(res.token, _next_code(secret), client_ip=EXTERNAL_IP)
    Session.objects.filter(pk=ok.session_id).update(mfa_verified_at=db_now() - timedelta(minutes=30))
    stale = sessions.authenticate(ok.token, client_ip=EXTERNAL_IP)
    with pytest.raises(MfaRequired):
        users.create_user(
            stale,
            username="syn.u.1",
            display_name="ک",
            account_kind="PERSON",
            initial_password=PASSWORD,
            reason="test",
        )
    with pytest.raises(InvalidCredentials):  # an already used TOTP step is refused (replay guard)
        auth.step_up(stale, _next_code(secret), client_ip=EXTERNAL_IP)
    auth.step_up(stale, _RECOVERY[u.pk][0], client_ip=EXTERNAL_IP)  # a recovery code also steps up
    fresh = sessions.authenticate(ok.token, client_ip=EXTERNAL_IP)
    created = users.create_user(
        fresh,
        username="syn.u.1",
        display_name="کاربر ساختگی",
        account_kind="PERSON",
        initial_password=PASSWORD,
        reason="test",
    )
    assert created.status == "CREATED"


# -------------------------------------------------------------------------------------------- lockout
@pytest.mark.django_db
def test_five_failures_lock_for_fifteen_minutes_with_security_event_and_auto_unlock() -> None:
    u = person()
    for _ in range(5):
        with pytest.raises(InvalidCredentials):
            auth.login(u.username, "Wrong-Pass-1!", client_ip=INTERNAL_IP)
    u.refresh_from_db()
    assert u.status == "LOCKED" and u.locked_until is not None
    assert AuditEvent.objects.filter(action="platform.security.lockout", resource_id=str(u.pk)).count() == 1
    with pytest.raises(InvalidCredentials):  # even the right password while locked
        auth.login(u.username, PASSWORD, client_ip=INTERNAL_IP)
    User.objects.filter(pk=u.pk).update(locked_until=db_now() - timedelta(seconds=1))
    assert auth.login(u.username, PASSWORD, client_ip=INTERNAL_IP).state == "ACTIVE"
    u.refresh_from_db()
    assert u.status == "ACTIVE" and u.failed_login_count == 0


@pytest.mark.django_db
def test_it_ops_unlocks_without_changing_the_password() -> None:
    u = person(status="LOCKED")
    _ops, ops = with_role("it_ops")
    before = u.credential.password_hash
    users.unlock_user(ops, u.pk, reason="user called helpdesk")
    u.refresh_from_db()
    assert u.status == "ACTIVE" and u.credential.password_hash == before
    with pytest.raises(AccessDenied):  # it_ops cannot reset passwords
        users.reset_password(
            ops,
            u.pk,
            new_one_time_password=SYN_PW_NEW,
            reason="no",
        )


# ----------------------------------------------------------------------------------- password change
@pytest.mark.django_db
def test_one_time_password_forces_change_then_activates() -> None:
    u = person(status="CREATED", one_time=True)
    res = auth.login(u.username, PASSWORD, client_ip=INTERNAL_IP)
    assert res.must_change_password
    with pytest.raises(PasswordChangeRequired):
        sessions.authenticate(res.token, client_ip=INTERNAL_IP)
    c = sessions.authenticate(res.token, client_ip=INTERNAL_IP, allow_password_change=True)
    with pytest.raises(PasswordPolicyViolation):
        auth.change_my_password(c, PASSWORD, PASSWORD)  # reuse refused
    other = auth.login(u.username, PASSWORD, client_ip=INTERNAL_IP)
    auth.change_my_password(c, PASSWORD, "Brand-New-Pass-9!")
    u.refresh_from_db()
    assert u.status == "ACTIVE" and not u.credential.must_change and not u.credential.is_one_time
    sessions.authenticate(res.token, client_ip=INTERNAL_IP)  # current session kept
    with pytest.raises(AuthenticationRequired):  # the other session was revoked
        sessions.authenticate(other.token, client_ip=INTERNAL_IP)


@pytest.mark.django_db
def test_expired_one_time_password_is_refused_with_the_same_answer() -> None:
    u = person(status="CREATED", one_time=True)
    type(u.credential).objects.filter(pk=u.pk).update(
        set_at=db_now() - timedelta(hours=80), one_time_expires_at=db_now() - timedelta(hours=8)
    )
    with pytest.raises(InvalidCredentials):
        auth.login(u.username, PASSWORD, client_ip=INTERNAL_IP)
    assert LoginAttempt.objects.filter(user=u, outcome="ONE_TIME_EXPIRED").exists()


# ------------------------------------------------------------------------------------------- sessions
@pytest.mark.django_db
def test_idle_and_absolute_timeouts_expire_the_session() -> None:
    u = person()
    res = auth.login(u.username, PASSWORD, client_ip=INTERNAL_IP)
    s = Session.objects.get(pk=res.session_id)
    assert s.absolute_expires_at - s.created_at == timedelta(hours=12)
    assert s.idle_expires_at - s.created_at == timedelta(minutes=120)
    Session.objects.filter(pk=s.pk).update(idle_expires_at=db_now() - timedelta(seconds=1))
    with pytest.raises(AuthenticationRequired):
        sessions.authenticate(res.token, client_ip=INTERNAL_IP)
    s.refresh_from_db()
    assert (s.state, s.end_reason) == ("EXPIRED", "IDLE_TIMEOUT")


@pytest.mark.django_db
def test_operator_session_timeouts() -> None:
    op = person(account_kind="OPERATOR", network_policy="INTERNAL_ONLY")
    s = Session.objects.get(pk=auth.login(op.username, PASSWORD, client_ip=INTERNAL_IP).session_id)
    assert s.idle_expires_at - s.created_at == timedelta(hours=8)
    assert s.absolute_expires_at - s.created_at == timedelta(hours=12)  # Q-0102


@pytest.mark.django_db
def test_fourth_login_ends_the_oldest_session() -> None:
    u = person()
    tokens = [auth.login(u.username, PASSWORD, client_ip=INTERNAL_IP) for _ in range(4)]
    first = Session.objects.get(pk=tokens[0].session_id)
    assert (first.state, first.end_reason) == ("REVOKED", "CONCURRENT_LIMIT")
    assert Session.objects.filter(user=u, state="ACTIVE").count() == 3
    assert AuditEvent.objects.filter(
        action="platform.identity.session.revoke", resource_id=str(first.pk)
    ).exists()


@pytest.mark.django_db
def test_revoke_own_session_only_and_admin_revoke() -> None:
    a, b = person(), person()
    ra = auth.login(a.username, PASSWORD, client_ip=INTERNAL_IP)
    rb = auth.login(b.username, PASSWORD, client_ip=INTERNAL_IP)
    ca = sessions.authenticate(ra.token, client_ip=INTERNAL_IP)
    from platform_core.engine.errors import NotFound

    with pytest.raises(NotFound):  # SEC-01: another user's session id
        sessions.revoke_my_session(ca, rb.session_id)
    _ops, ops = with_role("it_ops")
    assert sessions.revoke_sessions_of(ops, b.pk, reason="lost laptop") == 1
    with pytest.raises(AuthenticationRequired):
        sessions.authenticate(rb.token, client_ip=INTERNAL_IP)


# ----------------------------------------------------------------------------------------- admin users
@pytest.mark.django_db
def test_user_admin_create_disable_enable_reset_mfa() -> None:
    o, owner = with_role("owner_admin")
    with pytest.raises(PasswordPolicyViolation):
        users.create_user(
            owner,
            username="syn.weak",
            display_name="ک",
            account_kind="PERSON",
            initial_password=SYN_PW_WEAK,
            reason="test",
        )
    op = users.create_user(
        owner,
        username="syn.op.1",
        display_name="اپراتور ساختگی",
        account_kind="OPERATOR",
        network_policy="ANY_WITH_MFA_OUTSIDE",
        initial_password=PASSWORD,
        reason="hire",
    )
    assert op.network_policy == "INTERNAL_ONLY" and op.credential.is_one_time  # DEC-052 forced
    with pytest.raises(StateTransitionNotAllowed):  # the last disabler cannot be disabled
        users.disable_user(owner, o.pk, reason="self")
    target = person()
    res = auth.login(target.username, PASSWORD, client_ip=INTERNAL_IP)
    users.disable_user(owner, target.pk, reason="left the company")
    with pytest.raises(AuthenticationRequired):
        sessions.authenticate(res.token, client_ip=INTERNAL_IP)
    users.enable_user(owner, target.pk, reason="returned")
    _enrol(target)
    with pytest.raises(AccessDenied):
        mfa.reset_user_mfa(owner, o.pk, reason="own")
    assert mfa.reset_user_mfa(owner, target.pk, reason="lost phone") == 1
    target.refresh_from_db()
    assert (
        not target.mfa_enrolled
        and not RecoveryCode.objects.filter(user=target, used_at__isnull=True).exists()
    )
    assert MfaFactor.objects.get(user=target).secret_ciphertext is None


# ---------------------------------------------------------------------------------------------- races
@pytest.mark.django_db(transaction=True)
def test_concurrent_logins_never_exceed_the_session_cap(audit_cleanup: None, settings) -> None:
    ensure_catalogue()
    set_network(settings)
    u = person()
    n = 8
    results = run_concurrently(lambda i: auth.login(u.username, PASSWORD, client_ip=INTERNAL_IP), n)
    assert all(not isinstance(r, BaseException) for r in results), results
    assert Session.objects.filter(user=u, state="ACTIVE").count() == 3
    assert Session.objects.filter(user=u, state="REVOKED", end_reason="CONCURRENT_LIMIT").count() == n - 3


@pytest.mark.django_db(transaction=True)
def test_concurrent_wrong_passwords_lock_exactly_once(audit_cleanup: None, settings) -> None:
    ensure_catalogue()
    set_network(settings)
    u = person()
    n = 9
    results = run_concurrently(lambda i: auth.login(u.username, "Wrong-Pass-1!", client_ip=INTERNAL_IP), n)
    assert all(isinstance(r, InvalidCredentials) for r in results), results
    u.refresh_from_db()
    assert u.status == "LOCKED"
    assert LoginAttempt.objects.filter(user=u, outcome="INVALID_CREDENTIALS").count() == 5
    assert LoginAttempt.objects.filter(user=u, outcome="LOCKED").count() == n - 5
    assert AuditEvent.objects.filter(action="platform.security.lockout", resource_id=str(u.pk)).count() == 1
