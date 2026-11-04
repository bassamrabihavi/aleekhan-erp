# Rollback (PHASE_00 / 00.7)

Rule (REPOSITORY_AND_RELEASE_CONTRACT_FA): migration ID, model revision and API version are reviewed together;
no destructive migration without backup/copy/verification and a rollback path. Release tags only after an
approved Gate.

## 1. Before every deploy

1. Fresh backup + sha256 (docs/ops/BACKUP_RESTORE.md section 4) and note the current state:
   `git rev-parse HEAD`, `manage.py showmigrations platform_core` (last applied migration per app).
2. CI green for the commit (`.github/workflows/ci.yml` or `tools/ci_local.sh` logs), including the migration
   round-trip (`backend/scripts/db_roundtrip.sh`: up -> zero -> up, schema diff empty).
3. Read the release notes: which migrations are new, are they reversible (all PHASE_00 migrations 0001-0006 are;
   the round-trip proves it), does the API contract version change.

## 2. Code-only rollback (no new migration in the release)

1. Redeploy the previous image / commit (`ALEEKHAN_BUILD_COMMIT` = previous sha).
2. Check `/api/v1/version` shows the previous commit and `/api/v1/health/ready` is ready.

## 3. Rollback with migrations

1. Stop writers (scale web/workers to 0).
2. With the NEW code still deployed (it contains the reverse operations), migrate back to the last migration
   of the previous release, per app: `manage.py migrate platform_core <previous_migration_name>`.
   Example PHASE_00: back to before integration = `manage.py migrate platform_core 0003`.
3. Deploy the previous code, run `ops/db/grants.sql`, start, check `/health/ready` (migrations up).
4. If a reverse migration is not possible or fails (data-destroying change), restore the pre-deploy backup
   into a new database instead (docs/ops/BACKUP_RESTORE.md section 4) - this is why step 1.1 is mandatory.

Notes:
- Reverse migrations that drop tables delete their data (e.g. 0004 removes the integration tables). The audit
  table is append-only: its reverse migration exists for the round-trip on throw-away databases; on a real
  database do not roll back past 0002 - restore from backup instead.
- The migration role is the OWNER role (docs/ops/DB_ROLES.md); the app role cannot run DDL by design.
- Outbox events created by the newer release remain in the table; their consumers are idempotent.

## 4. Frontend rollback

The UI is a static bundle served by the reverse proxy: redeploy the previous `frontend/dist` (its file hashes
are recorded by the CI `artifacts` stage, `frontend-dist.sha256`).

## 5. After any rollback

Record: time stopped / restored, commit before and after, migrations before and after, backup sha256 used (if
any), checks run. A rollback in staging/prod is reported to the employer.
