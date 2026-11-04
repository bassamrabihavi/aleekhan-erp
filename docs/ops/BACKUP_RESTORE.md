# Backup and restore (PHASE_00 / 00.7)

Decisions: **DEC-004** RPO 1 h / RTO 4 h, monthly restore drill. **DEC-045 A**: first drill in a local test
environment, repeated on staging once the in-company server exists (DEC-002/DEC-042, Ubuntu 24.04 + Docker
Compose). Acceptance case **OPS-01** ("backup restore drill: data and hash verified", minimum phase 12) - the
PHASE_00 drill proves the procedure early; it does not close OPS-01.

Everything marked TECHNICAL DEFAULT below is an engineering default, not an approved business rule; the
employer/IT confirm it before production (SECURITY_BASELINE 4: "backup RPO/RTO formally approved before
production").

## 1. What is backed up

| Item | How | Notes |
|---|---|---|
| PostgreSQL database (all platform tables, audit, outbox, integration staging) | `pg_dump -Fc` (logical, custom format) | one consistent snapshot per dump (MVCC); restore with `pg_restore --single-transaction --exit-on-error` |
| Point-in-time recovery for RPO 1 h | WAL archiving (`archive_mode=on`, `archive_command` to the backup volume) + a nightly base backup (`pg_basebackup`) | TECHNICAL DEFAULT design for staging/prod; not configured in PHASE_00 (no server yet) |
| Uploaded source files (later phases) | object storage / volume snapshot | not stored in PHASE_00 (only hashes, docs/integration/README.md) |
| Configuration | deployment repo + secret store | secrets are never in backups of the repository |

## 2. Schedule and retention (TECHNICAL DEFAULT, to confirm with IT)

- Logical dump: hourly (meets RPO 1 h even without WAL archiving) - keep 48 hourly, 30 daily, 12 monthly.
- WAL archiving: continuous; base backup nightly; keep 7 days of WAL.
- Restore drill: monthly (DEC-004) with `ops/backup/drill.sh`-style verification against a copy of the
  latest real backup **on the staging server** (never on a developer machine: real data stays in the company).
- Monitor: backup job exit code + age of the newest backup file (alert if older than 90 minutes).

## 3. Encryption and integrity of backups (TECHNICAL DEFAULT)

- Every backup file gets a SHA-256 next to it (`<file>.sha256`); the drill re-verifies the hash before
  restoring.
- Encrypt at rest before the file leaves the database host: `age` (recommended: small, auditable, public-key
  recipients) or `gpg --encrypt` with the backup public key, e.g.
  `pg_dump -Fc ... | age -r <backup-public-key> > aleekhan-YYYYmmddHH.dump.age`.
  The private key is held offline by the employer/IT (not on the database server, never in Git).
- Backup volume: separate disk / host, write-only for the backup job, not mounted by the app containers.
- Backups contain personal and business data: same classification as the production database
  (SECURITY_BASELINE 2); restore tests with real data only on the staging server.

## 4. Restore procedure (production)

1. Declare the incident, stop writers: scale the web/worker containers to 0 (or maintenance mode).
2. Pick the backup (newest good, or point in time), verify `sha256sum -c <file>.sha256`, decrypt.
3. Restore into a NEW database (never over the damaged one): `createdb aleekhan_restore_<date>`;
   `pg_restore --single-transaction --exit-on-error -d aleekhan_restore_<date> <dump>`
   (PITR: restore the base backup + `recovery_target_time`).
4. Run `ops/db/grants.sql` (privileges for the app/readonly roles) and verify:
   `manage.py migrate --check`, `manage.py outbox_status`, row counts of key tables, audit triggers enabled
   (`pg_trigger.tgenabled = 'O'`), `/api/v1/health/ready` = ready.
5. Point the application at the restored database (rename databases or change `PGDATABASE`), start, smoke
   test, record the incident with times (RTO measurement) and the backup sha256.
6. Outbox: events that were PENDING at backup time are re-dispatched; consumers are idempotent (inbox,
   `docs/integration/README.md`), so duplicates are discarded.

## 5. The drill script (`ops/backup/drill.sh`)

```bash
set -a; . <test DB env file outside the repo>; set +a     # libpq env; password never printed
PG_BIN=<postgres 17 bin dir> bash ops/backup/drill.sh reports/phase-00/step-7/logs/drill
```

Throw-away databases `aleekhan_drill_src` / `aleekhan_drill_restored` (refuses other prefixes). Steps: migrate,
seed SYNTHETIC labelled rows through the real write path (`ops/backup/drill_seed.py`, refuses any database not
named `aleekhan_drill_*`), fingerprint every public table (row count + md5 of the ordered rows) plus triggers
and functions, `pg_dump -Fc`, sha256, drop the source, re-verify sha256, restore into a new database, compare
fingerprints, `migrate --check`, check the audit append-only trigger still rejects DELETE, read through the
application (`outbox_status`), drop everything. Output: `drill_report.json`, `drill_report.md`,
`fingerprint_before.txt`, `fingerprint_after.txt`, `fingerprint_diff.txt`. The dump itself lives in a temp
directory and is deleted (only its hash and size are reported).

**Limits of the PHASE_00 drill:** tiny synthetic dataset on the local portable PostgreSQL 17 (no Docker on the
work machine), so its timings prove the procedure, not production RTO; RPO is a property of the schedule/WAL
archiving above and is not demonstrated by one dump. Repeat on staging with production-sized data (PHASE_01/12).
