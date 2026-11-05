"""Password policy and credential writes (DEC-051 APPROVED; employer answer Q-0105).

Policy values come from parameters (never constants): ``password_min_length`` (8),
``password_require_uppercase``
/ ``_digit`` / ``_symbol`` (true), ``password_max_age_days`` (90), ``password_initial_validity_hours`` (72),
``password_change_at_first_login`` (true), ``password_history_reuse_depth`` (5: the last 5 passwords - the
current one included - are refused). A common-password list is not part of DEC-051 and is not applied.

Character classes (Unicode-aware): upper-case = ``str.isupper``; digit = ``str.isdigit`` (Persian digits
count);
symbol = any character that is not a letter, a digit or white space. ``MAX_LENGTH`` 1024 = the contract limit
(``LoginRequest.password.maxLength``).

Hashing: Django's password-hasher framework (``settings.PASSWORD_HASHERS``: PBKDF2-SHA256, no new dependency).
Clear passwords never reach the audit log, the outbox, the idempotency store or logs; errors name only the
failed rule.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from django.contrib.auth.hashers import check_password, make_password

from platform_core.engine.errors import FieldError, PasswordPolicyViolation
from platform_core.params.values import effective_bool, effective_days, effective_hours, effective_int

from .models import Credential, PasswordHistory, User

MAX_LENGTH: Final = 1024
# A valid hash of a random value: verified against when the user does not exist (same work as a real check).
_DUMMY_HASH_CACHE: dict[str, str] = {}


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int
    require_upper: bool
    require_digit: bool
    require_symbol: bool
    reuse_depth: int

    @classmethod
    def current(cls) -> PasswordPolicy:
        return cls(
            min_length=effective_int("password_min_length"),
            require_upper=effective_bool("password_require_uppercase"),
            require_digit=effective_bool("password_require_digit"),
            require_symbol=effective_bool("password_require_symbol"),
            reuse_depth=effective_int("password_history_reuse_depth"),
        )


def _is_symbol(ch: str) -> bool:
    return not (ch.isalpha() or ch.isdigit() or ch.isspace())


def policy_failures(password: str, policy: PasswordPolicy) -> list[str]:
    """Machine codes of the rules a password breaks (pure; property-tested)."""
    failures: list[str] = []
    if len(password) < policy.min_length:
        failures.append("MIN_LENGTH")
    if len(password) > MAX_LENGTH:
        failures.append("MAX_LENGTH")
    if policy.require_upper and not any(ch.isupper() for ch in password):
        failures.append("UPPERCASE_REQUIRED")
    if policy.require_digit and not any(ch.isdigit() for ch in password):
        failures.append("DIGIT_REQUIRED")
    if policy.require_symbol and not any(_is_symbol(ch) for ch in password):
        failures.append("SYMBOL_REQUIRED")
    return failures


def recent_hashes(user: User, depth: int) -> list[str]:
    """The current hash plus the newest ``depth - 1`` history hashes (= the last ``depth`` passwords)."""
    hashes: list[str] = []
    cred = Credential.objects.filter(user=user).first()
    if cred is not None:
        hashes.append(cred.password_hash)
    if depth > len(hashes):
        hashes.extend(
            PasswordHistory.objects.filter(user=user)
            .order_by("-set_at", "-id")
            .values_list("password_hash", flat=True)[: depth - len(hashes)]
        )
    return hashes[:depth]


def validate_new_password(user: User | None, password: str) -> None:
    policy = PasswordPolicy.current()
    failures = policy_failures(password, policy)
    if user is not None and not failures:
        if any(check_password(password, h) for h in recent_hashes(user, policy.reuse_depth)):
            failures.append("RECENTLY_USED")
    if failures:
        raise PasswordPolicyViolation(
            "the password does not satisfy the password policy (DEC-051)",
            errors=[FieldError("password", code) for code in failures],
        )


def hash_password(password: str) -> str:
    return make_password(password)


def verify_password(password: str, encoded: str | None) -> bool:
    """Constant-work check: a missing hash is checked against a dummy hash (no enumeration by timing)."""
    if encoded is None:
        dummy = _DUMMY_HASH_CACHE.get("dummy")
        if dummy is None:  # hash of a random value, same hasher and work factor as real credentials
            dummy = make_password(secrets.token_urlsafe(16))
            _DUMMY_HASH_CACHE["dummy"] = dummy
        check_password(password, dummy)
        return False
    return check_password(password, encoded)


def write_credential(
    user: User,
    password: str,
    *,
    now: datetime,
    one_time: bool,
    set_by_id: uuid.UUID | None,
) -> Credential:
    """Store a new password hash (old hash -> append-only history). Caller validated the policy and holds the
    user row lock inside a unit of work."""
    encoded = hash_password(password)
    cred = Credential.objects.select_for_update().filter(user=user).first()
    one_time_expires = now + effective_hours("password_initial_validity_hours") if one_time else None
    expires = None if one_time else now + effective_days("password_max_age_days")
    must_change = one_time and effective_bool("password_change_at_first_login")
    if one_time and not must_change:
        # ck_credential_one_time_expiry: a one-time credential always forces the change
        must_change = True
    if cred is None:
        return Credential.objects.create(
            user=user,
            password_hash=encoded,
            set_at=now,
            set_by_id=set_by_id,
            must_change=must_change,
            is_one_time=one_time,
            one_time_expires_at=one_time_expires,
            expires_at=expires,
        )
    PasswordHistory.objects.create(user=user, password_hash=cred.password_hash, set_at=cred.set_at)
    Credential.objects.filter(pk=cred.pk).update(
        password_hash=encoded,
        set_at=now,
        set_by_id=set_by_id,
        must_change=must_change,
        is_one_time=one_time,
        one_time_expires_at=one_time_expires,
        expires_at=expires,
    )
    cred.refresh_from_db()
    return cred


def must_change(cred: Credential | None, now: datetime) -> bool:
    """True if the user must change the password before doing anything else (one-time or rotation due)."""
    if cred is None:
        return True
    if cred.must_change:
        return True
    return cred.expires_at is not None and cred.expires_at <= now


def one_time_expired(cred: Credential | None, now: datetime) -> bool:
    return bool(
        cred is not None
        and cred.is_one_time
        and cred.one_time_expires_at is not None
        and cred.one_time_expires_at <= now
    )
