# REPORT — PHASE_01 / 01.7 Security & Ops

```
PROJECT: Aleekhan
PHASE: PHASE_01
STEP: 01.7
COMMIT SHA: bccd109
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-10
IMPLEMENTER: Claude Code (aleekhan-implementer); report written and verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 01.6 PASS (reports/phase-01/step-6/REVIEW.md)
```

## 1. Purpose & acceptance
Step text: "01.7 — Security & Ops: secret scan, dependency scan, privacy/permissions tests, perf, backup/rollback & job monitoring؛ security checklist امضا شود."

The checklist is `docs/security/PHASE_01_SECURITY_CHECKLIST.md`. Its sign-off rows are left empty: they are filled only from each signer's own statement, at the Gate.

## 2. Actual changes
**Scope A — security and operations evidence**
- **Secret and dependency scan:** secret scan over the tree and full history: 0 findings. pip-audit on the runtime lock: no known vulnerabilities. `npm audit --omit=dev`: 0. The informational pip-audit of the whole dev venv was **not performed** (network unreachable); it is recorded as SKIPPED, not as a pass. No new dependency.
- **Privacy and permission tests** (`test_phase01_step7_privacy.py`, 24 tests):
  - each of the 11 roles × the 86 PHASE_01 operations that need a permission: every operation not granted by matrix v1.3 answers 403;
  - every MFA-flagged operation answers 401 `MFA_REQUIRED` without a fresh MFA check;
  - documents above a role's sensitivity cap answer 404 and are absent from lists;
  - no GET response carries a never-exposed field;
  - after a full login/MFA/one-time-password/reset/password-change run, a search of every `platform_*` row and every log record finds no plaintext secret.
- **Performance** (`test_perf_phase01.py`, marker `perf`, real PG on work-windows): see §5. The first run found inboxes reloading permissions per row (7.5 s / 9.0 s at 1000 rows); a per-request permission cache in `authz/policy.py` fixed it. The before-run is kept in `logs/perf_before_request_cache.*`.
- **Backup and rollback:**
  - the backup drill now covers the PHASE_01 tables, migrations 0011–0018 and the audit hash chain (14 checks);
  - new rollback rehearsal `ops/backup/rollback_rehearsal.sh` (test_* databases only, 17 checks). Scenario A: down to 0010, schema equals a fresh 0010, data kept, forward again with an empty diff. Scenario B: with job runs present, reversing 0011 is refused by design; the database stays consistent. On a live system, going back past 0011 means restoring from backup (`docs/ops/ROLLBACK.md` §3a).
- **Job monitoring:** `housekeeping_health`, `manage.py job_status` (can fail on warning, for cron alerts) and `manage.py run_housekeeping`. `GET /admin/health` gains optional `jobs.housekeeping` blocks (contract **0.6.3-draft**, additive). Page 36 shows a housekeeping block.
- **Orphan upload cleanup** (carried from 01.4): new job `document_orphan_cleanup` deletes stored bytes with no database row, older than 24 h only; audited and safe to repeat.
- **REV-0124:** a middleware (`api/upload_limit.py`) answers 413 from `Content-Length` before any multipart byte is read. The matching proxy limit is in `docs/ops/DEPLOYMENT_LIMITS.md`.
- **Checklist item 2.3** (`.env.example` lists every variable) is now DONE: the template already listed every variable, and its test runs without a skip.

**Scope B — carried items**
- **Matrix v1.3** (employer 2026-11-10; migration 0017, reversible): the owner reads all documents and downloads CLEAN files, audited. These are not business-approval permissions, so the DB guard is not widened (tested). Permission golden: 2 cells. E2E: the owner opens and downloads the document before deciding. UAT step 3.11 added.
- **REV-0129:** new final outbox state DISCARDED (migration 0018, reversible). It is set only by `manage.py outbox_dead_letter list|replay|discard`, which needs an active `owner_admin` and a reason, and is audited. A discarded head releases later events of its aggregate.
- **REV-0130:** `blocked_aggregates` counts only aggregates with events waiting behind a dead letter, as the OpenAPI text says.
- **REV-0131:** page 36 shows «رویداد شکست‌خورده نهایی»; the English term is only a tooltip.
- **Parameters page:** the publish button is hidden when the owner holds publish only through `owner_admin` on a TECHNICAL value.

## 3. Data integrity
- Migrations 0017 and 0018 are reversible; roundtrip OK.
- Discard is audited and only moves DEAD_LETTER → DISCARDED; rollback of 0018 turns DISCARDED back into DEAD_LETTER.
- The orphan cleanup never touches a file that still has a row, and waits 24 h before deleting.

## 4. Security evidence
- Secret scan tree + history: 0 findings (`logs/orch/secret_scan.log`).
- Logs redacted; grep for the account name and hostname finds 0 hits.
- Matrix-driven deny-by-default, MFA, sensitivity-cap and no-plaintext-secret tests as in §2.

## 5. Test evidence
Orchestrator re-runs on work-windows (PG 17.9, installed Edge); logs in `logs/orch/`.

| Command | Outcome | Log |
|---|---|---|
| ruff check + format --check | PASS | `logs/orch/ruff.log` |
| mypy strict | PASS, 191 files | `logs/orch/mypy.log` |
| makemigrations --check | No changes detected | `logs/orch/makemigrations_check.log` |
| `pytest -m "not perf"` full | **1939 passed, 1 skipped** (real ClamAV), 7 deselected | `logs/orch/pytest.log`, `pytest.xml` |
| `pytest -m perf` | 7 passed | `logs/orch/perf.log` |
| race tests ×3 | 27 passed each run | `logs/orch/concurrency_x3.log` |
| `db_roundtrip.sh` (0017 + 0018) | ROUNDTRIP OK | `logs/orch/db_roundtrip.log` |
| `roles_check.sh` | passed=50, failed=0 | `logs/orch/roles_check.log` |
| `rollback_rehearsal.sh` | PASS, failures 0 | `logs/orch/rollback_rehearsal.log` |
| frontend eslint / typecheck / build | PASS | `logs/orch/eslint.log`, `typecheck.log`, `build.log` |
| vitest | **44 passed** | `logs/orch/vitest.log` |
| Playwright E2E (real backend + real DB, Edge) | **22 passed**, plus 1 passed in the backend-down run | `logs/orch/e2e.log` |
| secret scan (tree + history) | findings=0 | `logs/orch/secret_scan.log` |

Performance numbers (implementer run on work-windows, `logs/perf.log`; budgets are TECHNICAL DEFAULTS):

| Measure | Result | Budget |
|---|---|---|
| approvals inbox p95, 1000 rows | 2570 ms | 5 s |
| tasks inbox p95, 1000 rows | 2166 ms | 5 s |
| audit chain, 1 / 4 / 8 writers | 274 / 261 / 263 rows/s, chain contiguous | — |
| outbox 2000 events, 1 / 4 dispatchers | 494 / 462 events/s, lag p95 4.0 / 4.3 s | — |

Implementer runs, in `logs/`: backup drill 14 checks pass; OpenAPI valid 0.6.3-draft (88 paths, 107 operations); verify_handoff 0 failures; pip-audit runtime 0, npm audit 0; dev-venv pip-audit SKIPPED (network).

## 6. Demo (employer)
- UAT T-003 gains step 3.11: the owner opens and downloads a document before deciding.
- Page 36 shows the housekeeping block and the Farsi dead-letter label.

## 7. Issues / decisions
**Open checklist items, all need the staging server or a go-live decision:** break-glass account (1.10), TLS at the proxy (2.6), encrypted backups (2.7), CSP (3.4), proxy body limit (3.6), artifact signing (3.11), job scheduler (4.4), RPO/RTO on staging (4.8). They fall under the employer's PHASE_00 condition: closed before production and the pilot.

**Technical defaults, documented:** housekeeping overdue after 26 h; orphan grace 24 h; 64 KiB multipart allowance; upload limit 25 MB; perf budgets.

**Interpretation:** dead-letter replay is owner-only, like discard.

**Employer questions (one at a time):**
1. Replay/discard of failed events: owner only, or may IT (`it_ops`) also replay?
2. Daily housekeeping with an alert after 26 h without success, until IT sets the schedule.
3. Upload limit 25 MB.

**Proposed for later:** move the inbox row filter into SQL; an HTTP operation for dead-letter replay/discard (contract change).

## 8. Rollback
- DB: `manage.py migrate platform_core 0016`.
- Code: `git revert <commit>`.

## 9. Review request
Request PASS. Reviewer attention:
- the per-request permission cache (no cross-request or cross-user leakage);
- the upload-limit middleware;
- the DISCARDED state and the owner-only console command;
- the orphan cleanup safety rules;
- the privacy test coverage and the checklist evidence paths.

## 10. Next step
01.8 Report & Review: Gate packet, tag phase-01-rcN, then STOP for the employer's Gate decision.
