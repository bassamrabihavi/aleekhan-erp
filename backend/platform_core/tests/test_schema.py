"""Schema-level checks: seed row, named constraints, timestamptz, no out-of-scope tables, no drift."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction

from platform_core.models import SchemaMeta

PLATFORM_TABLES = [
    "platform_audit_event",
    "platform_outbox_event",
    "platform_idempotency_record",
    "platform_schema_meta",
]


@pytest.mark.django_db
def test_seed_row_present_and_singleton() -> None:
    meta = SchemaMeta.objects.get()
    assert meta.id == 1
    assert meta.schema_contract == "PHASE_00.2"
    assert meta.seeded_by_migration == "platform_core.0003_seed_schema_meta"
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        SchemaMeta.objects.create(id=2, schema_contract="x", seeded_by_migration="x")
    assert "ck_schema_meta_singleton" in str(exc.value)


@pytest.mark.django_db
def test_all_check_constraints_are_explicitly_named() -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT conrelid::regclass::text, conname FROM pg_constraint "
            "WHERE contype = 'c' AND conrelid::regclass::text = ANY(%s)",
            [PLATFORM_TABLES],
        )
        rows = cur.fetchall()
    assert len(rows) >= 20
    unnamed = [r for r in rows if not r[1].startswith("ck_")]
    assert unnamed == []


@pytest.mark.django_db
def test_timestamps_are_timestamptz() -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ANY(%s) AND right(column_name, 3) = '_at'",
            [PLATFORM_TABLES],
        )
        rows = cur.fetchall()
    assert len(rows) >= 10
    assert {r[2] for r in rows} == {"timestamp with time zone"}


@pytest.mark.django_db
def test_no_business_or_auth_tables_in_phase_00() -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {r[0] for r in cur.fetchall()}
    assert tables == {*PLATFORM_TABLES, "django_migrations"}


@pytest.mark.django_db
def test_no_missing_migrations() -> None:
    out = StringIO()
    call_command("makemigrations", "--check", "--dry-run", stdout=out)
    assert "No changes detected" in out.getvalue()
