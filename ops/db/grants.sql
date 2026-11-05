-- Privileges after migrations (PHASE_00 / 00.7, docs/ops/DB_ROLES.md). Idempotent; run as the OWNER role
-- (or a superuser) after EVERY `manage.py migrate`:
--   psql -v ON_ERROR_STOP=1 -v app=<app_role> -v ro=<readonly_role> -d <database> -f ops/db/grants.sql

\set ON_ERROR_STOP 1

-- runtime DML on every table / sequence (covers objects created before default privileges existed)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app";
REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM :"app";

-- append-only evidence: INSERT + SELECT only (defence in depth on top of the DB triggers of 0002/0005)
REVOKE UPDATE, DELETE ON platform_audit_event FROM :"app";
REVOKE UPDATE, DELETE ON platform_compensation_record FROM :"app";
REVOKE UPDATE ON platform_inbox_event FROM :"app";

-- PHASE_01 / 01.2 (docs/db/ERD.md "PHASE_01 privileges"). Defence in depth on top of the 0008 triggers.
-- append-only evidence / history: never updated or deleted by the runtime role
REVOKE UPDATE, DELETE ON platform_password_history FROM :"app";
REVOKE UPDATE, DELETE ON platform_workflow_step_event FROM :"app";
REVOKE UPDATE, DELETE ON platform_audit_integrity_run FROM :"app";
-- login events: no UPDATE; DELETE only for the retention purge (trigger refuses rows inside DEC-032's 2 years)
REVOKE UPDATE ON platform_login_attempt FROM :"app";
-- history tables are written only by the SECURITY DEFINER history triggers (owner), never directly
REVOKE INSERT, UPDATE, DELETE ON platform_org_unit_history FROM :"app";
REVOKE INSERT, UPDATE, DELETE ON platform_position_history FROM :"app";
-- closing columns only (trigger), never deleted
REVOKE DELETE ON platform_break_glass_usage FROM :"app";
REVOKE DELETE ON platform_stored_object FROM :"app";
-- no hard delete of identity, role, assignment, org, workflow, document, job or parameter rows (status / validity
-- ends instead; DATA_TABLE PHASE_01 conventions)
REVOKE DELETE ON platform_user, platform_credential, platform_mfa_factor, platform_role, platform_role_assignment,
    platform_org_unit_type, platform_org_unit, platform_position, platform_position_assignment,
    platform_approval_request, platform_work_task, platform_workflow_instance, platform_job_run,
    platform_document, platform_document_revision, platform_parameter_definition, platform_parameter_value,
    platform_dynamic_field_definition FROM :"app";
-- reviewed catalogues: written only by migrations (permission matrix, upload allow-list, job types, workflow
-- definitions)
REVOKE INSERT, UPDATE, DELETE ON platform_permission, platform_upload_type, platform_job_definition,
    platform_workflow_definition FROM :"app";
-- the runtime role calls the parameter lookup from SECURITY INVOKER triggers (default privileges revoke EXECUTE)
GRANT EXECUTE ON FUNCTION platform_param_value(text), platform_param_int(text), platform_holds_owner_admin(uuid),
    platform_position_peak_primary(uuid, uuid, timestamptz, timestamptz) TO :"app";

-- migration bookkeeping and the schema contract are owned by the deploy step, never written at runtime
REVOKE INSERT, UPDATE, DELETE ON django_migrations FROM :"app";
REVOKE INSERT, UPDATE, DELETE ON platform_schema_meta FROM :"app";

-- read-only role
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"ro";
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM :"ro";
