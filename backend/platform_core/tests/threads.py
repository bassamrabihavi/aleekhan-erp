"""Run a callable concurrently on separate DB connections (race tests against PostgreSQL)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from django.db import connections


def run_concurrently(fn: Callable[[int], Any], n: int, *, timeout: float = 60) -> list[Any]:
    """Start ``n`` threads behind a barrier; return each result or the exception it raised (by index)."""
    barrier = threading.Barrier(n)
    results: list[Any] = [None] * n

    def worker(i: int) -> None:
        try:
            barrier.wait(timeout=timeout)
            results[i] = fn(i)
        except BaseException as exc:  # collected and asserted by the test
            results[i] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
    if any(t.is_alive() for t in threads):
        raise TimeoutError("concurrent workers did not finish")
    return results
