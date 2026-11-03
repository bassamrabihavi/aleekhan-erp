"""Optimistic concurrency: ``row_version`` <-> strong ETag / ``If-Match`` (openapi-draft conventions).

* ``ETag`` is the strong tag ``"<row_version>"``.
* ``If-Match`` missing -> 428 ``PRECONDITION_REQUIRED``; malformed / ``*`` / a list -> 400
  ``VALIDATION_FAILED``; weak tag (never matches under strong comparison, RFC 9110 13.1.1) or stale version
  -> 412 ``VERSION_CONFLICT``.
* Writes use ``UPDATE ... WHERE pk = %s AND row_version = <expected>``; the DB trigger ``platform_touch_row``
  bumps ``row_version`` by exactly one, so the new version is ``expected + 1``.
* A record that does not exist (or is outside the caller's scope - the caller passes a scoped queryset)
  yields 404 ``NOT_FOUND``.
"""

from __future__ import annotations

import re
from typing import Any

from django.db import models, transaction

from .errors import (
    EngineContractError,
    FieldError,
    NotFound,
    PreconditionRequired,
    ValidationFailed,
    VersionConflict,
)

_STRONG_ETAG_RE = re.compile(r'"([1-9][0-9]{0,18})"')
_WEAK_ETAG_RE = re.compile(r'W/"[^"]*"')
MAX_ROW_VERSION = 2**63 - 1  # bigint


def make_etag(row_version: int) -> str:
    if not 1 <= row_version <= MAX_ROW_VERSION:
        raise ValueError("row_version out of range")
    return f'"{row_version}"'


def parse_if_match(header: str | None) -> int:
    """Return the expected ``row_version`` from an ``If-Match`` header value."""
    if header is None or not header.strip():
        raise PreconditionRequired("If-Match header is required for this write")
    value = header.strip()
    if _WEAK_ETAG_RE.fullmatch(value):
        raise VersionConflict("weak ETag never matches (strong comparison)")
    m = _STRONG_ETAG_RE.fullmatch(value)
    if m is None or int(m.group(1)) > MAX_ROW_VERSION:
        raise ValidationFailed(
            "If-Match must be a single strong ETag",
            errors=[FieldError(field="If-Match", code="INVALID_ETAG")],
        )
    return int(m.group(1))


def update_versioned[M: models.Model](
    queryset: models.QuerySet[M], pk: Any, expected_version: int, **values: Any
) -> int:
    """Compare-and-set update. Returns the new ``row_version``; raises 404 / 412."""
    if "row_version" in values:
        raise EngineContractError("row_version is maintained by the database trigger")
    if not values:
        raise EngineContractError("nothing to update")
    updated = queryset.filter(pk=pk, row_version=expected_version).update(**values)
    if updated == 1:
        return expected_version + 1
    if not queryset.filter(pk=pk).exists():
        raise NotFound()
    raise VersionConflict("row_version does not match the current version")


def lock_versioned[M: models.Model](queryset: models.QuerySet[M], pk: Any, expected_version: int) -> M:
    """``SELECT ... FOR UPDATE`` the row and check its version (for read-modify-write in one transaction)."""
    if not transaction.get_connection(queryset.db).in_atomic_block:
        raise EngineContractError("lock_versioned must run inside transaction.atomic()")
    obj = queryset.select_for_update().filter(pk=pk).first()
    if obj is None:
        raise NotFound()
    if getattr(obj, "row_version") != expected_version:  # noqa: B009 - generic model
        raise VersionConflict("row_version does not match the current version")
    return obj
