-- Least-privilege PostgreSQL roles for one Aleekhan database (PHASE_00 / 00.7, docs/ops/DB_ROLES.md).
--
-- Run ONCE per database as a cluster admin (superuser or CREATEROLE + database owner), BEFORE the first
-- migration, with psql variables:
--   psql -v ON_ERROR_STOP=1 -v db=<database> -v owner=<owner_role> -v app=<app_role> -v ro=<readonly_role> \
--        -f ops/db/roles.sql
--
-- * owner : owns the database, schema and every object; used ONLY by `manage.py migrate` (deploy step).
-- * app   : runtime role of the web/worker processes; DML only (no DDL, not owner, so it can neither
--           ALTER/DISABLE triggers nor DROP/TRUNCATE tables). Audit / compensation rows: INSERT + SELECT
--           only (ops/db/grants.sql revokes UPDATE/DELETE).
-- * ro    : read-only (reporting, support, backups verification).
--
-- Roles are created NOLOGIN and WITHOUT a password. Passwords are never written to a file, a log or this
-- repository: the operator enables login interactively, e.g. `ALTER ROLE <app> LOGIN;` then `\password <app>`
-- in psql (scram-sha-256), and stores the value in the deployment secret store (SECURITY_BASELINE 2).

\set ON_ERROR_STOP 1

CREATE ROLE :"owner" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE :"app" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE :"ro" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

ALTER DATABASE :"db" OWNER TO :"owner";
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO :"owner", :"app", :"ro";
-- statement timeouts for the runtime roles (TECHNICAL DEFAULTS, tune on staging)
ALTER ROLE :"app" IN DATABASE :"db" SET statement_timeout = '30s';
ALTER ROLE :"ro" IN DATABASE :"db" SET statement_timeout = '120s';
ALTER ROLE :"ro" IN DATABASE :"db" SET default_transaction_read_only = on;

\connect :"db"

ALTER SCHEMA public OWNER TO :"owner";
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app", :"ro";

-- Objects the owner creates later (migrations) get these privileges automatically; ops/db/grants.sql then
-- narrows the append-only tables and must run after every migrate.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"app";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
    GRANT SELECT ON TABLES TO :"ro";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
