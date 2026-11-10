# PHASE_01 Trace Map (step 01.8)

Scope source: `handoff/03_PHASE_PLAN/PHASE_01.md` (domain, backend/API, engine, steps 01.1-01.8, cross-cutting
requirements, Gate, mandatory outputs), acceptance cases `handoff/06_TEST_AND_ACCEPTANCE/GLOBAL_ACCEPTANCE_CASES.csv`
(`minimum_phase` 1), UI pages `handoff/08_UI_AND_UX/UI_PAGE_PHASE_MAP.csv` (PHASE_01), employer requirements in
`CLAUDE.md` (DEC-002/003/043) and the decisions DEC-048..056. Every row: requirement -> implementing files -> tests
-> evidence -> review -> status.

Status values: **DONE** (implemented + evidence + review PASS), **PARTIAL** (part done; the rest is named with an
owner), **OPEN** (not done; owner named), **EMPLOYER** (needs an employer action, answer or signature; agents
cannot close it), **CARRIED** (deliberately left to a later phase / the staging server, with the reason).
Counts are copied from the cited logs; nothing is estimated.

Evidence sets:
- **S8** = full local CI (13 stages, `bash tools/ci_local.sh reports/phase-01/step-8/logs/ci`) on the final
  PHASE_01 tree (01.8 code included), machine work-windows, test PostgreSQL 17 on 127.0.0.1:5433 (password never
  printed): `reports/phase-01/step-8/logs/ci/` (`summary.md` 13/13 stages PASS, every stage exit code 0). The run was made before the 01.8
  commit; `summary.md` records the git tree id of every code directory as tested, so it can be matched to the
  commit with `git rev-parse <commit>:backend` etc. (REV-0134). `commit.txt` is filled by the orchestrator. Two prose-only doc edits (`docs/db/ERD.md` rows 0014-0018, `docs/discovery/STATE_TRANSITIONS.md` §1.1 replay wording) were saved while S8 was running (before the tree ids were taken at the end); no test reads these files. The recorded `docs` tree id includes them.
- **S8-shots** = all PHASE_01 screenshots from the S8 E2E run: `reports/phase-01/step-8/screenshots/`
  (71 PNG files, `phase01-<view>-<1440-desktop|1180-laptop|768-tablet|390-mobile>.png`, plus the PHASE_00
  system-status views of the same run).
- **Sn** (n = 1..7) = per-step evidence `reports/phase-01/step-n/logs/` and the reviewer re-runs in
  `reports/phase-01/step-n/REVIEW.md`.

Test counts (S8, from the logs):

| Suite | Log (`reports/phase-01/step-8/logs/ci/`) | Result |
|---|---|---|
| ruff check + format | `01_lint.log` | PASS (All checks passed; 290 files already formatted) |
| mypy strict | `02_type.log` | PASS (no issues found in 192 source files) |
| tools unittest | `03_tools.log` | PASS (Ran 42 tests, OK) |
| pytest unit + integration (without contract / route-parity files, without perf) | `04_unit.log`, `pytest-unit-integration.xml` | PASS (1070 passed, 1 skipped = real ClamAV contract test: clamd not configured; 7 deselected = perf stage); junit tests=1071 failures=0 errors=0 |
| migration up / zero / up + partial rollback + `makemigrations --check` | `05_migration.log`, `migration/` | PASS (ROUNDTRIP OK; schema diff EMPTY, 6073 lines; partial rollback to 0006 = PHASE_00.2 contract; no extension left; makemigrations --check: No changes detected) |
| OpenAPI validation + API contract | `06_contract.log`, `pytest-contract.xml` | PASS (OpenAPI valid 3.1.0, 0.6.3-draft, 88 paths, 107 operations; contract tests 18 passed) |
| authorization (route parity, log redaction) | `07_authz.log`, `pytest-authz.xml` | PASS (961 passed) |
| frontend: npm ci, eslint, typecheck, vitest, build | `08_frontend.log` | PASS (npm ci, eslint --max-warnings=0, typecheck, vitest 4 files / 44 tests passed, vite build; 5 dist files) |
| Playwright E2E (real Django + PostgreSQL, Edge) | `09_e2e.log` | PASS (22 passed + 1 passed in the backend-down run; 71 screenshots) |
| perf (PHASE_00 smoke + PHASE_01 perf) | `10_perf.log`, `perf.json`, `perf_phase01.json` | PASS (PHASE_00 smoke 1 passed; PHASE_01 6 passed: 1000-row inbox p95 2638.0 ms approvals / 2086.5 ms tasks vs 5000 ms budget; audit chain 152.0 / 277.2 / 240.7 rows/s with 1/4/8 writers, chain contiguous, budget 20; dispatch 441.8 / 412.5 events/s with 1/4 dispatchers, budget 50 - TECHNICAL DEFAULT budgets) |
| secret scan (tree + history), runtime lock, pip-audit, npm audit | `11_security.log`, `secret_scan.json`, `pip_audit_runtime.json` | PASS (secret scan 1087 files + 98 history commits, findings=0, 1 allowlisted history fingerprint; runtime lock matches the venv; pip-audit runtime lock: No known vulnerabilities found (after 2 network retries); npm audit --omit=dev: found 0 vulnerabilities; informational dev/QA venv pip-audit NOT performed - network unavailable, not a gate) |
| DB roles, backup drill, rollback rehearsal | `12_ops.log`, `roles/`, `drill/`, `rollback/` | PASS (roles check passed=50 failed=0; backup drill PASS, 14 checks, 44 tables identical after restore, audit chain verifies; rollback rehearsal PASS, 17 checks, failures 0) |
| SBOMs, dist hashes | `13_artifacts.log`, `sbom-*.cdx.json`, `frontend-dist.sha256` | PASS (SBOM python via pip-audit CycloneDX, SBOM frontend, 5 dist files hashed) |

## 1. Phase sections (PHASE_01.md)

| # | Requirement | Implementing files | Tests | Evidence | Review | Status |
|---|---|---|---|---|---|---|
| D1 | Domain: User, Role, Scope, Permission | `identity/models.py`, `identity/roles.py`, `identity/users.py`, `authz/policy.py`; migrations 0007-0010, 0014, 0015, 0017 | `test_phase01_identity.py`, `test_phase01_roles*.py`, `test_phase01_authz_engine.py` (golden `permission_decisions.golden.json`), `test_phase01_step7_privacy.py` | S8 `04_unit.log` | step-2/3/7 REVIEW PASS | DONE |
| D2 | MFA | `identity/mfa.py` (TOTP RFC 6238, replay guard, 10 recovery codes, admin reset), `identity/crypto.py` (AES-256-GCM) | `test_phase01_totp_passwords.py` (golden `totp_rfc6238.golden.json`), `test_phase01_auth_engine.py`, step-up tests in `test_phase01_step7_privacy.py` | S8 `04_unit.log`, `09_e2e.log` (owner first login with TOTP) | step-3/4/5 REVIEW PASS | DONE (DEC-050) |
| D3 | Audit | `engine/uow.py`, `engine/audit_chain.py` (hash chain), append-only trigger (0001/0002), audit query API | `test_audit_event.py` (raw/ORM UPDATE/DELETE/TRUNCATE refused), `test_phase01_audit_chain.py` (changed field, deleted row, raw insert detected; concurrent writers one chain) | S8 `04_unit.log`; `12_ops.log` (drill verifies the chain) | step-3/7 REVIEW PASS | DONE |
| D4 | Outbox | `engine/outbox.py` (DISCARDED 0018), `engine/events.py` (catalogue, producer contract), provenance 0016 | `test_engine_outbox.py`, `test_integration_events.py`, `test_integration_consumers.py`, `test_phase01_step7_ops.py` | S8 `04_unit.log` | step-6/7 REVIEW PASS | DONE |
| D5 | Job | `jobs/models.py`, `jobs/service.py` (safe cancel, protected jobs, housekeeping incl. `document_orphan_cleanup`), `ops/monitoring.py`, `manage.py job_status` / `run_housekeeping` | `test_phase01_params_jobs*.py`, `test_phase01_step7_ops.py` | S8 `04_unit.log`, `09_e2e.log` (page 36 safe cancel) | step-3/4/7 REVIEW PASS | DONE (scheduler on the server: CARRIED, checklist 4.4) |
| D6 | Task | `workflow/` (WorkTask, approvals, cancellation + compensation) | `test_phase01_workflow*.py`, `test_phase01_roles_approvals_engine.py` | S8 `04_unit.log`, `09_e2e.log` | step-3/4/5 REVIEW PASS | DONE |
| D7 | Document + encrypted file refs | `documents/` (quarantine pipeline SEC-03, storage, scanner adapter, purge), migration 0007 | `test_phase01_documents_engine.py`, `test_api_phase01_flows.py::test_documents_sec03_*`, `test_phase01_step7_dec056_v13.py` | S8 `04_unit.log`, `09_e2e.log` | step-3/4/7 REVIEW PASS | DONE (real ClamAV contract test SKIPPED with reason: clamd not configured on this machine) |
| D8 | DynamicField draft | `params/` dynamic field definitions as DRAFT only (C-33) | `test_phase01_params*.py` | S8 `04_unit.log` | step-2/3/4 REVIEW PASS | DONE (scope split C-33: EMPLOYER confirmation, section 4) |
| D9 | Source provenance, commit/migration, backward compatibility of new data | outbox `producer`/`build_commit`/`schema_migration` (0016); synthetic label on test rows; additive contract versions 0.5.0 -> 0.6.3-draft | `test_integration_events.py` (provenance), contract tests | S8 `04_unit.log`, `06_contract.log` | step-6 REVIEW PASS | DONE |
| B1 | Login / session / logout | `api/session_auth.py`, `identity/sessions.py`, `api/phase01/auth_views.py` (CSRF rotated, REV-0123) | `test_api_phase01_*`, `test_phase01_auth_engine.py` | S8 `04_unit.log`, `09_e2e.log` (login, logout) | step-3/4/5 REVIEW PASS | DONE (DEC-051) |
| B2 | Approval / task API | `api/phase01/workflow_views.py` | `test_api_phase01_flows.py`, `test_api_bola.py` | S8 `04_unit.log` | step-4 REVIEW PASS | DONE |
| B3 | Audit query | `api/phase01/ops_views.py` (audit list + integrity) | `test_api_phase01_*` | S8 `04_unit.log`, `09_e2e.log` (page 36 integrity «سالم») | step-4/5 REVIEW PASS | DONE |
| B4 | Job control | `api/phase01/ops_views.py` (safe cancel with reason, protected jobs refused) | `test_api_phase01_flows.py::test_jobs_safe_cancel_health_and_audit` | S8 `04_unit.log`, `09_e2e.log` | step-4/5 REVIEW PASS | DONE |
| B5 | Shared navigation / RTL component library | `frontend/src/` shell, `components/`, tokens | vitest, E2E axe checks | S8 `08_frontend.log`, `09_e2e.log` | step-5 REVIEW PASS | DONE |
| B6 | Role-aware dashboard | `frontend/src/pages/HomePage.tsx` (navigation from `GET /me/permissions`; server stays authoritative) | E2E "role-sensitive nav, server-side 403" | S8 `09_e2e.log`, S8-shots `phase01-home-owner-*` | step-5 REVIEW PASS | DONE |
| E1 | Workflow | `workflow/` (maker != checker, one decision, expiry, DEC-055 bootstrap, DEC-056 owner decide) | `test_phase01_workflow*.py`, `test_phase01_roles_approvals_engine.py` | S8 `04_unit.log` | step-3/5/6 REVIEW PASS | DONE |
| E2 | Idempotency | `engine/idempotency.py`, `api/idempotent.py` (one-time secrets never stored) | `test_engine_idempotency.py`, HTTP race tests | S8 `04_unit.log` | step-4 REVIEW PASS | DONE |
| E3 | Field-level redaction | `authz/policy.py` `redact_fields`, `engine/redaction.py` | `test_phase01_authz_engine.py`, `test_log_redaction.py`, `test_redaction_persian.py`, never-exposed field test (`test_phase01_step7_privacy.py`) | S8 `04_unit.log`, `07_authz.log` | step-3/7 REVIEW PASS | DONE |
| E4 | Cancellation state machine | `workflow/` cancellation with compensation; `jobs/` safe cancel (STATE_TRANSITIONS §4.5/4.7) | `test_phase01_workflow_engine.py::test_cancel_with_compensation_*`, `test_phase01_params_jobs_engine.py::test_safe_cancel_*` | S8 `04_unit.log` | step-3 REVIEW PASS | DONE (force kill refused, DEC-024; SEC-02 is PHASE_11) |
| E5 | Session management | `identity/sessions.py` (idle/absolute limits, 3 concurrent, `CONCURRENT_LIMIT`), page "my sessions" | `test_phase01_auth_engine.py` | S8 `04_unit.log`, S8-shots `phase01-my-sessions-*` | step-3/5 REVIEW PASS | DONE (DEC-051, Q-0101/0102) |
| E6 | Retention | `jobs/service.py` (login events 24 months, audit never purged, rejected uploads 30 days, orphan bytes 24 h grace) | `test_phase01_params_jobs_engine.py::test_audit_events_are_never_purged`, `test_phase01_documents_engine.py::test_eicar_*`, `test_phase01_step7_ops.py::test_orphan_cleanup_*` | S8 `04_unit.log` | step-3/7 REVIEW PASS | DONE (Notification retention 180 d = TECHNICAL DEFAULT proposal, REV-0104) |
| E7 | Signed releases | - | - | - | - | **CARRIED** (checklist 3.11: artifact signing with the staging release pipeline; SBOM + dist sha256 exist: S8 `13_artifacts.log`) |
| E8 | Every documented rule has a golden test and a decision owner; unknown rules blocked | golden files `tests/golden/*.golden.json` (permission decisions, TOTP, outbox machine, event catalogue, ...); BUSINESS_RULE parameters refused with `RULE_NOT_APPROVED` | `test_phase01_*` golden tests | S8 `04_unit.log` | step-3/6/7 REVIEW PASS | DONE |

## 2. Steps 01.1-01.8

| Step | Required (PHASE_01.md) | Implementation commit | Review | Status |
|---|---|---|---|---|
| 01.1 | conflicts, data table, state transitions, OpenAPI draft, mock/UI binding, risks; P0 decisions; no mutation | `89e5f0d` | `reports/phase-01/step-1/REVIEW.md` PASS | DONE |
| 01.2 | migration version, PK/FK/unique/check/index, audit, outbox, rollback, non-sensitive seed; up/down + schema diff | `153651f` (rework 1; first `84e5acd`) | `step-2/REVIEW.md` PASS (1 rework) | DONE |
| 01.3 | calculation/state/conflict/idempotency logic, error codes; unit/property/golden tests before UI | `3f1f3ab` (rework 1; first `6fc3eea`) | `step-3/REVIEW.md` PASS (1 rework) | DONE |
| 01.4 | scoped permission, rate limit, ETag/version, pagination, request id, OpenAPI, real tests | `f6a60a5` | `step-4/REVIEW.md` PASS | DONE |
| 01.5 | pages, Farsi RTL responsive, loading/error/empty/stale, keyboard, 4-size screenshots, E2E | `ef4902a` | `step-5/REVIEW.md` PASS | DONE; employer UAT T-003 open (section 4) |
| 01.6 | related sources/events only; staging, retries, backoff, compensation, freshness, conflict queue; no direct change of another module | `7c1a93d` | `step-6/REVIEW.md` PASS | DONE |
| 01.7 | secret scan, dependency scan, privacy/permission tests, perf, backup/rollback, job monitoring; checklist signed | `bccd109` | `step-7/REVIEW.md` PASS | DONE except the checklist signature (EMPLOYER, G9) |
| 01.8 | report template, commit hash, migrations, test results, UI snapshots, trace map, issues; STOP | 7a360eb | `step-8/REVIEW.md` | PASS |

## 3. Cross-cutting requirements

| Area | Requirement | Evidence | Status |
|---|---|---|---|
| DB | migration + FK/check/index + audit/outbox + rollback | `docs/db/ERD.md` (0007-0018 incl. reverse of each), `docs/ops/ROLLBACK.md` §3a; S8 `05_migration.log` (round trip), `12_ops.log` (rollback rehearsal to 0010 with data) | DONE |
| API | OpenAPI & schema compatibility + idempotency + auth + errors | `docs/api/openapi-draft.yaml` 0.6.3-draft (`CONTRACT_VERSION` equal), `docs/api/API_RUNTIME.md`; S8 `06_contract.log` (validation + contract tests), `07_authz.log` (route parity) | DONE |
| UI | RTL desktop/laptop/tablet/mobile, a11y, role-sensitive, real screenshots | S8-shots (all views x 1440/1180/768/390, real backend), axe checks in E2E (S8 `09_e2e.log`), role-sensitive navigation + server 403 E2E | DONE |
| ENGINE | deterministic contract + sample & golden tests + traceability | `backend/platform_core/tests/golden/`, hypothesis property tests, `docs/engine/PHASE01_ENGINE.md`, `docs/integration/EVENT_CATALOGUE.md` | DONE |
| SEC | RBAC/ABAC, threat analysis, redaction, secure logs, scan | matrix v1.3 + DB guards; `docs/discovery/RISKS.md` R-21..R-35; `docs/security/PHASE_01_SECURITY_CHECKLIST.md`; S8 `11_security.log`, `07_authz.log` | DONE technically; checklist signature EMPLOYER; deployment items CARRIED (section 4) |
| QA | unit/integration/E2E/race/property/migration/security + independent evidence | S8 (13 stages); concurrency tests `test_phase01_concurrency.py`, `test_engine_uow_concurrency.py`, HTTP race tests; reviewer re-runs in each step REVIEW | DONE |

## 4. Gate criteria (PHASE_01.md "Gate پذیرش")

| # | Criterion | Evidence | Status / owner |
|---|---|---|---|
| G1 | Unauthorised role is denied | `test_phase01_step7_privacy.py` (11 roles x every PHASE_01 operation the matrix does not grant -> 403), `test_api_bola.py` (every `{id}` family -> 404 out of scope), E2E server-side 403 | DONE (S8 `04_unit.log`, `09_e2e.log`) |
| G2 | Audit cannot be tampered with | `test_audit_event.py` (UPDATE/DELETE/TRUNCATE refused by trigger), `test_phase01_audit_chain.py` (chain detects change / gap / raw insert), roles check (app role cannot disable triggers), page 36 integrity | DONE (S8 `04_unit.log`, `12_ops.log`) |
| G3 | Job kill only with permission and reason | safe cancel needs `platform.ops.job.cancel` + reason; protected jobs `JOB_PROTECTED`; force kill refused (DEC-024; SEC-02 is PHASE_11) | DONE (`test_phase01_params_jobs*.py`, `test_api_phase01_flows.py::test_jobs_safe_cancel_health_and_audit`, E2E page 36) |
| G4 | Multi-user concurrency | `test_phase01_concurrency.py` (6 races), `test_engine_uow_concurrency.py`, `test_api_phase01_race.py` (HTTP), `test_phase01_audit_chain.py::test_concurrent_writers_*`, HTTP races (Idempotency-Key, If-Match, parallel decisions, REV-0120); perf with 1/4/8 writers | DONE (S8 `04_unit.log`, `10_perf.log`) |
| G5 | UI keyboard / mobile | E2E keyboard RTL tree, focus, axe; S8-shots 390-mobile of every view | DONE (S8 `09_e2e.log`); employer UAT T-003 **EMPLOYER** |
| G6 | All security P0 tests pass | SEC-01 and SEC-03 (section 5) + privacy/permission suite | DONE (S8) |
| G7 | No known open Critical/P0 | no open P0/P1 REV issue (section 8); all PHASE_01 decisions APPROVED (section 7) | DONE (reviewer confirms) |
| G8 | No mandatory test FAIL / unexplained SKIP | S8: 1 skip with reason (ClamAV real-scanner contract test, clamd not configured on work-windows); 7 perf tests deselected in the unit stage and run in the perf stage; informational dev-venv pip-audit not performed (network), not a gate | DONE |
| G9 | Migrations reversible or approved compensation plan | S8 `05_migration.log` (round trip), rollback rehearsal (S8 `12_ops.log`): down to 0010 with data; reverse of 0011 refused by design while job runs exist -> restore from backup (`docs/ops/ROLLBACK.md` §3a) | DONE (the refusal is documented, not a compensation plan the employer approved: **EMPLOYER** acknowledges at the Gate) |
| G10 | Permission Matrix approved | `docs/security/PERMISSION_MATRIX_DRAFT.md` APPROVED v1.3 (DEC-049 + DEC-056 + extensions 2026-11-10) | DONE |
| G11 | CI report linked to commit | S8 `summary.md` (tree ids per directory; `commit.txt` filled by the orchestrator after the commit) | DONE (`commit.txt` = 7a360eb; all 6 tree ids match, verified by orchestrator and reviewer) |
| G12 | Real, non-demo UI | every PHASE_01 page bound to the real API; E2E against real Django + PostgreSQL; synthetic-data banner on synthetic data | DONE |
| G13 | Whole scope traceable | this file | DONE (01.8 PASS, `step-8/REVIEW.md`) |
| G14 | Employer and auditor acceptance; security checklist signed (01.7 text) | `docs/security/PHASE_01_SECURITY_CHECKLIST.md` sign-off rows blank on purpose | **EMPLOYER** |

Other items that need the employer at the Gate (one at a time):
1. **UAT T-003** (pages 36/39/40/42/46 + org tree, `reports/phase-01/step-5/UAT_HOWTO_FA.md`): result not recorded.
2. **Security checklist PHASE_01** sign-off; open deployment items (break-glass account 1.10, TLS 2.6, encrypted
   backups 2.7, CSP 3.4, proxy body limit 3.6, artifact signing 3.11, job scheduler 4.4, RPO/RTO on staging 4.8)
   are before production / pilot, as the PHASE_00 condition.
3. **TECHNICAL DEFAULTS** to confirm: login rate limits 20/min per IP and 10/min per user (step-4 REVIEW);
   housekeeping overdue after 26 h; orphan grace 24 h; multipart allowance 64 KiB; perf budgets; Notification
   retention 180 days (REV-0104); 60 s clock tolerance for no back-dating.
4. **Scope splits** proposed in 01.1 and implemented that way: C-33 (page 42: parameters + DRAFT dynamic fields in
   PHASE_01, the rest PHASE_11), C-34 (page 36: health/jobs in PHASE_01, dashboards PHASE_11), C-46 (no document
   check-out in PHASE_01; PHASE_12 candidate).
5. **Rollback boundary** of 0011 (G9).

## 5. Acceptance cases (GLOBAL_ACCEPTANCE_CASES.csv, minimum_phase 1)

| Case | Scenario / expected | Implementing files | Tests | Evidence | Status |
|---|---|---|---|---|---|
| SEC-01 (P0) | unauthorized object id request -> BOLA/IDOR blocked | `authz/policy.py` (`require_record` -> 404, list == object check, `scope_q`/`grant_q`), every `{id}` view | `test_api_bola.py::test_every_id_path_family_has_a_bola_case`, `::test_out_of_scope_object_ids_answer_404_on_every_operation`, `test_phase01_authz_engine.py::test_out_of_scope_record_is_not_found_not_forbidden`, `test_phase01_step7_privacy.py` (sensitivity cap 404) | S8 `04_unit.log` | DONE |
| SEC-03 (P0) | unsafe file upload -> quarantined and no execution | `documents/` (allow-list, quarantine state machine, scanner adapter, CLEAN-only download, purge), `api/upload_limit.py` (413 before parsing) | `test_phase01_documents_engine.py::test_eicar_is_quarantined_rejected_and_purged_after_30_days`, `::test_scanner_unavailable_keeps_the_file_quarantined`, `test_api_phase01_flows.py::test_documents_sec03_quarantine_review_and_attachment_download`, `test_phase01_step7_ops.py::test_oversized_upload_*`, E2E "upload into quarantine" | S8 `04_unit.log`, `09_e2e.log` | DONE with the ClamAV real-scanner contract test SKIPPED (clamd not configured on work-windows; the adapter path is covered by the test double) - real scanner on the staging server: CARRIED (DEC-053) |

No other case has `minimum_phase` <= 1 (SEC-02 force kill belongs to PHASE_11).

## 6. UI pages (UI_PAGE_PHASE_MAP.csv, PHASE_01) and the org tree (DEC-043)

| Page | Title | Implementation | E2E | Screenshots (S8-shots, each at 1440/1180/768/390) | Status |
|---|---|---|---|---|---|
| 36 | سلامت سیستم و Job | `frontend/src/pages/OpsPage.tsx` (health counters, integration block 01.6, housekeeping block 01.7, audit integrity, jobs + safe cancel) | `phase01.spec.ts` "page 36: ..." | `phase01-ops-*` | DONE (PHASE_11 part: C-34) |
| 39 | تسک‌ها و تأییدها | `WorkPage.tsx` (approval inboxes, decisions with reason, DEC-055 bootstrap, tasks) | "page 39: ...", "page 39 + 40: the owner ... decides" | `phase01-work-approvals-*`, `phase01-work-approvals-owner-decided-*` | DONE |
| 40 | مدیریت اسناد | `DocumentsPage.tsx` (upload into quarantine, CLEAN-only download, submit/approve/reject) | "document controller: ...", "page 39 + 40 ..." | `phase01-documents-*`, `phase01-document-detail-*` | DONE (PHASE_12 part: C-46) |
| 42 | پارامترها و چیدمان UI | `ParametersPage.tsx` (classification groups, OWNER_POLICY owner-only, BUSINESS_RULE `RULE_NOT_APPROVED`) | "page 42: ..." | `phase01-parameters-*`, `phase01-parameter-detail-*` | DONE (PHASE_11 part: C-33) |
| 46 | امنیت و کاربران | `SecurityPage.tsx` (users, one-time password once, lock/unlock, resets, sessions, roles, assignments, pending second approval) | "page 46: ..." | `phase01-security-users-*`, `phase01-security-roles-*`, `phase01-security-assignments-*` | DONE |
| org tree | درخت سازمانی (DEC-043/048) | `OrgPage.tsx` (WAI-ARIA tree, RTL keyboard, units / unit-head position / holders, effective from now) | "org tree: ..." | `phase01-org-empty-*`, `phase01-org-tree-*` | DONE |
| shell | login / MFA / home / forbidden / my sessions | `App.tsx`, `auth/`, `HomePage.tsx` | "login page ...", "owner first login ...", "logout ..." | `phase01-login-*`, `phase01-home-owner-*`, `phase01-forbidden-*`, `phase01-my-sessions-*` | DONE |

All pages are DRAFT / not approved in the handoff map (`approved=False`); the employer UAT T-003 covers them.

## 7. Decisions relevant to PHASE_01 (from `control/PROJECT_STATUS.json` and `control/decisions/DECISION_LOG.md`)

| ID | Prio | Status | Where implemented | Evidence |
|---|---|---|---|---|
| DEC-002 | P0 | APPROVED | fully web UI (React SPA on the API) | S8 `09_e2e.log` |
| DEC-003 | P0 | APPROVED | users only in the system, created by the owner/admin (`identity/users.py`, page 46); no AD/LDAP/SSO; TECHNICAL roles never approve business (DB guards 0008, exception DEC-056); explicit audited self-assignment (`confirm_self_assignment`) | `test_phase01_roles*.py`, `test_phase01_authz_engine.py`; S8 `04_unit.log` |
| DEC-032 | P1 | APPROVED | maker != checker, second approver for business-approval role grants, approval expiry, login-event retention 24 months | DB guards 0008/0013/0014; tests `test_phase01_roles_approvals_engine.py` |
| DEC-043 | P0 | APPROVED | org tree inside the system (units, positions, reports-to), page "org tree" | `org/`, `OrgPage.tsx`; `test_phase01_org.py`, `test_phase01_org_engine.py`, E2E org tree |
| DEC-048 | P0 | APPROVED | org tree details: unit types, PRIMARY/ACTING, no cycles, depth <= 6, unit head capacity 1, no back-dating (REV-0107/0109) | 0007/0008/0011; `test_phase01_concurrency.py` |
| DEC-049 | P0 | APPROVED | permission matrix v1.0 (11 roles, 43 permissions, 111 grants), unlock by it_ops, owner bootstrap from the console | 0010; golden `permission_decisions.golden.json` |
| DEC-050 | P0 | APPROVED | TOTP + 10 recovery codes + admin reset | `identity/mfa.py`, `identity/totp.py`; `totp_rfc6238.golden.json` |
| DEC-051 | P0 | APPROVED | password policy, lockout 5/15 min, sessions idle 2 h / 8 h, absolute 12 h, 3 concurrent, step-up window | `identity/`; parameters with DEC provenance (0010) |
| DEC-052 | P0 | APPROVED | internal network CIDRs from configuration, VPN/unknown = outside, operator accounts INTERNAL_ONLY | `identity/network.py`; CHECK in 0007 |
| DEC-053 | P0 | APPROVED | allow-list pdf/png/jpg/jpeg/dxf/xlsx, 25 MB (Q-0104), quarantine, ClamAV adapter, encrypted storage | `documents/`; SEC-03 tests |
| DEC-054 | P1 | APPROVED | option C: `manage.py bootstrap_owner [--recover]` on the console; break-glass account before go-live (checklist 1.10) | `management/commands/bootstrap_owner.py`; `test_phase01_params_jobs_engine.py`, `test_phase01_step5_backend.py` |
| DEC-055 | P1 | APPROVED (B) | one-time owner bootstrap self-approval, DB-locked (0013) | `bootstrapSelfApproveRequest`; `test_phase01_dec055.py`; E2E page 39 |
| DEC-056 | P0 | APPROVED (+ extensions 2026-11-10) | v1.1 owner reads/decides approvals (0014); v1.2 document approve + BUSINESS_RULE publish (0015, REV-0125); v1.3 document read/download (0017); in-app grant of owner_admin needs a second approver | golden 2+2 cells; `test_phase01_step6_dec056.py`, `test_phase01_step7_dec056_v13.py`; E2E "page 39 + 40" |
| (follow-up) | - | employer 2026-11-10 | REV-0133: `it_ops` may replay a dead letter; discard owner-only; both audited | `ops/dead_letters.py` `ALLOWED_ROLES`; `test_phase01_step7_ops.py` (01.8) |
| DEC-016 | P0 | OPEN (PHASE_06) | not used by PHASE_01 (no Rahkaran source); freshness of platform events uses TECHNICAL DEFAULT thresholds | - |

Employer answers Q-0101..Q-0106 are recorded in `DECISION_LOG.md` (REV-0110). No new DEC-### was opened in 01.8.

## 8. Review issues raised in PHASE_01

| ID | Sev | Raised | Subject | State |
|---|---|---|---|---|
| REV-0013 | P3 | 00.4 | 401 without `WWW-Authenticate` | PHASE_01: `api/session_auth.py` `authenticate_header` returns `Cookie` (so DRF sends `WWW-Authenticate: Cookie` on 401); C-42 proposed `Session realm="aleekhan"` - wording drift, no dedicated test found. **OPEN P3** (doc/test), proposed below |
| REV-0101 | P2 | 01.1 | MFA step-up flag on `rejectDocumentRevision` | fixed `84e5acd`/`153651f` (01.2), regression in contract tests |
| REV-0102 | P3 | 01.1 | commit hash missing in the 01.1 report | fixed `25d0abd` |
| REV-0103 | P3 | 01.1 | host name in junit logs | fixed `25d0abd` (+ `tools/redact_paths.py --in-place`, 01.2) |
| REV-0104 | P3 | 01.1 | Notification retention labelled technical default | fixed 01.2 (DATA_TABLE label: proposal under DEC-032); value still to confirm (section 4 item 3) |
| REV-0105 | P1 | 01.2 r0 | role lifecycle not enforced in DB | fixed `153651f` |
| REV-0106 | P2 | 01.2 r0 | OWNER_POLICY publish | fixed `153651f` (Q-0103) |
| REV-0107 | P2 | 01.2 r0 | back-dating | fixed `153651f` |
| REV-0108 | P3 | 01.2 r0 | report sha | fixed `1f21be8` |
| REV-0109 | P2 | 01.2 | position assignment back-dating trigger | fixed `6fc3eea` (0011) |
| REV-0110 | P3 | 01.2 | employer answers not in the decision log | fixed `d93805b` |
| REV-0111..REV-0115 | P1-P3 | 01.3 r0 | operator revisions, GLOBAL scope_q + cap, superseded params, refused-login outcome, purge on_commit | fixed `3f1f3ab` (step-3 REVIEW "CLOSED") |
| REV-0116 | P2 | 01.3 r0 | DEC-055 packet process | fixed (DEC-055 APPROVED, packet) |
| REV-0117 | P3 | 01.3 | DEC-055 packet status text | fixed `9e2d96c` |
| REV-0118 | P3 | 01.3 | always-true assertion | fixed `f6a60a5` (01.4) |
| REV-0119 | P3 | 01.3 | account name in a phase-00 log | fixed `9e2d96c` (redacted; grep = 0) |
| REV-0120..REV-0123 | P2-P3 | 01.4 | parent-revision lock, withdraw reason, publish note, CSRF rotation | fixed `ef4902a` (01.5) |
| REV-0124 | P3 | 01.4 | upload size checked after parsing | fixed `bccd109` (01.7, `api/upload_limit.py`) |
| REV-0125 | P2 | 01.5 | DEC-056 scope (documents, BUSINESS_RULE publish) | resolved by employer extension, fixed `7c1a93d` (0015) |
| REV-0126 | P3 | 01.5 | page 46 subtitle | fixed `7c1a93d` |
| REV-0127 | P3 | 01.5 | committed screenshots not tied to the reviewed commit | fixed in 01.8: all screenshots regenerated from the final tree (S8-shots; footer build = the tested tree, see PHASE_REPORT §5 note) |
| REV-0128 | P3 | 01.5 | UAT / E2E of the owner deciding another person's request | fixed `7c1a93d` (E2E + UAT 3.9/3.10) |
| REV-0129..REV-0131 | P2-P3 | 01.6 | poison event blocks its aggregate; blocked_aggregates; Farsi page 36 | fixed `bccd109` (01.7) |
| REV-0132 | P2 | 01.7 | no direct tests of `request_cache` | fixed in 01.8: `tests/test_authz_request_cache.py` (8 tests) - S8 `04_unit.log` |
| REV-0133 | P3 | 01.7 | dead-letter replay role | fixed in 01.8 per employer decision 2026-11-10 (`ops/dead_letters.py`, 4 new tests + updated refusal test) - S8 `04_unit.log` |
| REV-0134 | P3 | 01.7 | empty logs without command / exit code | fixed in 01.8 (`tools/ci_local.sh`: `# command` block + `# exit code: N` in every S8 log, exit-code column in `summary.md`) |
| REV-0135 | P3 | 01.7 | page 36 screenshots not committed | fixed in 01.8 (S8-shots `phase01-ops-*` with integration + housekeeping blocks) |

No P0/P1 issue is open.

## 9. Mandatory outputs ("خروجی‌های اجباری برای گزارش")

| Output | Where | Status |
|---|---|---|
| CHANGELOG | `CHANGELOG.md` (PHASE_01 sections 01.1-01.8) | DONE |
| migration IDs | `docs/db/ERD.md` §4 (0007-0018 with reverse) | DONE |
| updated ERD / OpenAPI | `docs/db/ERD.md`; `docs/api/openapi-draft.yaml` 0.6.3-draft (S8 `06_contract.log`: valid) | DONE |
| diff | `git log` / `git diff phase-00-rc..<01.8 commit>`; per-step commits section 2 | DONE |
| tests.xml / logs | S8 `pytest-unit-integration.xml`, `pytest-contract.xml`, `pytest-authz.xml`, `NN_*.log`; per-step `reports/phase-01/step-N/logs/` | DONE |
| security artifacts | S8 `secret_scan.json`, `pip_audit_runtime.json`, `sbom-python-runtime*.cdx.json`, `sbom-frontend.cdx.json`, `roles/`, `drill/`, `rollback/`, `frontend-dist.sha256`; `docs/security/PHASE_01_SECURITY_CHECKLIST.md` | DONE |
| UI screenshots | S8-shots `reports/phase-01/step-8/screenshots/` (final tree) | DONE |
| recorded conflicts | `docs/discovery/CONFLICTS.md` C-26..C-46 | DONE (proposals C-33/C-34/C-46 need the employer, section 4) |
| evidence links | this file, `reports/phase-01/PHASE_REPORT.md` | DONE |
| signed checklist | `docs/security/PHASE_01_SECURITY_CHECKLIST.md` sign-off | **EMPLOYER** |
| new decisions | DEC-048..DEC-056 + follow-ups (`control/decisions/DECISION_LOG.md`) | DONE |
| rollback instructions | `docs/ops/ROLLBACK.md` (§3a), `docs/db/ERD.md` reverse column, `docs/ops/BACKUP_RESTORE.md` | DONE |
