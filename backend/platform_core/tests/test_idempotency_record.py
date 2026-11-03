"""IdempotencyRecord: unique(actor_id, key), CHECKs, expires_at index, concurrent duplicate insert."""

from __future__ import annotations

import threading
import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, connections, transaction
from django.utils import timezone

from platform_core.models import IdempotencyRecord, IdempotencyState

from .factories import idempotency_record


@pytest.mark.django_db
def test_same_actor_same_key_rejected_other_actor_allowed() -> None:
    actor, key = uuid.uuid4(), uuid.uuid4()
    idempotency_record(actor_id=actor, key=key)
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        idempotency_record(actor_id=actor, key=key)
    assert "uq_idempotency_record_actor_key" in str(exc.value)
    idempotency_record(actor_id=uuid.uuid4(), key=key)  # different actor: allowed
    assert IdempotencyRecord.objects.filter(key=key).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("override", "constraint"),
    [
        ({"method": "GET"}, "ck_idempotency_record_method"),
        ({"state": "DONE"}, "ck_idempotency_record_state"),
        ({"request_hash": "ABC"}, "ck_idempotency_record_hash_fmt"),
        ({"request_hash": "G" * 64}, "ck_idempotency_record_hash_fmt"),
        ({"endpoint": ""}, "ck_idempotency_record_endpoint_nonempty"),
        ({"response_status": 99}, "ck_idempotency_record_status_range"),
        ({"response_status": 600}, "ck_idempotency_record_status_range"),
        ({"state": IdempotencyState.COMPLETED}, "ck_idempotency_record_completed_has_status"),
        ({"expires_at": "PAST"}, "ck_idempotency_record_expiry_after_create"),
    ],
)
def test_check_constraints_fire(override: dict[str, object], constraint: str) -> None:
    if override.get("expires_at") == "PAST":
        override = {"expires_at": timezone.now() - timedelta(minutes=5)}
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        idempotency_record(**override)
    assert constraint in str(exc.value)


@pytest.mark.django_db
def test_completed_with_status_and_row_version_bump() -> None:
    rec = idempotency_record()
    IdempotencyRecord.objects.filter(pk=rec.pk).update(
        state=IdempotencyState.COMPLETED, response_status=201, response_body={"ok": True}
    )
    rec.refresh_from_db()
    assert rec.state == IdempotencyState.COMPLETED
    assert rec.row_version == 2
    assert rec.updated_at >= rec.created_at


@pytest.mark.django_db
def test_expires_at_index_exists() -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'platform_idempotency_record' "
            "AND indexname = 'ix_idempotency_record_expires'"
        )
        row = cur.fetchone()
    assert row is not None
    assert "(expires_at)" in row[0]


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_insert_exactly_one_wins() -> None:
    """Two connections race to insert the same (actor_id, key): the DB lets exactly one commit."""
    actor, key = uuid.uuid4(), uuid.uuid4()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        result = "error"
        try:
            barrier.wait(timeout=10)
            with transaction.atomic():
                idempotency_record(actor_id=actor, key=key)
            result = "ok"
        except IntegrityError:
            result = "dup"
        finally:
            connections.close_all()
            with lock:
                outcomes.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(outcomes) == ["dup", "ok"]
    assert IdempotencyRecord.objects.filter(actor_id=actor, key=key).count() == 1
