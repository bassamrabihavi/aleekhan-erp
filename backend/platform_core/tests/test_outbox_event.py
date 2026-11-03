"""OutboxEvent: unique event_id, delivery_status CHECK, dispatcher index, row_version trigger."""

from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from platform_core.models import DeliveryStatus, OutboxEvent

from .factories import outbox_event

pytestmark = pytest.mark.django_db


def test_db_defaults_on_insert() -> None:
    ev = outbox_event()
    ev.refresh_from_db()
    assert ev.delivery_status == DeliveryStatus.PENDING
    assert ev.attempts == 0
    assert ev.row_version == 1
    assert ev.schema_version == 1
    assert ev.next_attempt_at is not None
    assert ev.created_at is not None


def test_event_id_is_unique() -> None:
    eid = uuid.uuid4()
    outbox_event(event_id=eid)
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        outbox_event(event_id=eid)
    assert "uq_outbox_event_event_id" in str(exc.value)


@pytest.mark.parametrize(
    ("override", "constraint"),
    [
        ({"delivery_status": "SENT"}, "ck_outbox_event_delivery_status"),
        ({"delivery_status": DeliveryStatus.ACKED}, "ck_outbox_event_acked_has_ts"),
        ({"delivery_status": DeliveryStatus.DISPATCHED}, "ck_outbox_event_dispatched_has_ts"),
        ({"event_type": "Created"}, "ck_outbox_event_type_fmt"),
        ({"schema_version": 0}, "ck_outbox_event_schema_version_pos"),
        ({"aggregate_version": -1}, "ck_outbox_event_agg_version_nonneg"),
        ({"attempts": -1}, "ck_outbox_event_attempts_nonneg"),
        ({"payload": [1, 2]}, "ck_outbox_event_payload_object"),
        ({"actor_type": "USER"}, "ck_outbox_event_actor_id_for_user"),
        ({"actor_type": "BOT"}, "ck_outbox_event_actor_type"),
    ],
)
def test_check_constraints_fire(override: dict[str, object], constraint: str) -> None:
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        outbox_event(**override)
    assert constraint in str(exc.value)


def test_valid_status_rows_accepted() -> None:
    now = timezone.now()
    outbox_event(delivery_status=DeliveryStatus.DISPATCHED, dispatched_at=now)
    outbox_event(delivery_status=DeliveryStatus.ACKED, dispatched_at=now, acked_at=now)
    outbox_event(delivery_status=DeliveryStatus.DEAD_LETTER, attempts=5)
    assert OutboxEvent.objects.count() == 3


def test_update_bumps_row_version_and_keeps_created_at() -> None:
    ev = outbox_event()
    ev.refresh_from_db()
    created = ev.created_at
    OutboxEvent.objects.filter(pk=ev.pk).update(attempts=1, delivery_status=DeliveryStatus.FAILED)
    OutboxEvent.objects.filter(pk=ev.pk).update(row_version=999, created_at=timezone.now())
    ev.refresh_from_db()
    assert ev.row_version == 3  # trigger ignores a client-supplied row_version
    assert ev.created_at == created


def test_dispatcher_query_uses_partial_index() -> None:
    with connection.cursor() as cur:
        cur.execute("SET LOCAL enable_seqscan = off")
        cur.execute(
            "EXPLAIN SELECT id FROM platform_outbox_event "
            "WHERE delivery_status IN ('PENDING', 'FAILED') AND next_attempt_at <= now() "
            "ORDER BY next_attempt_at, id LIMIT 100 FOR UPDATE SKIP LOCKED"
        )
        plan = "\n".join(r[0] for r in cur.fetchall())
    assert "ix_outbox_event_dispatch" in plan
