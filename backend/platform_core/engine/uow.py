"""Transactional write helper: write + audit + outbox in ONE database transaction.

Contract (ARCHITECTURE_OVERVIEW: "One transaction = write to owning tables + immutable audit record + outbox
event"; openapi-draft ``write_requirements``)::

    with unit_of_work(ctx) as uow:
        ...                                  # the owning module's write(s)
        uow.audit(action="module.entity.verb", resource_type="module.entity", resource_id=str(pk), ...)
        uow.emit(event_type="module.entity.verbed", aggregate_type="module.entity", aggregate_id=..., ...)

* Everything runs inside ``transaction.atomic()``: if the body (or a later audit/outbox insert) raises, the
  write, the audit rows and the outbox rows are all rolled back - none survives.
* At least one audit row is mandatory; at least one outbox event is mandatory unless ``require_event=False``
  (e.g. an admin action whose effect is itself an outbox state change). Violations raise
  :class:`EngineContractError` *inside* the transaction, so the write is rolled back.
* Audit ``before``/``after`` and ``scope`` are redacted (REV-0009); outbox payloads with sensitive keys are
  rejected. ``reason`` is free text and ``resource_id`` an identifier: neither can be redacted by key, so
  callers must never put personal data or secrets there (reason = short operator justification, resource_id
  = surrogate id / 14-digit code only). This is a code-review rule (docs/engine/README.md section 1).
* Nested use joins the outer transaction as a savepoint (the outer commit decides durability).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from django.db import transaction

from platform_core.models import AuditEvent, AuditOutcome, OutboxEvent

from .context import RequestContext
from .errors import EngineContractError
from .redaction import redact, sensitive_paths


class UnitOfWork:
    def __init__(self, ctx: RequestContext, using: str) -> None:
        self.ctx = ctx
        self.using = using
        self.audit_events: list[AuditEvent] = []
        self.outbox_events: list[OutboxEvent] = []

    def audit(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str = "",
        resource_version: int | None = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        reason: str = "",
        scope: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            actor_type=self.ctx.actor.actor_type,
            actor_id=self.ctx.actor.actor_id,
            request_id=self.ctx.request_id,
            correlation_id=self.ctx.effective_correlation_id,
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_version=resource_version,
            scope=redact(dict(scope or {})),
            reason=reason,
            before=redact(dict(before)) if before is not None else None,
            after=redact(dict(after)) if after is not None else None,
        )
        event.save(using=self.using)
        self.audit_events.append(event)
        return event

    def emit(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int,
        payload: Mapping[str, Any] | None = None,
        schema_version: int = 1,
        causation_id: uuid.UUID | None = None,
    ) -> OutboxEvent:
        body = dict(payload or {})
        leaked = list(sensitive_paths(body))
        if leaked:
            raise EngineContractError(f"outbox payload contains sensitive keys: {leaked}")
        event = OutboxEvent(
            event_type=event_type,
            schema_version=schema_version,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            actor_type=self.ctx.actor.actor_type,
            actor_id=self.ctx.actor.actor_id,
            request_id=self.ctx.request_id,
            correlation_id=self.ctx.effective_correlation_id,
            causation_id=causation_id,
            payload=body,
        )
        event.save(using=self.using, force_insert=True)
        self.outbox_events.append(event)
        return event


@contextmanager
def unit_of_work(
    ctx: RequestContext, *, require_event: bool = True, using: str = "default"
) -> Iterator[UnitOfWork]:
    with transaction.atomic(using=using):
        uow = UnitOfWork(ctx, using)
        yield uow
        if not uow.audit_events:
            raise EngineContractError("a write must append at least one audit event")
        if require_event and not uow.outbox_events:
            raise EngineContractError("a write must append at least one outbox event")
