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
* PHASE_01 / 01.3: audit rows carry the caller's ``session_id`` and ``network_zone`` and are hash-chained
  (``audit_chain``). The **outermost** unit of work takes the chain lock when it starts - before any business
  row lock of the transaction - so every writer acquires locks in the same order (chain first) and the chain
  lock can never be part of a lock cycle. Audit rows are inserted immediately (a savepoint rollback removes
  them with the rest of the nested write). Rule for callers: open the unit of work before taking business row
  locks (``select_for_update``) in the same transaction; services in this repository do.
"""

from __future__ import annotations

import re
import threading
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from django.db import transaction

from platform_core.models import AuditEvent, AuditOutcome, OutboxEvent

from .audit_chain import acquire_chain_lock, append_chained
from .context import RequestContext
from .errors import EngineContractError
from .redaction import redact, sensitive_paths

_ACTION_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)+$")  # = models.DOTTED_NAME_PATTERN
_local = threading.local()  # per thread (= per Django DB connection): the open units of work


def _open_units() -> list[UnitOfWork]:
    units: list[UnitOfWork] | None = getattr(_local, "units", None)
    if units is None:
        units = []
        _local.units = units
    return units


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
        if not _ACTION_RE.fullmatch(action):
            raise EngineContractError(f"audit action {action!r} is not a dotted lower-case name")
        if not resource_type:
            raise EngineContractError("audit resource_type is required")
        event = AuditEvent(
            actor_type=self.ctx.actor.actor_type,
            actor_id=self.ctx.actor.actor_id,
            request_id=self.ctx.request_id,
            correlation_id=self.ctx.effective_correlation_id,
            session_id=self.ctx.session_id,
            network_zone=self.ctx.network_zone,
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
        append_chained([event], using=self.using)
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
    units = _open_units()
    outer = next((u for u in reversed(units) if u.using == using), None)
    with transaction.atomic(using=using):
        acquire_chain_lock(using)  # re-entrant: a no-op wait for nested units of work of this transaction
        uow = UnitOfWork(ctx, using)
        units.append(uow)
        try:
            yield uow
        finally:
            units.pop()
        if not uow.audit_events:
            raise EngineContractError("a write must append at least one audit event")
        if require_event and not uow.outbox_events:
            raise EngineContractError("a write must append at least one outbox event")
    if outer is not None:  # the enclosing unit of work counts the writes of the nested ones (contract check)
        outer.audit_events.extend(uow.audit_events)
        outer.outbox_events.extend(uow.outbox_events)


class NothingToDo(Exception):
    """Raise inside :func:`unit_of_work_or_nothing` when the locked rows show there is nothing to change."""


@contextmanager
def unit_of_work_or_nothing(
    ctx: RequestContext, *, require_event: bool = True, using: str = "default"
) -> Iterator[UnitOfWork]:
    """A unit of work that may end without a write: raising :class:`NothingToDo` rolls it back silently.

    Used by sweeps and checks that must lock rows inside the unit of work (lock order: chain lock first) but
    often find nothing to do - instead of writing a meaningless audit row.
    """
    try:
        with unit_of_work(ctx, require_event=require_event, using=using) as uow:
            yield uow
    except NothingToDo:
        return
