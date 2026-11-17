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

## 3b. PHASE_02 migrations 0019-0029 (02.7 rehearsal; 0029 added by the 02.8 Gate follow-up)

| Migration | Reverse | Data note |
|---|---|---|
| 0029 change-request one-open + expiry (REV-0290) | yes | `expires_at` dropped (EXPIRED rows stay EXPIRED); runs of `change_request_expiry_sweep` and its definition removed. Forward stops (count only) if an order has two open requests |
| 0028 code-rule `golden_summary` (REV-0244) | yes | derived display column dropped; lists recompute on read after a code rollback |
| 0027 matrix v2.2 (integration queue) | yes | steward / owner / viewer lose freshness / conflict grants; items stay |
| 0026 Planning source seed | yes while no batch / conflict references it; with batches the row is kept (PROTECT, nothing lost) | import batches, staging rows and conflict items stay |
| 0025 year numbers (`platform_number_counter`) + planning reject | yes (refused while a planning-rejected request exists) | the counter table is dropped and the 0023 sequences are re-created. **02.7 fix:** the forward re-positions each (kind, Jalali year) counter at the highest CU-/SO-/CR- number already issued, so rollback + forward never re-issues a number (before the fix the counters restarted at 1 and the next number collided with an issued one - found by this rehearsal) |
| 0023 / 0024 engine, matrix v2.1 | yes | |
| 0022 matrix v2.0 (PHASE_02 roles) | **refused while a PHASE_02 role is assigned** (PROTECT FK, by design) | rolling back a used matrix needs a compensation plan; on a running system = restore from backup (section 3 step 4) |
| 0019-0021 schema, guards, seed | only reachable after 0022 | the tables hold orders, serials and snapshots: never drop them on a live system |

Rehearsal: `ops/backup/rollback_rehearsal.sh` scenarios C and D. C (PHASE_01 data, PHASE_02 schema, no PHASE_02
business rows): head -> 0027 -> 0018 succeeds, schema identical to a fresh 0018, no `identity_*` / `commercial_*`
table or PHASE_02 function left, forward with an empty schema diff. D (PHASE_02 data): the reverse stops at
0022 (`IntegrityError` on `platform_role`), 0023-0028 reversed, schema identical to a fresh 0022, every PHASE_02
row and the serial counter kept; forward to head and `ops/backup/drill_verify_phase02.py` passes (gapless
serials, versions, snapshots, number counters, import batches). Evidence:
`reports/phase-02/step-7/logs/rollback_rehearsal.log`, `logs/rollback/rehearsal_report.json`.

## 4. Frontend rollback

The UI is a static bundle served by the reverse proxy: redeploy the previous `frontend/dist` (its file hashes
are recorded by the CI `artifacts` stage, `frontend-dist.sha256`).

## 5. After any rollback

Record: time stopped / restored, commit before and after, migrations before and after, backup sha256 used (if
any), checks run. A rollback in staging/prod is reported to the employer.
