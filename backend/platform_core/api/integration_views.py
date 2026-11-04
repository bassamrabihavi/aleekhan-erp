"""Integration endpoints (PHASE_00 / 00.6, openapi-draft ``integration`` tag). Read-only except conflict
resolution,
which never writes business data.

Deny by default: every view uses :class:`ScopedPermission` with an explicit ``required_action``; production
has no authentication backend yet (PHASE_01) and the PHASE_00 policy denies everything, so in production these
endpoints answer 401 (no principal). The behaviour behind the permission is tested through the TEST-ONLY
harness (``platform_core/tests/api_harness.py``) with a synthetic principal and policy.

* ``GET  /integration/freshness``                         per-source freshness (cursor pagination by code,
  ETag)
* ``GET  /integration/conflicts``                         conflict queue (cursor pagination, ``status``
  filter)
* ``GET  /integration/conflicts/{conflict_id}``           one item (ETag = row version)
* ``POST /integration/conflicts/{conflict_id}/resolve``   OPEN -> RESOLVED | DISMISSED (If-Match +
  Idempotency-Key)
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any, Final

from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.engine.concurrency import make_etag
from platform_core.engine.context import db_now
from platform_core.engine.errors import FieldError, NotFound, ValidationFailed
from platform_core.engine.idempotency import StoredResponse
from platform_core.engine.uow import UnitOfWork
from platform_core.integration.conflicts import resolve_conflict
from platform_core.integration.freshness import freshness_of
from platform_core.integration.models import ConflictItem, ConflictStatus, IntegrationSource

from .base import AleekhanAPIView
from .concurrency import expected_version, representation_etag, with_row_etag
from .idempotent import idempotent_response
from .pagination import AleekhanCursorPagination
from .permissions import ScopedPermission, require_principal, scoped_queryset

READ_FRESHNESS: Final = "platform.integration.freshness.read"
READ_CONFLICTS: Final = "platform.integration.conflict.read"
RESOLVE_CONFLICT: Final = "platform.integration.conflict.resolve"
SOURCE_CODE_RE: Final = re.compile(r"[a-z][a-z0-9_]{2,63}")
NO_STORE: Final = {"Cache-Control": "no-store"}


def utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class SourceCodePagination(AleekhanCursorPagination):
    ordering = "code"


class ConflictPagination(AleekhanCursorPagination):
    ordering = "id"


def _freshness_item(source: IntegrationSource, now: datetime) -> dict[str, Any]:
    info = freshness_of(source, now)
    return {
        "source_code": source.code,
        "name_fa": source.name_fa,
        "kind": source.kind,
        "direction": source.direction,
        "is_enabled": source.is_enabled,
        "freshness": info.freshness.value,
        "last_success_at": utc(source.last_success_at),
        "last_as_of": utc(source.last_as_of),
        "staleness_threshold_seconds": int(source.staleness_threshold.total_seconds()),
        "threshold_basis": source.threshold_basis,
        "policy_decision_id": source.policy_decision_id,
    }


class IntegrationFreshnessView(AleekhanAPIView):
    permission_classes = [ScopedPermission]
    required_action = READ_FRESHNESS

    def get(self, request: Request) -> Response:
        qs = scoped_queryset(request, self, IntegrationSource.objects.all())
        paginator = SourceCodePagination()
        page = paginator.paginate_queryset(qs, request, self)
        assert page is not None
        now = db_now()
        items = [_freshness_item(s, now) for s in page]
        meta = {"page_size": paginator.page_size, "next_cursor": paginator.next_cursor}
        # ETag covers the items and the page, not checked_at: it changes only when a source's state changes.
        etag = representation_etag({"items": items, "page": meta})
        body = {"items": items, "page": meta, "checked_at": utc(now.replace(microsecond=0))}
        return Response(body, headers={"ETag": etag, "Cache-Control": "no-cache"})


def conflict_body(item: ConflictItem) -> dict[str, Any]:
    return {
        "conflict_id": str(item.conflict_id),
        "source_code": item.source.code,
        "batch_id": str(item.batch_id) if item.batch_id is not None else None,
        "kind": item.kind,
        "conflict_key": item.conflict_key,
        "details": item.details,
        "status": item.status,
        "raised_at": utc(item.raised_at),
        "resolved_at": utc(item.resolved_at),
        "resolution_note": item.resolution_note or None,
        "row_version": item.row_version,
    }


def _conflict_filters(request: Request) -> dict[str, str]:
    errors: list[FieldError] = []
    filters: dict[str, str] = {}
    status = request.query_params.get("status")
    if status is not None:
        if status not in ConflictStatus.values:
            errors.append(FieldError(field="status", code="INVALID_CHOICE"))
        else:
            filters["status"] = status
    source_code = request.query_params.get("source_code")
    if source_code is not None:
        if not SOURCE_CODE_RE.fullmatch(source_code):
            errors.append(FieldError(field="source_code", code="PATTERN_MISMATCH"))
        else:
            filters["source__code"] = source_code
    if errors:
        raise ValidationFailed(errors=errors)
    return filters


class ConflictListView(AleekhanAPIView):
    permission_classes = [ScopedPermission]
    required_action = READ_CONFLICTS

    def get(self, request: Request) -> Response:
        filters = _conflict_filters(request)
        qs = scoped_queryset(request, self, ConflictItem.objects.select_related("source")).filter(**filters)
        paginator = ConflictPagination()
        page = paginator.paginate_queryset(qs, request, self)
        assert page is not None
        response = paginator.get_paginated_response([conflict_body(i) for i in page])
        response["Cache-Control"] = "no-store"
        return response


def _scoped_conflict(request: Request, view: AleekhanAPIView, conflict_id: uuid.UUID) -> ConflictItem:
    item = (
        scoped_queryset(request, view, ConflictItem.objects.select_related("source"))
        .filter(conflict_id=conflict_id)
        .first()
    )
    if item is None:
        raise NotFound()  # missing or outside the caller's scope (BOLA/IDOR)
    return item


class ConflictDetailView(AleekhanAPIView):
    permission_classes = [ScopedPermission]
    required_action = READ_CONFLICTS

    def get(self, request: Request, conflict_id: uuid.UUID) -> Response:
        item = _scoped_conflict(request, self, conflict_id)
        return with_row_etag(Response(conflict_body(item), headers=NO_STORE), item.row_version)


class ConflictResolveView(AleekhanAPIView):
    """POST: ``{"outcome": "RESOLVED" | "DISMISSED", "note": "..."}`` + ``If-Match`` + ``Idempotency-Key``."""

    permission_classes = [ScopedPermission]
    required_action = RESOLVE_CONFLICT

    def post(self, request: Request, conflict_id: uuid.UUID) -> Response:
        require_principal(request)
        version = expected_version(request)
        qs = scoped_queryset(request, self, ConflictItem.objects.all())
        data = request.data if isinstance(request.data, dict) else {}

        def handler(uow: UnitOfWork) -> StoredResponse:
            unknown = sorted(set(data) - {"outcome", "note"})
            if not isinstance(request.data, dict) or unknown:
                raise ValidationFailed(
                    errors=[FieldError(field=k, code="UNKNOWN_FIELD") for k in unknown]
                    or [FieldError(field="body", code="NOT_AN_OBJECT")]
                )
            outcome = data.get("outcome")
            note = data.get("note")
            item = resolve_conflict(
                uow.ctx,
                qs,
                conflict_id,
                expected_version=version,
                outcome=outcome if isinstance(outcome, str) else "",
                note=note if isinstance(note, str) else "",
                uow=uow,
            )
            return StoredResponse(200, conflict_body(item), {"ETag": make_etag(item.row_version)})

        return idempotent_response(
            request, endpoint=f"/api/v1/integration/conflicts/{conflict_id}/resolve", handler=handler
        )
