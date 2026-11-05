"""Identity, credentials, sessions, roles and permissions (PHASE_01 / 01.2).

Design: docs/discovery/DATA_TABLE.md (PHASE_01 section), STATE_TRANSITIONS.md section 4.1/4.2/4.8,
docs/security/PERMISSION_MATRIX_DRAFT.md (APPROVED v1.0, DEC-049), docs/db/ERD.md section PHASE_01.

Decisions reflected in the schema (APPROVED 2026-11-04, control/decisions/DECISION_LOG.md):

* DEC-003: users only created inside the system (no AD/LDAP/SSO column exists); a TECHNICAL role never holds a
  business-approval permission (trigger ``trg_role_permission_no_ba_in_technical``).
* DEC-032: role assignments of roles holding a business-approval permission need a second person
  (``requires_second_approval`` forced by trigger; ACTIVE only with an APPROVED request decided by someone
  else).
* DEC-050: TOTP only (CHECK); recovery codes stored as hashes only.
* DEC-051: password history (hashes only), one-time initial password with expiry, lockout fields; the numbers
  themselves are versioned parameters (platform_parameter_value), never constants here.
* DEC-052: personal operator accounts only (``OPERATOR``), always INTERNAL_ONLY (CHECK).
* DEC-054: at most one sealed break-glass account (partial unique) + append-only usage record; no API.

Exclusion constraints, triggers and the FK/index renaming are raw SQL in migration 0008 (see its docstring).
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import CheckConstraint, ExpressionWrapper, F, Q, UniqueConstraint, Value
from django.db.models.functions import Coalesce, Now

from platform_core.schema_common import (
    DECISION_ID_PATTERN,
    MATRIX_VERSION_PATTERN,
    MODULE_PATTERN,
    PASSWORD_HASH_PATTERN,
    PERMISSION_PATTERN,
    SHA256_PATTERN,
    SYNTHETIC_LABEL,
    SYSTEM_KEY_PATTERN,
    USERNAME_PATTERN,
    NetworkZone,
    Provenance,
    Sensitivity,
    in_values,
    min_length,
)


def _user_fk(related_name: str = "+", *, null: bool = True) -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        "platform_core.User",
        on_delete=models.PROTECT,
        null=null,
        blank=null,
        related_name=related_name,
        db_index=False,
    )


# ------------------------------------------------------------------------------------------------- user
class UserStatus(models.TextChoices):
    CREATED = "CREATED", "Created (initial one-time password not yet changed)"
    ACTIVE = "ACTIVE", "Active"
    LOCKED = "LOCKED", "Locked (automatic, until locked_until or unlock)"
    DISABLED = "DISABLED", "Disabled (never deleted)"


class AccountKind(models.TextChoices):
    PERSON = "PERSON", "Personal account"
    OPERATOR = "OPERATOR", "Personal shop-floor operator account (internal network only, DEC-052)"


class NetworkPolicy(models.TextChoices):
    INTERNAL_ONLY = "INTERNAL_ONLY", "Factory network only"
    ANY_WITH_MFA_OUTSIDE = "ANY_WITH_MFA_OUTSIDE", "Any network, MFA required outside (DEC-042)"


class User(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=64)
    display_name = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=UserStatus.choices, db_default=UserStatus.CREATED)
    account_kind = models.CharField(max_length=16, choices=AccountKind.choices)
    network_policy = models.CharField(max_length=24, choices=NetworkPolicy.choices)
    mfa_enrolled = models.BooleanField(db_default=False)
    # DEC-054 (A, before production): the sealed emergency account. Flag only; no API creates or uses it.
    is_break_glass = models.BooleanField(db_default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)
    failed_login_count = models.IntegerField(db_default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    status_changed_at = models.DateTimeField(db_default=Now())
    provenance = models.CharField(max_length=16, choices=Provenance.choices, db_default=Provenance.SYS)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    # NULL only for the console bootstrap of the first owner (audited as system bootstrap, DEC-003/DEC-054).
    created_by = _user_fk()
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_user"
        constraints = [
            UniqueConstraint(fields=["username"], name="uq_user_username"),
            UniqueConstraint(
                fields=["is_break_glass"], condition=Q(is_break_glass=True), name="uq_user_single_break_glass"
            ),
            CheckConstraint(condition=Q(username__regex=USERNAME_PATTERN), name="ck_user_username_fmt"),
            CheckConstraint(condition=~Q(display_name=""), name="ck_user_display_name_nonempty"),
            CheckConstraint(condition=in_values("status", UserStatus.values), name="ck_user_status"),
            CheckConstraint(
                condition=in_values("account_kind", AccountKind.values), name="ck_user_account_kind"
            ),
            CheckConstraint(
                condition=in_values("network_policy", NetworkPolicy.values), name="ck_user_network_policy"
            ),
            CheckConstraint(
                condition=~Q(account_kind=AccountKind.OPERATOR)
                | Q(network_policy=NetworkPolicy.INTERNAL_ONLY),
                name="ck_user_operator_internal_only",
            ),
            CheckConstraint(
                condition=~Q(status=UserStatus.LOCKED) | Q(locked_until__isnull=False),
                name="ck_user_locked_has_until",
            ),
            CheckConstraint(
                condition=~Q(is_break_glass=True) | Q(account_kind=AccountKind.PERSON),
                name="ck_user_break_glass_person",
            ),
            CheckConstraint(condition=Q(failed_login_count__gte=0), name="ck_user_failed_count_nonneg"),
            CheckConstraint(
                condition=in_values("provenance", [Provenance.SYS, Provenance.SEED_SYNTHETIC]),
                name="ck_user_provenance",
            ),
            CheckConstraint(
                condition=~Q(provenance=Provenance.SEED_SYNTHETIC)
                | Q(display_name__contains=SYNTHETIC_LABEL),
                name="ck_user_synthetic_label",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_user_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["status"], name="ix_user_status"),
            models.Index(fields=["created_by"], name="ix_user_created_by"),
            models.Index(fields=["updated_by"], name="ix_user_updated_by"),
        ]

    def __str__(self) -> str:
        return f"{self.username} [{self.status}]"


class Credential(models.Model):
    """Current password hash (1:1). Policy values (length, rotation, one-time expiry): DEC-051 parameters."""

    user = models.OneToOneField(
        User, on_delete=models.PROTECT, primary_key=True, related_name="credential", db_column="user_id"
    )
    password_hash = models.CharField(max_length=256)
    set_at = models.DateTimeField(db_default=Now())
    set_by = _user_fk()
    must_change = models.BooleanField(db_default=True)
    is_one_time = models.BooleanField(db_default=False)
    one_time_expires_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # rotation deadline (DEC-051: 90 days)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_credential"
        constraints = [
            CheckConstraint(
                condition=Q(password_hash__regex=PASSWORD_HASH_PATTERN), name="ck_credential_hash_fmt"
            ),
            CheckConstraint(
                condition=~Q(is_one_time=True) | Q(one_time_expires_at__isnull=False, must_change=True),
                name="ck_credential_one_time_expiry",
            ),
            CheckConstraint(
                condition=Q(one_time_expires_at__isnull=True) | Q(one_time_expires_at__gt=F("set_at")),
                name="ck_credential_one_time_after_set",
            ),
            CheckConstraint(
                condition=Q(expires_at__isnull=True) | Q(expires_at__gt=F("set_at")),
                name="ck_credential_expiry_after_set",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_credential_row_version_pos"),
        ]
        indexes = [models.Index(fields=["set_by"], name="ix_credential_set_by")]

    def __str__(self) -> str:
        return f"credential of {self.user_id}"


class PasswordHistory(models.Model):
    """Previous password hashes (append-only; DEC-051 rotation). Never a clear password."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+", db_index=False)
    password_hash = models.CharField(max_length=256)
    set_at = models.DateTimeField()
    recorded_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "platform_password_history"
        constraints = [
            CheckConstraint(
                condition=Q(password_hash__regex=PASSWORD_HASH_PATTERN), name="ck_password_history_hash_fmt"
            ),
        ]
        indexes = [models.Index(fields=["user", "set_at"], name="ix_password_history_user")]

    def __str__(self) -> str:
        return f"password history {self.user_id} @ {self.set_at}"


class MfaMethod(models.TextChoices):
    TOTP = "TOTP", "Time-based one-time password (DEC-050)"


class MfaFactorStatus(models.TextChoices):
    PENDING = "PENDING", "Enrolment started, not confirmed"
    ACTIVE = "ACTIVE", "Active"
    REVOKED = "REVOKED", "Revoked (secret removed, metadata kept)"


class MfaFactor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="mfa_factors", db_index=False)
    method = models.CharField(max_length=8, choices=MfaMethod.choices, db_default=MfaMethod.TOTP)
    status = models.CharField(
        max_length=8, choices=MfaFactorStatus.choices, db_default=MfaFactorStatus.PENDING
    )
    # Encrypted with a key from the secret store (key_ref names it); the key itself is never in the DB.
    secret_ciphertext = models.BinaryField(null=True, blank=True)
    key_ref = models.CharField(max_length=64, blank=True, default="")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_step = models.BigIntegerField(null=True, blank=True)  # TOTP replay guard (monotonic, trigger)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = _user_fk()
    revoke_reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_mfa_factor"
        constraints = [
            UniqueConstraint(
                fields=["user", "method"],
                condition=Q(status=MfaFactorStatus.ACTIVE),
                name="uq_mfa_factor_one_active",
            ),
            UniqueConstraint(
                fields=["user"], condition=Q(status=MfaFactorStatus.PENDING), name="uq_mfa_factor_one_pending"
            ),
            CheckConstraint(condition=in_values("method", MfaMethod.values), name="ck_mfa_factor_method"),
            CheckConstraint(
                condition=in_values("status", MfaFactorStatus.values), name="ck_mfa_factor_status"
            ),
            CheckConstraint(
                condition=Q(status=MfaFactorStatus.REVOKED)
                | Q(secret_ciphertext__isnull=False, revoked_at__isnull=True),
                name="ck_mfa_factor_live_has_secret",
            ),
            CheckConstraint(
                condition=~Q(status=MfaFactorStatus.REVOKED)
                | Q(secret_ciphertext__isnull=True, revoked_at__isnull=False),
                name="ck_mfa_factor_revoked_no_secret",
            ),
            CheckConstraint(
                condition=~Q(status=MfaFactorStatus.ACTIVE) | Q(confirmed_at__isnull=False),
                name="ck_mfa_factor_active_confirmed",
            ),
            CheckConstraint(
                condition=Q(secret_ciphertext__isnull=True) | ~Q(key_ref=""), name="ck_mfa_factor_key_ref"
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_mfa_factor_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["user", "status"], name="ix_mfa_factor_user"),
            models.Index(fields=["revoked_by"], name="ix_mfa_factor_revoked_by"),
        ]

    def __str__(self) -> str:
        return f"{self.method} factor of {self.user_id} [{self.status}]"


class RecoveryCode(models.Model):
    """One-time recovery code (DEC-050: 10 per generation), hash only; used_at is set exactly once."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+", db_index=False)
    generation = models.UUIDField()
    code_hash = models.CharField(max_length=256)
    created_at = models.DateTimeField(db_default=Now())
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "platform_recovery_code"
        constraints = [
            UniqueConstraint(fields=["user", "code_hash"], name="uq_recovery_code_user_hash"),
            CheckConstraint(
                condition=Q(code_hash__regex=PASSWORD_HASH_PATTERN), name="ck_recovery_code_hash_fmt"
            ),
        ]
        indexes = [models.Index(fields=["user", "generation"], name="ix_recovery_code_user_gen")]

    def __str__(self) -> str:
        return f"recovery code {self.pk} of {self.user_id}"


class SessionState(models.TextChoices):
    MFA_PENDING = "MFA_PENDING", "Password ok, MFA pending"
    ACTIVE = "ACTIVE", "Active"
    EXPIRED = "EXPIRED", "Expired (idle/absolute timeout)"
    REVOKED = "REVOKED", "Revoked"
    LOGGED_OUT = "LOGGED_OUT", "Logged out"


SESSION_LIVE = [SessionState.MFA_PENDING, SessionState.ACTIVE]
SESSION_ENDED = [SessionState.EXPIRED, SessionState.REVOKED, SessionState.LOGGED_OUT]


class SessionEndReason(models.TextChoices):
    IDLE_TIMEOUT = "IDLE_TIMEOUT", "Idle timeout"
    ABSOLUTE_TIMEOUT = "ABSOLUTE_TIMEOUT", "Absolute timeout"
    MFA_TIMEOUT = "MFA_TIMEOUT", "MFA not completed in time"
    LOGOUT = "LOGOUT", "Logout"
    SELF_REVOKE = "SELF_REVOKE", "Revoked by the user"
    ADMIN_REVOKE = "ADMIN_REVOKE", "Revoked by an administrator"
    USER_DISABLED = "USER_DISABLED", "User disabled"
    PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed or reset"
    MFA_RESET = "MFA_RESET", "MFA reset"
    # 01.3 (migration 0011): the oldest live session ended on a new login (DEC-051, Q-0101 END_OLDEST_SESSION)
    CONCURRENT_LIMIT = "CONCURRENT_LIMIT", "Ended by the concurrent-session limit (oldest session)"


class Session(models.Model):
    """Server-side session. ``id`` is the public handle; the cookie value is stored only as SHA-256."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_key_hash = models.CharField(max_length=64)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sessions", db_index=False)
    state = models.CharField(max_length=16, choices=SessionState.choices)
    created_at = models.DateTimeField(db_default=Now())
    last_seen_at = models.DateTimeField(db_default=Now())
    idle_expires_at = models.DateTimeField()
    absolute_expires_at = models.DateTimeField()
    mfa_verified_at = models.DateTimeField(null=True, blank=True)
    network_zone = models.CharField(max_length=8, choices=NetworkZone.choices)
    client_ip = models.GenericIPAddressField(null=True, blank=True)  # from the trusted proxy (DEC-052)
    user_agent_hash = models.CharField(max_length=64, blank=True, default="")
    ended_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(max_length=20, choices=SessionEndReason.choices, blank=True, default="")
    revoked_by = _user_fk()
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_session"
        constraints = [
            UniqueConstraint(fields=["session_key_hash"], name="uq_session_key_hash"),
            CheckConstraint(
                condition=Q(session_key_hash__regex=SHA256_PATTERN), name="ck_session_key_hash_fmt"
            ),
            CheckConstraint(condition=in_values("state", SessionState.values), name="ck_session_state"),
            CheckConstraint(condition=in_values("network_zone", NetworkZone.values), name="ck_session_zone"),
            CheckConstraint(
                condition=in_values("end_reason", ["", *SessionEndReason.values]),
                name="ck_session_end_reason",
            ),
            CheckConstraint(
                condition=Q(user_agent_hash="") | Q(user_agent_hash__regex=SHA256_PATTERN),
                name="ck_session_ua_hash_fmt",
            ),
            CheckConstraint(
                condition=~in_values("state", SESSION_LIVE) | Q(ended_at__isnull=True, end_reason=""),
                name="ck_session_live_not_ended",
            ),
            CheckConstraint(
                condition=~in_values("state", SESSION_ENDED)
                | (Q(ended_at__isnull=False) & ~Q(end_reason="")),
                name="ck_session_ended_has_reason",
            ),
            CheckConstraint(
                condition=Q(absolute_expires_at__gt=F("created_at")), name="ck_session_absolute_after_create"
            ),
            CheckConstraint(
                condition=Q(idle_expires_at__lte=F("absolute_expires_at")), name="ck_session_idle_le_absolute"
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_session_row_version_pos"),
        ]
        indexes = [
            models.Index(
                fields=["user", "created_at"],
                name="ix_session_user_live",
                condition=Q(state__in=SESSION_LIVE),
            ),
            models.Index(
                fields=["absolute_expires_at"], name="ix_session_expiry", condition=Q(state__in=SESSION_LIVE)
            ),
            models.Index(fields=["user", "created_at"], name="ix_session_user"),
            models.Index(fields=["revoked_by"], name="ix_session_revoked_by"),
        ]

    def __str__(self) -> str:
        return f"session {self.id} [{self.state}]"


class LoginOutcome(models.TextChoices):
    OK = "OK", "Password accepted"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS", "Wrong username or password"
    LOCKED = "LOCKED", "Account locked"
    DISABLED = "DISABLED", "Account disabled"
    ONE_TIME_EXPIRED = "ONE_TIME_EXPIRED", "Initial one-time password expired (DEC-051)"
    NETWORK_POLICY_DENIED = "NETWORK_POLICY_DENIED", "Internal-only account from outside (DEC-042/052)"
    MFA_OK = "MFA_OK", "MFA code accepted"
    MFA_FAILED = "MFA_FAILED", "MFA code rejected"
    RECOVERY_CODE_USED = "RECOVERY_CODE_USED", "Recovery code used (DEC-050)"
    # 01.3 rework (REV-0114, migration 0012): correct password, refused: MFA applies (outside login) and
    # the user has no MFA factor yet - a refusal, never a success, and it does not reset the lockout window
    MFA_ENROLMENT_REQUIRED = "MFA_ENROLMENT_REQUIRED", "Refused: MFA required but not enrolled"


class LoginAttempt(models.Model):
    """Login-ceremony security event. Append-only; deletable only after the DEC-032 retention (trigger)."""

    id = models.BigAutoField(primary_key=True)
    occurred_at = models.DateTimeField(db_default=Now())
    username_attempted = models.CharField(max_length=64)  # normalised; may not exist; never the password
    user = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    outcome = models.CharField(max_length=24, choices=LoginOutcome.choices)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    network_zone = models.CharField(max_length=8, choices=NetworkZone.choices)
    request_id = models.UUIDField(null=True, blank=True)
    session = models.ForeignKey(
        Session, on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )

    class Meta:
        db_table = "platform_login_attempt"
        constraints = [
            CheckConstraint(
                condition=in_values("outcome", LoginOutcome.values), name="ck_login_attempt_outcome"
            ),
            CheckConstraint(
                condition=in_values("network_zone", NetworkZone.values), name="ck_login_attempt_zone"
            ),
        ]
        indexes = [
            models.Index(fields=["username_attempted", "occurred_at"], name="ix_login_attempt_username"),
            models.Index(fields=["user", "occurred_at"], name="ix_login_attempt_user"),
            models.Index(fields=["client_ip", "occurred_at"], name="ix_login_attempt_ip"),
            models.Index(fields=["occurred_at"], name="ix_login_attempt_occurred"),
            models.Index(fields=["session"], name="ix_login_attempt_session"),
        ]

    # ------------------------------------------------------------------------------------- roles/permissions

    def __str__(self) -> str:
        return f"login {self.username_attempted} {self.outcome}"


class Permission(models.Model):
    """Action catalogue (seeded by reviewed migrations only; the app role has SELECT only)."""

    action = models.CharField(max_length=120, primary_key=True)
    module = models.CharField(max_length=32)
    description_fa = models.CharField(max_length=300)
    # '' = not classified by the approved matrix v1.0 (DEC-049 gives no per-action class; not invented here)
    sensitivity = models.CharField(max_length=2, choices=Sensitivity.choices, blank=True, default="")
    mfa_step_up = models.BooleanField()
    business_approval = models.BooleanField()
    maker_checker = models.BooleanField()  # SoD: decider != maker (DEC-032)
    matrix_version = models.CharField(max_length=16)
    decision_id = models.CharField(max_length=7)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "platform_permission"
        constraints = [
            CheckConstraint(condition=Q(action__regex=PERMISSION_PATTERN), name="ck_permission_action_fmt"),
            CheckConstraint(condition=Q(module__regex=MODULE_PATTERN), name="ck_permission_module_fmt"),
            CheckConstraint(condition=~Q(description_fa=""), name="ck_permission_description_nonempty"),
            CheckConstraint(
                condition=in_values("sensitivity", ["", *Sensitivity.values]),
                name="ck_permission_sensitivity",
            ),
            CheckConstraint(
                condition=~Q(business_approval=True) | Q(maker_checker=True, mfa_step_up=True),
                name="ck_permission_ba_is_sod_and_mfa",
            ),
            CheckConstraint(
                condition=Q(matrix_version__regex=MATRIX_VERSION_PATTERN),
                name="ck_permission_matrix_version_fmt",
            ),
            CheckConstraint(
                condition=Q(decision_id__regex=DECISION_ID_PATTERN), name="ck_permission_decision_fmt"
            ),
        ]

    def __str__(self) -> str:
        return self.action


class RoleKind(models.TextChoices):
    TECHNICAL = "TECHNICAL", "Technical (never business approval, DEC-003)"
    BUSINESS = "BUSINESS", "Business"


class RoleStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    RETIRED = "RETIRED", "Retired"


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64)
    name_fa = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=RoleKind.choices)
    status = models.CharField(max_length=8, choices=RoleStatus.choices, db_default=RoleStatus.DRAFT)
    matrix_version = models.CharField(max_length=16, blank=True, default="")
    decision_id = models.CharField(max_length=7, blank=True, default="")
    provenance = models.CharField(max_length=16, choices=Provenance.choices, db_default=Provenance.SYS)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk()
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_role"
        constraints = [
            UniqueConstraint(fields=["code"], name="uq_role_code"),
            CheckConstraint(condition=Q(code__regex=SYSTEM_KEY_PATTERN), name="ck_role_code_fmt"),
            CheckConstraint(condition=~Q(name_fa=""), name="ck_role_name_nonempty"),
            CheckConstraint(condition=in_values("kind", RoleKind.values), name="ck_role_kind"),
            CheckConstraint(condition=in_values("status", RoleStatus.values), name="ck_role_status"),
            CheckConstraint(
                condition=Q(matrix_version="") | Q(matrix_version__regex=MATRIX_VERSION_PATTERN),
                name="ck_role_matrix_version_fmt",
            ),
            # an ACTIVE role always names the approved matrix version it matches (DEC-049)
            CheckConstraint(
                condition=~Q(status=RoleStatus.ACTIVE) | ~Q(matrix_version=""),
                name="ck_role_active_has_matrix",
            ),
            CheckConstraint(
                condition=Q(decision_id="") | Q(decision_id__regex=DECISION_ID_PATTERN),
                name="ck_role_decision_fmt",
            ),
            CheckConstraint(
                condition=in_values("provenance", [Provenance.SYS, Provenance.MIGRATION_SEED]),
                name="ck_role_provenance",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_role_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["created_by"], name="ix_role_created_by"),
            models.Index(fields=["updated_by"], name="ix_role_updated_by"),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.kind}, {self.status})"


class GrantMode(models.TextChoices):
    SCOPE = "SCOPE", "Within the assignment scope (matrix ●)"
    OWN = "OWN", "Own records only (matrix ○)"
    OWN_UNIT = "OWN_UNIT", "Own org unit only (matrix '● own unit')"
    OWN_AND_OWN_UNIT = "OWN_AND_OWN_UNIT", "Own records + own org unit (matrix '○ + own unit')"


class RolePermission(models.Model):
    """Role -> permission. Editable only while the role is DRAFT (trigger); TECHNICAL roles get no BA rows."""

    id = models.BigAutoField(primary_key=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="grants", db_index=False)
    permission = models.ForeignKey(
        Permission, on_delete=models.PROTECT, related_name="+", db_column="permission_action", db_index=False
    )
    grant_mode = models.CharField(max_length=20, choices=GrantMode.choices)
    # documents only: highest document sensitivity class visible through this grant (matrix: S1 / S1-S2)
    max_sensitivity = models.CharField(max_length=2, blank=True, default="")
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "platform_role_permission"
        constraints = [
            UniqueConstraint(fields=["role", "permission"], name="uq_role_permission_pair"),
            CheckConstraint(
                condition=in_values("grant_mode", GrantMode.values), name="ck_role_permission_mode"
            ),
            CheckConstraint(
                condition=in_values("max_sensitivity", ["", "S1", "S2", "S3"]),
                name="ck_role_permission_max_sensitivity",
            ),
        ]
        indexes = [models.Index(fields=["permission"], name="ix_role_permission_permission")]

    def __str__(self) -> str:
        return f"{self.role_id} -> {self.permission_id} ({self.grant_mode})"


class ScopeKind(models.TextChoices):
    GLOBAL = "GLOBAL", "Global"
    ORG_UNIT = "ORG_UNIT", "One org unit"
    ORG_UNIT_SUBTREE = "ORG_UNIT_SUBTREE", "Org unit and its subtree"


class AssignmentStatus(models.TextChoices):
    PENDING_APPROVAL = "PENDING_APPROVAL", "Waiting for a second person (DEC-032)"
    ACTIVE = "ACTIVE", "Active"
    EXPIRED = "EXPIRED", "Expired (valid_to reached)"
    REVOKED = "REVOKED", "Revoked"


class GrantedVia(models.TextChoices):
    ADMIN = "ADMIN", "Granted in the application by an authorised user"
    CONSOLE_BOOTSTRAP = (
        "CONSOLE_BOOTSTRAP",
        "Console bootstrap of the first owner (TECHNICAL role only, DEC-049)",
    )


class RoleAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="role_assignments", db_index=False)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="assignments", db_index=False)
    scope_kind = models.CharField(max_length=20, choices=ScopeKind.choices)
    scope_unit = models.ForeignKey(
        "platform_core.OrgUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    valid_from = models.DateTimeField(db_default=Now())
    valid_to = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=AssignmentStatus.choices)
    granted_via = models.CharField(max_length=20, choices=GrantedVia.choices, db_default=GrantedVia.ADMIN)
    granted_by = _user_fk()
    # DEC-003: self-assignment is allowed only explicitly and is always visible (generated, never written).
    self_assignment = models.GeneratedField(
        expression=Coalesce(
            ExpressionWrapper(Q(granted_by=F("user")), output_field=models.BooleanField()), Value(False)
        ),
        output_field=models.BooleanField(),
        db_persist=True,
    )
    # DEC-032: forced to "role holds a business-approval permission" by trigger (cannot be set false).
    requires_second_approval = models.BooleanField(db_default=False)
    approval_request = models.ForeignKey(
        "platform_core.ApprovalRequest",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    reason = models.CharField(max_length=500)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = _user_fk()
    revoke_reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_role_assignment"
        constraints = [
            CheckConstraint(
                condition=in_values("status", AssignmentStatus.values), name="ck_role_assignment_status"
            ),
            CheckConstraint(
                condition=in_values("scope_kind", ScopeKind.values), name="ck_role_assignment_scope_kind"
            ),
            CheckConstraint(
                condition=Q(scope_kind=ScopeKind.GLOBAL, scope_unit__isnull=True)
                | Q(
                    scope_kind__in=[ScopeKind.ORG_UNIT, ScopeKind.ORG_UNIT_SUBTREE], scope_unit__isnull=False
                ),
                name="ck_role_assignment_scope_ref",
            ),
            CheckConstraint(
                condition=in_values("granted_via", GrantedVia.values), name="ck_role_assignment_granted_via"
            ),
            CheckConstraint(
                condition=Q(granted_via=GrantedVia.ADMIN, granted_by__isnull=False)
                | Q(granted_via=GrantedVia.CONSOLE_BOOTSTRAP, granted_by__isnull=True),
                name="ck_role_assignment_granted_by",
            ),
            CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=F("valid_from")),
                name="ck_role_assignment_validity",
            ),
            CheckConstraint(condition=Q(min_length("reason", 3)), name="ck_role_assignment_reason"),
            CheckConstraint(
                condition=~Q(status=AssignmentStatus.REVOKED)
                | (Q(revoked_at__isnull=False) & Q(min_length("revoke_reason", 3))),
                name="ck_role_assignment_revoked_reason",
            ),
            CheckConstraint(
                condition=~Q(requires_second_approval=True)
                | ~Q(status=AssignmentStatus.ACTIVE)
                | Q(approval_request__isnull=False),
                name="ck_role_assignment_second_approval",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_role_assignment_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["user", "status"], name="ix_role_assignment_user"),
            models.Index(fields=["role", "status"], name="ix_role_assignment_role"),
            models.Index(fields=["scope_unit"], name="ix_role_assignment_scope_unit"),
            models.Index(fields=["granted_by"], name="ix_role_assignment_granted_by"),
            models.Index(fields=["approval_request"], name="ix_role_assignment_approval"),
            models.Index(fields=["revoked_by"], name="ix_role_assignment_revoked_by"),
            models.Index(fields=["updated_by"], name="ix_role_assignment_updated_by"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} as {self.role_id} [{self.status}]"


class BreakGlassUsage(models.Model):
    """DEC-054 (A): each use of the sealed emergency account. No API; written by the console command only."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+", db_index=False)
    started_at = models.DateTimeField(db_default=Now())
    reason = models.CharField(max_length=500)
    session = models.ForeignKey(
        Session, on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    alerted_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    password_rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "platform_break_glass_usage"
        constraints = [
            CheckConstraint(condition=Q(min_length("reason", 3)), name="ck_break_glass_usage_reason"),
            CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F("started_at")),
                name="ck_break_glass_usage_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "started_at"], name="ix_break_glass_usage_user"),
            models.Index(fields=["session"], name="ix_break_glass_usage_session"),
        ]

    def __str__(self) -> str:
        return f"break-glass use {self.id}"
