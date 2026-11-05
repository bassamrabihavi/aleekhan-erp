"""MFA enrolment, recovery codes and admin reset (DEC-050 APPROVED: TOTP + 10 one-time recovery codes;
admin reset with reason + admin MFA + audit; owner recovery = console command, DEC-054).

* ``start_enrolment``  new PENDING factor with an encrypted random seed; the provisioning URI (QR) is returned
  once and never stored or logged. A previous PENDING factor is revoked. Refused while an ACTIVE factor exists
  (reset first).
* ``confirm_enrolment`` first valid TOTP code -> factor ACTIVE, ``user.mfa_enrolled``, the session counts as
  MFA-verified, and ``mfa_recovery_code_count`` (10) recovery codes are generated and returned **once**; the
  DB
  keeps only ``sha256$<hex>`` of each (single use: ``used_at`` is set once, trigger).
* ``reset_user_mfa``    holder of ``platform.identity.user.reset_mfa`` + fresh MFA + reason; never on oneself
  (the owner's own recovery is the console command, DEC-054). Factors -> REVOKED (secret removed), unused
  recovery codes invalidated, all sessions of the user revoked (MFA_RESET).

Recovery codes carry 50 random bits (10 base32 characters), so a fast hash is adequate (the codes are not
human-chosen); they are bound to the user id inside the hash.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from typing import Final

from platform_core.authz.policy import Caller, require_permission, require_step_up
from platform_core.engine.context import db_now
from platform_core.engine.errors import (
    AccessDenied,
    FieldError,
    InvalidCredentials,
    NotFound,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.engine.uow import UnitOfWork, unit_of_work
from platform_core.models import AuditOutcome
from platform_core.params.values import effective, effective_int

from . import crypto, sessions, totp
from .models import MfaFactor, MfaFactorStatus, MfaMethod, RecoveryCode, Session, SessionEndReason, User

RECOVERY_CHARS: Final = 10


@dataclass(frozen=True)
class Enrolment:
    factor_id: uuid.UUID
    provisioning_uri: str  # shown once


def recovery_hash(user_id: uuid.UUID, code: str) -> str:
    norm = code.strip().replace("-", "").replace(" ", "").upper()
    return "sha256$" + hashlib.sha256(user_id.bytes + b":" + norm.encode("ascii", "ignore")).hexdigest()


def _new_recovery_code() -> str:
    raw = base64.b32encode(secrets.token_bytes(8)).decode("ascii")[:RECOVERY_CHARS]
    return f"{raw[:5]}-{raw[5:]}"


def _audit(uow: UnitOfWork, action: str, event_type: str, factor: MfaFactor, *, reason: str = "") -> None:
    uow.audit(
        action=action,
        resource_type="platform.mfa_factor",
        resource_id=str(factor.pk),
        resource_version=factor.row_version,
        after={"status": factor.status, "method": factor.method},
        reason=reason,
        scope={"user_id": str(factor.user_id)},
    )
    uow.emit(
        event_type=event_type,
        aggregate_type="platform.mfa_factor",
        aggregate_id=str(factor.pk),
        aggregate_version=factor.row_version,
        payload={"id": str(factor.pk), "user_id": str(factor.user_id), "status": factor.status},
    )


def _revoke(uow: UnitOfWork, factor: MfaFactor, *, by: uuid.UUID | None, reason: str) -> None:
    MfaFactor.objects.filter(pk=factor.pk).update(
        status=MfaFactorStatus.REVOKED,
        secret_ciphertext=None,
        key_ref="",
        revoked_at=db_now(),
        revoked_by_id=by,
        revoke_reason=reason[:500],
    )
    factor.refresh_from_db()
    _audit(uow, "platform.identity.mfa.revoke", "platform.identity.mfa.revoked", factor, reason=reason)


def start_enrolment(caller: Caller, *, request_id: uuid.UUID | None = None) -> Enrolment:
    if effective("mfa_method") != MfaMethod.TOTP:
        raise StateTransitionNotAllowed("only TOTP is approved (DEC-050)")
    with unit_of_work(caller.context(request_id)) as uow:
        user = User.objects.select_for_update().get(pk=caller.user_id)
        if MfaFactor.objects.filter(user=user, status=MfaFactorStatus.ACTIVE).exists():
            raise StateTransitionNotAllowed("an active MFA factor exists; it must be reset first")
        for old in MfaFactor.objects.select_for_update().filter(user=user, status=MfaFactorStatus.PENDING):
            _revoke(uow, old, by=user.pk, reason="superseded by a new enrolment")
        secret = totp.new_secret()
        key_ref, blob = crypto.encrypt(secret, aad=b"mfa:" + user.pk.bytes)
        factor = MfaFactor.objects.create(
            user=user, method=MfaMethod.TOTP, secret_ciphertext=blob, key_ref=key_ref
        )
        _audit(uow, "platform.identity.mfa.enrol_start", "platform.identity.mfa.enrolment_started", factor)
    return Enrolment(factor.pk, totp.provisioning_uri(secret, account=user.username))


def confirm_enrolment(caller: Caller, code: str, *, request_id: uuid.UUID | None = None) -> list[str]:
    """Returns the recovery codes (shown once)."""
    wrong = False
    codes: list[str] = []
    with unit_of_work(caller.context(request_id)) as uow:
        user = User.objects.select_for_update().get(pk=caller.user_id)
        factor = (
            MfaFactor.objects.select_for_update().filter(user=user, status=MfaFactorStatus.PENDING).first()
        )
        if factor is None or factor.secret_ciphertext is None:
            raise StateTransitionNotAllowed("no MFA enrolment is pending")
        now = db_now()
        secret = crypto.decrypt(
            bytes(factor.secret_ciphertext), key_ref=factor.key_ref, aad=b"mfa:" + user.pk.bytes
        )
        step = totp.match_step(secret, code.strip(), now.timestamp(), last_used_step=None)
        if step is None:
            uow.audit(
                action="platform.identity.mfa.enrol_confirm",
                resource_type="platform.mfa_factor",
                resource_id=str(factor.pk),
                outcome=AuditOutcome.DENIED,
                scope={"user_id": str(user.pk)},
            )
            uow.emit(
                event_type="platform.identity.mfa.enrolment_failed",
                aggregate_type="platform.mfa_factor",
                aggregate_id=str(factor.pk),
                aggregate_version=factor.row_version,
                payload={"id": str(factor.pk)},
            )
            wrong = True
        else:
            MfaFactor.objects.filter(pk=factor.pk).update(
                status=MfaFactorStatus.ACTIVE, confirmed_at=now, last_used_step=step
            )
            factor.refresh_from_db()
            User.objects.filter(pk=user.pk).update(mfa_enrolled=True)
            generation = uuid.uuid4()
            for _ in range(effective_int("mfa_recovery_code_count")):
                plain = _new_recovery_code()
                RecoveryCode.objects.create(
                    user=user, generation=generation, code_hash=recovery_hash(user.pk, plain)
                )
                codes.append(plain)
            if caller.session_id is not None:
                session = Session.objects.select_for_update().get(pk=caller.session_id)
                sessions.mark_step_up(uow, session, now)
            _audit(uow, "platform.identity.mfa.enrol_confirm", "platform.identity.mfa.enrolled", factor)
    if wrong:
        raise InvalidCredentials()
    return codes


def reset_user_mfa(
    caller: Caller, user_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> int:
    """Admin reset (DEC-050 R2). Returns the number of revoked factors."""
    require_permission(caller, "platform.identity.user.reset_mfa")
    require_step_up(caller, "platform.identity.user.reset_mfa")
    text = reason.strip()
    if len(text) < 3:
        raise ValidationFailed("a reason is required", errors=[FieldError("reason", "REQUIRED")])
    if user_id == caller.user_id:
        raise AccessDenied("own MFA is reset through the console recovery command (DEC-054)")
    with unit_of_work(caller.context(request_id)) as uow:
        target = User.objects.select_for_update().filter(pk=user_id).first()
        if target is None:
            raise NotFound()
        return reset_factors(uow, target, by=caller.user_id, reason=text)


def reset_factors(uow: UnitOfWork, target: User, *, by: uuid.UUID | None, reason: str) -> int:
    """Shared by the admin reset and the console recovery (caller holds the user row lock)."""
    factors = list(
        MfaFactor.objects.select_for_update().filter(
            user=target, status__in=[MfaFactorStatus.PENDING, MfaFactorStatus.ACTIVE]
        )
    )
    for f in factors:
        _revoke(uow, f, by=by, reason=reason)
    now = db_now()
    RecoveryCode.objects.filter(user=target, used_at__isnull=True).update(used_at=now)
    User.objects.filter(pk=target.pk).update(mfa_enrolled=False)
    sessions.revoke_user_sessions(uow, target.pk, SessionEndReason.MFA_RESET, revoked_by_id=by, note=reason)
    uow.audit(
        action="platform.identity.user.reset_mfa",
        resource_type="platform.user",
        resource_id=str(target.pk),
        reason=reason,
        after={"revoked_factors": len(factors)},
    )
    return len(factors)
