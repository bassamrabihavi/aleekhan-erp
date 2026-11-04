"""00.6 consumers: handler registry, inbox dedupe, retries with backoff (injected clock + jitter source), dead
letter -> compensation records, sweep, and races (concurrent dispatchers / concurrent processing of one
event).

Handlers here are SYNTHETIC test consumers (``platform.synthetic_*``); no business compensation exists.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from hypothesis import given
from hypothesis import strategies as st

from platform_core.engine import consumers as cs
from platform_core.engine import outbox as ob
from platform_core.engine.errors import EngineContractError
from platform_core.engine.uow import unit_of_work
from platform_core.models import (
    AuditEvent,
    CompensationOutcome,
    CompensationRecord,
    DeliveryStatus,
    InboxEvent,
    OutboxEvent,
)

from .factories import outbox_event
from .threads import run_concurrently

S = DeliveryStatus
GOLDEN = Path(__file__).parent / "golden" / "integration_backoff.golden.json"
EVT = "platform.synthetic.created"
T0 = datetime(2030, 1, 1, tzinfo=UTC)  # injected clock, far from the DB clock on purpose
POLICY = ob.OutboxPolicy(
    max_attempts=3, base_delay=timedelta(seconds=10), factor=2, max_delay=timedelta(minutes=5)
)


class Recorder:
    """Synthetic consumer: counts calls, can fail N times or always, can write an audit row via the
    context."""

    def __init__(self, fail_times: int = 0, *, always: bool = False, write: bool = False) -> None:
        self.calls: list[uuid.UUID] = []
        self.fail_times = fail_times
        self.always = always
        self.write = write
        self.lock = threading.Lock()

    def __call__(self, env: ob.EventEnvelope, hctx: cs.HandlerContext) -> None:
        with self.lock:
            self.calls.append(env.event_id)
            if self.always or self.fail_times > 0:
                self.fail_times -= 1
                raise RuntimeError("SYNTHETIC handler failure with secret-ish text")
        if self.write:
            with unit_of_work(hctx.request, require_event=False, using=hctx.using) as uow:
                uow.audit(
                    action="platform.synthetic.consumed",
                    resource_type="platform.synthetic",
                    resource_id=str(env.event_id),
                )


def _handler(
    name: str, fn: Any, *, compensate: Any = None, types: frozenset[str] = frozenset({EVT})
) -> cs.EventHandler:
    return cs.EventHandler(
        consumer=f"platform.{name}",
        event_types=types,
        handle=fn,
        compensation_doc="SYNTHETIC test consumer: no business effect to undo.",
        compensate=compensate,
    )


def _publisher(*handlers: cs.EventHandler) -> cs.RegistryPublisher:
    reg = cs.HandlerRegistry()
    for h in handlers:
        reg.register(h)
    return cs.RegistryPublisher(reg)


# ------------------------------------------------------------------------------------------- policy / backoff
def test_integration_policy_golden() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    p = ob.INTEGRATION_POLICY
    assert {
        "max_attempts": p.max_attempts,
        "base_delay_seconds": p.base_delay.total_seconds(),
        "factor": p.factor,
        "max_delay_seconds": p.max_delay.total_seconds(),
        "jitter_permille": p.jitter_permille,
        "lease_seconds": p.lease.total_seconds(),
        "batch_size": p.batch_size,
    } == golden["policy"]
    key = uuid.UUID(int=0)
    no_jitter = ob.OutboxPolicy(
        max_attempts=p.max_attempts, base_delay=p.base_delay, factor=p.factor, max_delay=p.max_delay
    )
    assert {str(a): no_jitter.delay_after(a, key).total_seconds() for a in range(1, 13)} == golden[
        "attempt_to_delay_seconds_without_jitter"
    ]
    assert {str(a): p.delay_after(a, key).total_seconds() for a in range(1, 13)} == golden[
        "attempt_to_delay_seconds_sha256_jitter_key_uuid0"
    ]


@given(a=st.integers(min_value=1, max_value=64), sample=st.integers(min_value=0, max_value=2**64 - 1))
def test_injected_jitter_source_bounds(a: int, sample: int) -> None:
    fixed = ob.OutboxPolicy(
        max_attempts=8,
        base_delay=timedelta(seconds=5),
        factor=2,
        max_delay=timedelta(minutes=30),
        jitter_permille=250,
        jitter_source=lambda _k, _a: sample,
    )
    plain = ob.backoff_delay(a, base=fixed.base_delay, factor=2, cap=fixed.max_delay)
    got = fixed.delay_after(a, uuid.uuid4())  # key ignored by the injected source
    assert plain * 0.75 - timedelta(microseconds=1) <= got <= plain
    assert got == fixed.delay_after(a, uuid.uuid4())


def test_jitter_extremes_and_invalid_source() -> None:
    kw: dict[str, Any] = {
        "base": timedelta(seconds=8),
        "factor": 2,
        "cap": timedelta(hours=1),
        "jitter_permille": 250,
    }
    assert ob.backoff_delay(1, jitter_source=lambda k, a: 0, **kw) == timedelta(seconds=8)
    assert ob.backoff_delay(1, jitter_source=lambda k, a: 2**64 - 1, **kw) > timedelta(seconds=6)
    with pytest.raises(ValueError):
        ob.backoff_delay(1, jitter_source=lambda k, a: 2**64, **kw)


# ------------------------------------------------------------------------------------------- registry
def test_registry_validation() -> None:
    ok = _handler("synthetic_a", Recorder())
    with pytest.raises(EngineContractError):
        cs.EventHandler(
            consumer="Bad Name", event_types=frozenset({EVT}), handle=Recorder(), compensation_doc="x"
        )
    with pytest.raises(EngineContractError):
        cs.EventHandler(
            consumer="platform.x", event_types=frozenset(), handle=Recorder(), compensation_doc="x"
        )
    with pytest.raises(EngineContractError):
        cs.EventHandler(
            consumer="platform.x", event_types=frozenset({"NoDots"}), handle=Recorder(), compensation_doc="x"
        )
    with pytest.raises(EngineContractError):
        cs.EventHandler(
            consumer="platform.x", event_types=frozenset({EVT}), handle=Recorder(), compensation_doc=" "
        )
    reg = cs.HandlerRegistry()
    reg.register(ok)
    with pytest.raises(EngineContractError):
        reg.register(_handler("synthetic_a", Recorder()))
    assert reg.handlers_for(EVT) == [ok] and reg.handlers_for("platform.other.x") == []


# ------------------------------------------------------------------------------------------- inbox
@pytest.mark.django_db
def test_process_once_dedupes_by_consumer_and_event() -> None:
    row = outbox_event()
    env = ob._envelope(row, 1)
    rec = Recorder(write=True)
    h = _handler("synthetic_a", rec)
    assert cs.process_once(h, env) is True
    assert cs.process_once(h, env) is False  # redelivery skipped
    assert rec.calls == [row.event_id]
    assert InboxEvent.objects.filter(consumer="platform.synthetic_a", event_id=row.event_id).count() == 1
    with pytest.raises(EngineContractError):
        cs.process_once(_handler("synthetic_b", Recorder(), types=frozenset({"platform.other.x"})), env)


@pytest.mark.django_db
def test_failed_handler_rolls_back_its_inbox_row_and_writes() -> None:
    row = outbox_event()
    env = ob._envelope(row, 1)

    def failing(e: ob.EventEnvelope, hctx: cs.HandlerContext) -> None:
        with unit_of_work(hctx.request, require_event=False) as uow:
            uow.audit(action="platform.synthetic.partial", resource_type="platform.synthetic")
        raise RuntimeError("after a write")

    with pytest.raises(RuntimeError):
        cs.process_once(_handler("synthetic_a", failing), env)
    assert not InboxEvent.objects.exists()
    assert not AuditEvent.objects.filter(action="platform.synthetic.partial").exists()


@pytest.mark.django_db
def test_inbox_rows_cannot_be_updated() -> None:
    row = outbox_event()
    cs.process_once(_handler("synthetic_a", Recorder()), ob._envelope(row, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        InboxEvent.objects.update(attempt=9)


# ------------------------------------------------------------------------------------------- retries
@pytest.mark.django_db
def test_retry_with_backoff_on_injected_clock_then_delivered() -> None:
    row = outbox_event()
    OutboxEvent.objects.filter(pk=row.pk).update(next_attempt_at=T0)
    rec = Recorder(fail_times=1)
    pub = _publisher(_handler("synthetic_a", rec))
    stats = ob.dispatch_once(pub, POLICY, now=T0)
    row.refresh_from_db()
    assert (stats.failed, row.delivery_status, row.attempts) == (1, S.FAILED, 1)
    assert row.last_error == "HANDLER_FAILED:platform.synthetic_a:RuntimeError"  # no exception text stored
    delay = POLICY.delay_after(1, row.event_id)
    assert row.next_attempt_at == T0 + delay
    assert ob.dispatch_once(pub, POLICY, now=T0 + delay - timedelta(microseconds=1)).claimed == 0
    stats = ob.dispatch_once(pub, POLICY, now=T0 + delay)
    row.refresh_from_db()
    assert (stats.delivered, row.delivery_status, row.attempts) == (1, S.ACKED, 2)
    assert len(rec.calls) == 2


@pytest.mark.django_db
def test_one_failing_consumer_does_not_make_another_apply_twice() -> None:
    row = outbox_event()
    OutboxEvent.objects.filter(pk=row.pk).update(next_attempt_at=T0)
    good, bad = Recorder(), Recorder(fail_times=1)
    pub = _publisher(_handler("synthetic_good", good), _handler("synthetic_bad", bad))
    ob.dispatch_once(pub, POLICY, now=T0)
    ob.dispatch_once(pub, POLICY, now=T0 + timedelta(hours=1))
    row.refresh_from_db()
    assert row.delivery_status == S.ACKED
    assert len(good.calls) == 1 and len(bad.calls) == 2
    assert set(InboxEvent.objects.values_list("consumer", flat=True)) == {
        "platform.synthetic_good",
        "platform.synthetic_bad",
    }


@pytest.mark.django_db
def test_event_without_subscribers_is_acknowledged() -> None:
    row = outbox_event(event_type="platform.nobody.listens")
    ob.dispatch_once(_publisher(_handler("synthetic_a", Recorder())), POLICY)
    row.refresh_from_db()
    assert row.delivery_status == S.ACKED


# ------------------------------------------------------------------------------------------- compensation
def _dead_letter(pub: cs.RegistryPublisher, row: OutboxEvent) -> ob.DispatchStats:
    OutboxEvent.objects.filter(pk=row.pk).update(next_attempt_at=T0)
    stats = ob.DispatchStats()
    for i in range(POLICY.max_attempts):
        s = ob.dispatch_once(pub, POLICY, now=T0 + timedelta(days=i), on_dead_letter=pub.on_dead_letter)
        stats.dead_lettered += s.dead_lettered
        stats.compensation_errors += s.compensation_errors
    row.refresh_from_db()
    assert row.delivery_status == S.DEAD_LETTER
    return stats


@pytest.mark.django_db
def test_dead_letter_records_compensation_per_unprocessed_consumer() -> None:
    row = outbox_event()
    hook_calls: list[str] = []

    def hook(env: ob.EventEnvelope, failure: str, hctx: cs.HandlerContext) -> None:
        hook_calls.append(failure)

    def broken_hook(env: ob.EventEnvelope, failure: str, hctx: cs.HandlerContext) -> None:
        with unit_of_work(hctx.request, require_event=False) as uow:
            uow.audit(action="platform.synthetic.hook_partial", resource_type="platform.synthetic")
        raise ValueError("SYNTHETIC hook failure")

    pub = _publisher(
        _handler("synthetic_ok", Recorder()),  # processes fine -> no compensation
        _handler("synthetic_manual", Recorder(always=True)),  # no hook -> MANUAL_REQUIRED
        _handler("synthetic_hooked", Recorder(always=True), compensate=hook),
        _handler("synthetic_broken", Recorder(always=True), compensate=broken_hook),
    )
    stats = _dead_letter(pub, row)
    assert stats.dead_lettered == 1 and stats.compensation_errors == 0
    got = {
        r.consumer: (r.outcome, r.hook_error, r.trigger)
        for r in CompensationRecord.objects.filter(event_id=row.event_id)
    }
    assert got == {
        "platform.synthetic_manual": (CompensationOutcome.MANUAL_REQUIRED, "", "DEAD_LETTER"),
        "platform.synthetic_hooked": (CompensationOutcome.COMPLETED, "", "DEAD_LETTER"),
        "platform.synthetic_broken": (CompensationOutcome.HOOK_FAILED, "ValueError", "DEAD_LETTER"),
    }
    assert hook_calls == [row.last_error]
    assert all(r.failure_code == row.last_error for r in CompensationRecord.objects.all())
    assert not AuditEvent.objects.filter(
        action="platform.synthetic.hook_partial"
    ).exists()  # savepoint rollback
    assert AuditEvent.objects.filter(action="platform.integration.compensation.record").count() == 3
    events = OutboxEvent.objects.filter(event_type="platform.integration.compensation_recorded")
    assert events.count() == 3 and all(e.causation_id == row.event_id for e in events)
    # idempotent: a second notification / sweep records nothing new and does not rerun the hook
    assert pub.on_dead_letter(ob._envelope(row, row.attempts), row.last_error) == []
    assert cs.sweep_dead_letters(pub) == 0
    assert hook_calls == [row.last_error]
    with pytest.raises(IntegrityError), transaction.atomic():  # append-only
        CompensationRecord.objects.update(hook_error="x")


@pytest.mark.django_db
def test_sweep_repairs_dead_letters_without_compensation() -> None:
    row = outbox_event()
    OutboxEvent.objects.filter(pk=row.pk).update(
        delivery_status=S.DEAD_LETTER, attempts=3, last_error="X_CODE"
    )
    pub = _publisher(_handler("synthetic_a", Recorder()))
    assert cs.sweep_dead_letters(pub) == 1
    rec = CompensationRecord.objects.get()
    assert (rec.consumer, rec.failure_code, rec.outcome) == (
        "platform.synthetic_a",
        "X_CODE",
        "MANUAL_REQUIRED",
    )
    assert cs.sweep_dead_letters(pub) == 0


@pytest.mark.django_db
def test_failing_compensation_never_crashes_the_dispatcher() -> None:
    row = outbox_event()

    def boom(env: ob.EventEnvelope, failure: str) -> None:
        raise RuntimeError("compensation bookkeeping down")

    pub = _publisher(_handler("synthetic_a", Recorder(always=True)))
    OutboxEvent.objects.filter(pk=row.pk).update(next_attempt_at=T0)
    errs = 0
    for i in range(POLICY.max_attempts):
        errs += ob.dispatch_once(
            pub, POLICY, now=T0 + timedelta(days=i), on_dead_letter=boom
        ).compensation_errors
    row.refresh_from_db()
    assert row.delivery_status == S.DEAD_LETTER and errs == 1
    assert cs.sweep_dead_letters(pub) == 1  # the sweep catches up


@pytest.mark.django_db
def test_recover_stale_dead_letter_triggers_hook() -> None:
    row = outbox_event()
    seen: list[tuple[uuid.UUID, str]] = []
    one_shot = ob.OutboxPolicy(max_attempts=1, base_delay=timedelta(seconds=1), lease=timedelta(seconds=1))
    assert len(ob.claim_batch(one_shot)) == 1  # dispatcher crashes after the claim
    n = ob.recover_stale(
        one_shot,
        now=datetime.now(UTC) + timedelta(hours=1),
        on_dead_letter=lambda e, f: seen.append((e.event_id, f)),
    )
    row.refresh_from_db()
    assert n == 1 and row.delivery_status == S.DEAD_LETTER
    assert seen == [(row.event_id, "LEASE_EXPIRED")]


# ------------------------------------------------------------------------------------------- races
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_concurrent_dispatchers_with_registry_process_each_event_once_per_consumer() -> None:
    for i in range(40):
        outbox_event(aggregate_id=f"synthetic-{i}")
    a, b = Recorder(write=True), Recorder()
    pub = _publisher(_handler("synthetic_a", a), _handler("synthetic_b", b))
    policy = ob.OutboxPolicy(batch_size=5)

    def dispatcher(_: int) -> int:
        n = 0
        while True:
            stats = ob.dispatch_once(pub, policy)
            if stats.claimed == 0:
                return n
            n += stats.delivered

    results = run_concurrently(dispatcher, 4)
    assert all(isinstance(r, int) for r in results), results
    assert sum(results) == 40
    assert len(a.calls) == len(set(a.calls)) == 40 and len(b.calls) == len(set(b.calls)) == 40
    assert InboxEvent.objects.count() == 80
    assert AuditEvent.objects.filter(action="platform.synthetic.consumed").count() == 40


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_concurrent_redelivery_of_one_event_runs_the_handler_once() -> None:
    """At-least-once delivery (e.g. lease recovery) may hand the same event to 6 workers at the same time."""
    row = outbox_event()
    env = ob._envelope(row, 1)
    rec = Recorder(write=True)
    h = _handler("synthetic_a", rec)
    results = run_concurrently(lambda _i: cs.process_once(h, env), 6)
    assert all(isinstance(r, bool) for r in results), results
    assert sum(results) == 1 and len(rec.calls) == 1
    assert InboxEvent.objects.count() == 1
    assert AuditEvent.objects.filter(action="platform.synthetic.consumed").count() == 1
