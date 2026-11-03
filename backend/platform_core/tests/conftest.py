"""Fixtures for platform_core tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.db import connection


@pytest.fixture
def audit_cleanup(transactional_db: None) -> Iterator[None]:
    """TEST-ONLY teardown for transactional tests that *commit* audit rows.

    The audit table is append-only (DB trigger rejects DELETE and TRUNCATE of a non-empty table), so
    pytest-django's TRUNCATE flush would fail after such a test. This fixture runs before that flush (it
    depends on ``transactional_db``) and, as the throw-away test database owner, temporarily disables the
    row trigger to delete the synthetic rows. Never used outside the test database.
    """
    yield
    with connection.cursor() as cur:
        cur.execute("ALTER TABLE platform_audit_event DISABLE TRIGGER trg_audit_event_append_only")
        try:
            cur.execute("DELETE FROM platform_audit_event")
        finally:
            cur.execute("ALTER TABLE platform_audit_event ENABLE TRIGGER trg_audit_event_append_only")
