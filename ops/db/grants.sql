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

-- migration bookkeeping and the schema contract are owned by the deploy step, never written at runtime
REVOKE INSERT, UPDATE, DELETE ON django_migrations FROM :"app";
REVOKE INSERT, UPDATE, DELETE ON platform_schema_meta FROM :"app";

-- read-only role
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"ro";
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM :"ro";
