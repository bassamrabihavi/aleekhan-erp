# Rollback (PHASE_00 / 00.7, PHASE_01 / 01.7)

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

## 3a. PHASE_01 migrations 0007-0018 (01.7 rehearsal)

| Migration | Reverse | Data note |
|---|---|---|
| 0018 outbox DISCARDED + `document_orphan_cleanup` job | yes | DISCARDED events go back to DEAD_LETTER (the old code knows that state; the owner's discard stays in the audit trail); runs of the orphan job and its definition are removed |
| 0017 matrix v1.3 | yes | owner_admin loses document read/download, `matrix_version` 1.2; downloads already made stay audited |
| 0016 outbox provenance / ordering index | yes | provenance columns dropped |
| 0015 / 0014 matrix v1.2 / v1.1 | yes | owner grants and guard bodies of 0014 / 0008-0013 restored |
| 0011 engine (housekeeping job types) | **refused while job runs exist** (PROTECT FK, by design) | job runs and append-only audit integrity runs are evidence; a rollback below 0011 on a running system = restore from backup instead (section 3 step 4) |

Rehearsal: `ops/backup/rollback_rehearsal.sh <out-dir>` (throw-away `test_aleekhan_drill_rb_*` databases with
synthetic data). Scenario A (data, no job runs): `migrate platform_core 0010` succeeds, schema identical to a
fresh 0010, business rows kept, then forward to head with an empty schema diff. Scenario B (data + job runs):
the reverse stops at 0011 with `ProtectedError` and leaves a consistent state (schema identical to a fresh 0011,
rows kept); forward to head works. Evidence: `reports/phase-01/step-7/logs/rollback_rehearsal*`.

## 4. Frontend rollback

The UI is a static bundle served by the reverse proxy: redeploy the previous `frontend/dist` (its file hashes
are recorded by the CI `artifacts` stage, `frontend-dist.sha256`).

## 5. After any rollback

Record: time stopped / restored, commit before and after, migrations before and after, backup sha256 used (if
any), checks run. A rollback in staging/prod is reported to the employer.
