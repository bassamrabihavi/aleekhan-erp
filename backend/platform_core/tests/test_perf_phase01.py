"""PHASE_01 / 01.7 performance evidence (marker ``perf``; run with ``pytest -m perf``). SYNTHETIC data only.

Real PostgreSQL test database, Django test client in-process (no network, no proxy, no gunicorn). Numbers are
evidence of the machine that ran them (``ALEEKHAN_MACHINE`` is recorded), not an SLA. Every budget below is a
TECHNICAL DEFAULT gross-regression guard (an N+1 explosion, a lost index, a lock held too long); real targets
belong to the pilot environment and are not decided here. ``ALEEKHAN_PERF_OUT=<file>`` writes the numbers as
JSON (one object per test, keyed by test name).

1. Inboxes at the per-record check limit (01.4 report section 7, ``FILTER_SCAN_CAP`` = 1000):
   ``GET /workflow/approvals?inbox=to_decide`` for an approver whose 1000 PENDING requests are all his own
   (maker != checker: every row is checked and refused -> the whole cap is scanned) and
   ``GET /workflow/tasks?inbox=mine`` for an employee with 1000 tasks of other people in the table.
2. Audit chain lock: N concurrent writers (separate DB connections) each commit K units of work with one
   audit row; throughput (rows/s) and the chain stays contiguous and verifies.
3. Outbox dispatch: 2000 events over 50 aggregates through the in-process consumer registry (per-aggregate
   ordering on), one dispatcher and four concurrent dispatchers; events/s and delivery lag (acked - created).
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import time
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from platform_core.engine import audit_chain as ac
from platform_core.engine import consumers as cs
from platform_core.engine import outbox as ob
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.uow import unit_of_work
from platform_core.models import AuditEvent, DeliveryStatus, OutboxEvent
from platform_core.workflow.models import ApprovalRequest, WorkTask

from .engine_fixtures import network as set_network
from .phase01_api import get, session_client, with_roles
from .threads import run_concurrently

pytestmark = [pytest.mark.perf]

RATES = {
    "anon": "100000/min",
    "principal": "100000/min",
    "health": "100000/min",
    "login_ip": "100000/min",
    "login_user": "100000/min",
}
INBOX_ROWS = 1000
INBOX_ITERATIONS = 15
# TECHNICAL DEFAULT budgets (gross-regression guards, not SLAs)
INBOX_P95_BUDGET_MS = 5000.0
AUDIT_MIN_ROWS_PER_S = 20.0
DISPATCH_MIN_EVENTS_PER_S = 50.0


def _record(name: str, data: dict[str, Any]) -> None:
    data = {
        "machine": os.environ.get("ALEEKHAN_MACHINE", "unknown"),
        "python": platform.python_version(),
        "postgres_server_version": getattr(connection, "pg_version", None),
        "budget_basis": "TECHNICAL_DEFAULT (gross-regression guard, in-process, synthetic data, not an SLA)",
        **data,
    }
    print(json.dumps({name: data}, indent=2, default=str))
    out = os.environ.get("ALEEKHAN_PERF_OUT", "").strip()
    if out:
        path = Path(out)
        current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        current[name] = data
        path.write_text(json.dumps(current, indent=2, default=str), encoding="utf-8")


def _latency(fn: Callable[[], Any], n: int) -> dict[str, float]:
    fn()  # warm-up
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    return {
        "n": float(n),
        "p50_ms": round(statistics.median(samples), 1),
        "p95_ms": round(samples[max(0, int(0.95 * n) - 1)], 1),
        "max_ms": round(samples[-1], 1),
    }


# ------------------------------------------------------------------------------------------- 1. inboxes
@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache")
@override_settings(ALEEKHAN_THROTTLE_RATES=RATES)
def test_perf_inboxes_at_the_per_record_check_limit(settings: Any) -> None:
    set_network(settings)
    approver = with_roles("document_approver")
    now = timezone.now()
    ApprovalRequest.objects.bulk_create(
        [
            ApprovalRequest(
                action_id="platform.document.approve",
                resource_type="document_revision",
                resource_id=str(uuid.uuid4()),
                resource_revision=1,
                requested_by=approver,
                requested_at=now,
                expires_at=now + timedelta(days=30),
            )
            for _ in range(INBOX_ROWS)
        ],
        batch_size=500,
    )
    other = with_roles("employee")
    WorkTask.objects.bulk_create(
        [
            WorkTask(subject=f"کار ساختگی {i}", assignee_kind="USER", assignee_user=other, created_by=other)
            for i in range(INBOX_ROWS)
        ],
        batch_size=500,
    )
    employee = with_roles("employee")
    ca, ce = session_client(approver), session_client(employee)

    def approvals() -> None:
        r = get(ca, "/workflow/approvals", {"inbox": "to_decide", "page_size": 50})
        assert r.status_code == 200 and json.loads(r.content)["items"] == []  # all his own: none decidable

    def tasks() -> None:
        r = get(ce, "/workflow/tasks", {"inbox": "mine", "page_size": 50})
        assert r.status_code == 200 and json.loads(r.content)["items"] == []

    results = {
        "approvals_to_decide_1000_scanned": _latency(approvals, INBOX_ITERATIONS),
        "tasks_mine_1000_scanned": _latency(tasks, INBOX_ITERATIONS),
    }
    _record(
        "inboxes",
        {"rows": INBOX_ROWS, "p95_budget_ms": INBOX_P95_BUDGET_MS, "results": results},
    )
    for name, r in results.items():
        assert r["p95_ms"] < INBOX_P95_BUDGET_MS, (name, r)


# --------------------------------------------------------------------------------- 2. audit chain lock
def _write_audits(k: int) -> None:
    ctx = RequestContext(Actor.user(uuid.uuid4()), request_id=uuid.uuid4(), network_zone="INTERNAL")
    for i in range(k):
        with unit_of_work(ctx, require_event=False) as uow:
            uow.audit(
                action="platform.synthetic.update", resource_type="platform.synthetic", resource_id=str(i)
            )


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
@pytest.mark.parametrize("writers", [1, 4, 8])
def test_perf_audit_chain_lock_throughput_under_concurrency(writers: int) -> None:
    per_writer = 50
    t0 = time.perf_counter()
    results = run_concurrently(lambda _i: _write_audits(per_writer), writers, timeout=300)
    elapsed = time.perf_counter() - t0
    assert all(not isinstance(r, BaseException) for r in results), results
    total = writers * per_writer
    seqs = list(
        AuditEvent.objects.exclude(chain_seq=None).order_by("chain_seq").values_list("chain_seq", flat=True)
    )
    assert seqs == list(range(1, total + 1))  # one contiguous chain, no gap, no duplicate
    check = ac.check_chain()
    assert check.first_broken is None and check.checked == total
    rate = total / elapsed
    _record(
        f"audit_chain_writers_{writers}",
        {
            "writers": writers,
            "units_of_work": total,
            "elapsed_s": round(elapsed, 3),
            "rows_per_s": round(rate, 1),
            "min_rows_per_s_budget": AUDIT_MIN_ROWS_PER_S,
            "chain_contiguous": True,
        },
    )
    assert rate > AUDIT_MIN_ROWS_PER_S


# ----------------------------------------------------------------------------------- 3. outbox dispatch
def _publisher(seen: list[int]) -> cs.RegistryPublisher:
    reg = cs.HandlerRegistry()
    reg.register(
        cs.EventHandler(
            consumer="platform.synthetic_perf",
            event_types=frozenset({"platform.synthetic.created"}),
            handle=lambda env, _ctx: seen.append(env.aggregate_version),
            compensation_doc="SYNTHETIC perf consumer: no business effect to undo.",
        )
    )
    return cs.RegistryPublisher(reg)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
@pytest.mark.parametrize("dispatchers", [1, 4])
def test_perf_outbox_dispatch_lag(dispatchers: int) -> None:
    events, aggregates = 2000, 50
    OutboxEvent.objects.bulk_create(
        [
            OutboxEvent(
                event_type="platform.synthetic.created",
                aggregate_type="platform.synthetic",
                aggregate_id=f"agg-perf-{i % aggregates}",
                aggregate_version=i // aggregates + 1,
                actor_type="SYSTEM",
                payload={"note": "synthetic"},
            )
            for i in range(events)
        ],
        batch_size=1000,
    )
    seen: list[int] = []
    pub = _publisher(seen)
    policy = ob.OutboxPolicy(batch_size=100)

    def run(_i: int) -> int:
        idle = 0
        while idle < 3:
            if ob.dispatch_once(pub, policy).claimed == 0:
                idle += 1
                if not OutboxEvent.objects.exclude(delivery_status=DeliveryStatus.ACKED).exists():
                    return 0
                time.sleep(0.01)
            else:
                idle = 0
        return 1

    t0 = time.perf_counter()
    results = run_concurrently(run, dispatchers, timeout=600)
    elapsed = time.perf_counter() - t0
    assert all(not isinstance(r, BaseException) for r in results), results
    assert OutboxEvent.objects.filter(delivery_status=DeliveryStatus.ACKED).count() == events
    with connection.cursor() as cur:
        cur.execute(
            "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM acked_at - created_at)), "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM acked_at - created_at)), "
            "max(extract(epoch FROM acked_at - created_at)) FROM platform_outbox_event"
        )
        p50, p95, mx = cur.fetchone()
    rate = events / elapsed
    _record(
        f"outbox_dispatch_{dispatchers}",
        {
            "events": events,
            "aggregates": aggregates,
            "dispatchers": dispatchers,
            "batch_size": policy.batch_size,
            "elapsed_s": round(elapsed, 3),
            "events_per_s": round(rate, 1),
            "lag_p50_s": round(float(p50), 3),
            "lag_p95_s": round(float(p95), 3),
            "lag_max_s": round(float(mx), 3),
            "min_events_per_s_budget": DISPATCH_MIN_EVENTS_PER_S,
            "note": "lag includes the backlog wait: every event was enqueued before dispatch started",
        },
    )
    assert rate > DISPATCH_MIN_EVENTS_PER_S
    assert len(seen) == events
