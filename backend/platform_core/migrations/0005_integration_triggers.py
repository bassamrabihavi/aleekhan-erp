"""PostgreSQL triggers for the 00.6 integration tables (reversible).

* ``platform_touch_row`` (from 0002) on the four versioned integration tables: ``row_version + 1``,
  ``updated_at = statement_timestamp()``, ``created_at`` unchanged.
* ``platform_import_batch``: provenance columns are immutable (source, sha256, size, name, actor, request,
  received_at). A corrected file is a NEW batch, never an edit of the old one (SOURCE_MAPPING: "binary original
  immutable").
* ``platform_import_staging_row``: the staged raw payload and its position are immutable; only the validation
  outcome (status, error codes) may change.
* ``platform_compensation_record``: append-only (UPDATE/DELETE rejected, reuses ``platform_reject_mutation``).
* ``platform_inbox_event``: UPDATE rejected (a processed marker never changes; housekeeping may DELETE old rows).

All raise SQLSTATE 23001 (restrict_violation -> django.db.IntegrityError).
"""

from django.db import migrations

FORWARD_SQL = r"""
CREATE TRIGGER trg_integration_source_touch
    BEFORE UPDATE ON platform_integration_source
    FOR EACH ROW EXECUTE FUNCTION platform_touch_row();
CREATE TRIGGER trg_import_batch_touch
    BEFORE UPDATE ON platform_import_batch
    FOR EACH ROW EXECUTE FUNCTION platform_touch_row();
CREATE TRIGGER trg_staging_row_touch
    BEFORE UPDATE ON platform_import_staging_row
    FOR EACH ROW EXECUTE FUNCTION platform_touch_row();
CREATE TRIGGER trg_conflict_item_touch
    BEFORE UPDATE ON platform_conflict_item
    FOR EACH ROW EXECUTE FUNCTION platform_touch_row();

CREATE FUNCTION platform_import_batch_provenance_guard() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    IF NEW.source_id IS DISTINCT FROM OLD.source_id
       OR NEW.file_sha256 IS DISTINCT FROM OLD.file_sha256
       OR NEW.byte_size IS DISTINCT FROM OLD.byte_size
       OR NEW.original_name IS DISTINCT FROM OLD.original_name
       OR NEW.actor_type IS DISTINCT FROM OLD.actor_type
       OR NEW.actor_id IS DISTINCT FROM OLD.actor_id
       OR NEW.request_id IS DISTINCT FROM OLD.request_id
       OR NEW.received_at IS DISTINCT FROM OLD.received_at THEN
        RAISE EXCEPTION 'import batch provenance is immutable'
            USING ERRCODE = 'restrict_violation',
                  HINT = 'Import the corrected file as a new batch.';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_import_batch_provenance
    BEFORE UPDATE ON platform_import_batch
    FOR EACH ROW EXECUTE FUNCTION platform_import_batch_provenance_guard();

CREATE FUNCTION platform_staging_row_payload_guard() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    IF NEW.batch_id IS DISTINCT FROM OLD.batch_id
       OR NEW.sheet_name IS DISTINCT FROM OLD.sheet_name
       OR NEW.row_number IS DISTINCT FROM OLD.row_number
       OR NEW.payload IS DISTINCT FROM OLD.payload
       OR NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256 THEN
        RAISE EXCEPTION 'staged row payload is immutable'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_staging_row_payload
    BEFORE UPDATE ON platform_import_staging_row
    FOR EACH ROW EXECUTE FUNCTION platform_staging_row_payload_guard();

CREATE TRIGGER trg_compensation_record_append_only
    BEFORE UPDATE OR DELETE ON platform_compensation_record
    FOR EACH ROW EXECUTE FUNCTION platform_reject_mutation();

CREATE TRIGGER trg_inbox_event_no_update
    BEFORE UPDATE ON platform_inbox_event
    FOR EACH ROW EXECUTE FUNCTION platform_reject_mutation();
"""

REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS trg_inbox_event_no_update ON platform_inbox_event;
DROP TRIGGER IF EXISTS trg_compensation_record_append_only ON platform_compensation_record;
DROP TRIGGER IF EXISTS trg_staging_row_payload ON platform_import_staging_row;
DROP FUNCTION IF EXISTS platform_staging_row_payload_guard();
DROP TRIGGER IF EXISTS trg_import_batch_provenance ON platform_import_batch;
DROP FUNCTION IF EXISTS platform_import_batch_provenance_guard();
DROP TRIGGER IF EXISTS trg_conflict_item_touch ON platform_conflict_item;
DROP TRIGGER IF EXISTS trg_staging_row_touch ON platform_import_staging_row;
DROP TRIGGER IF EXISTS trg_import_batch_touch ON platform_import_batch;
DROP TRIGGER IF EXISTS trg_integration_source_touch ON platform_integration_source;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0004_integration"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
