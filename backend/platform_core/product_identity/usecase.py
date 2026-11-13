"""Small helpers shared by the PHASE_02 use cases (Identity and Commercial), PHASE_01 service style.

* :func:`authorize` - action-level permission (403), optional record scope (404 outside it) and the MFA
  step-up of permissions flagged ``mfa_step_up`` (401). PHASE_02 records carry no org unit: every grant is
  SCOPE over all customers (DEC-057 answer 3), so the record check needs a GLOBAL assignment.
* :func:`lock` / :func:`check_version` - ``SELECT ... FOR UPDATE`` inside the unit of work, then the
  optimistic version (412 ``VERSION_CONFLICT``).
* :func:`reason_text` - a short operator justification (>= 3 characters), never personal data.
* :func:`next_number` - race-safe, unique technical numbers for customers, orders and change requests
  (PROPOSED format, docs/discovery/DATA_TABLE.md "02.3 numbers"): a database sequence per kind (gaps are
  allowed: a rolled back write consumes a number; uniqueness is the UNIQUE constraint of each table).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Final

from django.db import connections, models

from platform_core.authz.policy import Caller, Decision, RecordScope, require_record, require_step_up
from platform_core.engine.errors import NotFound, VersionConflict

from .refusals import Reason, refuse

GLOBAL_RECORD: Final = RecordScope()

# kind -> (sequence, prefix). Created by migration 0023 (``platform_core.0023_phase02_engine``).
NUMBER_SEQUENCES: Final = {
    "customer": ("identity_customer_no_seq", "CU-"),
    "order": ("commercial_order_no_seq", "SO-"),
    "change_request": ("commercial_change_request_no_seq", "CR-"),
}
NUMBER_PATTERN: Final = r"^(CU|SO|CR)-[0-9]{6,}$"


def authorize(caller: Caller, action: str, *, record: RecordScope | None = GLOBAL_RECORD) -> Decision:
    """403 without the action, 404 if the (unit-less) record is outside every grant, 401 without fresh MFA."""
    decision = require_record(caller, action, record or GLOBAL_RECORD)
    require_step_up(caller, action)
    return decision


def lock[M: models.Model](model: type[M], pk: Any, *, related: Iterable[str] = ()) -> M:
    qs = (
        model._default_manager.select_for_update(of=("self",))
        if related
        else model._default_manager.select_for_update()
    )
    if related:
        qs = qs.select_related(*related)
    obj = qs.filter(pk=pk).first()
    if obj is None:
        raise NotFound()
    return obj


def check_version(obj: Any, expected: int | None) -> None:
    """``If-Match``: ``None`` is refused by the API layer (428); the engine compares what it is given."""
    if expected is not None and obj.row_version != expected:
        raise VersionConflict()


def reason_text(text: str, *, field: str = "reason") -> str:
    value = (text or "").strip()
    if len(value) < 3:
        refuse(Reason.REQUIRED, field=field, detail="a reason of at least 3 characters is required")
    return value[:500]


def optional_text(value: str | None, *, max_len: int, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        refuse(Reason.INVALID, field=field)
    text = value.strip()
    if not text:
        return None
    if len(text) > max_len:
        refuse(Reason.INVALID, field=field, detail=f"{field} is longer than {max_len} characters")
    return text


def required_text(value: str | None, *, max_len: int, field: str) -> str:
    text = optional_text(value, max_len=max_len, field=field)
    if text is None:
        refuse(Reason.REQUIRED, field=field)
    return text


def next_number(kind: str, *, using: str = "default") -> str:
    sequence, prefix = NUMBER_SEQUENCES[kind]
    with connections[using].cursor() as cur:
        cur.execute("SELECT nextval(%s::regclass)", [f"public.{sequence}"])
        row = cur.fetchone()
    assert row is not None
    return f"{prefix}{int(row[0]):06d}"


def uuid_or_refuse(value: Any, *, field: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        refuse(Reason.INVALID, field=field)


def acknowledged(warnings: Iterable[str] | None, known: Iterable[str]) -> frozenset[str]:
    """The acknowledged warning codes; an unknown code is refused (no silent typo)."""
    given = frozenset(warnings or ())
    unknown = given - frozenset(known)
    if unknown:
        refuse(Reason.UNKNOWN_WARNING, field="acknowledge_warnings")
    return given
