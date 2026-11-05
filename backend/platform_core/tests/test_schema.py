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
    # 00.6 integration framework
    "platform_inbox_event",
    "platform_compensation_record",
    "platform_integration_source",
    "platform_import_batch",
    "platform_import_staging_row",
    "platform_conflict_item",
]
# PHASE_01 / 01.2 platform tables (identity, org, workflow, documents, params, jobs). No business entity.
PHASE01_TABLES = [
    "platform_user",
    "platform_credential",
    "platform_password_history",
    "platform_mfa_factor",
    "platform_recovery_code",
    "platform_session",
    "platform_login_attempt",
    "platform_permission",
    "platform_role",
    "platform_role_permission",
    "platform_role_assignment",
    "platform_break_glass_usage",
    "platform_org_unit_type",
    "platform_org_unit",
    "platform_org_unit_history",
    "platform_position",
    "platform_position_history",
    "platform_position_assignment",
    "platform_workflow_definition",
    "platform_workflow_instance",
    "platform_workflow_step_event",
    "platform_approval_request",
    "platform_work_task",
    "platform_upload_type",
    "platform_stored_object",
    "platform_document",
    "platform_document_revision",
    "platform_parameter_definition",
    "platform_parameter_value",
    "platform_dynamic_field_definition",
    "platform_job_definition",
    "platform_job_run",
    "platform_audit_integrity_run",
]


@pytest.mark.django_db
def test_seed_row_present_and_singleton() -> None:
    meta = SchemaMeta.objects.get()
    assert meta.id == 1
    # 0010 (PHASE_01 / 01.2) moves the marker forward; its reverse restores the 0003 values
    assert meta.schema_contract == "PHASE_01.2"
    assert meta.seeded_by_migration == "platform_core.0010_seed_phase01_catalogue"
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        SchemaMeta.objects.create(id=2, schema_contract="x", seeded_by_migration="x")
    assert "ck_schema_meta_singleton" in str(exc.value)


@pytest.mark.django_db
def test_all_check_constraints_are_explicitly_named() -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT conrelid::regclass::text, conname FROM pg_constraint "
            "WHERE contype = 'c' AND conrelid::regclass::text = ANY(%s)",
            [PLATFORM_TABLES + PHASE01_TABLES],
        )
        rows = cur.fetchall()
    assert len(rows) >= 200
    unnamed = [r for r in rows if not r[1].startswith("ck_")]
    assert unnamed == []


@pytest.mark.django_db
def test_timestamps_are_timestamptz() -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ANY(%s) AND right(column_name, 3) = '_at'",
            [PLATFORM_TABLES + PHASE01_TABLES],
        )
        rows = cur.fetchall()
    assert len(rows) >= 80
    assert {r[2] for r in rows} == {"timestamp with time zone"}


@pytest.mark.django_db
def test_only_platform_tables_no_business_or_django_auth_tables() -> None:
    """PHASE_01 adds platform tables only: no business entity, no django.contrib.auth/session tables."""
    with connection.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {r[0] for r in cur.fetchall()}
    assert tables == {*PLATFORM_TABLES, *PHASE01_TABLES, "django_migrations"}


@pytest.mark.django_db
def test_no_missing_migrations() -> None:
    out = StringIO()
    call_command("makemigrations", "--check", "--dry-run", stdout=out)
    assert "No changes detected" in out.getvalue()
