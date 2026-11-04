"""Perf smoke (00.7, marker ``perf``; run with ``pytest -m perf``). SYNTHETIC data only.

Measures latency (p50 / p95 / max, milliseconds) of the PHASE_00 read endpoints through the Django test
client against the real PostgreSQL test database: ``/health/live``, ``/health/ready``, ``/version`` and the
integration freshness list (TEST-ONLY harness principal, 25 synthetic sources + the seeded ones).

These numbers measure the application path on the machine running the tests (no network, no proxy, no
gunicorn) and are recorded as evidence, not as an SLA. The budget below is a TECHNICAL DEFAULT that only
catches gross regressions (e.g. an N+1 query or a migration-graph load per call); real performance targets
belong to the pilot environment and are not decided here. ``ALEEKHAN_PERF_OUT=<file>`` writes the numbers
as JSON.
"""

from __future__ import annotations

import json
import os
import statistics
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from django.test import Client, override_settings

from platform_core.api import integration_views as iv
from platform_core.integration.models import IntegrationSource

from . import factories

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("clear_cache"), pytest.mark.django_db]

ITERATIONS = 200
WARMUP = 10
# TECHNICAL DEFAULT gross-regression budget for p95 per request in-process (not an SLA).
P95_BUDGET_MS = 250.0
RATES = {"anon": "100000/min", "principal": "100000/min", "health": "100000/min"}


def _measure(fn: Callable[[], Any]) -> dict[str, float]:
    for _ in range(WARMUP):
        fn()
    samples = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    return {
        "n": float(len(samples)),
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(samples[int(0.95 * len(samples)) - 1], 3),
        "max_ms": round(samples[-1], 3),
    }


@pytest.mark.urls("platform_core.tests.api_harness")
@override_settings(ALEEKHAN_THROTTLE_RATES=RATES)
def test_perf_smoke_read_endpoints(client: Client) -> None:
    for _ in range(25):
        factories.integration_source()
    who = {
        "HTTP_X_TEST_PRINCIPAL": str(uuid.uuid4()),
        "HTTP_X_TEST_ACTIONS": iv.READ_FRESHNESS,
        "HTTP_X_TEST_SCOPE": ",".join(
            IntegrationSource.objects.values_list("code", flat=True).order_by("code")
        ),
    }

    def get(url: str, **headers: Any) -> Callable[[], Any]:
        def call() -> Any:
            r = client.get(url, **headers)
            assert r.status_code == 200, (url, r.status_code)
            return r

        return call

    results = {
        "health_live": _measure(get("/api/v1/health/live")),
        "health_ready": _measure(get("/api/v1/health/ready")),
        "version": _measure(get("/api/v1/version")),
        "integration_freshness_page25": _measure(get("/api/v1/_test/integration/freshness", **who)),
    }
    report = {
        "iterations": ITERATIONS,
        "warmup": WARMUP,
        "p95_budget_ms": P95_BUDGET_MS,
        "budget_basis": "TECHNICAL_DEFAULT (gross-regression guard, in-process test client, not an SLA)",
        "results": results,
    }
    print(json.dumps(report, indent=2))
    out = os.environ.get("ALEEKHAN_PERF_OUT", "").strip()
    if out:
        Path(out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    for name, r in results.items():
        assert r["p95_ms"] < P95_BUDGET_MS, (name, r)
