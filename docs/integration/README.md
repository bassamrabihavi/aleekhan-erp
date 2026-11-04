# Integration framework — PHASE_00 / 00.6

Status: DRAFT (part of the Gate-0 platform skeleton). Platform mechanics only: **no business entity, no business
write, no real data, no write to any external system**. Code: `backend/platform_core/integration/`,
`backend/platform_core/engine/consumers.py`, `backend/platform_core/engine/outbox.py`,
`backend/platform_core/api/integration_views.py`. Contract: `docs/api/openapi-draft.yaml` `0.4.0-draft`
(tag `integration`). Error codes: `docs/engine/ERROR_CODES.md`.

Sources of the requirements: `handoff/02_DOMAIN_CONTRACTS/SOURCE_MAPPING_AND_IMPORT.md` (provenance, staging,
dedup/idempotency, freshness, rollback-with-compensation), `STATE_EVENT_AND_API_CONTRACT.md` (event envelope,
idempotent handlers, DLQ visible), `ARCHITECTURE_OVERVIEW_FA.md` (one transaction = write + audit + outbox; never
write another module's tables), ADR-001 (Rahkaran = Excel import / read-only).

All numbers below marked **TECHNICAL DEFAULT** are engineering defaults, not business rules. They are parameters
in code/seed data and must be confirmed (ops in 00.7; snapshot validity by the owner in **DEC-016**, OPEN).

## 1. Tables (migrations `0004_integration`, `0005_integration_triggers`, `0006_seed_integration_sources`)

| Table | Purpose | Key constraints |
|---|---|---|
| `platform_integration_source` | registry of source systems (metadata only) | `uq_integration_source_code`; `ck_integration_source_read_only` (`direction = 'READ_ONLY'`); decision id `^DEC-[0-9]{3}$`; threshold > 0; `last_success_at` ⇔ `last_success_batch` |
| `platform_import_batch` | one received file per (source, SHA-256) + provenance | `uq_import_batch_source_sha256`; sha256 hex; size > 0; actor consistency; status timestamps; error rows ≤ rows; trigger `trg_import_batch_provenance` (source, sha256, size, name, actor, request, received_at immutable) |
| `platform_import_staging_row` | staged rows (sheet, row number, JSON payload, payload SHA-256, status, row error codes) | `uq_staging_row_position` (batch, sheet, row); payload object; `ERROR` ⇒ codes non-empty; trigger `trg_staging_row_payload` (payload/position immutable) |
| `platform_conflict_item` | conflict queue | `uq_conflict_item_conflict_id`; partial unique `uq_conflict_item_open_key` (source, kind, key WHERE OPEN); resolution columns consistent with status |
| `platform_inbox_event` | consumer dedupe | `uq_inbox_event_consumer_event`; UPDATE rejected |
| `platform_compensation_record` | permanent-failure record per consumer + event | `uq_compensation_record_consumer_event`; append-only trigger |

All versioned tables use the 0002 `platform_touch_row` trigger (`row_version + 1`, `updated_at`). Rollback:
`migrate platform_core 0003` drops all of the above (tested with synthetic data); full `zero` round-trip with
empty schema diff: `backend/scripts/db_roundtrip.sh`.

Seeded sources (metadata, no files, no passwords):

| code | kind | policy decision (apply / supersede / compensate) | staleness threshold |
|---|---|---|---|
| `rahkaran_excel` | EXCEL_FILE | DEC-016 (snapshot validity, re-import policy) | 24 h — **TECHNICAL DEFAULT** |
| `legacy_planning_xlsm` | XLSM_FILE (data only, never executed) | DEC-025 (explicit sheet/VBA map) | 7 days — **TECHNICAL DEFAULT** |
| `legacy_wh_xlsm` | XLSM_FILE (data only, never executed) | DEC-025 | 7 days — **TECHNICAL DEFAULT** |

`threshold_basis = TECHNICAL_DEFAULT` is stored and returned by the API until the owner approves a value
(`OWNER_APPROVED`).

## 2. Import batch (`integration/imports.py`)

```
RECEIVED ──stage_rows──▶ STAGED ──validate_batch──▶ VALIDATED ──apply*──▶ APPLIED ──compensate*──▶ COMPENSATED
   │                        │                          │  └──supersede*──▶ SUPERSEDED
   └──────reject_batch──────┴──────────────────────────┴──▶ REJECTED
* = gated by the source's policy decision → 409 RULE_NOT_APPROVED in PHASE_00
```

- `receive_file(ctx, source_code=, content=bytes|stream, original_name=, source_as_of=)`: streams the content
  through SHA-256, counts bytes, keeps **nothing** of the content (object storage is a later phase). Stores the
  basename only (directories, control and bidi characters removed; ZWNJ kept), actor, request/correlation id,
  `source_as_of` (claimed snapshot time, must be timezone-aware). Limits: empty file → `VALIDATION_FAILED`
  (`EMPTY_FILE`); > 50 MiB → `PAYLOAD_TOO_LARGE` (**TECHNICAL DEFAULT**); disabled source → `SOURCE_DISABLED`.
- **Idempotent**: same source + same SHA-256 → the existing batch (`created=False`), audit
  `platform.integration.batch.receive_duplicate`, no second event, freshness not refreshed. Race safe through
  the unique constraint (race test: 6 concurrent importers → 1 batch, 1 event, 5 duplicate audits). A different
  source or different bytes is a different batch. A corrected file is a new batch; batches are never edited.
- `stage_rows(ctx, batch_id, rows)`: RECEIVED → STAGED. Each row: `row_number ≥ 1`, sheet ≤ 100 chars, unique
  (sheet, row), payload JSON object ≤ 16 KiB canonical (**TECHNICAL DEFAULT**), ≤ 200 000 rows per batch. Rows with
  a sensitive key (password, secret, token, salary, wage, payroll, …; `engine/redaction.py`) are refused and
  **nothing** is stored (DEC-028: no salary/contact data). Errors list field paths and codes, never values.
- `validate_batch(ctx, batch_id, validators=())`: STAGED → VALIDATED. Structural row codes `EMPTY_ROW`,
  `DUPLICATE_PAYLOAD` (second and later identical payloads), plus codes from optional per-source validators
  (none approved in PHASE_00). Row status `PENDING_REVIEW` or `ERROR`. If at least one row is valid the
  source's `last_success_at` / `last_success_batch` / `last_as_of` are updated in the same transaction.
- `reject_batch(ctx, batch_id, reason=)`: identified USER + reason (≤ 500 chars).
- `apply_batch`, `supersede_batch`, `compensate_batch`: check the transition, then
  `require_approved_rule(source.policy_decision_id)` → `RULE_NOT_APPROVED` (`decision_id` DEC-016 / DEC-025).
  There is no apply implementation; staged data never reaches a business table in PHASE_00. Row statuses
  `MATCHED` / `APPROVED` exist in the schema for later phases and are unreachable now.

Every transition is one unit of work: state + audit (`platform.integration.batch.*`) + outbox event
(`platform.integration.batch_received|batch_staged|batch_validated|batch_rejected`; payload = ids, source code,
counts, hash — no row data).

### How WH-01 (phase 6, "snapshot imports twice → single accounted snapshot") will use it
The warehouse module imports a `ListData` snapshot through `receive_file(source_code="rahkaran_excel", …)`. A
second import of the same file returns the same batch (`created=False`), so the module must account a snapshot
only when it handles `platform.integration.batch_validated` for that batch — exactly once thanks to the inbox
(`process_once`). A *different* file covering the same `as_of` is a new batch; whether it supersedes the earlier
one is DEC-016 (re-import policy) and stays `RULE_NOT_APPROVED` until decided. WH-01 itself is not implemented
here (phase 6).

## 3. Retries and backoff (`engine/outbox.py`)

Delivery stays *at least once* (00.3 design). Additions in 00.6:

- `INTEGRATION_POLICY` (**TECHNICAL DEFAULT**): `max_attempts = 8`, `base = 5 s`, `factor = 2`, `cap = 30 min`,
  `jitter = 250 ‰` (each delay shortened by 0–25 %), `lease = 5 min`, `batch = 50`. Delays without jitter:
  5, 10, 20, 40, 80, 160, 320 s → 8th failure = `DEAD_LETTER` after ≈ 10.6 min of back-off. Golden:
  `tests/golden/integration_backoff.golden.json`. (The 00.3 generic default `OutboxPolicy()` is unchanged.)
- Deterministic tests: `OutboxPolicy.jitter_source(key, attempt) -> int in [0, 2^64)` (default
  `sha256(event_id:attempt)`), and `now=` on `claim_batch`, `mark_failed`, `dispatch_once`, `recover_stale`
  (explicit clock instead of the database clock).
- `last_error` stores a safe code only: `HANDLER_FAILED:<consumer>:<ExceptionClass>`, `LEASE_EXPIRED`, … never an
  exception message.

## 4. Consumers, inbox and compensation (`engine/consumers.py`)

- `EventHandler(consumer, event_types, handle, compensation_doc, compensate=None)`; `compensation_doc` is
  mandatory (state what compensation means, or "none needed: …").
- `process_once`: `INSERT … ON CONFLICT (consumer, event_id) DO NOTHING` into `platform_inbox_event` and the
  handler's writes in one transaction. Redelivery → skipped; handler exception → both rolled back → retried.
  Race test: 6 workers given the same event at once → handler runs once.
- `RegistryPublisher(registry)` is the `OutboxPublisher` for in-process consumers. It runs every subscribed
  handler; one failing consumer makes the event retry, already-processed consumers are skipped by the inbox
  (no double effect). Events without subscribers are acknowledged. Race test: 4 dispatchers × 40 events × 2
  consumers → 80 inbox rows, each handler once per event.
- Compensation (mechanism only): `dispatch_once(..., on_dead_letter=publisher.on_dead_letter)` (also
  `recover_stale`). For each subscribed consumer **without** an inbox row for the dead event, one
  `platform_compensation_record` (unique per consumer + event) + audit `platform.integration.compensation.record`
  + outbox `platform.integration.compensation_recorded` (causation = dead event) in one transaction; the hook runs
  in a savepoint. Outcomes: `MANUAL_REQUIRED` (no hook), `COMPLETED`, `HOOK_FAILED` (class name only; hook writes
  rolled back). Idempotent (locks the outbox row; a second call records nothing and does not rerun the hook).
  A failing compensation never stops the dispatcher (`DispatchStats.compensation_errors`);
  `sweep_dead_letters(publisher)` records what is missing. Replay of a dead letter (00.3,
  `replay_dead_letter`) keeps the compensation record.
- PHASE_00 registers **no** real consumer; tests use synthetic consumers only.

## 5. Freshness (`integration/freshness.py`, `GET /api/v1/integration/freshness`)

`never` (no successful import) / `fresh` (`now − last_success_at ≤ threshold`; a future timestamp counts as age
0) / `stale`. "Successful" = a batch VALIDATED with at least one valid row; duplicates do not refresh. Response per
source: `source_code, name_fa, kind, direction, is_enabled, freshness, last_success_at, last_as_of,
staleness_threshold_seconds, threshold_basis, policy_decision_id`, plus `checked_at`. Cursor pagination by
`source_code`; strong `ETag` over items + page (not `checked_at`); `Cache-Control: no-cache`. UI rule (SOURCE_MAPPING
§7): show `as_of`/freshness; never present stale or `TECHNICAL_DEFAULT`-judged data as real time.

Monotonic provenance (REV-0601, 00.7): `validate_batch` locks the source row (`SELECT … FOR UPDATE`) and
advances `last_success_at / last_success_batch / last_as_of` only if the batch is not older
(`imports.supersedes_freshness`): a dated batch replaces an undated or not-newer `last_as_of`; an undated batch
replaces only an undated one; `last_success_at` never decreases. A batch that does not advance freshness is
still VALIDATED; its audit row carries `freshness_advanced=false`. **Basis = import time** (`last_success_at`),
a TECHNICAL DEFAULT until **DEC-016** decides whether the snapshot date (`source_as_of`) should drive staleness;
until then the UI must show `last_as_of` next to `fresh`.

## 6. Conflict queue (`integration/conflicts.py`)

`OPEN → RESOLVED | DISMISSED` (terminal; a recurrence opens a new item).
- `raise_conflict(ctx, source_code=, kind=, key=, details=, batch_id=)`: idempotent while OPEN (partial unique
  index; race test: 6 raisers → 1 item). `details` redacted (`[REDACTED]` for sensitive keys), ≤ 8 KiB,
  identifiers only. Event `platform.integration.conflict_raised` (catalog `DataConflictRaised`).
- `resolve_conflict(ctx, scoped_queryset, conflict_id, expected_version=, outcome=, note=)`: identified USER,
  `If-Match` version, outcome `RESOLVED|DISMISSED`, note 1–500 chars. Item + audit (`reason` = note) + event
  `platform.integration.conflict_resolved` in one transaction. **No business write**: the owning module reacts to
  the event in its own phase.

## 7. API (all deny by default)

| Operation | Permission (`required_action`) | Notes |
|---|---|---|
| `GET /integration/freshness` | `platform.integration.freshness.read` | scope = sources |
| `GET /integration/conflicts` | `platform.integration.conflict.read` | `status`, `source_code` filters (cannot widen scope) |
| `GET /integration/conflicts/{conflict_id}` | `platform.integration.conflict.read` | ETag = row version; out of scope → 404 |
| `POST /integration/conflicts/{conflict_id}/resolve` | `platform.integration.conflict.resolve` | `If-Match` + `Idempotency-Key`; 409 if not OPEN |

PHASE_00 production: no authentication backend and `DenyAllPolicy` → 401 for everybody (tested). Behaviour behind
the permission is tested via the TEST-ONLY harness (`tests/api_harness.py`, synthetic principal, explicit actions
via `X-Test-Actions`). Real roles for these actions come from the PHASE_01 permission matrix (Admin/IT; data
steward for conflicts — to be confirmed, DEC-032 PROPOSED). There is no upload endpoint: imports are invoked by
server-side code only (the upload page belongs to the owning phase, with SEC-03 quarantine).

## 8. Known limits / not in this step

- No worker process (Celery/Redis) is wired: `dispatch_once` / `recover_stale` / `sweep_dead_letters` are library
  calls; scheduling and job monitoring are 00.7 (security & ops) / PHASE_01 (Jobs page).
- No file storage and no XLSX/XLSM parser: a parser (openpyxl, read-only, no macro evaluation, sandboxed worker;
  ExcelSourceRecord with cell/formula/cached value) belongs to the owning phases (06 / 12) and DEC-025/DEC-035.
- No file quarantine/scan (SEC-03, PHASE_01; tooling 00.7).
- Denied/failed attempts inside a rolled-back unit of work leave no audit row (known 00.3 limit).
- Freshness thresholds and the re-import / supersede policy wait for **DEC-016**; legacy workbook mapping for
  **DEC-025**.
