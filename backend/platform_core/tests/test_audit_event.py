"""AuditEvent: append-only enforced by PostgreSQL triggers (UPDATE/DELETE/TRUNCATE) + named CHECKs."""

from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, connection, transaction

from platform_core.models import ActorType, AuditAppendOnlyError, AuditEvent

from .factories import audit_event

pytestmark = pytest.mark.django_db


def _pgcode(exc: BaseException) -> str | None:
    return getattr(exc.__cause__, "sqlstate", None)


def test_insert_sets_server_utc_timestamp() -> None:
    ev = audit_event()
    ev.refresh_from_db()
    assert ev.occurred_at is not None
    offset = ev.occurred_at.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


def test_raw_update_is_rejected_by_trigger() -> None:
    ev = audit_event()
    with pytest.raises(IntegrityError) as exc, transaction.atomic(), connection.cursor() as cur:
        cur.execute("UPDATE platform_audit_event SET reason = 'tampered' WHERE id = %s", [ev.id])
    assert "append-only" in str(exc.value)
    assert _pgcode(exc.value) == "23001"
    ev.refresh_from_db()
    assert ev.reason == ""


def test_queryset_update_is_rejected_by_trigger() -> None:
    ev = audit_event()
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditEvent.objects.filter(id=ev.id).update(reason="tampered")


def test_raw_delete_is_rejected_by_trigger() -> None:
    ev = audit_event()
    with pytest.raises(IntegrityError) as exc, transaction.atomic(), connection.cursor() as cur:
        cur.execute("DELETE FROM platform_audit_event WHERE id = %s", [ev.id])
    assert _pgcode(exc.value) == "23001"
    assert AuditEvent.objects.filter(id=ev.id).exists()


def test_queryset_delete_is_rejected_by_trigger() -> None:
    audit_event()
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditEvent.objects.all().delete()
    assert AuditEvent.objects.count() == 1


def test_truncate_of_nonempty_table_is_rejected() -> None:
    audit_event()
    with pytest.raises(IntegrityError) as exc, transaction.atomic(), connection.cursor() as cur:
        cur.execute("TRUNCATE platform_audit_event")
    assert "TRUNCATE" in str(exc.value)
    assert AuditEvent.objects.count() == 1


def test_truncate_of_empty_table_is_allowed() -> None:
    assert AuditEvent.objects.count() == 0
    with connection.cursor() as cur:
        cur.execute("TRUNCATE platform_audit_event")


def test_orm_guard_rejects_save_of_existing_and_delete() -> None:
    ev = audit_event()
    ev.reason = "tampered"
    with pytest.raises(AuditAppendOnlyError):
        ev.save()
    with pytest.raises(AuditAppendOnlyError):
        ev.delete()


def test_triggers_are_installed() -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT tgname FROM pg_trigger WHERE tgrelid = 'platform_audit_event'::regclass "
            "AND NOT tgisinternal ORDER BY tgname"
        )
        assert [r[0] for r in cur.fetchall()] == [
            "trg_audit_event_append_only",
            "trg_audit_event_no_truncate",
        ]


@pytest.mark.parametrize(
    ("override", "constraint"),
    [
        ({"actor_type": "ROBOT"}, "ck_audit_event_actor_type"),
        ({"actor_type": ActorType.USER, "actor_id": None}, "ck_audit_event_actor_id_for_user"),
        ({"outcome": "MAYBE"}, "ck_audit_event_outcome"),
        ({"action": "NoDots"}, "ck_audit_event_action_fmt"),
        ({"action": "platform."}, "ck_audit_event_action_fmt"),
        ({"resource_type": ""}, "ck_audit_event_resource_type_nonempty"),
        ({"resource_version": -1}, "ck_audit_event_resource_version_nonneg"),
        ({"scope": ["not", "an", "object"]}, "ck_audit_event_scope_object"),
    ],
)
def test_check_constraints_fire(override: dict[str, object], constraint: str) -> None:
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        audit_event(**override)
    assert constraint in str(exc.value)


def test_user_actor_with_id_is_accepted() -> None:
    ev = audit_event(actor_type=ActorType.USER, actor_id=uuid.uuid4(), action="production.batch.start-cut")
    assert AuditEvent.objects.filter(id=ev.id).exists()
