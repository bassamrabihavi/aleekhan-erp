"""Stable error-code catalogue and typed exception hierarchy (PHASE_00 / 00.3).

Contract: ``docs/api/openapi-draft.yaml`` (``components.schemas.ErrorCode``,
``components.schemas.Problem`` and ``x-aleekhan-conventions.error_codes``). Codes and HTTP statuses are
*stable*: changing them breaks clients and fails the golden test ``test_error_catalogue_golden``. Persian
texts (``message_fa``) may change; clients must branch on ``code`` only.
Documentation: ``docs/engine/ERROR_CODES.md``.

Errors never carry stack traces, SQL, secrets or PII (Problem schema description). ``detail`` is written by
the engine for developers/operators and must stay generic.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar

PROBLEM_TYPE_BASE = "https://errors.aleekhan.invalid/"
DECISION_ID_RE = re.compile(r"DEC-[0-9]{3}")


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    MFA_REQUIRED = "MFA_REQUIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    PRECONDITION_REQUIRED = "PRECONDITION_REQUIRED"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    IDEMPOTENCY_KEY_REQUIRED = "IDEMPOTENCY_KEY_REQUIRED"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    IDEMPOTENCY_IN_PROGRESS = "IDEMPOTENCY_IN_PROGRESS"
    RULE_NOT_APPROVED = "RULE_NOT_APPROVED"
    STATE_TRANSITION_NOT_ALLOWED = "STATE_TRANSITION_NOT_ALLOWED"
    RATE_LIMITED = "RATE_LIMITED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class ErrorSpec:
    code: ErrorCode
    http_status: int
    title: str
    message_fa: str


_SPECS: tuple[ErrorSpec, ...] = (
    ErrorSpec(ErrorCode.VALIDATION_FAILED, 400, "Validation failed", "مقدار ورودی معتبر نیست."),
    ErrorSpec(
        ErrorCode.AUTHENTICATION_REQUIRED,
        401,
        "Authentication required",
        "برای این کار باید وارد سامانه شوید.",
    ),
    ErrorSpec(ErrorCode.MFA_REQUIRED, 401, "MFA required", "برای این کار تأیید هویت دومرحله‌ای لازم است."),
    ErrorSpec(ErrorCode.ACCESS_DENIED, 403, "Access denied", "شما مجوز انجام این کار را ندارید."),
    ErrorSpec(ErrorCode.NOT_FOUND, 404, "Not found", "مورد درخواستی پیدا نشد."),
    ErrorSpec(
        ErrorCode.METHOD_NOT_ALLOWED, 405, "Method not allowed", "این نوع درخواست برای این مسیر مجاز نیست."
    ),
    ErrorSpec(
        ErrorCode.PRECONDITION_REQUIRED,
        428,
        "Precondition required",
        "نسخه رکورد (If-Match) ارسال نشده است؛ ابتدا رکورد را دوباره بارگذاری کنید.",
    ),
    ErrorSpec(
        ErrorCode.VERSION_CONFLICT,
        412,
        "Version conflict",
        "این رکورد در این فاصله توسط کاربر دیگری تغییر کرده است؛ آن را دوباره بارگذاری کنید.",
    ),
    ErrorSpec(
        ErrorCode.IDEMPOTENCY_KEY_REQUIRED,
        428,
        "Idempotency key required",
        "کلید یکتای درخواست (Idempotency-Key) ارسال نشده است.",
    ),
    ErrorSpec(
        ErrorCode.IDEMPOTENCY_KEY_REUSED,
        422,
        "Idempotency key reused",
        "این کلید یکتا قبلاً برای درخواست دیگری به کار رفته است.",
    ),
    ErrorSpec(
        ErrorCode.IDEMPOTENCY_IN_PROGRESS,
        409,
        "Idempotency key in progress",
        "همین درخواست هنوز در حال پردازش است؛ کمی بعد دوباره تلاش کنید.",
    ),
    ErrorSpec(
        ErrorCode.RULE_NOT_APPROVED,
        409,
        "Rule not approved",
        "قاعده کسب‌وکاری این کار هنوز تصویب نشده است و سامانه آن را انجام نمی‌دهد.",
    ),
    ErrorSpec(
        ErrorCode.STATE_TRANSITION_NOT_ALLOWED,
        409,
        "State transition not allowed",
        "این تغییر وضعیت از وضعیت فعلی مجاز نیست.",
    ),
    ErrorSpec(
        ErrorCode.RATE_LIMITED, 429, "Too many requests", "تعداد درخواست‌ها زیاد است؛ کمی بعد تلاش کنید."
    ),
    ErrorSpec(ErrorCode.PAYLOAD_TOO_LARGE, 413, "Payload too large", "حجم داده ارسالی بیش از حد مجاز است."),
    ErrorSpec(
        ErrorCode.DEPENDENCY_UNAVAILABLE,
        503,
        "Dependency unavailable",
        "یکی از سرویس‌های لازم در دسترس نیست؛ کمی بعد تلاش کنید.",
    ),
    ErrorSpec(ErrorCode.INTERNAL_ERROR, 500, "Internal error", "خطای داخلی رخ داد؛ موضوع ثبت شد."),
)

ERROR_CATALOGUE: Mapping[ErrorCode, ErrorSpec] = {spec.code: spec for spec in _SPECS}


def spec_for(code: ErrorCode) -> ErrorSpec:
    return ERROR_CATALOGUE[code]


@dataclass(frozen=True)
class FieldError:
    """One entry of ``Problem.errors[]`` (``field`` + machine ``code`` + optional Persian text)."""

    field: str
    code: str
    message_fa: str = ""

    def as_dict(self) -> dict[str, str]:
        out = {"field": self.field, "code": self.code}
        if self.message_fa:
            out["message_fa"] = self.message_fa
        return out


MAX_FIELD_ERRORS = 100  # Problem.errors maxItems


class AleekhanError(Exception):
    """Base of every engine/API error. Subclasses bind exactly one :class:`ErrorCode`."""

    code: ClassVar[ErrorCode]

    def __init__(
        self,
        detail: str = "",
        *,
        errors: Sequence[FieldError] = (),
        decision_id: str | None = None,
    ) -> None:
        super().__init__(detail or self.spec.title)
        self.detail = detail
        self.errors: tuple[FieldError, ...] = tuple(errors)[:MAX_FIELD_ERRORS]
        self.decision_id = decision_id

    @property
    def spec(self) -> ErrorSpec:
        return ERROR_CATALOGUE[self.code]

    @property
    def http_status(self) -> int:
        return self.spec.http_status

    @property
    def message_fa(self) -> str:
        return self.spec.message_fa

    def to_problem(self, request_id: uuid.UUID) -> dict[str, Any]:
        """RFC 9457 body matching ``components.schemas.Problem``."""
        spec = self.spec
        body: dict[str, Any] = {
            "type": PROBLEM_TYPE_BASE + spec.code.value,
            "title": spec.title,
            "status": spec.http_status,
            "code": spec.code.value,
            "message_fa": spec.message_fa,
            "request_id": str(request_id),
        }
        if self.detail:
            body["detail"] = self.detail
        if self.decision_id is not None:
            body["decision_id"] = self.decision_id
        if self.errors:
            body["errors"] = [e.as_dict() for e in self.errors]
        return body


class ClientError(AleekhanError):
    """4xx: the request can be corrected by the caller."""


class ServerError(AleekhanError):
    """5xx: not the caller's fault."""


class ConflictError(ClientError):
    """409 family (state / rule / in-flight duplicate)."""


class ValidationFailed(ClientError):
    code = ErrorCode.VALIDATION_FAILED


class AuthenticationRequired(ClientError):
    code = ErrorCode.AUTHENTICATION_REQUIRED


class MfaRequired(ClientError):
    code = ErrorCode.MFA_REQUIRED


class AccessDenied(ClientError):
    code = ErrorCode.ACCESS_DENIED


class NotFound(ClientError):
    """Also used for records outside the caller's scope (BOLA/IDOR: 404, not 403)."""

    code = ErrorCode.NOT_FOUND


class MethodNotAllowed(ClientError):
    code = ErrorCode.METHOD_NOT_ALLOWED


class PreconditionRequired(ClientError):
    code = ErrorCode.PRECONDITION_REQUIRED


class VersionConflict(ClientError):
    code = ErrorCode.VERSION_CONFLICT


class IdempotencyKeyRequired(ClientError):
    code = ErrorCode.IDEMPOTENCY_KEY_REQUIRED


class IdempotencyKeyReused(ClientError):
    code = ErrorCode.IDEMPOTENCY_KEY_REUSED


class IdempotencyInProgress(ConflictError):
    code = ErrorCode.IDEMPOTENCY_IN_PROGRESS


class RuleNotApproved(ConflictError):
    """A business rule whose decision (DEC-###) is not APPROVED. Always carries ``decision_id``."""

    code = ErrorCode.RULE_NOT_APPROVED

    def __init__(self, decision_id: str, detail: str = "") -> None:
        if not DECISION_ID_RE.fullmatch(decision_id):
            raise ValueError(f"decision_id must match DEC-###, got {decision_id!r}")
        super().__init__(detail, decision_id=decision_id)


class StateTransitionNotAllowed(ConflictError):
    code = ErrorCode.STATE_TRANSITION_NOT_ALLOWED


class RateLimited(ClientError):
    code = ErrorCode.RATE_LIMITED


class PayloadTooLarge(ClientError):
    code = ErrorCode.PAYLOAD_TOO_LARGE


class DependencyUnavailable(ServerError):
    code = ErrorCode.DEPENDENCY_UNAVAILABLE


class InternalError(ServerError):
    code = ErrorCode.INTERNAL_ERROR


def _concrete(cls: type[AleekhanError]) -> list[type[AleekhanError]]:
    out: list[type[AleekhanError]] = []
    for sub in cls.__subclasses__():
        if "code" in sub.__dict__:
            out.append(sub)
        out.extend(_concrete(sub))
    return out


EXCEPTION_FOR_CODE: Mapping[ErrorCode, type[AleekhanError]] = {c.code: c for c in _concrete(AleekhanError)}


class EngineContractError(RuntimeError):
    """Programming error: the engine was used against its contract (e.g. a write without audit).

    Not a client error; the API layer maps any unexpected exception to INTERNAL_ERROR.
    """
