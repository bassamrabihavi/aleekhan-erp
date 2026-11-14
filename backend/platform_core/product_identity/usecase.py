"""Small helpers shared by the PHASE_02 use cases (Identity and Commercial), PHASE_01 service style.

* :func:`authorize` - action-level permission (403), optional record scope (404 outside it) and the MFA
  step-up of permissions flagged ``mfa_step_up`` (401). PHASE_02 records carry no org unit: every grant is
  SCOPE over all customers (DEC-057 answer 3), so the record check needs a GLOBAL assignment.
* :func:`lock` / :func:`check_version` - ``SELECT ... FOR UPDATE`` inside the unit of work, then the
  optimistic version (412 ``VERSION_CONFLICT``).
* :func:`reason_text` - a short operator justification (>= 3 characters), never personal data.
* :func:`next_number` - race-safe, unique technical numbers for customers, orders and change requests
  (DEC-058 amendment 2026-11-14): ``CU-`` / ``SO-`` / ``CR-`` + the Jalali year of creation (Asia/Tehran) +
  ``-`` + at least 6 digits, e.g. ``SO-1405-000001``. Numbering restarts at 1 every Jalali year. One counter
  row per (kind, year) in ``platform_number_counter`` (migration 0025), moved by an atomic upsert under its
  row lock: two concurrent writers never get the same number; uniqueness is also the UNIQUE constraint of
  each table. Gaps are allowed. The DB lets the counter only move forward (no reset, no delete).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Final

from django.db import connections, models

from platform_core.authz.policy import Caller, Decision, RecordScope, require_record, require_step_up
from platform_core.engine.context import db_now
from platform_core.engine.errors import NotFound, VersionConflict

from .jalali import jalali_year_tehran
from .refusals import Reason, refuse

GLOBAL_RECORD: Final = RecordScope()

# kind -> prefix. Counter table: migration 0025 (``platform_core.0025_phase02_api_numbers``).
NUMBER_PREFIXES: Final = {"customer": "CU", "order": "SO", "change_request": "CR"}
NUMBER_PATTERN: Final = r"^(CU|SO|CR)-[0-9]{4}-[0-9]{6,}$"
_NEXT_NUMBER_SQL: Final = (
    "INSERT INTO public.platform_number_counter AS c (kind, jalali_year, last_value) VALUES (%s, %s, 1) "
    "ON CONFLICT (kind, jalali_year) DO UPDATE SET last_value = c.last_value + 1, updated_at = now() "
    "RETURNING c.last_value"
)


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
    """``<prefix>-<jalali year>-<n, at least 6 digits>``; call inside the creating unit of work."""
    prefix = NUMBER_PREFIXES[kind]
    year = jalali_year_tehran(db_now(using))
    with connections[using].cursor() as cur:
        cur.execute(_NEXT_NUMBER_SQL, [kind, year])
        row = cur.fetchone()
    assert row is not None
    return f"{prefix}-{year:04d}-{int(row[0]):06d}"


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
