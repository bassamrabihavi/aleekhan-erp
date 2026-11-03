"""Outbox dispatcher: backoff properties/golden, transitions, dead letter, replay, SKIP LOCKED race."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.test import override_settings
from hypothesis import given
from hypothesis import strategies as st

from platform_core.engine import outbox as ob
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import EngineContractError, NotFound, StateTransitionNotAllowed
from platform_core.engine.testing import InMemoryTestPublisher
from platform_core.models import AuditEvent, DeliveryStatus, OutboxEvent

from .factories import outbox_event
from .threads import run_concurrently

GOLDEN = Path(__file__).parent / "golden" / "backoff.golden.json"
S = DeliveryStatus
FAST = ob.OutboxPolicy(
    max_attempts=3, base_delay=timedelta(seconds=10), factor=2, max_delay=timedelta(minutes=5)
)


# ------------------------------------------------------------------------------------------- backoff
def test_default_backoff_golden() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["attempt_to_delay_seconds"]
    p = ob.OutboxPolicy()
    actual = {k: p.delay_after(int(k), uuid.UUID(int=0)).total_seconds() for k in golden}
    assert actual == {k: float(v) for k, v in golden.items()}


attempts = st.integers(min_value=1, max_value=10_000)
bases = st.integers(min_value=1, max_value=60_000_000)  # microseconds
factors = st.integers(min_value=1, max_value=10)


@given(a=attempts, base_us=bases, factor=factors, extra_cap=st.integers(min_value=0, max_value=10**10))
def test_backoff_bounded_monotone_deterministic(a: int, base_us: int, factor: int, extra_cap: int) -> None:
    base, cap = timedelta(microseconds=base_us), timedelta(microseconds=base_us + extra_cap)
    d1 = ob.backoff_delay(a, base=base, factor=factor, cap=cap)
    d2 = ob.backoff_delay(a + 1, base=base, factor=factor, cap=cap)
    assert base <= d1 <= cap
    assert d1 <= d2
    assert d1 == ob.backoff_delay(a, base=base, factor=factor, cap=cap)
    if a == 1:
        assert d1 == base


@given(a=attempts, permille=st.integers(min_value=0, max_value=1000), key=st.text(max_size=36))
def test_backoff_jitter_is_deterministic_and_bounded(a: int, permille: int, key: str) -> None:
    kw: dict[str, Any] = {"base": timedelta(seconds=2), "factor": 2, "cap": timedelta(hours=1)}
    plain = ob.backoff_delay(a, **kw)
    jittered = ob.backoff_delay(a, jitter_permille=permille, jitter_key=key, **kw)
    assert jittered == ob.backoff_delay(a, jitter_permille=permille, jitter_key=key, **kw)
    lower = plain - timedelta(microseconds=(plain // timedelta(microseconds=1)) * permille // 1000)
    assert lower <= jittered <= plain


@pytest.mark.parametrize(
    "kwargs",
    [
        {"attempt": 0},
        {"factor": 0},
        {"jitter_permille": 1001},
        {"base": timedelta(0)},
        {"cap": timedelta(milliseconds=1)},
    ],
)
def test_backoff_rejects_invalid_parameters(kwargs: dict[str, object]) -> None:
    args: dict[str, object] = {
        "attempt": 1,
        "base": timedelta(seconds=1),
        "factor": 2,
        "cap": timedelta(hours=1),
    }
    args.update(kwargs)
    with pytest.raises(ValueError):
        ob.backoff_delay(**args)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------------- dispatch
@pytest.mark.django_db
def test_dispatch_delivers_pending_and_acks() -> None:
    e1, e2 = outbox_event(), outbox_event(aggregate_id="synthetic-2")
    pub = InMemoryTestPublisher()
    stats = ob.dispatch_once(pub, FAST)
    assert (stats.claimed, stats.delivered) == (2, 2)
    assert [env.event_id for env in pub.published] == [e1.event_id, e2.event_id]  # next_attempt_at, id order
    for row in OutboxEvent.objects.all():
        assert row.delivery_status == S.ACKED
        assert row.attempts == 1
        assert row.acked_at is not None and row.dispatched_at is not None
    assert ob.dispatch_once(pub, FAST).claimed == 0  # nothing re-sent


@pytest.mark.django_db
def test_failure_backs_off_then_dead_letters_after_max_attempts() -> None:
    row = outbox_event()
    pub = InMemoryTestPublisher()
    pub.fail_always = True
    for attempt in range(1, FAST.max_attempts + 1):
        stats = ob.dispatch_once(pub, FAST)
        row.refresh_from_db()
        assert row.attempts == attempt
        assert row.last_error == "TEST_PUBLISHER_FAILURE"
        if attempt < FAST.max_attempts:
            assert stats.failed == 1 and row.delivery_status == S.FAILED
            # not due yet -> not claimed again
            assert ob.claim_batch(FAST) == []
            expected = FAST.delay_after(attempt, row.event_id)
            assert row.next_attempt_at - row.updated_at == expected
            OutboxEvent.objects.filter(pk=row.pk).update(next_attempt_at=row.created_at)  # make it due
        else:
            assert stats.dead_lettered == 1 and row.delivery_status == S.DEAD_LETTER
    assert ob.dispatch_once(pub, FAST).claimed == 0  # dead letters are never claimed


@pytest.mark.django_db
def test_failed_event_is_retried_and_delivered() -> None:
    row = outbox_event()
    pub = InMemoryTestPublisher()
    pub.fail_event_ids.add(row.event_id)
    ob.dispatch_once(pub, FAST)
    pub.fail_event_ids.clear()
    OutboxEvent.objects.filter(pk=row.pk).update(next_attempt_at=row.created_at)
    stats = ob.dispatch_once(pub, FAST)
    row.refresh_from_db()
    assert stats.delivered == 1 and row.delivery_status == S.ACKED and row.attempts == 2
    assert pub.published[0].attempt == 2


@pytest.mark.django_db
def test_stale_dispatched_rows_are_recovered_as_failed_attempts() -> None:
    row = outbox_event()
    claimed = ob.claim_batch(FAST)  # dispatcher "crashes" after the claim
    assert len(claimed) == 1
    assert ob.recover_stale(FAST) == 0  # lease still running
    short = ob.OutboxPolicy(max_attempts=3, base_delay=timedelta(seconds=10), lease=timedelta(microseconds=1))
    assert ob.recover_stale(short) == 1
    row.refresh_from_db()
    assert (row.delivery_status, row.attempts, row.last_error) == (S.FAILED, 1, "LEASE_EXPIRED")
    # the crashed dispatcher's late ACK is rejected (compare-and-set on row_version)
    assert ob.mark_delivered(claimed[0]) is False


@pytest.mark.django_db
def test_publisher_error_text_is_never_stored() -> None:
    row = outbox_event()

    class Leaky:
        def publish(self, envelope: ob.EventEnvelope) -> None:
            raise ConnectionError("amqp://user:synthetic-secret@host")

    ob.dispatch_once(Leaky(), FAST)
    row.refresh_from_db()
    assert row.last_error == "ConnectionError"


# ------------------------------------------------------------------------------------------- admin replay
@pytest.mark.django_db
def test_dead_letter_replay_is_audited_and_restricted() -> None:
    row = outbox_event()
    OutboxEvent.objects.filter(pk=row.pk).update(delivery_status=S.DEAD_LETTER, attempts=3, last_error="X")
    admin = RequestContext(
        Actor.user(uuid.UUID("00000000-0000-4000-8000-0000000000aa")), request_id=uuid.uuid4()
    )
    with pytest.raises(EngineContractError):
        ob.replay_dead_letter(RequestContext(Actor.system()), row.event_id, reason="synthetic")
    with pytest.raises(EngineContractError):
        ob.replay_dead_letter(admin, row.event_id, reason="  ")
    with pytest.raises(NotFound):
        ob.replay_dead_letter(admin, uuid.uuid4(), reason="synthetic")
    ob.replay_dead_letter(admin, row.event_id, reason="synthetic broker fixed")
    row.refresh_from_db()
    assert (row.delivery_status, row.attempts, row.last_error) == (S.PENDING, 0, "")
    audit = AuditEvent.objects.get(request_id=admin.request_id)
    assert audit.action == "platform.outbox.replay" and audit.resource_id == str(row.event_id)
    assert audit.before == {"delivery_status": "DEAD_LETTER", "attempts": 3}
    with pytest.raises(StateTransitionNotAllowed):  # PENDING is not a dead letter
        ob.replay_dead_letter(admin, row.event_id, reason="again")


def test_machine_rejects_illegal_moves() -> None:
    m = ob.OUTBOX_DELIVERY_MACHINE
    for src, dst in [
        (S.ACKED, S.PENDING),
        (S.PENDING, S.ACKED),
        (S.DEAD_LETTER, S.DISPATCHED),
        (S.FAILED, S.ACKED),
    ]:
        with pytest.raises(StateTransitionNotAllowed):
            m.assert_transition(src, dst)


@override_settings(ALEEKHAN_ENV="prod")
def test_in_memory_publisher_refused_outside_dev_test() -> None:
    with pytest.raises(EngineContractError):
        InMemoryTestPublisher()


# ------------------------------------------------------------------------------------------- race
@pytest.mark.django_db(transaction=True)
def test_concurrent_dispatchers_publish_each_event_exactly_once() -> None:
    """4 dispatchers on separate connections share 60 events: SKIP LOCKED => no event published twice."""
    for i in range(60):
        outbox_event(aggregate_id=f"synthetic-{i}")
    pub = InMemoryTestPublisher()
    policy = ob.OutboxPolicy(batch_size=7)

    def dispatcher(_: int) -> int:
        delivered = 0
        while True:
            stats = ob.dispatch_once(pub, policy)
            if stats.claimed == 0:
                return delivered
            delivered += stats.delivered

    results = run_concurrently(dispatcher, 4)
    assert all(isinstance(r, int) for r in results), results
    assert sum(results) == 60
    ids = [env.event_id for env in pub.published]
    assert len(ids) == len(set(ids)) == 60
    assert OutboxEvent.objects.filter(delivery_status=S.ACKED, attempts=1).count() == 60
