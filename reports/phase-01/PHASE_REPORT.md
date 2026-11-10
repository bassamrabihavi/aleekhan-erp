# PHASE REPORT - PHASE_01 Platform & Identity (step 01.8)

```
PROJECT: Aleekhan
PHASE: PHASE_01 (هسته سازمانی، امنیت، اسناد و گردش کار)
STEP: 01.8 (phase report over 01.1-01.8)
COMMIT SHA: PENDING (01.8 commit, filled by the orchestrator; S8 evidence = final tree, matched by the git tree ids in reports/phase-01/step-8/logs/ci/summary.md)
BRANCH/PR: main (GitHub, public per DEC-046)
STATUS: PARTIAL - all engineering scope done; step 01.8 IN_PROGRESS -> review; Gate items that need the employer are open (section 7)
TIME OF REPORT (UTC): 2026-11-10
IMPLEMENTER: Claude Code (aleekhan-implementer), machine work-windows
SOURCE BASELINE: handoff v1.0 (verify_handoff: OK=300, KNOWN_DEFECT=1 PACKAGE_MANIFEST.json per DEC-044, EXCLUDED=46, failures=0 - reports/phase-01/step-8/logs/impl/verify_handoff.log)
```

Traceability of every scope item, step, Gate criterion, acceptance case, UI page, decision and review issue:
`reports/phase-01/TRACE_MAP.md`. Commit list and per-step changes: `CHANGELOG.md` (PHASE_01 sections).

## 1. Purpose & acceptance IDs

- Purpose: the organisational and security core - in-system users only (DEC-003), roles/scopes/permissions
  (matrix v1.3), MFA, sessions, org hierarchy tree (DEC-043/048), approvals and tasks, documents with a quarantine
  pipeline, typed parameters, jobs with safe cancel, audit hash chain, outbox events with a catalogue - served by
  `/api/v1` and a Farsi RTL web UI (pages 36, 39, 40, 42, 46 + org tree).
- Acceptance IDs (`GLOBAL_ACCEPTANCE_CASES.csv`, `minimum_phase` 1): **SEC-01** (BOLA/IDOR blocked, P0) and
  **SEC-03** (unsafe upload quarantined, no execution, P0) - TRACE_MAP §5.
- UI pages in scope (`UI_PAGE_PHASE_MAP.csv`): 36, 39, 40, 42, 46 (all DRAFT / not approved in the map) + the org
  tree view (DEC-043) - TRACE_MAP §6.
- 01.8 items done in this step: REV-0132 (P2), REV-0133 (employer decision 2026-11-10), REV-0134, REV-0127 /
  REV-0135 (screenshots from the final tree), `docs/db/ERD.md` rows 0014-0018, `CHANGELOG.md`, `TRACE_MAP.md`,
  this report + JSON, step-8 REPORT.json, S8 evidence.
- Out of scope: business modules (PHASE_02+), code issuing (DEC-005/DEC-008), Rahkaran/legacy imports (PHASE_06+),
  force kill (SEC-02, PHASE_11), rules/monitoring dashboards (C-34, PHASE_11), document check-out (C-46,
  PHASE_12).

## 2. Actual changes (whole phase)

| Step | Main changes | Implementation commit |
|---|---|---|
| 01.1 | conflicts C-26..C-46, DATA_TABLE (27 entities), STATE_TRANSITIONS §4, MOCK_UI_BINDING §6, RISKS R-21..R-35, OpenAPI 0.5.0-draft (97 planned operations), permission matrix draft, decision packets DEC-032/048..054 | `89e5f0d` |
| 01.2 | migrations 0007-0010 (33 tables, DB guards for DEC-003/032/048-054, matrix v1.0 seed: 43 permissions, 11 roles, 111 grants), roles check, round trip, hostname redaction | `153651f` (first `84e5acd`) |
| 01.3 | domain engine: identity/MFA/sessions, authz policy, org, workflow approvals/tasks/cancellation, document pipeline, params, jobs, audit hash chain, `bootstrap_owner`; migrations 0011-0013 (REV-0109, REV-0113/0114, DEC-055) | `3f1f3ab` (first `6fc3eea`) |
| 01.4 | 99 PHASE_01 operations over HTTP, `RbacPolicy`, session auth + CSRF, login rate limits, If-Match/ETag, idempotency, request id, BOLA tests, contract 0.6.0-draft | `f6a60a5` |
| 01.5 | UI: login/MFA shell, pages 36/39/40/42/46 + org tree on the real API, E2E + screenshots; DEC-056 matrix v1.1 (0014); REV-0120..0123 | `ef4902a` |
| 01.6 | event catalogue + producer contract, N/N-1 consumers, per-aggregate order, freshness on page 36 (0016); DEC-056 matrix v1.2 (0015); REV-0126/0128 | `7c1a93d` |
| 01.7 | privacy/permission matrix tests, perf, backup drill + rollback rehearsal, housekeeping monitoring, orphan cleanup, upload limit (REV-0124); matrix v1.3 (0017); dead-letter discard (0018, REV-0129..0131); security checklist | `bccd109` |
| 01.8 | REV-0132 `tests/test_authz_request_cache.py`; REV-0133 `ops/dead_letters.py` + `manage.py outbox_dead_letter` (replay: owner_admin or it_ops; discard: owner_admin) + docs; REV-0134 `tools/ci_local.sh` (command + exit code in every log, tree ids, OpenAPI validation, PHASE_01 perf, rollback rehearsal in the ops stage) + `docs/ops/CI.md`; `docs/db/ERD.md`; phase report set; S8 evidence and screenshots | PENDING |

- API: 107 operations on 88 paths (S8 `06_contract.log`: "OpenAPI valid 3.1.0 0.6.3-draft 88 paths 107
  operations"); `CONTRACT_VERSION` 0.6.3-draft; additive versions since 0.5.0.
- Migrations: `platform_core.0007` .. `0018` (12, all reversible; TRACE_MAP §9, `docs/db/ERD.md` §4). None added
  in 01.8.
- UI: pages 36/39/40/42/46, org tree, login/MFA/home/forbidden/my sessions (TRACE_MAP §6).
- Jobs/console: `bootstrap_owner`, `outbox_status`, `outbox_dead_letter`, `job_status`, `run_housekeeping`.

## 3. Data integrity

- Named PK/FK/UNIQUE/CHECK/EXCLUDE constraints and triggers (0007-0018): `docs/db/ERD.md` §4-6; schema dump
  S8 `migration/schema_up_1.sql`.
- DB-enforced rules: DEC-003 (TECHNICAL roles hold no business approval, exactly three DEC-056 owner pairs), DEC-032
  (maker != checker, second approver, expiry), DEC-048 (no cycles, depth, one PRIMARY, capacity, no back-dating),
  DEC-050..054 (TOTP replay, hashed recovery codes, INTERNAL_ONLY operators, upload allow-list/size, one
  break-glass account), DEC-055 (one-time bootstrap self-approval).
- Every write = one unit of work (business change + audit + outbox, audit chain lock); idempotency records;
  optimistic concurrency `row_version` / If-Match; per-aggregate event order; a rejected event rolls the write back.
- Append-only audit with a verified hash chain; the app DB role cannot update/delete audit or disable triggers
  (S8 `12_ops.log` roles check).
- No real data: all fixtures synthetic; synthetic rows carry «محیط آزمایشی — داده ساختگی».
- 14-digit codes: not used in PHASE_01 (format type from PHASE_00; issuing BLOCKED, DEC-005/DEC-008).

## 4. Security evidence

- AuthN: local users only (DEC-003), PBKDF2 passwords + history, one-time password 72 h with forced change, TOTP +
  recovery codes, lockout, idle/absolute/concurrent session limits, CSRF + SameSite cookies, login rate limits.
- AuthZ: deny by default; matrix v1.3 (11 roles); record scope -> 404 (SEC-01); MFA step-up for flagged operations;
  field redaction. S8 `04_unit.log` (privacy suite: 11 roles x every PHASE_01 operation), `07_authz.log` (route
  parity 961 passed).
- Uploads (SEC-03): allow-list, 25 MB, quarantine, scanner adapter, CLEAN-only download, 413 before parsing.
- Secrets / dependencies: S8 `11_security.log` - secret scan 1087 files + 98 history commits, findings=0 (1 allowlisted history fingerprint); pip-audit runtime lock: no known vulnerabilities; npm audit --omit=dev: 0 vulnerabilities; the informational dev/QA venv pip-audit was NOT performed (network unavailable), stated as such.
- Logs: redacted with `tools/redact_paths.py` (host/account names); no plaintext secret in any `platform_*` row or
  log after a full ceremony (`test_phase01_step7_privacy.py`).
- Checklist: `docs/security/PHASE_01_SECURITY_CHECKLIST.md` (status + evidence per item; sign-off blank on purpose).
- Known risks / carried: TLS, CSP, encrypted backups, proxy body limit, artifact signing, scheduler, break-glass
  account, RPO/RTO on staging (checklist 1.10, 2.6, 2.7, 3.4, 3.6, 3.11, 4.4, 4.8) - before production / pilot.

## 5. Test evidence

S8 = full local CI `bash tools/ci_local.sh reports/phase-01/step-8/logs/ci` on the final PHASE_01 tree (01.8 code
included; run before the commit, tree ids in `summary.md`), machine work-windows, test PostgreSQL 17, Edge for
Playwright, throw-away databases `test_aleekhan_*_s8`; Playwright HTML report and output outside the repo;
screenshots to `reports/phase-01/step-8/screenshots/`. Every log starts with the stage's commands and ends with
`# exit code: N` (REV-0134). Two prose-only doc edits (`docs/db/ERD.md` rows 0014-0018, `docs/discovery/STATE_TRANSITIONS.md` §1.1 replay wording) were saved while S8 was running (before the tree ids were taken at the end); no test reads these files. The recorded `docs` tree id includes them.

| Check | Result | Log (S8 = `reports/phase-01/step-8/logs/ci/`) |
|---|---|---|
| ruff check + format | PASS (All checks passed; 290 files already formatted) | S8 `01_lint.log` |
| mypy strict | PASS (no issues found in 192 source files) | S8 `02_type.log` |
| tools unittest | PASS (Ran 42 tests, OK) | S8 `03_tools.log` |
| pytest unit + integration | PASS (1070 passed, 1 skipped = real ClamAV contract test: clamd not configured; 7 deselected = perf stage); junit tests=1071 failures=0 errors=0 | S8 `04_unit.log`, `pytest-unit-integration.xml` |
| migration up / zero / up, partial 0006, `makemigrations --check` | PASS (ROUNDTRIP OK; schema diff EMPTY, 6073 lines; partial rollback to 0006 = PHASE_00.2 contract; no extension left; makemigrations --check: No changes detected) | S8 `05_migration.log`, `migration/` |
| OpenAPI validation + API contract | PASS (OpenAPI valid 3.1.0, 0.6.3-draft, 88 paths, 107 operations; contract tests 18 passed) | S8 `06_contract.log` |
| authorization (route parity, log redaction) | PASS (961 passed) | S8 `07_authz.log` |
| frontend eslint / typecheck / vitest / build | PASS (npm ci, eslint --max-warnings=0, typecheck, vitest 4 files / 44 tests passed, vite build; 5 dist files) | S8 `08_frontend.log` |
| Playwright E2E (real backend + DB) and screenshots | PASS (22 passed + 1 passed in the backend-down run; 71 screenshots) | S8 `09_e2e.log`, `reports/phase-01/step-8/screenshots/` |
| perf (PHASE_00 smoke + PHASE_01) | PASS (PHASE_00 smoke 1 passed; PHASE_01 6 passed: 1000-row inbox p95 2638.0 ms approvals / 2086.5 ms tasks vs 5000 ms budget; audit chain 152.0 / 277.2 / 240.7 rows/s with 1/4/8 writers, chain contiguous, budget 20; dispatch 441.8 / 412.5 events/s with 1/4 dispatchers, budget 50 - TECHNICAL DEFAULT budgets) | S8 `10_perf.log`, `perf.json`, `perf_phase01.json` |
| security | PASS (secret scan 1087 files + 98 history commits, findings=0, 1 allowlisted history fingerprint; runtime lock matches the venv; pip-audit runtime lock: No known vulnerabilities found (after 2 network retries); npm audit --omit=dev: found 0 vulnerabilities; informational dev/QA venv pip-audit NOT performed - network unavailable, not a gate) | S8 `11_security.log` |
| DB roles, backup drill, rollback rehearsal | PASS (roles check passed=50 failed=0; backup drill PASS, 14 checks, 44 tables identical after restore, audit chain verifies; rollback rehearsal PASS, 17 checks, failures 0) | S8 `12_ops.log` |
| artifacts (SBOMs, dist hashes) | PASS (SBOM python via pip-audit CycloneDX, SBOM frontend, 5 dist files hashed) | S8 `13_artifacts.log` |
| handoff hashes | OK=300, KNOWN_DEFECT=1, EXCLUDED=46, failures=0 | `reports/phase-01/step-8/logs/impl/verify_handoff.log` |

Notes: the pytest unit stage leaves out the contract and route-parity files (own stages); `test_log_redaction.py`
and `test_redaction_persian.py` run in both the unit and the authz stage, so the stage counts must not be summed.
Perf tests are deselected in the unit stage and run in the perf stage. The one skip is the real ClamAV contract test (reason printed in `04_unit.log`). The drill / rehearsal JSON reports and the screenshot footers show `e3d56a0` (the HEAD of the worktree; the 01.8 changes were uncommitted when S8 ran; `frontend/` is unchanged since `e3d56a0`).

## 6. Demo

- Local: test PostgreSQL, `cd backend && python manage.py migrate && python manage.py runserver`, `cd frontend &&
  npm run dev`, open `http://127.0.0.1:5173/`; first owner from the console (`manage.py bootstrap_owner`);
  synthetic data only.
- Employer UAT: T-003 (`reports/phase-01/step-5/UAT_HOWTO_FA.md`) - result not recorded yet. T-001/T-002 (PHASE_00)
  PASS.
- Screenshots: `reports/phase-01/step-8/screenshots/` (final tree, every view at 1440/1180/768/390, page 36 with the
  integration and housekeeping blocks).

## 7. Issues / decisions

No open P0/P1 defect (TRACE_MAP §8). Open items:

| Item | Owner | Effect | Safe fallback |
|---|---|---|---|
| UAT T-003 | employer | Gate acceptance | - |
| Security checklist PHASE_01 sign-off | employer + auditor + IT | 01.7 step text, Gate | - |
| Deployment items (checklist 1.10, 2.6, 2.7, 3.4, 3.6, 3.11, 4.4, 4.8) | IT, staging server | production / pilot readiness | local drill, documented limits, console recovery |
| TECHNICAL DEFAULTS: login rate 20/min IP + 10/min user, housekeeping overdue 26 h, orphan grace 24 h, 64 KiB multipart allowance, perf budgets, Notification retention 180 d, 60 s clock tolerance | employer confirmation | behaviour values | documented defaults, changeable as parameters / settings |
| Scope splits C-33 (page 42), C-34 (page 36), C-46 (no check-out) | employer | scope boundary to PHASE_11/12 | implemented as proposed |
| Rollback boundary: reverse of 0011 refused while job runs exist (restore from backup instead) | employer acknowledgement | rollback plan | `docs/ops/ROLLBACK.md` §3a |
| ClamAV real-scanner contract test skipped (no clamd on work-windows) | IT (staging) | SEC-03 with the real scanner | test-double scanner; files stay quarantined if the scanner is unavailable |
| REV-0013 / C-42 wording: 401 sends `WWW-Authenticate: Cookie`, C-42 proposed `Session realm="aleekhan"`; no dedicated test | implementer (P3) | RFC conformance documentation | header present via DRF |
| HTTP operation for dead-letter replay/discard | contract change, later phase | console only today | `manage.py outbox_dead_letter` |
| DEC-016 OPEN (P0, PHASE_06) | employer | not used in PHASE_01 | - |

New decisions in PHASE_01: DEC-048..DEC-056 and the employer follow-ups recorded in
`control/decisions/DECISION_LOG.md` (last: 2026-11-10 failed-event handling, REV-0133).

## 8. Rollback

- 01.8 has no migration: revert the 01.8 commit. Reverting REV-0133 makes replay owner-only again; reverting
  `tools/ci_local.sh` restores the old log format.
- Database: reverse migrations newest first (`docs/db/ERD.md` §4 reverse column, `docs/ops/ROLLBACK.md` §3a);
  rehearsed down to 0010 with data (S8 `12_ops.log`, `rollback/`); below 0011 on a running system restore from
  backup (`docs/ops/BACKUP_RESTORE.md`, drill S8 `drill/`).

## 9. Review request

Request **PASS** for 01.8. Check:
1. REV-0132: `backend/platform_core/tests/test_authz_request_cache.py` against `authz/policy.py` `request_cache`.
2. REV-0133: `backend/platform_core/ops/dead_letters.py` `ALLOWED_ROLES`, `management/commands/outbox_dead_letter.py`,
   new tests in `test_phase01_step7_ops.py`; DECISION_LOG.md last entry; docs.
3. REV-0134: any S8 log (`# command` block, `# exit code: N`), `summary.md` tree ids vs `git rev-parse
   <commit>:<dir>`.
4. REV-0127/REV-0135: `reports/phase-01/step-8/screenshots/` (names, four widths, page 36 blocks).
5. `TRACE_MAP.md` against PHASE_01.md, the acceptance CSV, the UI map and the REV list in step-1..7 REVIEW.md.

## 10. Next step (proposal only)

After the 01.8 review: the orchestrator fills `commit.txt` / the SHA fields, writes
`reports/phase-01/GATE_PACKET_FA.md`, tags `phase-01-rcN` and STOPS for the employer's Gate-1 decision.
