"""PostgreSQL triggers for platform tables (reversible).

* platform_audit_event: append-only. Row-level BEFORE UPDATE/DELETE trigger, and a statement-level
  BEFORE TRUNCATE trigger that rejects TRUNCATE of a non-empty table. Both raise SQLSTATE 23001
  (restrict_violation -> django.db.IntegrityError).
* platform_outbox_event / platform_idempotency_record: BEFORE UPDATE "touch" trigger that sets
  row_version = OLD.row_version + 1, updated_at = statement_timestamp() and keeps created_at unchanged.

Note: a table owner can still DISABLE TRIGGER; production hardening (separate migration-owner role and a
runtime role without UPDATE/DELETE/TRUNCATE on the audit table) is an ops item for step 00.7.
"""

from django.db import migrations

FORWARD_SQL = r"""
CREATE FUNCTION platform_reject_mutation() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION 'table % is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation',
              HINT = 'Audit events are immutable; record a new compensating event instead.';
END;
$fn$;

CREATE TRIGGER trg_audit_event_append_only
    BEFORE UPDATE OR DELETE ON platform_audit_event
    FOR EACH ROW EXECUTE FUNCTION platform_reject_mutation();

-- TRUNCATE is rejected whenever the table holds rows. Truncating an EMPTY table is a no-op and is allowed
-- so that test-database flushes (Django TransactionTestCase) work; it cannot destroy any audit data.
CREATE FUNCTION platform_reject_truncate_nonempty() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    has_rows boolean;
BEGIN
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I)', TG_TABLE_SCHEMA, TG_TABLE_NAME) INTO has_rows;
    IF has_rows THEN
        RAISE EXCEPTION 'table % is append-only: TRUNCATE is not allowed', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NULL;
END;
$fn$;

CREATE TRIGGER trg_audit_event_no_truncate
    BEFORE TRUNCATE ON platform_audit_event
    FOR EACH STATEMENT EXECUTE FUNCTION platform_reject_truncate_nonempty();

CREATE FUNCTION platform_touch_row() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    NEW.row_version := OLD.row_version + 1;
    NEW.updated_at := statement_timestamp();  -- same clock as the db_default Now() columns
    NEW.created_at := OLD.created_at;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_outbox_event_touch
    BEFORE UPDATE ON platform_outbox_event
    FOR EACH ROW EXECUTE FUNCTION platform_touch_row();

CREATE TRIGGER trg_idempotency_record_touch
    BEFORE UPDATE ON platform_idempotency_record
    FOR EACH ROW EXECUTE FUNCTION platform_touch_row();
"""

REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS trg_idempotency_record_touch ON platform_idempotency_record;
DROP TRIGGER IF EXISTS trg_outbox_event_touch ON platform_outbox_event;
DROP FUNCTION IF EXISTS platform_touch_row();
DROP TRIGGER IF EXISTS trg_audit_event_no_truncate ON platform_audit_event;
DROP FUNCTION IF EXISTS platform_reject_truncate_nonempty();
DROP TRIGGER IF EXISTS trg_audit_event_append_only ON platform_audit_event;
DROP FUNCTION IF EXISTS platform_reject_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
