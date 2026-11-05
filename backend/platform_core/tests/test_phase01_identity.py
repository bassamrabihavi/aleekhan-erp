"""PHASE_01 / 01.2: identity tables - CHECKs and triggers (DEC-003/050/051/052/054). Synthetic data only."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.db.models.functions import Now
from django.utils import timezone

from platform_core.identity.models import (
    BreakGlassUsage,
    Credential,
    LoginAttempt,
    MfaFactor,
    PasswordHistory,
    RecoveryCode,
    Session,
    User,
)

from .phase01_factories import db_refuses, user

pytestmark = pytest.mark.django_db
HASH = "argon2$argon2id$v=19$m=65536,t=3,p=4$c3lu$c3ludGhldGlj"  # synthetic, not a real password hash


def _session(u: User, **over: object) -> Session:
    now = timezone.now()
    data: dict[str, object] = {
        "session_key_hash": uuid.uuid4().hex * 2,
        "user": u,
        "state": "ACTIVE",
        "idle_expires_at": now + timedelta(hours=2),
        "absolute_expires_at": now + timedelta(hours=12),
        "network_zone": "INTERNAL",
    }
    data.update(over)
    return Session.objects.create(**data)


def test_username_lowercase_pattern_and_unique() -> None:
    u = user(username="syn.alpha")
    with db_refuses("ck_user_username_fmt"):
        user(username="Syn.Alpha")
    with db_refuses("uq_user_username"):
        user(username=u.username)


def test_synthetic_rows_must_carry_the_label() -> None:
    with db_refuses("ck_user_synthetic_label"):
        user(display_name="کاربر بدون برچسب")


def test_operator_accounts_are_internal_only() -> None:
    """DEC-052 O-A: personal operator accounts, factory network only."""
    user(account_kind="OPERATOR", network_policy="INTERNAL_ONLY")
    with db_refuses("ck_user_operator_internal_only"):
        user(account_kind="OPERATOR", network_policy="ANY_WITH_MFA_OUTSIDE")


def test_no_directory_or_shared_account_kinds() -> None:
    """DEC-003 (no AD/LDAP/SSO) and DEC-052 (no shared terminal account): only PERSON / OPERATOR exist."""
    for kind in ("SERVICE", "SHARED_TERMINAL", "LDAP"):
        with db_refuses("ck_user_account_kind"):
            user(account_kind=kind)
    cols = {f.name for f in User._meta.get_fields()}
    assert not cols & {"ldap_dn", "sso_subject", "external_id", "directory_id", "password"}


def test_locked_user_has_locked_until() -> None:
    with db_refuses("ck_user_locked_has_until"):
        user(status="LOCKED")
    user(status="LOCKED", locked_until=timezone.now() + timedelta(minutes=15))


def test_only_one_break_glass_account_and_flag_immutable() -> None:
    """DEC-054 (A): one sealed emergency account; the flag cannot be moved to another user later."""
    bg = user(is_break_glass=True)
    with db_refuses("uq_user_single_break_glass"):
        user(is_break_glass=True)
    other = user()
    with db_refuses("immutable_column"):
        User.objects.filter(pk=other.pk).update(is_break_glass=True)
    BreakGlassUsage.objects.create(user=bg, reason="synthetic drill")
    with db_refuses("ck_break_glass_usage_account"):
        BreakGlassUsage.objects.create(user=other, reason="synthetic drill")


def test_break_glass_usage_is_append_only_except_closing_columns() -> None:
    bg = user(is_break_glass=True)
    use = BreakGlassUsage.objects.create(user=bg, reason="synthetic drill")
    BreakGlassUsage.objects.filter(pk=use.pk).update(alerted_at=Now(), ended_at=Now())
    with db_refuses("append_only"):
        BreakGlassUsage.objects.filter(pk=use.pk).update(ended_at=timezone.now() + timedelta(hours=1))
    with db_refuses("append_only"):
        BreakGlassUsage.objects.filter(pk=use.pk).update(reason="changed")
    with db_refuses("append_only"):
        BreakGlassUsage.objects.filter(pk=use.pk).delete()


def test_user_row_version_bumps_on_update() -> None:
    u = user()
    User.objects.filter(pk=u.pk).update(display_name=u.display_name + " ۲")
    u.refresh_from_db()
    assert u.row_version == 2


def test_credential_one_time_password_rules() -> None:
    """DEC-051: one-time initial password has an expiry and forces a change at first login."""
    u = user()
    now = timezone.now()
    with db_refuses("ck_credential_one_time_expiry"):
        Credential.objects.create(user=u, password_hash=HASH, set_at=now, is_one_time=True, must_change=True)
    with db_refuses("ck_credential_one_time_expiry"):
        Credential.objects.create(
            user=u,
            password_hash=HASH,
            set_at=now,
            is_one_time=True,
            must_change=False,
            one_time_expires_at=now + timedelta(hours=72),
        )
    with db_refuses("ck_credential_hash_fmt"):
        Credential.objects.create(user=u, password_hash="clear-text-password", set_at=now)
    Credential.objects.create(
        user=u,
        password_hash=HASH,
        set_at=now,
        is_one_time=True,
        must_change=True,
        one_time_expires_at=now + timedelta(hours=72),
        expires_at=now + timedelta(days=90),
    )


def test_password_history_is_append_only() -> None:
    u = user()
    h = PasswordHistory.objects.create(user=u, password_hash=HASH, set_at=timezone.now())
    with db_refuses("append-only"):
        PasswordHistory.objects.filter(pk=h.pk).update(password_hash=HASH + "x")
    with db_refuses("append-only"):
        PasswordHistory.objects.filter(pk=h.pk).delete()


def test_mfa_totp_only_one_active_and_replay_guard() -> None:
    u = user()
    now = timezone.now()
    with db_refuses("ck_mfa_factor_method"):
        MfaFactor.objects.create(user=u, method="SMS", secret_ciphertext=b"x", key_ref="k1")
    f = MfaFactor.objects.create(
        user=u, status="ACTIVE", secret_ciphertext=b"enc", key_ref="k1", confirmed_at=now, last_used_step=100
    )
    with db_refuses("uq_mfa_factor_one_active"):
        MfaFactor.objects.create(
            user=u, status="ACTIVE", secret_ciphertext=b"e2", key_ref="k1", confirmed_at=now
        )
    with db_refuses("ck_mfa_factor_replay"):
        MfaFactor.objects.filter(pk=f.pk).update(last_used_step=99)
    MfaFactor.objects.filter(pk=f.pk).update(last_used_step=101)
    with db_refuses("ck_mfa_factor_revoked_no_secret"):
        MfaFactor.objects.filter(pk=f.pk).update(status="REVOKED", revoked_at=now)
    MfaFactor.objects.filter(pk=f.pk).update(status="REVOKED", revoked_at=now, secret_ciphertext=None)
    with db_refuses("terminal_immutable"):
        MfaFactor.objects.filter(pk=f.pk).update(revoke_reason="changed")


def test_recovery_codes_hash_only_and_used_once() -> None:
    """DEC-050: recovery codes stored as hashes; a used code cannot be reused or 'un-used'."""
    u = user()
    gen = uuid.uuid4()
    with db_refuses("ck_recovery_code_hash_fmt"):
        RecoveryCode.objects.create(user=u, generation=gen, code_hash="ABCD-1234")
    c = RecoveryCode.objects.create(user=u, generation=gen, code_hash=HASH)
    RecoveryCode.objects.filter(pk=c.pk).update(used_at=timezone.now())
    with db_refuses("append_only"):
        RecoveryCode.objects.filter(pk=c.pk).update(used_at=None)
    RecoveryCode.objects.filter(pk=c.pk).delete()  # regeneration removes old hashes (DATA_TABLE)


def test_session_state_invariants_and_terminal_rows_immutable() -> None:
    u = user()
    with db_refuses("ck_session_ended_has_reason"):
        _session(u, state="REVOKED")
    with db_refuses("ck_session_live_not_ended"):
        _session(u, ended_at=timezone.now())
    with db_refuses("ck_session_idle_le_absolute"):
        _session(u, idle_expires_at=timezone.now() + timedelta(hours=13))
    with db_refuses("ck_session_zone"):
        _session(u, network_zone="VPN")
    s = _session(u)
    Session.objects.filter(pk=s.pk).update(state="LOGGED_OUT", ended_at=timezone.now(), end_reason="LOGOUT")
    with db_refuses("terminal_immutable"):
        Session.objects.filter(pk=s.pk).update(state="ACTIVE", ended_at=None, end_reason="")


def test_login_attempts_append_only_and_retention_guard() -> None:
    """DEC-032: login events are kept 2 years (parameter retention_login_events_months = 24)."""
    a = LoginAttempt.objects.create(
        username_attempted="nobody", outcome="INVALID_CREDENTIALS", network_zone="UNKNOWN"
    )
    with db_refuses("append_only"):
        LoginAttempt.objects.filter(pk=a.pk).update(outcome="OK")
    with db_refuses("retention period"):
        LoginAttempt.objects.filter(pk=a.pk).delete()
    old = LoginAttempt.objects.create(
        username_attempted="nobody",
        outcome="INVALID_CREDENTIALS",
        network_zone="UNKNOWN",
        occurred_at=timezone.now() - timedelta(days=366 * 2 + 1),
    )
    LoginAttempt.objects.filter(pk=old.pk).delete()  # purge after the retention period is allowed
    with db_refuses("ck_login_attempt_outcome"):
        LoginAttempt.objects.create(username_attempted="x", outcome="PASSWORD_SHOWN", network_zone="UNKNOWN")


def test_no_password_or_secret_columns_in_clear() -> None:
    """Secrets are hashes/ciphertext only: no column named like a clear password/secret/token."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name LIKE 'platform\\_%%' "
            "AND column_name ~ '(password|secret|token|recovery_code|session_key)'"
        )
        cols = {f"{t}.{c}" for t, c in cur.fetchall()}
    assert cols == {
        "platform_credential.password_hash",
        "platform_password_history.password_hash",
        "platform_mfa_factor.secret_ciphertext",
        "platform_session.session_key_hash",
        "platform_break_glass_usage.password_rotated_at",
    }
