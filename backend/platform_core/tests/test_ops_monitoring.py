"""00.7 job monitoring: ``outbox_snapshot`` and ``manage.py outbox_status`` (SYNTHETIC events)."""

from __future__ import annotations

import io
import json
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from platform_core.engine.context import db_now
from platform_core.engine.outbox import INTEGRATION_POLICY
from platform_core.models import DeliveryStatus, OutboxEvent
from platform_core.ops.monitoring import DUE_BACKLOG_WARN, outbox_snapshot

from . import factories

pytestmark = pytest.mark.django_db


def test_empty_queue_is_ok() -> None:
    snap = outbox_snapshot()
    assert snap.counts == {s: 0 for s in DeliveryStatus.values}
    assert (snap.verdict, snap.reasons, snap.due_now, snap.dead_letters) == ("ok", [], 0, 0)
    assert snap.oldest_pending_age_seconds is None and snap.last_dispatched_at is None


def test_counts_ages_and_verdicts() -> None:
    now = db_now()
    factories.outbox_event(next_attempt_at=now - timedelta(seconds=30))  # due PENDING
    factories.outbox_event(next_attempt_at=now + timedelta(hours=1))  # scheduled, not due
    factories.outbox_event(delivery_status=DeliveryStatus.FAILED, attempts=2, next_attempt_at=now)
    factories.outbox_event(delivery_status=DeliveryStatus.ACKED, acked_at=now - timedelta(minutes=1))
    factories.outbox_event(
        delivery_status=DeliveryStatus.DISPATCHED, dispatched_at=now - timedelta(seconds=5)
    )
    snap = outbox_snapshot(now=now)
    assert snap.counts["PENDING"] == 2 and snap.counts["FAILED"] == 1 and snap.counts["ACKED"] == 1
    assert snap.due_now == 2
    assert snap.oldest_due_age_seconds == 30
    assert snap.stale_dispatched == 0
    assert snap.verdict == "ok"
    assert snap.last_dispatched_at is not None and snap.last_acked_at is not None

    # dispatcher crashed: DISPATCHED older than the lease -> warn
    factories.outbox_event(
        delivery_status=DeliveryStatus.DISPATCHED,
        dispatched_at=now - INTEGRATION_POLICY.lease - timedelta(seconds=1),
    )
    snap = outbox_snapshot(now=now)
    assert (snap.stale_dispatched, snap.verdict, snap.reasons) == (1, "warn", ["STALE_DISPATCHED"])

    # backlog older than the TECHNICAL DEFAULT -> warn; dead letter -> critical
    later = now + DUE_BACKLOG_WARN + timedelta(minutes=1)
    assert "DUE_BACKLOG" in outbox_snapshot(now=later).reasons
    factories.outbox_event(delivery_status=DeliveryStatus.DEAD_LETTER, attempts=8)
    snap = outbox_snapshot(now=now)
    assert snap.dead_letters == 1 and snap.verdict == "critical" and snap.reasons[0] == "DEAD_LETTER_PRESENT"


def test_command_text_json_and_exit_codes() -> None:
    out = io.StringIO()
    call_command("outbox_status", stdout=out)
    assert "verdict: ok" in out.getvalue()
    out = io.StringIO()
    call_command("outbox_status", "--json", "--fail-on", "warn", stdout=out)
    assert json.loads(out.getvalue())["verdict"] == "ok"

    factories.outbox_event(
        delivery_status=DeliveryStatus.DEAD_LETTER,
        attempts=8,
        payload={"note": "synthetic"},
        last_error="SYNTHETIC_ERROR_CODE",
    )
    out = io.StringIO()
    call_command("outbox_status", "--json", stdout=out)
    data = json.loads(out.getvalue())
    assert data["dead_letters"] == 1 and data["verdict"] == "critical"
    assert "SYNTHETIC_ERROR_CODE" not in out.getvalue() and "synthetic" not in out.getvalue()
    with pytest.raises(CommandError) as exc:
        call_command("outbox_status", "--fail-on", "critical", stdout=io.StringIO())
    assert exc.value.returncode == 1


def test_snapshot_is_read_only() -> None:
    e = factories.outbox_event()
    before = OutboxEvent.objects.get(pk=e.pk).row_version
    outbox_snapshot()
    assert OutboxEvent.objects.get(pk=e.pk).row_version == before
