"""Shared machinery of the PHASE_01 endpoints.

* :class:`Phase01View` - session authentication + :class:`ScopedPermission` (action permission, MFA step-up,
  then record scope in the view: out of scope -> 404). :class:`SessionView` - the caller's own
  session/profile.
* Request bodies are validated against small field specs (:data:`BODIES`) that mirror the OpenAPI request
  schemas (``additionalProperties: false``: unknown fields -> 400 ``UNKNOWN_FIELD``); a contract test keeps
  the field names and required sets equal to the OpenAPI document.
* Lists: :func:`paginate` (DRF cursor over a stable unique key, scope in the queryset = ``scope_q``) and
  :func:`paginate_filtered` (keyset cursor + the SAME per-record check as the object endpoints, for scopes
  that are not expressible as one queryset filter, e.g. task holders through positions). Both answer
  ``{"items": [...], "page": {"page_size", "next_cursor"}}``.
* Writes: :func:`write` = ``Idempotency-Key`` -> ``engine.idempotency.run_idempotent`` (one transaction:
  idempotency record + the service's write + audit + outbox). :func:`lock_checked` locks the row inside that
  transaction, checks the record scope (404) BEFORE the version (412), so a stale ``If-Match`` on an
  out-of-scope id still answers 404.
"""

from __future__ import annotations

import base64
import binascii
import re
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from django.db import models
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.authz import policy as P
from platform_core.authz.policy import Caller, RecordScope
from platform_core.engine.errors import (
    AuthenticationRequired,
    FieldError,
    NotFound,
    ValidationFailed,
    VersionConflict,
)
from platform_core.engine.idempotency import StoredResponse, parse_idempotency_key
from platform_core.engine.uow import UnitOfWork
from platform_core.schema_common import (
    DECISION_ID_PATTERN,
    ENTITY_TYPE_PATTERN,
    MODULE_PATTERN,
    PERMISSION_PATTERN,
    SYSTEM_KEY_PATTERN,
    UNIT_TYPE_PATTERN,
    USERNAME_PATTERN,
)

from ..base import AleekhanAPIView
from ..concurrency import expected_version
from ..idempotent import idempotent_response
from ..pagination import MAX_CURSOR_LEN, AleekhanCursorPagination
from ..permissions import ScopedPermission, SessionOperation, require_principal
from ..request_id import request_id_of
from ..session_auth import SessionCookieAuthentication

NO_STORE: Final = {"Cache-Control": "no-store"}
UUID_RE: Final = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


# ------------------------------------------------------------------------------------------------ views
class Phase01View(AleekhanAPIView):
    """``required_action`` = permission of the safe methods (GET); ``write_action`` (if set) = permission of
    the unsafe methods of the same path (e.g. ``GET /admin/users`` read, ``POST /admin/users`` create)."""

    authentication_classes = [SessionCookieAuthentication]
    permission_classes = [ScopedPermission]
    required_action: str = ""
    write_action: str = ""
    allow_mfa_pending = False
    allow_password_change = False

    idempotent = True  # False only for the authentication ceremonies (C-27, ``idempotency_exempt``)

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        unsafe = request.method not in ("GET", "HEAD", "OPTIONS")
        if self.write_action and unsafe:
            self.required_action = self.write_action
        super().initial(request, *args, **kwargs)  # authentication, throttles, permission (+ MFA step-up)
        if unsafe and self.idempotent:
            # 428 / 400 for a missing / malformed Idempotency-Key before the body is even looked at
            parse_idempotency_key(request.headers.get("Idempotency-Key"))

    def caller(self) -> Caller:
        principal = require_principal(self.request)
        caller = getattr(principal, "caller", None)
        if not isinstance(caller, Caller):
            raise AuthenticationRequired()
        return caller

    def rid(self) -> uuid.UUID:
        return request_id_of(self.request)


class SessionView(Phase01View):
    permission_classes = [SessionOperation]


# ------------------------------------------------------------------------------------------ formatting
def utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def utc_req(value: datetime) -> str:
    out = utc(value)
    assert out is not None
    return out


def sid(value: uuid.UUID | None) -> str | None:
    return str(value) if value is not None else None


def opt_text(value: str) -> str | None:
    return value or None


# ------------------------------------------------------------------------------------ body validation
@dataclass(frozen=True)
class F:
    """One request field. ``kind``: str | uuid | ts | bool | int | strlist | obj (nested spec)."""

    kind: str
    required: bool = False
    nullable: bool = False
    min_len: int = 0
    max_len: int | None = None
    pattern: str | None = None
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    max_items: int | None = None
    item_pattern: str | None = None
    item_max_len: int | None = None
    nested: str | None = None  # name of a nested spec in BODIES (kind == "obj")


REASON: Final = F("str", required=True, min_len=3, max_len=500)
NAME_FA: Final = F("str", min_len=1, max_len=200)
KEY: Final = F("str", pattern=SYSTEM_KEY_PATTERN)
PERM_LIST: Final = F("strlist", max_items=500, item_pattern=PERMISSION_PATTERN, item_max_len=120)
ENTITY_REF: Final = F("obj", nested="EntityRef", nullable=True)
SCOPE_KINDS: Final = ("GLOBAL", "ORG_UNIT", "ORG_UNIT_SUBTREE", "SITE", "WAREHOUSE", "LINE", "CUSTOMER")
DATATYPES: Final = ("STRING", "INTEGER", "DECIMAL", "BOOLEAN", "DATE", "DURATION", "ENUM")
FIELD_DATATYPES: Final = ("STRING", "INTEGER", "DECIMAL", "BOOLEAN", "DATE", "ENUM", "REFERENCE")
SENSITIVITY_S0: Final = ("S0", "S1", "S2", "S3")

BODIES: Final[dict[str, dict[str, F]]] = {
    "EntityRef": {
        "entity_type": F("str", required=True, pattern=ENTITY_TYPE_PATTERN),
        "entity_id": F("str", required=True, min_len=1, max_len=64),
        "revision": F("int", nullable=True, minimum=1),
    },
    "Scope": {
        "kind": F("str", required=True, choices=SCOPE_KINDS),
        "ref_id": F("uuid", nullable=True),
    },
    "Assignee": {
        "kind": F("str", required=True, choices=("USER", "ORG_UNIT", "POSITION")),
        "ref_id": F("uuid", required=True),
    },
    "TypedValue": {
        "datatype": F("str", required=True, choices=DATATYPES),
        "value": F("scalar", required=True, nullable=True),
    },
    "ReasonRequest": {"reason": REASON},
    "OptionalNoteRequest": {"note": F("str", max_len=500)},
    "LoginRequest": {
        "username": F("str", required=True, min_len=1, max_len=150),
        "password": F("str", required=True, min_len=1, max_len=1024),
    },
    "MfaVerifyRequest": {"code": F("str", required=True, min_len=6, max_len=64)},
    "PasswordChangeRequest": {
        "current_password": F("str", required=True, min_len=1, max_len=1024),
        "new_password": F("str", required=True, min_len=1, max_len=1024),
    },
    "UserCreateRequest": {
        "username": F("str", required=True, pattern=USERNAME_PATTERN),
        "display_name": F("str", required=True, min_len=1, max_len=200),
        "account_kind": F("str", required=True, choices=("PERSON", "OPERATOR")),
        "network_policy": F("str", required=True, choices=("INTERNAL_ONLY", "ANY_WITH_MFA_OUTSIDE")),
        "reason": REASON,
    },
    "UserUpdateRequest": {
        "display_name": NAME_FA,
        "network_policy": F("str", choices=("INTERNAL_ONLY", "ANY_WITH_MFA_OUTSIDE")),
        "reason": REASON,
    },
    "RoleCreateRequest": {
        "code": F("str", required=True, pattern=SYSTEM_KEY_PATTERN),
        "name_fa": F("str", required=True, min_len=1, max_len=200),
        "kind": F("str", required=True, choices=("TECHNICAL", "BUSINESS")),
        "permissions": F(
            "strlist", required=True, max_items=500, item_pattern=PERMISSION_PATTERN, item_max_len=120
        ),
        "reason": REASON,
    },
    "RoleUpdateRequest": {"name_fa": NAME_FA, "permissions": PERM_LIST, "reason": REASON},
    "RoleAssignmentCreateRequest": {
        "user_id": F("uuid", required=True),
        "role_id": F("uuid", required=True),
        "scope": F("obj", required=True, nested="Scope"),
        "valid_from": F("ts"),
        "valid_to": F("ts", nullable=True),
        "confirm_self_assignment": F("bool"),
        "reason": REASON,
    },
    "OrgUnitCreateRequest": {
        "code": F("str", required=True, pattern=SYSTEM_KEY_PATTERN),
        "name_fa": F("str", required=True, min_len=1, max_len=200),
        "unit_type": F("str", required=True, pattern=UNIT_TYPE_PATTERN),
        "parent_unit_id": F("uuid", required=True, nullable=True),
        "valid_from": F("ts"),
        "reason": REASON,
    },
    "OrgUnitUpdateRequest": {"name_fa": NAME_FA, "reason": REASON},
    "OrgUnitMoveRequest": {
        "new_parent_unit_id": F("uuid", required=True),
        "effective_from": F("ts", required=True),
        "reason": REASON,
    },
    "PositionCreateRequest": {
        "unit_id": F("uuid", required=True),
        "code": F("str", required=True, pattern=SYSTEM_KEY_PATTERN),
        "title_fa": F("str", required=True, min_len=1, max_len=200),
        "reports_to_position_id": F("uuid", nullable=True),
        "is_unit_head": F("bool"),
        "primary_capacity": F("int", minimum=1),
        "reason": REASON,
    },
    "PositionUpdateRequest": {
        "title_fa": NAME_FA,
        "reports_to_position_id": F("uuid", nullable=True),
        "is_unit_head": F("bool"),
        "primary_capacity": F("int", minimum=1),
        "reason": REASON,
    },
    "PositionAssignmentCreateRequest": {
        "position_id": F("uuid", required=True),
        "user_id": F("uuid", required=True),
        "kind": F("str", required=True, choices=("PRIMARY", "ACTING")),
        "valid_from": F("ts", required=True),
        "valid_to": F("ts", nullable=True),
        "reason": REASON,
    },
    "TaskCreateRequest": {
        "subject": F("str", required=True, min_len=1, max_len=200),
        "related": ENTITY_REF,
        "assignee": F("obj", required=True, nested="Assignee"),
        "due_at": F("ts", nullable=True),
        "note": F("str", max_len=2000),
    },
    "TaskBlockRequest": {"reason": REASON, "blocked_by": ENTITY_REF},
    "TaskReassignRequest": {"assignee": F("obj", required=True, nested="Assignee"), "reason": REASON},
    "ApprovalDecisionRequest": {
        "resource_revision": F("int", required=True, minimum=1),
        "note": F("str", required=True, min_len=1, max_len=500),
    },
    "JobCancelRequest": {"reason": REASON},
    "DocumentCreateRequest": {
        "document_type": F("str", required=True, pattern=SYSTEM_KEY_PATTERN),
        "title_fa": F("str", required=True, min_len=1, max_len=200),
        "owner_entity": ENTITY_REF,
        "sensitivity": F("str", required=True, choices=("S1", "S2", "S3")),
        "legacy_location_ref": F("str", nullable=True, max_len=500),
    },
    "DocumentUpdateRequest": {
        "title_fa": NAME_FA,
        "legacy_location_ref": F("str", nullable=True, max_len=500),
    },
    "ParameterCreateRequest": {
        "parameter_key": F("str", required=True, pattern=SYSTEM_KEY_PATTERN),
        "label_fa": F("str", required=True, min_len=1, max_len=200),
        "datatype": F("str", required=True, choices=DATATYPES),
        "owner_module": F("str", required=True, pattern=MODULE_PATTERN),
        "classification": F("str", required=True, choices=("TECHNICAL", "OWNER_POLICY", "BUSINESS_RULE")),
        "decision_id": F("str", nullable=True, pattern=DECISION_ID_PATTERN),
        "reason": REASON,
    },
    "ParameterValueProposal": {
        "value": F("obj", required=True, nested="TypedValue"),
        "effective_from": F("ts", required=True),
        "reason": REASON,
    },
    "DynamicFieldCreateRequest": {
        "field_key": F("str", required=True, pattern=SYSTEM_KEY_PATTERN),
        "entity_scope": F("str", required=True, pattern=ENTITY_TYPE_PATTERN),
        "label_fa": F("str", required=True, min_len=1, max_len=200),
        "datatype": F("str", required=True, choices=FIELD_DATATYPES),
        "security_class": F("str", required=True, choices=SENSITIVITY_S0),
        "help_fa": F("str", nullable=True, max_len=500),
    },
    "DynamicFieldUpdateRequest": {"label_fa": NAME_FA, "help_fa": F("str", nullable=True, max_len=500)},
}

_COMPILED: dict[str, re.Pattern[str]] = {}


def _pattern(p: str) -> re.Pattern[str]:
    if p not in _COMPILED:
        _COMPILED[p] = re.compile(p)
    return _COMPILED[p]


def parse_ts(raw: Any, field: str) -> datetime:
    if not isinstance(raw, str) or not raw.endswith("Z") or len(raw) > 40:
        raise ValidationFailed(errors=[FieldError(field, "INVALID_TIMESTAMP")])
    try:
        value = datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError:
        raise ValidationFailed(errors=[FieldError(field, "INVALID_TIMESTAMP")]) from None
    return value


def parse_uuid(raw: Any, field: str) -> uuid.UUID:
    if not isinstance(raw, str) or not UUID_RE.fullmatch(raw):
        raise ValidationFailed(errors=[FieldError(field, "INVALID_UUID")])
    return uuid.UUID(raw)


def _check(spec: F, raw: Any, path: str, errors: list[FieldError]) -> Any:
    if raw is None:
        if spec.nullable:
            return None
        errors.append(FieldError(path, "NULL_NOT_ALLOWED"))
        return None
    kind = spec.kind
    if kind == "str":
        if not isinstance(raw, str):
            errors.append(FieldError(path, "INVALID_TYPE"))
        elif len(raw) < spec.min_len:
            errors.append(FieldError(path, "TOO_SHORT"))
        elif spec.max_len is not None and len(raw) > spec.max_len:
            errors.append(FieldError(path, "TOO_LONG"))
        elif spec.choices and raw not in spec.choices:
            errors.append(FieldError(path, "INVALID_CHOICE"))
        elif spec.pattern and not _pattern(spec.pattern).search(raw):
            errors.append(FieldError(path, "PATTERN_MISMATCH"))
        else:
            return raw
        return None
    if kind == "uuid":
        if not isinstance(raw, str) or not UUID_RE.fullmatch(raw):
            errors.append(FieldError(path, "INVALID_UUID"))
            return None
        return uuid.UUID(raw)
    if kind == "ts":
        try:
            return parse_ts(raw, path)
        except ValidationFailed:
            errors.append(FieldError(path, "INVALID_TIMESTAMP"))
            return None
    if kind == "bool":
        if not isinstance(raw, bool):
            errors.append(FieldError(path, "INVALID_TYPE"))
            return None
        return raw
    if kind == "int":
        if isinstance(raw, bool) or not isinstance(raw, int):
            errors.append(FieldError(path, "INVALID_TYPE"))
        elif (spec.minimum is not None and raw < spec.minimum) or (
            spec.maximum is not None and raw > spec.maximum
        ):
            errors.append(FieldError(path, "OUT_OF_RANGE"))
        else:
            return raw
        return None
    if kind == "scalar":  # TypedValue.value: string | boolean | null
        if not isinstance(raw, str | bool) or (isinstance(raw, str) and len(raw) > 500):
            errors.append(FieldError(path, "INVALID_TYPE"))
            return None
        return raw
    if kind == "strlist":
        if not isinstance(raw, list) or (spec.max_items is not None and len(raw) > spec.max_items):
            errors.append(FieldError(path, "INVALID_TYPE"))
            return None
        out: list[str] = []
        for i, item in enumerate(raw):
            if (
                not isinstance(item, str)
                or (spec.item_max_len is not None and len(item) > spec.item_max_len)
                or (spec.item_pattern and not _pattern(spec.item_pattern).search(item))
            ):
                errors.append(FieldError(f"{path}[{i}]", "PATTERN_MISMATCH"))
            else:
                out.append(item)
        return out
    if kind == "obj":
        assert spec.nested is not None
        return _object(BODIES[spec.nested], raw, path, errors)
    raise AssertionError(f"unknown field kind {kind}")  # pragma: no cover - specs are static


def _object(spec: Mapping[str, F], raw: Any, prefix: str, errors: list[FieldError]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        errors.append(FieldError(prefix or "body", "NOT_AN_OBJECT"))
        return {}
    out: dict[str, Any] = {}
    for key in sorted(set(raw) - set(spec)):
        errors.append(FieldError(f"{prefix}.{key}" if prefix else str(key)[:64], "UNKNOWN_FIELD"))
    for name, field_spec in spec.items():
        path = f"{prefix}.{name}" if prefix else name
        if name not in raw:
            if field_spec.required:
                errors.append(FieldError(path, "REQUIRED"))
            continue
        out[name] = _check(field_spec, raw[name], path, errors)
    return out


def body_of(request: Request, schema: str) -> dict[str, Any]:
    """Validated body (only the keys that were sent); 400 ``VALIDATION_FAILED`` with field paths + codes."""
    errors: list[FieldError] = []
    data = request.data
    out = _object(BODIES[schema], dict(data) if isinstance(data, dict) else data, "", errors)
    if errors:
        raise ValidationFailed(errors=errors[:100])
    return out


def query_uuid(request: Request, name: str) -> uuid.UUID | None:
    raw = request.query_params.get(name)
    return None if raw is None else parse_uuid(raw, name)


def query_choice(request: Request, name: str, choices: Iterable[str]) -> str | None:
    raw = request.query_params.get(name)
    if raw is None:
        return None
    if raw not in set(choices):
        raise ValidationFailed(errors=[FieldError(name, "INVALID_CHOICE")])
    return raw


def query_pattern(request: Request, name: str, pattern: str, max_len: int = 120) -> str | None:
    raw = request.query_params.get(name)
    if raw is None:
        return None
    if len(raw) > max_len or not _pattern(pattern).search(raw):
        raise ValidationFailed(errors=[FieldError(name, "PATTERN_MISMATCH")])
    return raw


def not_supported(field: str) -> ValidationFailed:
    """A contract field the 01.3 engine does not implement (reported in the 01.4 report; never ignored)."""
    return ValidationFailed(f"{field} is not supported yet", errors=[FieldError(field, "NOT_SUPPORTED")])


# ------------------------------------------------------------------------------------------ pagination
def paginate[M: models.Model](
    request: Request,
    view: AleekhanAPIView,
    qs: models.QuerySet[M],
    serialize: Callable[[M], dict[str, Any]],
    *,
    ordering: str = "id",
    headers: Mapping[str, str] | None = None,
) -> Response:
    paginator = AleekhanCursorPagination()
    paginator.ordering = ordering
    page = paginator.paginate_queryset(qs, request, view)
    assert page is not None
    response = paginator.get_paginated_response([serialize(x) for x in page])
    for k, v in (headers or NO_STORE).items():
        response[k] = v
    return response


FILTER_SCAN_CAP: Final = 1000  # TECH: rows inspected per page request by the per-record filter


def _decode_key_cursor(raw: str | None) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        if len(raw) > MAX_CURSOR_LEN:
            raise ValueError
        text = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("ascii")
        if not text.startswith("k:"):
            raise ValueError
        return uuid.UUID(text[2:])
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise ValidationFailed(
            "cursor is malformed or expired", errors=[FieldError(field="cursor", code="INVALID_CURSOR")]
        ) from None


def _encode_key_cursor(value: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"k:{value}".encode("ascii")).decode("ascii").rstrip("=")


def paginate_filtered[M: models.Model](
    request: Request,
    qs: models.QuerySet[M],
    allowed: Callable[[M], bool],
    serialize: Callable[[M], dict[str, Any]],
) -> Response:
    """Keyset pagination by ``id`` with a per-record check (the same check as the object endpoint): the list
    can never show a record its object endpoint would answer 404 for (SEC-01: list == object check). At most
    :data:`FILTER_SCAN_CAP` rows are inspected per request; ``next_cursor`` then continues the scan."""
    size = AleekhanCursorPagination().get_page_size(request)
    after = _decode_key_cursor(request.query_params.get("cursor"))
    base = qs.order_by("id")
    rows = base.filter(id__gt=after) if after is not None else base
    items: list[M] = []
    last: uuid.UUID | None = None
    scanned = 0
    for obj in rows.iterator(chunk_size=200):
        scanned += 1
        last = obj.pk
        if allowed(obj):
            items.append(obj)
        if len(items) >= size or scanned >= FILTER_SCAN_CAP:
            break
    more = last is not None and base.filter(id__gt=last).exists()
    next_cursor = _encode_key_cursor(last) if more and last is not None else None
    body = {"items": [serialize(x) for x in items], "page": {"page_size": size, "next_cursor": next_cursor}}
    return Response(body, headers=NO_STORE)


# --------------------------------------------------------------------------------------------- scope
def in_scope(caller: Caller, action: str, record: RecordScope) -> None:
    """404 ``NOT_FOUND`` for a record outside the caller's grants of ``action`` (SEC-01)."""
    P.require_record(caller, action, record)


def visible(caller: Caller, action: str, record: RecordScope) -> bool:
    return P.can(caller, action, record)


def get_or_404[M: models.Model](qs: models.QuerySet[M], **lookup: Any) -> M:
    obj = qs.filter(**lookup).first()
    if obj is None:
        raise NotFound()
    return obj


def lock_checked[M: models.Model](
    model: type[M],
    pk: Any,
    *,
    scope: Callable[[M], None],
    expected: int | None,
) -> M:
    """Inside the write transaction: lock the row, check scope (404) then ``If-Match`` (412)."""
    obj = model._default_manager.select_for_update().filter(pk=pk).first()
    if obj is None:
        raise NotFound()
    scope(obj)
    if expected is not None and getattr(obj, "row_version") != expected:  # noqa: B009
        raise VersionConflict("row_version does not match the current version")
    return obj


# ------------------------------------------------------------------------------------------------ writes
WriteResult = tuple[int, Any, Mapping[str, str]]


def write(
    view: Phase01View,
    handler: Callable[[Caller, uuid.UUID], StoredResponse],
    *,
    body: Any = None,
    hashed_body: bool = False,
) -> Response:
    """Run ``handler(caller, request_id)`` exactly once per ``Idempotency-Key`` (428 without, 422 on reuse
    with another body, stored response replayed with ``Idempotent-Replayed: true``)."""
    caller = view.caller()
    rid = view.rid()

    def run(_uow: UnitOfWork) -> StoredResponse:
        return handler(caller, rid)

    kwargs: dict[str, Any] = {"body": body} if hashed_body else {}
    return idempotent_response(
        view.request, endpoint=view.request.path, handler=run, require_event=False, **kwargs
    )


def if_match(view: Phase01View) -> int:
    """``If-Match`` of the request: missing 428, malformed 400 (before the idempotency claim)."""
    return expected_version(view.request)


def stored(status: int, body: Any, *, etag_version: int | None = None) -> StoredResponse:
    headers: dict[str, str] = {}
    if etag_version is not None:
        headers["ETag"] = f'"{etag_version}"'
    return StoredResponse(status, body, headers)


def etag_response(body: Any, row_version: int, *, status: int = 200) -> Response:
    return Response(body, status=status, headers={"ETag": f'"{row_version}"', **NO_STORE})
