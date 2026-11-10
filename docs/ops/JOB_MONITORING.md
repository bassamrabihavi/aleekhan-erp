# Job / outbox monitoring (PHASE_00 / 00.7)

PHASE_00 has one kind of background work: the transactional outbox (`platform_outbox_event`) dispatched by
`engine.outbox.dispatch_once` / `recover_stale` and consumed through the inbox (docs/integration/README.md).
Workers (Celery, ADR-001) are wired in a later phase; the monitoring contract exists now.

## `manage.py outbox_status`

Read-only (plain SELECTs, no locks, works with the `app` or `ro` role).

```bash
cd backend
python manage.py outbox_status            # human readable
python manage.py outbox_status --json     # one JSON object for a scraper
python manage.py outbox_status --fail-on warn      # exit 1 when verdict >= warn (cron / systemd timer)
```

Fields: `counts` per delivery state (PENDING, DISPATCHED, ACKED, FAILED, DEAD_LETTER), `due_now` (PENDING/FAILED
with `next_attempt_at <= now`), `oldest_due_age_seconds`, `oldest_pending_age_seconds`, `stale_dispatched`
(DISPATCHED older than the lease - the dispatcher crashed), `dead_letters`, `oldest_dead_letter_at`,
`last_dispatched_at`, `last_acked_at`, `open_conflicts` (integration conflict queue), `lease_seconds`,
`verdict` + `reasons`. It never prints payloads, error texts, actor ids or hostnames.

Verdicts (TECHNICAL DEFAULT thresholds, `platform_core/ops/monitoring.py`; ops to confirm on staging):

| Verdict | Reason code | Meaning / action |
|---|---|---|
| critical | `DEAD_LETTER_PRESENT` | an event exhausted its retries: owner or IT replays (`manage.py outbox_dead_letter replay`) or compensates (`consumers.record_compensation`) |
| warn | `STALE_DISPATCHED` | a dispatcher died holding a lease: run `recover_stale` (the dispatcher loop does it) and check the worker |
| warn | `DUE_BACKLOG` | the oldest due event waited > 15 min: dispatcher not running or too slow |
| ok | - | - |

## How to monitor (staging/prod, TECHNICAL DEFAULT)

- systemd timer or cron every minute on the app host: `manage.py outbox_status --json --fail-on warn`;
  non-zero exit -> alert (mail / chat) to IT; JSON appended to the job log for trends.
- Health probes: `/api/v1/health/live` (process) and `/api/v1/health/ready` (database, migrations, cache) for the
  reverse proxy / Docker healthcheck. Queue state is deliberately NOT on the public probes (operational
  information); an authenticated ops page arrives with PHASE_01 roles.
- Logs: JSON lines on stdout (`platform_core/api/logging.py`), with `request_id`; collected by Docker.
- Backups: see docs/ops/BACKUP_RESTORE.md section 2 (age of the newest backup).

## 01.6 additions (integration freshness)

`outbox_snapshot` / `outbox_status --json` carry an `integration` object (also served on page 36 by
`GET /admin/health`): `lag_seconds` (age of the oldest PENDING / FAILED / DISPATCHED event), `stale`
(lag > 900 s, TECHNICAL DEFAULT `DELIVERY_STALE_AFTER`), `blocked_aggregates` (aggregates with a DEAD_LETTER
event), `held_events` (undelivered events behind such a head - per-aggregate ordering), `open_conflicts`,
`compensation_open` (MANUAL_REQUIRED / HOOK_FAILED records), `last_acked_at`. New reasons:

| Verdict | Reason code | Meaning / action |
|---|---|---|
| warn | `DELIVERY_STALE` | consumers are behind by more than 15 min (dispatcher stopped or a consumer keeps failing) |
| critical (with `DEAD_LETTER_PRESENT`) | `ORDERING_BLOCKED` | later events of an aggregate wait behind a dead letter: replay it after the cause is fixed |

## 01.7 additions (housekeeping jobs, dead letters, orphan files)

### Housekeeping job monitoring
`ops.monitoring.housekeeping_health` - one entry per housekeeping job type (`jobs.service.HOUSEKEEPING_TYPES`,
seeded by migrations 0011 and 0018): newest run state, last success / failure, `overdue` (no SUCCEEDED run
within `HOUSEKEEPING_MAX_AGE` = 26 h, TECHNICAL DEFAULT for a daily schedule; a type that never ran is
overdue - PHASE_01 has no scheduler, so this is the honest answer) and `failing` (newest finished run FAILED,
machine `error_code` only). Shown on page 36 («کارهای نگهداری دوره‌ای») and in `GET /admin/health`
(`jobs.housekeeping`, `jobs.housekeeping_alerts`, contract 0.6.3-draft, additive).

```bash
python manage.py job_status                  # one line per job type + verdict ok|warn
python manage.py job_status --json           # one JSON object for a scraper
python manage.py job_status --fail-on warn   # exit 1 on warn (cron / systemd timer -> alert)
python manage.py run_housekeeping --all      # run every housekeeping job once (job-run lifecycle, audited)
python manage.py run_housekeeping audit_integrity_check
```

| Verdict | Reason code | Meaning / action |
|---|---|---|
| warn | `HOUSEKEEPING_FAILING` | the newest run of a job type FAILED: read the job run on page 36 (code only), fix, run again |
| warn | `HOUSEKEEPING_OVERDUE` | a job type had no success in 26 h: the timer is not running or the job keeps failing |

TECHNICAL DEFAULT schedule until the Celery worker (ADR-001) is wired: a systemd timer once a day at night on
the app host runs `manage.py run_housekeeping --all` (each job is idempotent, batched, safely cancellable at
its checkpoints); a second timer every 15 min runs `manage.py job_status --json --fail-on warn` and
`manage.py outbox_status --json --fail-on warn` and alerts IT on a non-zero exit.

### Orphan upload cleanup (`document_orphan_cleanup`, migration 0018)
An upload writes the encrypted bytes first and then the rows; when that transaction fails, the bytes are
deleted again (`upload_revision`), but a crash between the two can leave bytes with no
`platform_stored_object` row (01.4 report section 7). `documents.service.purge_orphans` removes such files:
only names the storage module writes (`<key[:2]>/<43-char key>` and `<key>.part`), only files older than
`ORPHAN_GRACE` = 24 h (TECHNICAL DEFAULT, far longer than any request), the row is re-checked inside the unit
of work, the file is deleted only after the audit row (`platform.document.object.orphan_purge`: key, size,
kind - never content) is committed. Idempotent; storage not configured = nothing to do. Other files in the
storage folder are never touched.

### Dead letters (REV-0129, REV-0133) - server console; replay: owner or IT, discard: owner only
```bash
python manage.py outbox_dead_letter list [--json]   # event id, type, aggregate type, time, attempts, held_behind
python manage.py outbox_dead_letter replay  --user <username> --event-id <uuid> --reason "<why>"
python manage.py outbox_dead_letter discard --user <username> --event-id <uuid> --reason "<why>"
```
`replay`: DEAD_LETTER -> PENDING (after the cause is fixed). `discard`: DEAD_LETTER -> DISCARDED (terminal, new in
0018): the event is never delivered and later events of the same aggregate are released, so a poison event
(e.g. SCHEMA_VERSION_UNSUPPORTED) no longer blocks its aggregate forever. `replay` needs an ACTIVE `owner_admin` or
`it_ops` holder, `discard` an ACTIVE `owner_admin` (employer decision 2026-11-10, REV-0133; `--owner` is kept as
an alias of `--user`). Both need a reason and are audited as that user (`platform.outbox.replay` / `platform.outbox.discard`). A compensation
record of the dead letter stays open for the consuming module. No HTTP operation (contract item).

`blocked_aggregates` (REV-0130) now counts only aggregates with events really waiting behind a dead letter (=
the OpenAPI description); a dead letter with nothing behind it shows in `dead_letters` / `DEAD_LETTER_PRESENT`.
