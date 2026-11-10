"""In-process event consumers (PHASE_00 / 00.6): handler registry, inbox dedupe, compensation hook.

The outbox delivers *at least once* (``outbox.py``). This module makes consumers *effectively once*:

* :class:`EventHandler` = consumer name + event types + ``handle`` + documented compensation. Handlers must be
  idempotent; the framework additionally dedupes by ``(consumer, event_id)`` in ``platform_inbox_event``.
* :func:`process_once` runs one handler for one envelope in ONE transaction: ``INSERT ... ON CONFLICT DO
  NOTHING`` into the inbox, then the handler's own writes. If the handler raises, both roll back (the event is
  retried with backoff); if the inbox row already exists the handler is skipped. Two workers racing on the
  same event serialize on the unique index: the second one waits, then sees the row and skips.
* :class:`RegistryPublisher` is an :class:`~platform_core.engine.outbox.OutboxPublisher`: it runs every
  handler registered for the event type; if any handler fails it raises :class:`PublishError` (safe code
  ``HANDLER_FAILED:<consumer>``) so the dispatcher backs off and retries. Already-processed handlers are
  skipped on the retry (inbox), so a failure of one consumer never makes another consumer apply an event
  twice.
* Compensation: when an event becomes DEAD_LETTER, :meth:`RegistryPublisher.on_dead_letter` records, per
  consumer that never processed it, one :class:`~platform_core.models.CompensationRecord` (unique per consumer
  + event), an audit row and a ``platform.integration.compensation_recorded`` outbox event in one unit of
  work, and runs the handler's ``compensate`` hook inside a savepoint. No hook -> ``MANUAL_REQUIRED``; hook
  raised -> ``HOOK_FAILED`` (class name only). PHASE_00 ships the mechanism only; no business compensation
  exists. :func:`sweep_dead_letters` repairs dead letters whose hook did not run (dispatcher crash).

Stored error texts are safe codes only (consumer name + exception class), never exception messages.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace

from django.db import connections, transaction

from platform_core.models import (
    AuditOutcome,
    CompensationOutcome,
    CompensationRecord,
    CompensationTrigger,
    DeliveryStatus,
    InboxEvent,
    OutboxEvent,
)

from .context import Actor, RequestContext
from .errors import EngineContractError
from .events import CATALOGUE, Catalogue, IncompatibleEvent, admit
from .outbox import EventEnvelope, PublishError, _envelope
from .uow import unit_of_work

_DOTTED = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)+")
MAX_CODE_LEN = 150


@dataclass(frozen=True)
class HandlerContext:
    """What a handler receives besides the envelope: a SYSTEM request context correlated with the event and
    the database alias. Handlers that write use ``unit_of_work(hctx.request)`` (it joins the inbox
    transaction)."""

    envelope: EventEnvelope
    request: RequestContext
    using: str


Handle = Callable[[EventEnvelope, HandlerContext], None]
Compensate = Callable[[EventEnvelope, str, HandlerContext], None]


@dataclass(frozen=True)
class EventHandler:
    consumer: str
    event_types: frozenset[str]
    handle: Handle
    # Mandatory documentation of what compensation means for this consumer (or why none is needed).
    compensation_doc: str
    compensate: Compensate | None = None

    def __post_init__(self) -> None:
        if not _DOTTED.fullmatch(self.consumer) or len(self.consumer) > MAX_CODE_LEN:
            raise EngineContractError(f"consumer name must be a dotted identifier: {self.consumer!r}")
        if not self.event_types:
            raise EngineContractError("a handler must subscribe to at least one event type")
        for et in self.event_types:
            if not _DOTTED.fullmatch(et):
                raise EngineContractError(f"event type must be a dotted identifier: {et!r}")
        if not self.compensation_doc.strip():
            raise EngineContractError(
                f"{self.consumer}: compensation_doc is required (state 'none needed: ...')"
            )


@dataclass
class HandlerRegistry:
    _handlers: dict[str, EventHandler] = field(default_factory=dict)

    def register(self, handler: EventHandler) -> EventHandler:
        if handler.consumer in self._handlers:
            raise EngineContractError(f"consumer {handler.consumer!r} is already registered")
        self._handlers[handler.consumer] = handler
        return handler

    def handlers_for(self, event_type: str) -> list[EventHandler]:
        return [h for _, h in sorted(self._handlers.items()) if event_type in h.event_types]

    @property
    def consumers(self) -> list[str]:
        return sorted(self._handlers)

    @property
    def event_types(self) -> frozenset[str]:
        out: set[str] = set()
        for h in self._handlers.values():
            out |= h.event_types
        return frozenset(out)


def _handler_context(envelope: EventEnvelope, using: str) -> HandlerContext:
    request = RequestContext(Actor.system(), correlation_id=envelope.correlation_id or envelope.event_id)
    return HandlerContext(envelope=envelope, request=request, using=using)


_INBOX_INSERT = (
    "INSERT INTO platform_inbox_event (consumer, event_id, event_type, attempt, processed_at) "
    "VALUES (%s, %s, %s, %s, statement_timestamp()) "
    "ON CONFLICT (consumer, event_id) DO NOTHING RETURNING id"
)


def process_once(handler: EventHandler, envelope: EventEnvelope, *, using: str = "default") -> bool:
    """Run ``handler`` for ``envelope`` unless already processed. Returns True if it ran (and committed)."""
    if envelope.event_type not in handler.event_types:
        raise EngineContractError(f"{handler.consumer} is not subscribed to {envelope.event_type}")
    with transaction.atomic(using=using):
        with connections[using].cursor() as cur:
            cur.execute(
                _INBOX_INSERT,
                [handler.consumer, envelope.event_id, envelope.event_type, max(1, envelope.attempt)],
            )
            inserted = cur.fetchone() is not None
        if not inserted:
            return False
        handler.handle(envelope, _handler_context(envelope, using))
    return True


def handler_failure_code(consumer: str, exc: BaseException) -> str:
    code = exc.safe_code if isinstance(exc, PublishError) else type(exc).__name__
    return f"HANDLER_FAILED:{consumer}:{code}"[:500]


class RegistryPublisher:
    """``OutboxPublisher`` that delivers to the in-process handlers of a :class:`HandlerRegistry`.

    01.6: before any handler runs, the envelope is admitted against the event catalogue
    (:func:`~platform_core.engine.events.admit`): versions N and N-1 are accepted (N-1 upcast to N, handlers
    only ever see the current version); an older or invalid payload is a permanent failure (DEAD_LETTER at
    once, compensation recorded), a newer version a transient one (retried with backoff).
    """

    def __init__(
        self, registry: HandlerRegistry, *, using: str = "default", catalogue: Catalogue = CATALOGUE
    ) -> None:
        self.registry = registry
        self.using = using
        self.catalogue = catalogue

    def publish(self, envelope: EventEnvelope) -> None:
        handlers = self.registry.handlers_for(envelope.event_type)
        if not handlers:
            return  # nobody listens: acknowledged (no admission needed)
        try:
            version, payload = admit(
                envelope.event_type, envelope.schema_version, envelope.payload, catalogue=self.catalogue
            )
        except IncompatibleEvent as exc:
            raise PublishError(exc.code, permanent=exc.permanent) from None
        if version != envelope.schema_version:
            envelope = replace(envelope, schema_version=version, payload=payload)
        failure: str | None = None
        for handler in handlers:
            try:
                process_once(handler, envelope, using=self.using)
            except Exception as exc:  # keep going: other consumers must not wait for a failing one
                failure = failure or handler_failure_code(handler.consumer, exc)
        if failure is not None:
            raise PublishError(failure)

    # ------------------------------------------------------------------------------------- compensation
    def on_dead_letter(self, envelope: EventEnvelope, failure_code: str) -> list[CompensationRecord]:
        """Record compensation for every subscribed consumer that never processed ``envelope``."""
        processed = set(
            InboxEvent.objects.using(self.using)
            .filter(event_id=envelope.event_id)
            .values_list("consumer", flat=True)
        )
        out: list[CompensationRecord] = []
        for handler in self.registry.handlers_for(envelope.event_type):
            if handler.consumer in processed:
                continue
            record = record_compensation(handler, envelope, failure_code, using=self.using)
            if record is not None:
                out.append(record)
        return out


def record_compensation(
    handler: EventHandler, envelope: EventEnvelope, failure_code: str, *, using: str = "default"
) -> CompensationRecord | None:
    """One compensation record per (consumer, event), with audit + outbox in the same transaction.

    Idempotent and race safe: the outbox row of the event is locked (``SELECT ... FOR UPDATE``) before the
    existence check, so concurrent sweeps serialize; a second call returns None and the hook is not run again.
    Hooks must only write to the database through the given context (their writes share the transaction).
    """
    hctx = _handler_context(envelope, using)
    with transaction.atomic(using=using):
        OutboxEvent.objects.using(using).select_for_update().filter(event_id=envelope.event_id).first()
        if (
            CompensationRecord.objects.using(using)
            .filter(consumer=handler.consumer, event_id=envelope.event_id)
            .exists()
        ):
            return None
        with unit_of_work(hctx.request, using=using) as uow:
            outcome = CompensationOutcome.MANUAL_REQUIRED
            hook_error = ""
            if handler.compensate is not None:
                try:
                    with transaction.atomic(using=using):  # savepoint: a failing hook leaves no partial write
                        handler.compensate(envelope, failure_code, hctx)
                    outcome = CompensationOutcome.COMPLETED
                except Exception as exc:
                    outcome = CompensationOutcome.HOOK_FAILED
                    hook_error = type(exc).__name__[:MAX_CODE_LEN]
            record = CompensationRecord(
                event_id=envelope.event_id,
                event_type=envelope.event_type,
                consumer=handler.consumer,
                aggregate_type=envelope.aggregate_type,
                aggregate_id=envelope.aggregate_id,
                trigger=CompensationTrigger.DEAD_LETTER,
                failure_code=failure_code[:500],
                outcome=outcome,
                hook_error=hook_error,
            )
            record.save(using=using, force_insert=True)
            uow.audit(
                action="platform.integration.compensation.record",
                resource_type="platform.compensation_record",
                resource_id=str(record.id),
                outcome=(
                    AuditOutcome.SUCCESS if outcome == CompensationOutcome.COMPLETED else AuditOutcome.FAILED
                ),
                after={"consumer": handler.consumer, "event_id": str(envelope.event_id), "outcome": outcome},
                scope={"event_type": envelope.event_type},
            )
            uow.emit(
                event_type="platform.integration.compensation_recorded",
                aggregate_type="platform.compensation_record",
                aggregate_id=str(record.id),
                aggregate_version=1,
                payload={
                    "compensation_id": str(record.id),
                    "event_id": str(envelope.event_id),
                    "consumer": handler.consumer,
                    "outcome": str(outcome),
                },
                causation_id=envelope.event_id,
            )
    return record


def sweep_dead_letters(
    publisher: RegistryPublisher, *, limit: int = 100, event_types: Iterable[str] | None = None
) -> int:
    """Record missing compensation for DEAD_LETTER events (repair after a dispatcher crash). Returns
    records."""
    types = sorted(set(event_types) if event_types is not None else publisher.registry.event_types)
    if not types:
        return 0
    rows = list(
        OutboxEvent.objects.using(publisher.using)
        .filter(delivery_status=DeliveryStatus.DEAD_LETTER, event_type__in=types)
        .order_by("occurred_at", "id")[:limit]
    )
    created = 0
    for row in rows:
        created += len(
            publisher.on_dead_letter(_envelope(row, row.attempts), row.last_error or "DEAD_LETTER")
        )
    return created
