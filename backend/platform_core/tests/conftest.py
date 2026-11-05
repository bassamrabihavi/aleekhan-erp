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


@pytest.fixture
def api_db(audit_cleanup: None) -> Iterator[None]:
    """01.4 HTTP tests: writes go through ``run_idempotent``, which refuses an outer transaction, so the API
    tests run on a transactional test database (committed rows, cleaned up afterwards). The seeded catalogue
    (permissions, roles, parameters, job types) is re-created after the previous test's flush."""
    from importlib import import_module

    from platform_core.documents.models import UploadType

    from .engine_fixtures import ensure_catalogue

    ensure_catalogue()
    seed = import_module("platform_core.migrations.0010_seed_phase01_catalogue")
    for ext, media, label, check in seed.UPLOAD_TYPES:  # DEC-053 allow-list, same values as migration 0010
        UploadType.objects.get_or_create(
            extension=ext,
            defaults={
                "media_type": media,
                "label_fa": label,
                "content_check": check,
                "decision_id": "DEC-053",
            },
        )
    yield
