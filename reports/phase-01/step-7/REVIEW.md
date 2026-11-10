VERDICT: PASS
PHASE/STEP: PHASE_01 / 01.7 Security & Ops   COMMIT: bccd109 (status/report-sha follow-up 83a516e)
REVIEWER: aleekhan-reviewer (independent, fresh context), work-windows, 2026-11-10. All runs below were repeated by me on throw-away `test_*` databases; logs are in the reviewer scratchpad, not committed.

## Re-run evidence (reviewer)
| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | All checks passed / 191 files already formatted |
| `mypy .` (strict) | Success: no issues found in 191 source files |
| `pytest` (default, `not perf`), DB `test_rev017` | 1939 passed, 1 skipped (clamd not reachable), 7 deselected — same as report |
| `pytest -m perf`, DB `test_rev017p` | 7 passed |
| `backend/scripts/db_roundtrip.sh` (DB `test_rev017_rt`) | schema diff EMPTY (6073 lines), ROUNDTRIP OK |
| `ops/backup/rollback_rehearsal.sh` (prefix `test_aleekhan_drill_rbrev`) | rehearsal PASS (failures: 0); A: 0010 schema equal, DISCARDED->DEAD_LETTER, matrix 1.0, forward 1.3/32 grants; B: 0011 reverse refused (PROTECT), consistent at 0011, forward clean |
| `ops/backup/drill.sh` (prefix `test_aleekhan_drill_rev017`) | drill PASS, audit hash chain verifies after restore |
| `ops/db/roles_check.sh` (DB `test_rev017_roles`) | passed=50 failed=0 |
| `frontend`: vitest / `npm run lint` / `npm run typecheck` | 44 passed / exit 0 / exit 0 |
| `frontend/scripts/e2e.sh` (real Django + PG `test_rev017_e2e`, Edge) | 22 passed + 1 passed (backend-down) |
| `tools/secret_scan.py --history` | findings=0 -> PASS |
| `tools/verify_handoff.py` | failures=0 (KNOWN_DEFECT=1 = C-14/DEC-044, pre-existing) |
| `npm audit --omit=dev` | found 0 vulnerabilities |
| pip-audit runtime | not re-run (no network); committed `logs/ci/pip_audit_runtime.json` shows `vulns: []` per package |

## CHECKS
- R01 ✔ Scope matches step text (PHASE_01.md:24: secret/dependency scan, privacy/permission tests, perf, backup/rollback, job monitoring, checklist). Carried items (REV-0124, REV-0129..0131, matrix v1.3) were assigned to 01.7 by the 01.6 review/decision log; no new business feature.
- R02 ✔ Matrix v1.3 backed by employer entry in `control/decisions/DECISION_LOG.md` (commit 48bec48, "DEC-056 extension 2"). Technical defaults (26 h overdue, 24 h orphan grace, 64 KiB overhead, 25 MB limit, perf budgets) are labelled TECHNICAL DEFAULT and listed as employer questions; owner-only replay is declared as an interpretation (REPORT.md:94) — see REV-0133.
- R03 ✔ 0017/0018 reversible; new CHECK `ck_outbox_event_discarded_has_ts` (models.py), partial index `ix_outbox_event_agg_open` updated to exclude SETTLED; roundtrip + rollback rehearsal reproduced (above); `makemigrations --check` covered by roundtrip/rehearsal "migrate --check clean".
- R04 ✔ `outbox.discard_dead_letter` (engine/outbox.py, new fn): select_for_update, state-machine assert, audited in the same unit of work; `ops/dead_letters.handle` checks ACTIVE owner_admin in the same `transaction.atomic`. Orphan purge audits per file and deletes bytes only `on_commit`, re-checks row inside the UoW (documents/service.py `purge_orphans`). Tests: `test_owner_discard_releases_the_aggregate_and_is_audited_with_reason`, `test_orphan_cleanup_removes_only_old_bytes_without_a_row` (row-backed, young, non-storage-name files untouched; idempotent).
- R05 ✔ Goldens updated and pass: `permission_decisions.golden.json` (2 v1.3 cells), `outbox_delivery_machine.golden.json` (DISCARDED terminal), `event_catalogue.golden.json`.
- R06 ✔ OpenAPI 0.6.3-draft additive (`jobs.housekeeping`, `housekeeping_alerts`); `CONTRACT_VERSION` bumped (api/views.py:32); contract tests in the full suite pass. No HTTP operation for dead letters (console only) — documented in docs/integration/README.md:200.
- R07 ✔ Page 36 housekeeping block + REV-0131 Farsi label: I viewed my E2E screenshot `phase01-ops-390-mobile.png` (RTL, Farsi, no overflow, footer contract 0.6.3-draft, synthetic banner, never-run jobs shown «هنوز اجرا نشده», not as healthy). E2E asserts no "dead letter" text in health panel and axe check (frontend/e2e/phase01.spec.ts:291-293). Parameters publish-button rule covered by vitest.
- R08 ✔ Deny-by-default 11 roles x 86 ops from `approved_matrix_grants()` (not hand-listed), MFA step-up, sensitivity-cap 404, never-exposed fields, plaintext-secret grep over all `platform_*` rows + logs (`test_phase01_step7_privacy.py`); upload 413 before parse (`api/upload_limit.py`, tests at test_phase01_step7_ops.py:336-361); request cache keyed by `user_id` and reset in `finally` (authz/policy.py `request_cache`); secret scan 0; no test DB password, account name or hostname in the commit (`git grep` = 0 hits, verified without printing the value).
- R09 ✔ `ops/dead_letters` writes outbox only through the engine function; `documents.service.purge_orphans` owns stored-object bytes via `documents/storage`; no direct writes to other owners' tables.
- R10 n/a No external import/integration in this step (Rahkaran untouched).
- R11 ✔ perf 7 passed (budgets TECHNICAL DEFAULT, before/after cache logs kept); backup drill and rollback rehearsal reproduced; dead-letter discard prevents permanent aggregate blocking; housekeeping monitoring + `job_status --fail-on warn`.
- R12 ✔ All suites reproduced by me with matching counts; E2E on real backend + real DB; ClamAV real-scanner skip stated honestly; dev-venv pip-audit stated SKIPPED, not PASS.
- R13 ✔ CHANGELOG, API_RUNTIME, openapi-draft, STATE_TRANSITIONS, EVENT_CATALOGUE, integration README, BACKUP_RESTORE, ROLLBACK §3a, DEPLOYMENT_LIMITS, JOB_MONITORING, PERMISSION_MATRIX_DRAFT v1.3, PHASE_01_SECURITY_CHECKLIST updated.
- R14 n/a Left to the employer at Gate time (checklist sign-off rows intentionally empty).

## ISSUES
- REV-0132 [P2] backend/platform_core/authz/policy.py `request_cache` / `_effective_grants` / `_facts` — the per-request permission memo (explicitly flagged for review, REPORT.md:109) has no direct unit test; safety today rests on construction (key includes user id, ContextVar reset in `finally`) and indirect BOLA/list tests. — repro: `grep -rn request_cache backend --include=*.py` finds only the definition and one call site (api/phase01/common.py:516). — expected fix: add tests that (a) nothing is cached outside the block, (b) the memo is gone after the block / after an exception, (c) two users inside one block get their own grants, (d) a grant revoked between two requests is seen by the second request. — regression test required: yes (those four).
- REV-0133 [P3] backend/platform_core/ops/dead_letters.py `_owner` — replay is now owner-only (before: "authorised admin", no caller existed). Conservative and declared as interpretation; awaiting employer answer (REPORT.md §7 Q1). — expected fix: none unless the employer chooses `it_ops`; then extend `_owner` check + test. — regression test: only if changed.
- REV-0134 [P3] reports/phase-01/step-7/logs/orch/eslint.log, typecheck.log — 0-byte logs are weak evidence of a pass (no command line / exit code recorded). Reproduced by me (exit 0). — expected fix: future logs record the command and exit code. — regression test: no.
- REV-0135 [P3] reports/phase-01/step-7/ — page 36 changed in this step but no screenshots were committed under the step folder (E2E wrote them to the git-ignored `frontend/test-results/screenshots`). Verified by my own E2E run. — expected fix: in 01.8 pass `E2E_SCREENSHOT_DIR` to a report folder so the Gate packet carries page-36 screenshots at 1440/1180/768/390. — regression test: no.

No P0/P1 issues.

## EMPLOYER ATTENTION
- بازپخش/کنارگذاشتن رویدادهای شکست‌خورده: فقط مالک، یا IT (`it_ops`) هم اجازهٔ بازپخش داشته باشد؟ (تصمیم شما)
- پیش‌فرض‌های فنی برای تأیید: هشدار نگهداری پس از ۲۶ ساعت بدون اجرای موفق؛ سقف آپلود ۲۵ مگابایت.
- چک‌لیست امنیتی فاز ۱ هنوز امضا نشده؛ امضا در زمان Gate با شماست. موارد باز (TLS، پشتیبان رمزشده، CSP، زمان‌بند Job و ...) قبل از تولید/پایلوت باید بسته شوند.
