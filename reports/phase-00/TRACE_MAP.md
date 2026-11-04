# PHASE_00 Trace Map (step 00.8)

Scope source: `handoff/03_PHASE_PLAN/PHASE_00.md` (sections, steps, cross-cutting requirements, Gate, mandatory
outputs). Every row: scope item -> implementing files -> tests -> evidence logs -> review file -> status.

Status values: **DONE** (implemented + evidence + review PASS), **PARTIAL** (part done; the rest is named with an
owner), **OPEN** (not done; owner named), **EMPLOYER** (needs an employer action or signature; agents cannot close
it). Counts are copied from the cited logs; nothing is estimated.

Evidence sets used below:
- **S7** = full 13-stage CI run of 00.7 on `d6b6de96784d8d4d715e5978a2552c3531798faa`:
  `reports/phase-00/step-7/logs/ci/` (`summary.md`: all 13 stages PASS). Hosted run: GitHub Actions run
  41790868012 on `b5397b6` (code identical), all steps `success` (`reports/phase-00/step-7/REVIEW.md`).
- **S8** = full 13-stage CI run by the orchestrator on the 00.8 commit
  `3c0ea1c03e0582d4a5e0d3e5e0fa76e151a659ed`: `reports/phase-00/step-8/logs/ci/` (`summary.md`: 13/13 PASS;
  `commit.txt` = 3c0ea1c). Hosted run: GitHub Actions run 41820871101 on `043cdff` (code identical to 3c0ea1c
  plus report/status commits; includes the REV-0704 SHA pins) completed `success` with the evidence artifact
  present (download needs a GitHub login, so the in-repo evidence is S8 `summary.md`).
- Handoff hashes: `reports/phase-00/step-8/logs/impl/verify_handoff.log` (implementer run during 00.8;
  `git diff 3c0ea1c~1 3c0ea1c -- handoff` is empty, so it applies to 3c0ea1c).

Test counts (from logs):

| Suite | S7 log | S8 log |
|---|---|---|
| ruff | `01_lint.log`: All checks passed | `01_lint.log`: All checks passed |
| mypy strict | `02_type.log`: PASS | `02_type.log`: no issues in 86 source files |
| tools unittest | `03_tools.log`: 37 tests OK | `03_tools.log`: 39 tests OK (+2 REV-0702 tests) |
| pytest unit+integration | `04_unit.log`: 488 passed, 1 skipped, 1 deselected | `04_unit.log`: 488 passed, 1 skipped (REV-0014), 1 deselected (perf, own stage) |
| migration round-trip | `05_migration.log`: schema diff EMPTY, ROUNDTRIP OK | `05_migration.log`: schema diff EMPTY (953 lines), ROUNDTRIP OK, `makemigrations --check` no changes |
| API contract | `06_contract.log`: 18 passed | `06_contract.log`: 18 passed |
| authorization | `07_authz.log`: 166 passed | `07_authz.log`: 166 passed |
| vitest | `08_frontend.log`: 23 passed (3 files) | `08_frontend.log`: 23 passed (3 files) |
| Playwright E2E | `09_e2e.log`: 12 passed + 1 passed | `09_e2e.log`: 12 passed + 1 passed; `screenshots/` (7) |
| perf smoke | `10_perf.log`: 1 passed | `10_perf.log`: 1 passed |
| secret scan | `11_security.log`: findings=0 | `11_security.log`: 566 text files, 54 commits, env_values_checked=1, allowlisted 1, findings=0 |
| pip-audit / npm audit | `11_security.log`: no known vulnerabilities / 0 vulnerabilities | `11_security.log`: no known vulnerabilities / 0 vulnerabilities |
| DB roles / backup drill | `12_ops.log`: roles passed=26 failed=0; drill PASS | `12_ops.log`: roles passed=26 failed=0; drill PASS |
| handoff hashes | `reports/phase-00/step-1/logs/verify_handoff_after_DEC-044.log` | `step-8/logs/impl/verify_handoff.log`: OK=300, KNOWN_DEFECT=1, EXCLUDED=46, failures=0 |

## 1. Phase sections (PHASE_00.md)

| # | Scope item | Implementing files | Tests | Evidence | Review | Status |
|---|---|---|---|---|---|---|
| B1 | Reference architecture | `handoff/01_ARCHITECTURE/ADR_001_TECH_STACK.md` (contract), `docs/adr/ADR-001.md` (as built), DEC-001; `backend/`, `frontend/` follow it | - | DEC-001 APPROVED in `control/PROJECT_STATUS.json` | step-2, step-3 REVIEW | DONE (choice). Signed ADR artefact: see G4 |
| B2 | Real data and conflicts recorded | `docs/discovery/CONFLICTS.md` (C-01..C-25), `DATA_TABLE.md` | - | step-1 logs; `step-8/logs/impl/verify_handoff.log` | step-1 REVIEW | DONE (C-14/C-15 refreshed to the post-DEC-044 state in 00.8) |
| B3 | Decision list | `control/decisions/`, `DECISION_LOG.md`, status file | `control/tools/status.py` gates | DEC-044/045/046 entries | step-1, step-7 REVIEW | DONE |
| B4 | Threat model | `docs/discovery/RISKS.md` (00.1 risk register), `docs/security/THREAT_MODEL_DELTA_00.6_00.7.md` (STRIDE T-60..T-78) | - | - | step-7 REVIEW (REV-0703) | PARTIAL: no single consolidated STRIDE table for the 00.2-00.5 components (API/UI are covered by RISKS.md + checklist sections 1-3). Owner: implementer, proposed for the Gate packet or PHASE_01 |
| B5 | Internal deployment path and backups | DEC-002 / DEC-042 (decisions), `docs/ops/BACKUP_RESTORE.md`, `ops/backup/drill.sh`, `docs/ops/ROLLBACK.md` | drill checks | S7 `12_ops.log`, `drill/drill_report.json` | step-7 REVIEW | PARTIAL: drill on the local test environment (DEC-045 A) DONE; staging server, WAL archiving, TLS proxy and encrypted backup volume wait for the server (IT, PHASE_01/12) |
| B6 | Source provenance for new data | `integration/imports.py` (sha256, size, provenance immutable), migration `0005` provenance guard; `docs/ui/brand/README.md` (logo provenance) | `test_integration_imports.py` | S7 `04_unit.log` | step-6 REVIEW | DONE |
| B7 | Repo scaffold | `backend/` (Django 5.2), `frontend/` (React/TS), `ruff.toml`, `.gitattributes`, `tools/` | all suites | S7, S8 | step-2, step-5 REVIEW | DONE |
| B8 | Migrations skeleton | `backend/platform_core/migrations/0001..0006` | `test_schema.py`, round-trip | S8 `05_migration.log` | step-2, step-6 REVIEW | DONE (`docs/db/ERD.md`) |
| B9 | Health API | `api/views.py` (`/health/live`, `/health/ready`, `/version`) | `test_api_platform.py`, contract tests | S8 `06_contract.log` | step-4 REVIEW | DONE |
| B10 | Access gate stub, NO business writes | `api/views.py` `AccessGateCheckView` (never ALLOW), `api/permissions.py` deny-by-default | `test_authz_route_parity.py` | S8 `07_authz.log` (166 passed) | step-4, step-7 REVIEW | DONE |
| B11 | Smoke UI design tokens | `frontend/src/styles/tokens.css`, `docs/ui/DESIGN_TOKENS.md`, `SystemStatusPage.tsx` | vitest, Playwright | S7 `08_frontend.log`, `09_e2e.log`; screenshots | step-5, step-6 REVIEW; T-001, T-002 PASS (employer UAT) | DONE |
| B12 | Stack / ADR + ERD + API versioning + CI/QA/security pipeline | ADR (contract), `docs/db/ERD.md`, `/api/v1` + `docs/api/openapi-draft.yaml`, `.github/workflows/ci.yml`, `tools/ci_local.sh` | all stages | S7 summary, GitHub run 41790868012 | step-7 REVIEW | DONE (ADR signature: G4) |
| B13 | Source immutability and privacy controls | `.gitignore`, `control/tools/precommit_guard.py`, `tools/secret_scan.py`, `engine/redaction.py`, READ_ONLY source CHECK (`0004`) | `test_secret_scan.py`, `test_redaction_persian.py`, `test_log_redaction.py` | S8 `03_tools.log`, `11_security.log`, `07_authz.log` | step-6, step-7 REVIEW | DONE (REV-0702 fixed in `3c0ea1c`) |
| B14 | Each documented rule has a golden test + decision owner; unknown rules blocked | `engine/rules.py` (empty approved registry -> `RULE_NOT_APPROVED`), `tests/golden/*.golden.json` (5 technical golden files: backoff, error codes, import batch machine, integration backoff, outbox machine) | `test_engine_rules_state.py` (`test_no_business_rule_approved_in_phase_00`) | S8 `04_unit.log` | step-3 REVIEW | DONE (no business rule exists in PHASE_00) |

## 2. Steps 00.1-00.8

| Step | Required (PHASE_00.md) | Implementation commit | Review | Status |
|---|---|---|---|---|
| 00.1 | conflicts, data table, state transitions, OpenAPI draft, mock/UI binding, risks; P0 decisions; no mutation | `57f4500e87bb936c1b8a622faaee5bb4a657e1d6` | `reports/phase-00/step-1/REVIEW.md` PASS | DONE |
| 00.2 | migration version, PK/FK/unique/check/index, audit, outbox, rollback, seed; up/down + schema diff | `7cf1f10066aec4c7cda8e6794eab43e748af644e` | `step-2/REVIEW.md` PASS | DONE |
| 00.3 | calculation/state/conflict/idempotency logic, error codes; unit/property/golden tests | `a6efb53cff09aefdacb50ef48e092ec0041ced6f` | `step-3/REVIEW.md` PASS | DONE |
| 00.4 | scoped permission, rate limit, ETag/version, pagination, request id, OpenAPI, real tests | `bd332cbb85cf6269533c63c33a0e85f8489b90bd` | `step-4/REVIEW.md` PASS | DONE |
| 00.5 | RTL responsive, loading/error/empty/stale, keyboard, 4 screenshots, E2E | `fbd4218e8330226d3677583a054a42e9d1f20fff` | `step-5/REVIEW.md` PASS; T-001 PASS | DONE |
| 00.6 | staging, retries, backoff, compensation, freshness, conflict queue | `d7b444a8f2e907b8bb6c730faf15a5b455dc5e9e` | `step-6/REVIEW.md` PASS; T-002 PASS | DONE |
| 00.7 | secret scan, dependency scan, privacy/permission tests, perf, backup/rollback, job monitoring; checklist signed | `d6b6de96784d8d4d715e5978a2552c3531798faa` | `step-7/REVIEW.md` PASS (round 2) | DONE except checklist signature (EMPLOYER, see G9) |
| 00.8 | report template, commit hash, migrations, test results, UI snapshots, trace map, issues; STOP | `3c0ea1c03e0582d4a5e0d3e5e0fa76e151a659ed` | `step-8/REVIEW.md` (PASS pending the REV-0801..0803 doc fixes) | IN_REVIEW |

## 3. Cross-cutting requirements

| Area | Requirement | Evidence | Status |
|---|---|---|---|
| DB | migration + FK/check/index + audit/outbox + rollback | `docs/db/ERD.md`, `docs/db/README.md` §4, `docs/ops/ROLLBACK.md`; S8 `05_migration.log` | DONE |
| API | OpenAPI + schema compatibility + idempotency + auth + errors | `docs/api/openapi-draft.yaml`, `docs/api/API_RUNTIME.md`, `test_api_contract.py` (S8 18 passed), `test_engine_idempotency.py`; auth = deny-all until PHASE_01 (DEC-003) | DONE for PHASE_00 (login is PHASE_01) |
| UI | RTL desktop/laptop/tablet/mobile, a11y, role-sensitive, real screenshots | `reports/phase-00/step-6/screenshots/` and `step-7/logs/ci/screenshots/` (1440/1180/768/390 real, SIMULATED states labelled); role-sensitivity N/A (no roles before PHASE_01) | DONE (role part PHASE_01) |
| ENGINE | deterministic contract + sample and golden tests + traceability | `backend/platform_core/tests/golden/`, `test_engine_*.py` (hypothesis property tests), `docs/engine/README.md` | DONE |
| SEC | RBAC/ABAC, threat analysis, redaction, secure logs, scan | `docs/security/PHASE_00_SECURITY_CHECKLIST.md`, threat delta T-60..T-78, S8 `07_authz.log`, `11_security.log`; S7 `11_security.log` | DONE technically; checklist signature EMPLOYER |
| QA | unit/integration/E2E/race/property/migration/security + independent evidence | S7 and S8 (13 stages each), GitHub runs 41790868012 and 41820871101, reviewer re-runs in each REVIEW.md | DONE |

## 4. Gate criteria (PHASE_00.md "Gate پذیرش")

| # | Criterion | Evidence | Status / owner |
|---|---|---|---|
| G1 | All files have hash and source | handoff: `step-8/logs/impl/verify_handoff.log` (OK=300, KNOWN_DEFECT=1 = PACKAGE_MANIFEST.json per DEC-044, failures=0); imports: sha256 provenance (B6); logo: `docs/ui/brand/README.md` | DONE with the DEC-044 known defect |
| G2 | Code/Die/Stock path locked without an approved rule | `engine/rules.py` (no approved rule decision), `Code14Field` format only (issuing BLOCKED, DEC-005/DEC-008 OPEN), no business tables, sources READ_ONLY + `policy_decision_id` gate (`0004`, `0006`) | DONE |
| G3 | CI and backup restore drill in a test environment | S7 and S8 summaries (13/13 PASS each), GitHub runs 41790868012 and 41820871101; drill PASS S7 and S8 `12_ops.log` (local environment per DEC-045 A) | DONE (staging drill when the server exists - IT) |
| G4 | ADR approved and signed | DEC-001 APPROVED (choice); as-built record `docs/adr/ADR-001.md` (pinned versions, deviations D1-D11, sign-off section 7; status APPROVED by employer) | **DONE (employer)**: signed by the employer بسام ربیهاوی on 2026-11-04 (ADR-001 section 7); auditor and IT rows still blank |
| G5 | No known open Critical/P0 | P0 decisions with phase PHASE_00 are all APPROVED (DEC-001/002/003/004/028/036/041/042/045/046); open P0 decisions belong to later phases (OPEN: DEC-005, 007, 008, 010-013, 015-017, 019, 022, 023, 026, 035; PROPOSED: DEC-006, 020). No open P0/P1 REV issue (section 6) | DONE (reviewer confirms) |
| G6 | No mandatory test FAIL/SKIP without reason | 1 SKIP with reason (`test_env_example_lists_every_settings_variable`, REV-0014); 1 deselected perf test runs in its own stage (S7 `10_perf.log`) | **EMPLOYER**: REV-0014 needs the employer to edit `backend/.env.example` or allow the agent to edit it |
| G7 | Migrations reversible or approved compensation plan | round-trip S8 `05_migration.log`; reverse of each migration in `docs/db/ERD.md` §1 | DONE |
| G8 | Permission Matrix approved | `handoff/05_SECURITY/ROLE_PERMISSION_MATRIX_FA.md` is marked "proposed, needs approval by unit owners"; DEC-032 (maker-checker + audit retention) is PROPOSED, phase PHASE_01. PHASE_00 implements deny-all only | **EMPLOYER**: approve the matrix, or record that Gate-0 accepts deny-all with approval moved to PHASE_01 |
| G9 | Security checklist signed (step 00.7 text) | `docs/security/PHASE_00_SECURITY_CHECKLIST.md` "Sign-off" table is blank on purpose | **EMPLOYER** + auditor + IT |
| G10 | CI report linked to commit | `summary.md` header carries the commit (S7 `d6b6de9`, S8 `3c0ea1c`); GitHub Actions run 41790868012 on `b5397b6` and run 41820871101 on `043cdff` both completed `success` with the evidence artifact present | DONE (the GitHub artifact needs a login to download; the in-repo evidence is S8 `summary.md`) |
| G11 | Real, non-demo UI | system status page on real `/api/v1` (S7 `09_e2e.log` against real Django + PostgreSQL); SIMULATED screenshots are labelled | DONE; T-001, T-002 PASS |
| G12 | Full scope traceable | this file | DONE when 00.8 is reviewed |
| G13 | Employer and auditor acceptance | - | **EMPLOYER** |

Other items that need the employer:
- **C-17** (`/version` is public: api/contract version, short commit, environment name only;
  `docs/api/API_RUNTIME.md` §6). A technical decision; the employer should acknowledge it at the Gate.
- **DEC-016** (Rahkaran snapshot validity) is OPEN (P0, PHASE_06). Not a Gate-0 item, but freshness uses import
  time and TECHNICAL DEFAULT thresholds until it is decided (`0006_seed_integration_sources`).
- **DEC-046** consequences: everything committed is public (threat model T-75..T-78). Optional repository setting
  "require approval for fork PR workflows" (T-77).

## 5. Mandatory outputs ("خروجی‌های اجباری برای گزارش")

| Output | Where | Status |
|---|---|---|
| CHANGELOG | `CHANGELOG.md` | DONE |
| migration IDs | `docs/db/ERD.md` §1 (0001-0006) | DONE |
| updated ERD / OpenAPI | `docs/db/ERD.md`; `docs/api/openapi-draft.yaml` (unchanged since 00.6) | DONE |
| diff | `git log` / `git diff 2ad2885..3c0ea1c` (commit list in CHANGELOG) | DONE |
| tests.xml / logs | S7 `pytest-unit-integration.xml`, `pytest-contract.xml`, `pytest-authz.xml`; S8 same files; per-step logs `reports/phase-00/step-N/logs/` | DONE |
| security artifacts | S7 `secret_scan.json`, `pip_audit_runtime.json`, `sbom-python-runtime.cdx.json`, `sbom-frontend.cdx.json`, `roles/`, `frontend-dist.sha256`; S8 `secret_scan.json`; threat delta; checklist | DONE |
| UI screenshots | `reports/phase-00/step-5/screenshots/`, `step-6/screenshots/`, `step-7/logs/ci/screenshots/` | DONE |
| recorded conflicts | `docs/discovery/CONFLICTS.md` | DONE |
| evidence links | this file, `PHASE_REPORT.md` | DONE |
| signed checklist | `docs/security/PHASE_00_SECURITY_CHECKLIST.md` sign-off | **EMPLOYER** |
| new decisions | DEC-044, DEC-045, DEC-046 (`control/decisions/DECISION_LOG.md`) | DONE |
| rollback instructions | `docs/ops/ROLLBACK.md`, `docs/db/README.md` §4, `docs/ops/BACKUP_RESTORE.md` | DONE |

## 6. Decisions relevant to PHASE_00 (from `control/PROJECT_STATUS.json`)

| ID | Prio | Status | Use in PHASE_00 |
|---|---|---|---|
| DEC-001 | P0 | APPROVED | stack Django 5.2 / DRF / PostgreSQL 17 / React-TS (ADR signature: G4) |
| DEC-002 | P0 | APPROVED | fully web-based; deployment target |
| DEC-003 | P0 | APPROVED | in-system users only (PHASE_01); PHASE_00 has no login |
| DEC-004 | P0 | APPROVED | RPO 1 h / RTO 4 h; backup policy (drill) |
| DEC-005, DEC-008 | P0 | OPEN | code issuing BLOCKED; `Code14Field` format only |
| DEC-016 | P0 | OPEN (PHASE_06) | freshness basis = TECHNICAL DEFAULT |
| DEC-025 | P1 | OPEN (PHASE_12) | legacy workbook sources gated |
| DEC-027 | P1 | OPEN (PHASE_01) | pages 1-2 without prototype; no effect on PHASE_00 UI |
| DEC-028 | P0 | APPROVED | raw files local only; synthetic fixtures |
| DEC-032 | P1 | PROPOSED (PHASE_01) | maker-checker / audit retention; Permission Matrix (G8) |
| DEC-036 | P0 | APPROVED | independent Claude reviewer; Gate only by employer signature |
| DEC-037 | P1 | APPROVED | source versions of 2026-11-03 are the golden basis (later phases) |
| DEC-039 | P1 | CLOSED | FastAPI vs Django conflict closed |
| DEC-040 | P1 | APPROVED | source password only in env |
| DEC-041 | P0 | APPROVED | shared Git repo; data rule (visibility amended by DEC-046) |
| DEC-042 | P0 | APPROVED | production on the company server, HTTPS, proxy |
| DEC-043 | P0 | APPROVED (PHASE_01) | org hierarchy tree - PHASE_01 |
| DEC-044 | P1 | APPROVED | handoff CSV CRLF restore; manifest hash known defect |
| DEC-045 | P0 | APPROVED | CI on GitHub-hosted runners; local restore drill |
| DEC-046 | P0 | APPROVED | repository stays public |

## 7. Review issues raised in PHASE_00

| ID | Sev | Raised | Subject | State |
|---|---|---|---|---|
| REV-00.1-A / -B | - | kickoff | manifest hash / CSV EOL | resolved by DEC-044 (`f97040f`, `d35b3d8`); manifest = known defect |
| REV-0001 | P2 | 00.1 | OpenAPI security declaration | fixed `bd332cb` (00.4) |
| REV-0002 | P2 | 00.1 | lint/type evidence, validator install | closed in 00.2 (`7cf1f10`, step-2 REVIEW) |
| REV-0003 | P3 | 00.1 | Windows drive paths in verify_handoff | fixed `7cf1f10` (00.2) |
| REV-0004 | P3 | 00.1 | unused noqa | fixed `7cf1f10` (00.2) |
| REV-0005 | P2 | 00.2 | Python 3.12 target | fixed `a6efb53` (00.3) |
| REV-0006 | P3 | 00.2 | ruff scope | fixed `a6efb53` (00.3) |
| REV-0007 | P3 | 00.2 | audit-column exemption for platform tables | fixed `a6efb53` (00.3, docs) |
| REV-0008..REV-0012 | P3 | 00.3 | conftest guard, scope redaction, immutable rule registry, settings, idempotency failure path | fixed `bd332cb` (00.4) |
| REV-0013 | P3 | 00.4 | 401 without `WWW-Authenticate` | **deferred to PHASE_01** (session scheme) |
| REV-0014 | P3 | 00.4 | `backend/.env.example` not updated | **OPEN - EMPLOYER** (agent access denied; test skipped with reason) |
| REV-0015 | P3 | 00.4 | `NUM_PROXIES` default behind proxy | fixed `5f3f5c3` (00.7) |
| REV-0016 | P3 | 00.4 | readiness probe cost | fixed `5f3f5c3` (00.7) |
| REV-0501 | P3 | 00.5 | E2E screenshot dir overwrote evidence | fixed `d7b444a` (00.6) |
| REV-0502 | P3 | 00.5 | account name in a committed step-5 log | mitigated `5f3f5c3` (`tools/redact_paths.py` for new logs); the old log is historic evidence, not rewritten |
| REV-0503 | P3 | 00.5 | ready chip shown when stale | fixed `d7b444a` (00.6) |
| REV-0504 | P3 | 00.5 | 768 px empty grid cell | fixed `d7b444a` (00.6) |
| REV-0601 | P2 | 00.6 | freshness could move backwards | fixed `5f3f5c3` (00.7) |
| REV-0602 | P2 | 00.6 | Persian sensitive column names | fixed `5f3f5c3` (00.7) |
| REV-0603 | P3 | 00.6 | E2E browser preflight | fixed `5f3f5c3` (00.7) |
| REV-0701 | P0 | 00.7 | repository public vs DEC-041 | resolved by employer decision DEC-046 (`513153b`) |
| REV-0702 | P2 | 00.7 | secret-scan placeholder substring bypass | fixed `3c0ea1c` (00.8; S8 `03_tools.log`, `11_security.log`); prefix self-declaration = accepted residual risk (T-78, checklist 2.1) |
| REV-0703 | P3 | 00.7 | threat model assumes a private repo | fixed `3c0ea1c` (00.8; threat delta T-67, T-75..T-78; checklist 2.1/3.13) |
| REV-0704 | P3 | 00.7 | actions pinned to major tags | fixed `3c0ea1c` (00.8; `reports/phase-00/step-8/logs/rev0704_action_shas.log`); pins verified by GitHub run 41820871101 (`success`) |

Other open technical items carried to later phases (from the security checklist): CSP header (3.4, on the proxy,
DEC-042), artifact signing (3.10), staging restore drill / WAL archiving (4.2, 4.7), TLS termination (2.6).
