# REPORT — PHASE_01 / 01.6 Integration

```
PROJECT: Aleekhan
PHASE: PHASE_01
STEP: 01.6
COMMIT SHA: 7c1a93d
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-10
IMPLEMENTER: Claude Code (aleekhan-implementer); report written and verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 01.5 PASS (reports/phase-01/step-5/REVIEW.md)
```

## 1. Purpose & acceptance
Step text: "01.6 — Integration: فقط Source/Events مربوط؛ staging, retry, backoff, compensation, freshness, conflict queue."

PHASE_01 has no external source system: Rahkaran import starts in a later phase. The integration surface of this step is therefore the platform's own event pipeline (outbox → consumers). Other modules are not changed directly.

The step also carries the employer's DEC-056 extension (2026-11-10, matrix v1.2) and the 01.5 review items REV-0125/0126/0128.

## 2. Actual changes
**Scope A — event pipeline**
- **Event catalogue** (`engine/events.py`, new): 52 event types from PHASE_00 and PHASE_01. Each has a producer module, an aggregate type, versions, a payload JSON Schema and sensitivity S1 (ids, codes and counts only).
  - Golden copy `tests/golden/event_catalogue.golden.json`; readable copy `docs/integration/EVENT_CATALOGUE.md`, generated from the code.
- **Producer contract:** `UnitOfWork.emit` refuses an event that is not catalogued, has the wrong aggregate, a non-current version or a payload that does not match. The whole business write rolls back. The full backend suite runs every emit site through this check.
  - `platform.synthetic.*` events are accepted without a catalogue entry only when `ALEEKHAN_ENV` is test or dev. The probe events in `ops/db/roles_check.sh` and `ops/backup/drill_seed.py` moved into that namespace.
- **Provenance:** every new outbox row records `producer`, `build_commit` and `schema_migration` (migration 0016).
- **Consumers** (`RegistryPublisher`): accept schema version N and N-1 (N-1 is upcast). Older versions or invalid payloads go to dead letter at once (`PublishError(permanent=True)`) with a compensation record. A newer version than the consumer knows is retried with backoff. Inbox dedupe, retries with backoff and jitter, dead letter and the compensation hook from 00.6 are unchanged.
- **Per-aggregate order:** on by default, with a partial index. A dead-letter head holds back later events of its own aggregate only, until it is replayed (`ORDERING_BLOCKED`).
- **Freshness:** `ops.monitoring.integration_health` reports lag, a stale flag (> 900 s, technical default), blocked aggregates, held events, open conflicts, open compensations and the last ack. It appears in `outbox_status`, in `GET /admin/health` as the optional `integration` block (contract **0.6.2-draft**, additive) and on page 36.
- **No dead-letter HTTP API invented:** the contract has no such operation. Replay/discard over HTTP is listed as a contract item in `docs/integration/README.md` §9.

**Scope B — carried items**
- **DEC-056 extension, matrix v1.2** (migration 0015, reversible): `owner_admin` also holds `platform.document.approve` and `platform.config.parameter.publish`.
  - The DB guard exception is widened from one pair to exactly three owner pairs.
  - Maker ≠ checker is unchanged.
  - The permission golden changes exactly two cells.
- **REV-0128:** service and HTTP tests, plus a new E2E where the owner approves a document revision submitted by another synthetic user. UAT steps 3.9 and 3.10 added to `reports/phase-01/step-5/UAT_HOWTO_FA.md`.
- **REV-0126:** page 46 subtitle reworded for DEC-056, with a vitest text check.

## 3. Data integrity
- Migrations 0015 and 0016 are reversible. Roundtrip OK. Going down from 0016 to 0014 gives guard functions identical (md5) to a fresh 0014 (implementer log `migration/partial_down_0014.log`).
- A rejected event rolls back its business write: no row is ever written without its matching, valid outbox event.
- Backup drill (50 rows): pass (implementer log `backup_drill.log`).

## 4. Security evidence
- Event payloads are S1 only; schemas forbid extra fields.
- The owner's new rights are bounded in the DB guard to three named pairs.
- Secret scan: 0 findings (tree; implementer also ran history: 0).
- Logs redacted; grep for the account name and hostname finds 0 hits.

## 5. Test evidence
Orchestrator re-runs on work-windows (PG 17.9, installed Edge); logs in `logs/orch/`.

| Command | Outcome | Log |
|---|---|---|
| ruff check + format --check | PASS | `logs/orch/ruff.log` |
| mypy strict | PASS, 180 files | `logs/orch/mypy.log` |
| makemigrations --check | No changes detected | `logs/orch/makemigrations_check.log` |
| `pytest -m "not perf"` full | **1887 passed, 1 skipped** (real ClamAV), 1 deselected | `logs/orch/pytest.log`, `pytest.xml` |
| race tests ×3 | 27 passed each run | `logs/orch/concurrency_x3.log` |
| `db_roundtrip.sh` (0015 + 0016) | ROUNDTRIP OK | `logs/orch/db_roundtrip.log`, `roundtrip/` |
| `roles_check.sh` | passed=50, failed=0 | `logs/orch/roles_check.log` |
| frontend eslint / typecheck / build | PASS | `logs/orch/eslint.log`, `typecheck.log`, `build.log` |
| vitest | **38 passed** | `logs/orch/vitest.log` |
| Playwright E2E (real backend + real DB, Edge) | **22 passed**, plus 1 passed in the backend-down run | `logs/orch/e2e.log` |
| secret scan | findings=0 | `logs/orch/secret_scan.log` |

Implementer runs, in `logs/`: OpenAPI valid (0.6.2-draft, 88 paths, 107 operations); tools unittest 42 OK; verify_handoff 0 failures; backup drill pass; secret scan history 0.

## 6. Demo (employer)
Page 36 (System health) now shows the event pipeline freshness block. UAT T-003 gains steps 3.9/3.10: the owner approves a document revision submitted by someone else.

## 7. Issues / decisions
**Interpretations made (for reviewer and employer):**
1. The owner's publish right covers BUSINESS_RULE values only; TECHNICAL values still answer 403 for the owner. All BUSINESS_RULE parameters stay blocked by `RULE_NOT_APPROVED` (DEC-016), so the publish right has no visible effect yet.
2. Rejecting one's own BUSINESS_RULE proposal now returns `SELF_APPROVAL_FORBIDDEN` for everyone.
3. Ordering per aggregate is global: one dead-lettered event holds back later events of that aggregate until replayed.

**Employer question (to ask):** DEC-056 v1.2 gives the owner `document.approve` but not `document.read`/download, so he decides from the approval card without opening the file.

**Known gaps:**
- No dead-letter replay/discard over HTTP (contract item); replay is a console command.
- The Parameters page may show a publish button to the owner on TECHNICAL values; the server answers 403.
- The new E2E releases its synthetic PDF with the labelled test scanner (dev/test only), because ClamAV is not available locally.
- Screenshots were not regenerated in this step (REV-0127: regenerate from committed code at the Gate).

## 8. Rollback
- DB: `manage.py migrate platform_core 0014`.
- Code: `git revert <commit>`.

## 9. Review request
Request PASS. Reviewer attention:
- the producer contract in `UnitOfWork.emit` and the dev/test-only synthetic namespace;
- N/N-1 handling and the permanent dead-letter path;
- per-aggregate ordering and its blocking behaviour;
- the widened DB guard exception (0015) and its reverse;
- contract bump 0.6.2-draft.

## 10. Next step
01.7 Security & Ops: secret/dependency scan, privacy/permission tests, perf (inbox, audit-chain lock), backup/rollback, job monitoring; carried items REV-0124 and the orphan upload cleanup.
