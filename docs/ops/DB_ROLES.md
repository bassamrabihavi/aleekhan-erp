# Database roles - least privilege (PHASE_00 / 00.7)

PHASE_01 / 01.2 extends `ops/db/grants.sql` for the identity/org/workflow/document/parameter/job tables (no hard
delete, append-only history and evidence, migration-only catalogues, EXECUTE on the parameter functions) - table
in `docs/db/ERD.md` section 6; `ops/db/roles_check.sh` proves each rule as the app role.

SECURITY_BASELINE 4: "least privileged service accounts"; 2: "logs append-only under restricted roles".

| Role | Used by | Privileges |
|---|---|---|
| `owner` (e.g. `aleekhan_owner`) | `manage.py migrate` only (deploy step) | owns database, schema `public` and every object; DDL |
| `app` (e.g. `aleekhan_app`) | web + worker processes at runtime | `CONNECT`; schema `USAGE`; `SELECT/INSERT/UPDATE/DELETE` on tables, sequences `USAGE/SELECT`; **no** DDL, not owner (cannot `ALTER ... DISABLE TRIGGER`, `DROP`, `TRUNCATE`); audit + compensation tables: `INSERT/SELECT` only; inbox: no `UPDATE`; `django_migrations` / `platform_schema_meta`: read only; `statement_timeout = 30s` |
| `ro` (e.g. `aleekhan_readonly`) | reporting / support / backup verification | `SELECT` only, `default_transaction_read_only = on`, `statement_timeout = 120s` |

None of the roles is superuser, `CREATEDB`, `CREATEROLE`, `REPLICATION` or `BYPASSRLS`. A superuser is used only
by IT for cluster administration (`SET session_replication_role = replica`, which would skip triggers, requires
superuser - the app role is refused, see the check below).

Files:
- `ops/db/roles.sql` - once per database, before the first migration (creates the roles NOLOGIN without a
  password, transfers ownership, revokes `PUBLIC`, sets default privileges).
- `ops/db/grants.sql` - after **every** migration (idempotent): grants DML to `app`, narrows the append-only
  tables, read-only for `ro`.
- `ops/db/roles_check.sh` - automated proof on a throw-away database.

## Passwords

`roles.sql` never sets a password. IT enables login interactively and stores the value in the deployment secret
store (SECURITY_BASELINE 2):

```sql
ALTER ROLE aleekhan_app LOGIN;
\password aleekhan_app        -- psql prompts; scram-sha-256; nothing written to a file or history
```

The application connects as `app` (`PGUSER`/`PGPASSWORD` or `DATABASE_URL` from the secret store); the deploy
job runs migrations as `owner`, then `grants.sql`.

## Proof (`ops/db/roles_check.sh <out-dir>`)

Creates a throw-away database and three throw-away roles with a random suffix (cluster safe: the existing
admin/test login is not touched), runs `roles.sql`, migrates **as the owner role**, runs `grants.sql`, then
switches the admin session to each role with the `role` setting (`PGOPTIONS="-c role=..."`; privilege checks use
the current role exactly as for a login of that role, so no password is ever generated or stored) and checks:

- app: INSERT/SELECT audit, DML on platform tables, the Django unit of work (audit + outbox) and
  `manage.py outbox_status` work;
- app is refused: DELETE / UPDATE / TRUNCATE on the audit table, `ALTER TABLE ... DISABLE TRIGGER` (one and ALL),
  `DROP TRIGGER`, `SET session_replication_role = replica`, DELETE on compensation records, writes to
  `django_migrations`, CREATE TABLE / FUNCTION, DROP TABLE, ALTER TABLE;
- ro: SELECT works, INSERT/UPDATE/DELETE refused;
- the audit triggers are still enabled and the audit rows written by the app are intact.

It always drops the database and the roles (trap). Result: `roles_check.json` + the log.

Tests (pytest) keep using the throw-away test-database owner; `conftest.audit_cleanup` disables the audit trigger
only on `test_*` databases as that owner - which is exactly what the `app` role cannot do.
