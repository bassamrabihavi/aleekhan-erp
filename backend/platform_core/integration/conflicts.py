"""Conflict queue (PHASE_00 / 00.6): items that need a human decision. Resolving never writes business data.

Machine ``CONFLICT_MACHINE``: ``OPEN -> RESOLVED | DISMISSED`` (both terminal). A new occurrence after closing
opens a new item.

* :func:`raise_conflict` is idempotent while an item is OPEN: the partial unique index
  ``uq_conflict_item_open_key`` (source, kind, key WHERE status = OPEN) makes concurrent raisers converge on
  one item (``created=False`` for the others). ``details`` are redacted (sensitive keys -> ``[REDACTED]``) and
  size limited; they must carry identifiers only (code, sheet/cell reference), never personal data.
* :func:`resolve_conflict` requires an identified USER, ``If-Match`` row version, an outcome and a note; it
  writes the item + audit + outbox event (``platform.integration.conflict_resolved``) in one transaction. Any
  business consequence of the decision is the owning module's job in a later phase.
"""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from django.db import IntegrityError, models
from django.db.models.functions import Now

from platform_core.engine.context import RequestContext
from platform_core.engine.errors import (
    EngineContractError,
    FieldError,
    NotFound,
    ValidationFailed,
    VersionConflict,
)
from platform_core.engine.redaction import redact
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import UnitOfWork, unit_of_work
from platform_core.models import ActorType

from .models import ConflictItem, ConflictStatus, ImportBatch
from .sources import get_source

C = ConflictStatus
CONFLICT_MACHINE: Final = StateMachine(
    name="platform.integration.conflict",
    states=frozenset(C.values),
    transitions={
        C.OPEN: frozenset({C.RESOLVED, C.DISMISSED}),
        C.RESOLVED: frozenset(),
        C.DISMISSED: frozenset(),
    },
)
KIND_RE: Final = re.compile(r"[a-z][a-z0-9_]{2,63}")
MAX_KEY_LEN: Final = 200
MAX_DETAILS_BYTES: Final = 8 * 1024
MAX_NOTE_LEN: Final = 500
UNIQUE_OPEN: Final = "uq_conflict_item_open_key"
CLOSING_OUTCOMES: Final = frozenset({C.RESOLVED.value, C.DISMISSED.value})


def _has_control(text: str) -> bool:
    return any(unicodedata.category(ch) == "Cc" for ch in text)


@dataclass(frozen=True)
class RaiseResult:
    item: ConflictItem
    created: bool


def raise_conflict(
    ctx: RequestContext,
    *,
    source_code: str,
    kind: str,
    key: str,
    details: Mapping[str, Any] | None = None,
    batch_id: uuid.UUID | None = None,
    using: str = "default",
) -> RaiseResult:
    errors: list[FieldError] = []
    if not KIND_RE.fullmatch(kind or ""):
        errors.append(FieldError(field="kind", code="PATTERN_MISMATCH"))
    if not key or len(key) > MAX_KEY_LEN or _has_control(key):
        errors.append(FieldError(field="key", code="INVALID"))
    body = redact(dict(details or {}))
    try:
        size = len(json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError):
        errors.append(FieldError(field="details", code="NOT_JSON"))
        size = 0
    if size > MAX_DETAILS_BYTES:
        errors.append(FieldError(field="details", code="TOO_LARGE"))
    if errors:
        raise ValidationFailed(errors=errors)
    source = get_source(source_code, using=using)
    batch = None
    if batch_id is not None:
        batch = ImportBatch.objects.using(using).filter(pk=batch_id, source=source).first()
        if batch is None:
            raise NotFound()
    try:
        with unit_of_work(ctx, using=using) as uow:
            item = ConflictItem(
                source=source,
                batch=batch,
                conflict_key=key,
                kind=kind,
                details=body,
                raised_by_type=ctx.actor.actor_type,
                raised_by_id=ctx.actor.actor_id,
            )
            item.save(using=using, force_insert=True)
            item.refresh_from_db(using=using)
            uow.audit(
                action="platform.integration.conflict.raise",
                resource_type="platform.conflict_item",
                resource_id=str(item.conflict_id),
                resource_version=item.row_version,
                after={"status": item.status, "kind": kind},
                scope={"source_code": source.code},
            )
            uow.emit(
                event_type="platform.integration.conflict_raised",
                aggregate_type="platform.conflict_item",
                aggregate_id=str(item.conflict_id),
                aggregate_version=item.row_version,
                payload={
                    "conflict_id": str(item.conflict_id),
                    "source_code": source.code,
                    "kind": kind,
                    "batch_id": str(batch.id) if batch is not None else None,
                },
            )
        return RaiseResult(item, created=True)
    except IntegrityError as exc:
        diag = getattr(exc.__cause__, "diag", None)
        if getattr(diag, "constraint_name", None) != UNIQUE_OPEN:
            raise
    existing = (
        ConflictItem.objects.using(using)
        .select_related("source", "batch")
        .get(source=source, kind=kind, conflict_key=key, status=C.OPEN)
    )
    return RaiseResult(existing, created=False)


def resolve_conflict(
    ctx: RequestContext,
    queryset: models.QuerySet[ConflictItem],
    conflict_id: uuid.UUID,
    *,
    expected_version: int,
    outcome: str,
    note: str,
    uow: UnitOfWork | None = None,
    using: str = "default",
) -> ConflictItem:
    """OPEN -> RESOLVED | DISMISSED on a *scoped* queryset (out of scope -> 404).

    ``uow``: an open unit of work to join (e.g. the one of an idempotent API request); otherwise one is
    opened.
    """
    if ctx.actor.actor_type != ActorType.USER or ctx.actor.actor_id is None:
        raise EngineContractError("resolving a conflict must be performed by an identified user")
    errors: list[FieldError] = []
    if outcome not in CLOSING_OUTCOMES:
        errors.append(FieldError(field="outcome", code="INVALID_CHOICE"))
    text = (note or "").strip() if isinstance(note, str) else ""
    if not text:
        errors.append(FieldError(field="note", code="REQUIRED"))
    elif len(text) > MAX_NOTE_LEN or _has_control(text.replace("\n", " ")):
        errors.append(FieldError(field="note", code="INVALID"))
    if errors:
        raise ValidationFailed(errors=errors)
    if uow is not None:
        return _resolve(uow, queryset, conflict_id, expected_version, outcome, text, using)
    with unit_of_work(ctx, using=using) as own:
        return _resolve(own, queryset, conflict_id, expected_version, outcome, text, using)


def _resolve(
    uow: UnitOfWork,
    queryset: models.QuerySet[ConflictItem],
    conflict_id: uuid.UUID,
    expected_version: int,
    outcome: str,
    text: str,
    using: str,
) -> ConflictItem:
    ctx = uow.ctx
    item = (
        queryset.select_for_update(of=("self",))
        .select_related("source")
        .filter(conflict_id=conflict_id)
        .first()
    )
    if item is None:
        raise NotFound()
    if item.row_version != expected_version:
        raise VersionConflict("row_version does not match the current version")
    before = item.status
    CONFLICT_MACHINE.assert_transition(before, outcome)
    ConflictItem.objects.using(using).filter(pk=item.pk).update(
        status=outcome, resolved_by=ctx.actor.actor_id, resolved_at=Now(), resolution_note=text
    )
    item.refresh_from_db(using=using)
    uow.audit(
        action="platform.integration.conflict.resolve",
        resource_type="platform.conflict_item",
        resource_id=str(item.conflict_id),
        resource_version=item.row_version,
        before={"status": before},
        after={"status": item.status},
        reason=text,
        scope={"source_code": item.source.code},
    )
    uow.emit(
        event_type="platform.integration.conflict_resolved",
        aggregate_type="platform.conflict_item",
        aggregate_id=str(item.conflict_id),
        aggregate_version=item.row_version,
        payload={
            "conflict_id": str(item.conflict_id),
            "source_code": item.source.code,
            "status": item.status,
        },
    )
    return item
