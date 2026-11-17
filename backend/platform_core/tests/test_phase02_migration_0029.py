"""Migration 0029 (02.8 Gate follow-up, REV-0290) with data: reverse to 0028 and forward again on a test
database that holds an open change request. Forward backfills ``expires_at`` (submit + 30 days) and stops
with a count-only message when an order has two open requests. Synthetic data only; the database is always
migrated back to the leaf migration (finally block)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from platform_core.commercial import changes
from platform_core.devtools import phase02_engine as e
from platform_core.devtools.engine_fixtures import ensure_catalogue

APP = "platform_core"
BEFORE = (APP, "0028_phase02_golden_summary")
AFTER = (APP, "0029_dec059_cr_open_expiry")


@pytest.fixture
def phase02_tx(audit_cleanup: None) -> None:
    ensure_catalogue()


pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("phase02_tx")]


def _migrate(target: tuple[str, str]) -> None:
    ex = MigrationExecutor(connection)
    ex.loader.build_graph()
    ex.migrate([target])


def _leaf() -> None:
    ex = MigrationExecutor(connection)
    _migrate(ex.loader.graph.leaf_nodes(APP)[0])


def _cols() -> set[str]:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'commercial_order_change_request'"
        )
        return {r[0] for r in cur.fetchall()}


def test_0029_reverse_and_forward_with_open_requests() -> None:
    p = e.people()
    o = e.confirmed_order(p.co, p.po)
    o.refresh_from_db()
    cr = changes.create_change_request(
        p.co.caller,
        o.pk,
        kind="HOLD",
        items=[],
        reason="synthetic",
        expected_version=o.row_version,
        submit=True,
    )
    draft = changes.create_change_request(
        p.co2.caller, o.pk, kind="HOLD", items=[], reason="synthetic", expected_version=o.row_version
    )
    try:
        _migrate(BEFORE)
        assert "expires_at" not in _cols()
        with connection.cursor() as cur:  # a second open request, possible before 0029
            cur.execute(
                "UPDATE commercial_order_change_request SET status = 'SUBMITTED', submitted_at = now() "
                "WHERE id = %s",
                [draft.pk],
            )
        with pytest.raises(RuntimeError, match="1 order"):
            _migrate(AFTER)
        assert "expires_at" not in _cols()  # the failed forward left nothing behind
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE commercial_order_change_request SET status = 'WITHDRAWN' WHERE id = %s", [draft.pk]
            )
        _migrate(AFTER)
        assert "expires_at" in _cols()
        with connection.cursor() as cur:
            cur.execute(
                "SELECT expires_at - submitted_at FROM commercial_order_change_request WHERE id = %s", [cr.pk]
            )
            row = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM platform_job_definition WHERE job_type = 'change_request_expiry_sweep'"
            )
            jobs = cur.fetchone()
        assert row is not None and row[0] == timedelta(days=30)
        assert jobs is not None and jobs[0] == 1
    finally:
        _leaf()
