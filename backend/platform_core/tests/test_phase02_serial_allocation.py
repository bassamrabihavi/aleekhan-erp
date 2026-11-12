"""PHASE_02 / 02.2 serial allocation primitive against PostgreSQL (DEC-006 S-A + L-A + G-B + P-A).

* ID-02 (Gate "100 concurrent requests without serial duplicate"): 100 concurrent order confirms - no
  duplicate,
  **no gap** (G-B), exactly one snapshot v1 and one ``identity.serial.allocated`` event per committed line;
  forced
  failures roll back without consuming a number.
* ID-04: the same allocation key gives one serial (replay draws no number and writes no second event);
  concurrent
  duplicate confirms of one order have a single effect.
* Rollback after allocation consumes nothing (the counter row lock is released with the transaction).

Concurrency: ``ALEEKHAN_RACE_WORKERS`` (default 32) threads, each on its own DB connection, start behind a
barrier
and share the 100 confirms. The test server allows 100 connections in total (``max_connections``), so 100
simultaneous connections are not possible next to the test runner; every one of the 100 requests is still in
flight concurrently with the others of its worker set. All data is synthetic (``phase02_factories``).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from django.db import IntegrityError, connection

from platform_core.commercial.models import CustomerOrder, CustomerOrderLine
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.uow import unit_of_work
from platform_core.models import AuditEvent, OutboxEvent
from platform_core.product_identity.models import Serial, SerialCounter, SerialSnapshot
from platform_core.product_identity.serials import EVENT_TYPE, AllocationRequest, allocate_serial

from . import phase02_factories as f
from .engine_fixtures import ensure_catalogue
from .phase01_factories import user
from .threads import run_concurrently

REQUESTS = 100
WORKERS = int(os.environ.get("ALEEKHAN_RACE_WORKERS", "32"))
FAIL_EVERY = 10  # every 10th confirm fails after its allocation -> must not consume a number


def _next_value() -> int:
    return SerialCounter.objects.get(namespace_key="factory_serial").next_value


def _immediate() -> None:
    with connection.cursor() as cur:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute("SET CONSTRAINTS ALL DEFERRED")


# ------------------------------------------------------------------------------------- single transaction
@pytest.mark.django_db
def test_allocation_writes_serial_snapshot_audit_and_outbox_together() -> None:
    o, _lines, _creator = f.validated_order(2)
    confirmer = user()
    first = _next_value()
    numbers = f.confirm_order(o.pk, confirmer)
    _immediate()  # the deferred DB checks (gapless, snapshot v1, line pairing, version row) hold
    assert numbers == [str(first), str(first + 1)]  # plain integer text, consecutive, from the counter
    assert _next_value() == first + 2
    for ln in CustomerOrderLine.objects.filter(order=o):
        serial = Serial.objects.get(pk=str(ln.serial_id))
        assert (ln.status, serial.status, serial.allocated_by_id) == ("CONFIRMED", "ALLOCATED", confirmer.pk)
        snap = SerialSnapshot.objects.get(serial=serial)
        assert (snap.version, snap.reason, snap.order_version) == (1, "ALLOCATED", 1)
        event = OutboxEvent.objects.get(event_type=EVENT_TYPE, aggregate_id=str(serial.pk))
        assert event.payload == {"id": str(serial.pk), "status": "ALLOCATED", "snapshot_version": 1}
        assert event.producer == "platform_core.product_identity"
        assert (
            AuditEvent.objects.filter(action="identity.serial.allocate", resource_id=str(serial.pk)).count()
            == 1
        )
    assert CustomerOrder.objects.get(pk=o.pk).status == "CONFIRMED"


@pytest.mark.django_db
def test_id04_same_allocation_key_replays_the_same_serial_without_a_new_number() -> None:
    o, lines, _creator = f.validated_order(1)
    confirmer = user()
    first = _next_value()
    key = uuid.uuid4()
    request = AllocationRequest(
        idempotency_key=key,
        allocated_by=confirmer.pk,
        customer_id=o.customer_id,
        style_id=lines[0].style_id,
        style_revision_id=lines[0].style_revision_id,
        product_code_id=None,
        order_version=1,
        snapshot={"synthetic": True},
    )
    with unit_of_work(RequestContext(Actor.user(confirmer.pk))) as uow:
        a = allocate_serial(uow, request)
        b = allocate_serial(uow, request)
        CustomerOrderLine.objects.filter(pk=lines[0].pk).update(
            status="CONFIRMED", serial=a.serial, order_version=1
        )
    assert (a.replayed, b.replayed, a.serial.pk) == (False, True, b.serial.pk)
    assert _next_value() == first + 1
    assert OutboxEvent.objects.filter(event_type=EVENT_TYPE, aggregate_id=str(a.serial.pk)).count() == 1
    assert Serial.objects.filter(allocation_idempotency_key=key).count() == 1


@pytest.mark.django_db
def test_allocation_outside_a_user_actor_is_refused() -> None:
    from platform_core.engine.errors import EngineContractError

    o, lines, _creator = f.validated_order(1)
    with pytest.raises(EngineContractError), unit_of_work(RequestContext(Actor.system())) as uow:
        allocate_serial(
            uow,
            AllocationRequest(
                idempotency_key=uuid.uuid4(),
                allocated_by=user().pk,
                customer_id=o.customer_id,
                style_id=lines[0].style_id,
                style_revision_id=lines[0].style_revision_id,
                product_code_id=None,
                order_version=1,
                snapshot={},
            ),
        )


# ------------------------------------------------------------------------------------------- committed
@pytest.fixture
def phase02_tx(audit_cleanup: None) -> None:
    """Transactional DB (committed rows): the seeded catalogue is re-created after the previous flush."""
    ensure_catalogue()


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("phase02_tx")
def test_rollback_after_allocation_does_not_consume_a_number() -> None:
    o, _lines, _creator = f.validated_order(2)
    confirmer = user()
    first = _next_value()
    events_before = OutboxEvent.objects.filter(event_type=EVENT_TYPE).count()
    with pytest.raises(RuntimeError):
        f.confirm_order(o.pk, confirmer, fail_after_allocation=True)
    assert _next_value() == first  # G-B: the counter step rolled back with the confirm
    assert not Serial.objects.exists() and not SerialSnapshot.objects.exists()
    assert OutboxEvent.objects.filter(event_type=EVENT_TYPE).count() == events_before
    assert CustomerOrder.objects.get(pk=o.pk).status == "VALIDATED"
    assert f.confirm_order(o.pk, confirmer) == [str(first), str(first + 1)]  # the same numbers, no gap


def _confirm_share(
    orders: list[uuid.UUID], confirmer_ids: list[uuid.UUID]
) -> Callable[[int], list[tuple[int, str, Any]]]:
    from platform_core.identity.models import User

    def work(worker: int) -> list[tuple[int, str, Any]]:
        out: list[tuple[int, str, Any]] = []
        for idx in range(worker, len(orders), WORKERS):
            who = User.objects.get(pk=confirmer_ids[idx])
            try:
                numbers = f.confirm_order(
                    orders[idx], who, fail_after_allocation=(idx % FAIL_EVERY == FAIL_EVERY - 1)
                )
                out.append((idx, "OK", numbers))
            except RuntimeError:
                out.append((idx, "FAILED", None))
        return out

    return work


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("phase02_tx")
def test_id02_100_concurrent_confirms_no_duplicate_no_gap_one_snapshot_per_line_race() -> None:
    first = _next_value()
    orders, confirmers, line_counts = [], [], []
    _t, _c, _p, sty, rev = f.styled()
    for i in range(REQUESTS):
        o, lines, _creator = f.validated_order(
            1 + (i % 2), chain=(sty, rev)
        )  # 1 or 2 independent lines (ID-03)
        orders.append(o.pk)
        line_counts.append(len(lines))
        confirmers.append(user().pk)

    results = run_concurrently(_confirm_share(orders, confirmers), min(WORKERS, REQUESTS), timeout=600)
    flat = [r for worker in results for r in (worker if isinstance(worker, list) else [worker])]
    errors = [r for r in flat if isinstance(r, BaseException)]
    assert errors == []
    ok = {idx: numbers for idx, state, numbers in flat if state == "OK"}
    failed = {idx for idx, state, _n in flat if state == "FAILED"}
    assert len(ok) + len(failed) == REQUESTS
    assert failed == {i for i in range(REQUESTS) if i % FAIL_EVERY == FAIL_EVERY - 1}

    committed_lines = sum(line_counts[i] for i in ok)
    values = sorted(Serial.objects.values_list("serial_value", flat=True))
    numbers = [n for nums in ok.values() for n in nums]
    assert len(numbers) == len(set(numbers)) == committed_lines  # no duplicate
    assert values == list(
        range(first, first + committed_lines)
    )  # no gap (G-B), failed confirms consumed nothing
    assert sorted(int(n) for n in numbers) == values
    assert _next_value() == first + committed_lines
    # exactly one snapshot v1 and one event per committed line; nothing for the rolled back confirms
    assert (
        SerialSnapshot.objects.count() == SerialSnapshot.objects.filter(version=1).count() == committed_lines
    )
    assert OutboxEvent.objects.filter(event_type=EVENT_TYPE).count() == committed_lines
    assert (
        CustomerOrderLine.objects.filter(status="CONFIRMED", serial__isnull=False).count() == committed_lines
    )
    for idx in failed:
        assert CustomerOrder.objects.get(pk=orders[idx]).status == "VALIDATED"
        assert not CustomerOrderLine.objects.filter(order_id=orders[idx], serial__isnull=False).exists()

    # the failed ones are confirmed afterwards, concurrently: the run stays contiguous
    retry = sorted(failed)
    redo = run_concurrently(lambda i: f.confirm_order(orders[retry[i]], user()), len(retry), timeout=300)
    assert [r for r in redo if isinstance(r, BaseException)] == []
    total = sum(line_counts)
    assert sorted(Serial.objects.values_list("serial_value", flat=True)) == list(range(first, first + total))


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("phase02_tx")
def test_id04_concurrent_duplicate_confirms_of_one_order_have_a_single_effect_race() -> None:
    o, _lines, _creator = f.validated_order(2)
    first = _next_value()
    confirmers = [user() for _ in range(6)]
    results = run_concurrently(lambda i: f.confirm_order(o.pk, confirmers[i]), len(confirmers))
    winners = [r for r in results if isinstance(r, list) and r]
    losers = [r for r in results if not (isinstance(r, list) and r)]
    assert len(winners) == 1 and winners[0] == [str(first), str(first + 1)]
    assert all(isinstance(r, IntegrityError) for r in losers), losers  # second version row refused
    assert Serial.objects.count() == 2 and _next_value() == first + 2
    assert OutboxEvent.objects.filter(event_type=EVENT_TYPE).count() == 2
