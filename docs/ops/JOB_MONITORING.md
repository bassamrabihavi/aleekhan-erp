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
| critical | `DEAD_LETTER_PRESENT` | an event exhausted its retries: a human replays (`engine.outbox.replay_dead_letter`) or compensates (`consumers.record_compensation`) |
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
