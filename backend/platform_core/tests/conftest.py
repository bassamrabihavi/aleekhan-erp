"""Fixtures for platform_core tests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from django.conf import settings
from django.core.cache import cache
from django.db import connection


def assert_throwaway_test_db(settings_dict: Mapping[str, Any], env: str) -> None:
    """REV-0008: refuse destructive test helpers unless connected to the throw-away test database.

    pytest-django creates it as ``test_<NAME>`` (or ``TEST.NAME``); ``ALEEKHAN_ENV`` must be ``test``.
    """
    name = str(settings_dict.get("NAME") or "")
    if env != "test":
        raise RuntimeError(f"destructive test helper refused: ALEEKHAN_ENV={env!r} is not 'test'")
    if not name.startswith("test_"):
        raise RuntimeError(f"destructive test helper refused: database {name!r} is not a test_ database")


@pytest.fixture
def audit_cleanup(transactional_db: None) -> Iterator[None]:
    """TEST-ONLY teardown for transactional tests that *commit* audit rows.

    The audit table is append-only (DB trigger rejects DELETE and TRUNCATE of a non-empty table), so
    pytest-django's TRUNCATE flush would fail after such a test. This fixture runs before that flush (it
    depends on ``transactional_db``) and, as the throw-away test database owner, temporarily disables the
    row trigger to delete the synthetic rows. It refuses to run on anything but the test database.
    """
    assert_throwaway_test_db(connection.settings_dict, settings.ALEEKHAN_ENV)
    yield
    assert_throwaway_test_db(connection.settings_dict, settings.ALEEKHAN_ENV)
    with connection.cursor() as cur:
        cur.execute("ALTER TABLE platform_audit_event DISABLE TRIGGER trg_audit_event_append_only")
        try:
            cur.execute("DELETE FROM platform_audit_event")
        finally:
            cur.execute("ALTER TABLE platform_audit_event ENABLE TRIGGER trg_audit_event_append_only")


@pytest.fixture
def clear_cache() -> Iterator[None]:
    """Rate-limit counters live in the (local-memory) cache: isolate API tests from each other.

    Also resets the per-process readiness migrations-check cache (REV-0016)."""
    from platform_core.api.views import reset_migrations_check_cache

    cache.clear()
    reset_migrations_check_cache()
    yield
    cache.clear()
    reset_migrations_check_cache()
