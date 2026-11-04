# PHASE REPORT - PHASE_00 Baseline & Architecture Lock (step 00.8)

```
PROJECT: Aleekhan
PHASE: PHASE_00
STEP: 00.8 (phase report over 00.1-00.8)
COMMIT SHA: 3c0ea1c03e0582d4a5e0d3e5e0fa76e151a659ed (00.8; orchestrator full CI re-run on this commit: reports/phase-00/step-8/logs/ci/summary.md, 13/13 PASS)
BRANCH/PR: main (GitHub, public per DEC-046)
STATUS: PARTIAL - all engineering scope done; step 00.8 IN_REVIEW (PASS pending the REV-0801..0803 doc fixes); Gate items that need the employer are open (section 7)
TIME OF REPORT (UTC): 2026-11-04
IMPLEMENTER: Claude Code (aleekhan-implementer), machine work-windows
SOURCE BASELINE: handoff v1.0 (verify_handoff: OK=300, KNOWN_DEFECT=1 PACKAGE_MANIFEST.json per DEC-044, EXCLUDED=46, failures=0 - reports/phase-00/step-8/logs/impl/verify_handoff.log)
```

Traceability of every scope item, Gate criterion, mandatory output, decision and review issue:
`reports/phase-00/TRACE_MAP.md`. Commit list: `CHANGELOG.md`.

## 1. Purpose & acceptance IDs

- Purpose: lock the baseline - repo scaffold, platform DB skeleton, platform engine, `/api/v1` platform endpoints
  with deny-by-default access, a real smoke UI, an integration framework without business sources, CI, security
  and ops controls - with no business writes.
- Acceptance IDs: `handoff/06_TEST_AND_ACCEPTANCE/GLOBAL_ACCEPTANCE_CASES.csv` has no case with
  `minimum_phase` 0 (step-1 REVIEW). UI pages in scope: 0 (`UI_PAGE_PHASE_MAP.csv`; the smoke page follows C-16).
- 00.8 items done in this step: REV-0702 (P2), REV-0703 (P3), REV-0704 (P3), `CHANGELOG.md`, `docs/db/ERD.md`,
  `TRACE_MAP.md`, this report + JSON.
- Out of scope: all business modules, users/roles/org tree (PHASE_01, DEC-003/DEC-043), code issuing
  (DEC-005/DEC-008), real imports (PHASE_06+).

## 2. Actual changes (whole phase)

| Step | Main changes | Implementation commit |
|---|---|---|
| 00.1 | `docs/discovery/*`, `docs/api/openapi-draft.yaml`, `tools/verify_handoff.py` | `57f4500e87bb936c1b8a622faaee5bb4a657e1d6` |
| 00.2 | Django project, `platform_core` migrations 0001-0003, `Code14Field`, `backend/scripts/db_roundtrip.sh`, `docs/db/README.md` | `7cf1f10066aec4c7cda8e6794eab43e748af644e` |
| 00.3 | `engine/` (errors, uow, idempotency, concurrency, outbox, rules, state, redaction), golden files | `a6efb53cff09aefdacb50ef48e092ec0041ced6f` |
| 00.4 | `api/` (probes, version, access gate, problems, request id, throttling, pagination, ETag), contract tests | `bd332cbb85cf6269533c63c33a0e85f8489b90bd` |
| 00.5 | `frontend/` system status page, tokens, states, Playwright | `fbd4218e8330226d3677583a054a42e9d1f20fff` |
| 00.6 | `integration/`, migrations 0004-0006, consumers/inbox/compensation, freshness, conflict queue, logo | `d7b444a8f2e907b8bb6c730faf15a5b455dc5e9e` |
| 00.7 | `.github/workflows/ci.yml`, `tools/ci_local.sh`, `tools/secret_scan.py`, `ops/db`, `ops/backup`, `docs/ops`, `docs/security` | `d6b6de96784d8d4d715e5978a2552c3531798faa` |
| 00.8 | `tools/secret_scan.py` + tests (REV-0702), threat delta + checklist (REV-0703), action SHA pins + `docs/ops/CI.md` (REV-0704), `CHANGELOG.md`, `docs/db/ERD.md`, `docs/db/README.md` (pointer), `docs/adr/ADR-001.md`, `docs/discovery/CONFLICTS.md` (C-02/C-14/C-15), `reports/phase-00/TRACE_MAP.md`, `PHASE_REPORT.md/.json` | `3c0ea1c03e0582d4a5e0d3e5e0fa76e151a659ed` |

- API: `/api/v1/health/live`, `/health/ready`, `/version`, `/access-gate/check`, integration read endpoints (deny by
  default); contract `docs/api/openapi-draft.yaml` (unchanged in 00.8).
- Migrations: `platform_core.0001_initial`, `0002_db_triggers`, `0003_seed_schema_meta`, `0004_integration`,
  `0005_integration_triggers`, `0006_seed_integration_sources` (none added in 00.7 or 00.8).
- UI: one smoke page (system status) on real endpoints; screenshots 1440/1180/768/390.
- Jobs/config: outbox dispatcher + `manage.py outbox_status`; settings from env only.

## 3. Data integrity

- Named PK/FK/UNIQUE/CHECK constraints and indexes: `docs/db/ERD.md` (from the schema dump
  `reports/phase-00/step-7/logs/ci/migration/schema_up_1.sql`).
- Audit append-only (trigger + app role without UPDATE/DELETE/TRUNCATE), compensation append-only, inbox
  no-update; unit of work writes business change + audit + outbox in one transaction; idempotency records;
  optimistic concurrency via `row_version`.
- Import provenance: sha256 + size + original name are immutable (trigger `platform_import_batch_provenance_guard`);
  receive is idempotent by `(source_id, file_sha256)`; staging is separate from official data; sources are
  READ_ONLY by CHECK. No Excel/DXF raw file is parsed in PHASE_00.
- 14-digit codes: `varchar(14)` + regex, format only; issuing BLOCKED (DEC-005/DEC-008 OPEN).

## 4. Security evidence

- Auth: no login in PHASE_00 (PHASE_01, DEC-003); every route deny-by-default, route parity generated from the
  URLconf (S8 `reports/phase-00/step-8/logs/ci/07_authz.log`: 166 passed). MFA: N/A until PHASE_01.
- Secrets: `tools/secret_scan.py` over tracked + untracked files and full history; REV-0702 tightened the
  placeholder rule to whole values (`fullmatch`). S8 `reports/phase-00/step-8/logs/ci/11_security.log`: 566 text files, 54 commits,
  env_values_checked=1, 1 allowlisted fingerprint (00.7 test fixture), findings=0. The stricter rule produced
  no new history hit after the fix (one documentation false positive on the scanner's own docstring was handled
  by ignoring surrounding backticks, not by an allowlist entry).
- Dependency scan / SBOM: S8 `reports/phase-00/step-8/logs/ci/11_security.log` (pip-audit: no known
  vulnerabilities; npm audit: 0 vulnerabilities); SBOMs `sbom-python-runtime.cdx.json`, `sbom-frontend.cdx.json`
  in the same folder (same results in S7).
- CI supply chain: actions pinned to full commit SHAs (REV-0704,
  `reports/phase-00/step-8/logs/rev0704_action_shas.log`); `permissions: contents: read`;
  `persist-credentials: false`; no secrets; `pull_request` only (fork runs read-only). The pinned workflow ran
  green on GitHub (run 41820871101 on `043cdff`).
- Threat model: `docs/discovery/RISKS.md`, `docs/security/THREAT_MODEL_DELTA_00.6_00.7.md` (T-60..T-78; public
  repository threats T-75..T-78 added in 00.8). Checklist: `docs/security/PHASE_00_SECURITY_CHECKLIST.md`
  (unsigned).
- Known risks: repository is public (DEC-046); detection of private data is pattern-based (T-78); a value that
  declares itself synthetic with the prefix `example-` / `synthetic-` / `not-a-real-` is exempt from the scanner
  (accepted residual risk, T-78 / checklist 2.1).

## 5. Test evidence

S8 = orchestrator full run `bash tools/ci_local.sh reports/phase-00/step-8/logs/ci` on the 00.8 commit
`3c0ea1c03e0582d4a5e0d3e5e0fa76e151a659ed` (work-windows, test PostgreSQL env loaded, password not printed;
`summary.md` 13/13 PASS). Hosted: GitHub Actions run 41820871101 on `043cdff` (same code + report/status
commits, includes the SHA pins) `success`, evidence artifact present; earlier run 41790868012 on `b5397b6`
`success`. The GitHub artifact needs a login to download, so the in-repo evidence is S8 `summary.md`.
S7 = 00.7 full run on `d6b6de9` (`reports/phase-00/step-7/logs/ci/summary.md`).

| Check | Result | Log (S8 = `reports/phase-00/step-8/logs/ci/`) |
|---|---|---|
| ruff check + format | PASS (All checks passed) | S8 `01_lint.log` |
| mypy strict | PASS (no issues in 86 source files) | S8 `02_type.log` |
| tools unittest | PASS (39 tests) | S8 `03_tools.log` |
| pytest unit + integration | PASS (488 passed, 1 skipped = REV-0014 with reason, 1 deselected = perf stage) | S8 `04_unit.log`, `pytest-unit-integration.xml` |
| migration up / zero / up | PASS (schema diff EMPTY, 953 lines; ROUNDTRIP OK) | S8 `05_migration.log`, `migration/` |
| API contract | PASS (18 passed) | S8 `06_contract.log` |
| authorization | PASS (166 passed) | S8 `07_authz.log` |
| vitest | PASS (23 passed, 3 files) | S8 `08_frontend.log` |
| Playwright E2E (real backend), screenshots 1440/1180/768/390 | PASS (12 passed + 1 passed) | S8 `09_e2e.log`, `screenshots/` |
| perf smoke | PASS (1 passed) | S8 `10_perf.log` |
| secret scan (tree + history), pip-audit, npm audit | PASS (findings=0; no known vulnerabilities; 0 vulnerabilities) | S8 `11_security.log` |
| DB roles, backup/restore drill | PASS (roles passed=26 failed=0; drill PASS) | S8 `12_ops.log` |
| build artifacts (SBOMs, dist hashes) | PASS | S8 `13_artifacts.log` |
| handoff hashes | PASS (OK=300, KNOWN_DEFECT=1, failures=0) | `reports/phase-00/step-8/logs/impl/verify_handoff.log` (`handoff/` unchanged by 3c0ea1c) |

## 6. Demo

- Local: start the test PostgreSQL, `cd backend && python manage.py migrate && python manage.py runserver`, then
  `cd frontend && npm run dev`, open `http://127.0.0.1:5173` (no login in PHASE_00; synthetic data banner).
- Employer UAT already done: T-001 PASS (system status page), T-002 PASS (logo + palette)
  (`control/PROJECT_STATUS.json` `ready_for_test`).
- Screenshots: `reports/phase-00/step-7/logs/ci/screenshots/`.

## 7. Issues / decisions

No open P0/P1 defect. Open items (details in TRACE_MAP sections 4 and 7):

| Item | Owner | Effect | Safe fallback |
|---|---|---|---|
| G4 ADR signed - `docs/adr/ADR-001.md` (PROPOSED, sign-off blank) | employer + auditor + IT sign | Gate-0 criterion not met | DEC-001 APPROVED records the choice |
| G8 Permission Matrix approval (`ROLE_PERMISSION_MATRIX_FA.md` is "proposed"; DEC-032 PROPOSED) | employer | Gate general condition | PHASE_00 is deny-all |
| G9 security checklist signature | employer + auditor + IT | 00.7 step text | - |
| REV-0014 `backend/.env.example` | employer (or grant agent access) | 1 explained SKIP | test skipped with reason |
| C-17 `/version` public | employer acknowledgement | info disclosure (minimal) | returns version, short commit, env name only |
| DEC-016 OPEN (P0, PHASE_06) | employer | freshness basis | TECHNICAL DEFAULT thresholds, import-time basis |
| REV-0013 401 without `WWW-Authenticate` | PHASE_01 | RFC conformance | - |
| Threat model: no consolidated STRIDE for 00.2-00.5 components | implementer | documentation | RISKS.md + checklist |
| Staging drill, WAL archiving, TLS/CSP at the proxy, artifact signing | IT, later phases | production readiness | local drill evidence |

New decisions in PHASE_00: DEC-044, DEC-045, DEC-046 (`control/decisions/DECISION_LOG.md`).

## 8. Rollback

- 00.8 is code/docs only (no migration): revert the 00.8 commit (`git revert 3c0ea1c`). Reverting the workflow
  restores major-tag action references; reverting the scanner restores the weaker placeholder rule (not
  recommended).
- Database: `docs/db/README.md` §4 and `docs/ops/ROLLBACK.md` (reverse migrations newest first; backup first;
  below 0002 removes audit protection, below 0001 drops platform tables). Backup/restore procedure and drill:
  `docs/ops/BACKUP_RESTORE.md`, S8 `12_ops.log`.
- No destructive change in 00.8.

## 9. Review request

Request **PASS** for 00.8. Check:
1. REV-0702: `tools/secret_scan.py` `is_placeholder` (fullmatch) and `tools/tests/test_secret_scan.py`
   (`test_placeholder_words_inside_a_real_looking_value_are_findings`, `test_whole_value_placeholders`); S8
   `03_tools.log`, `11_security.log`.
2. REV-0703: `docs/security/THREAT_MODEL_DELTA_00.6_00.7.md` (component table, T-67, T-68, T-75..T-78, section
   3) and checklist 2.1 / 3.13 / section 5.
3. REV-0704: `.github/workflows/ci.yml` `uses:` lines vs `reports/phase-00/step-8/logs/rev0704_action_shas.log`;
   GitHub run 41820871101 (`success`).
4. `reports/phase-00/TRACE_MAP.md` against PHASE_00.md, `docs/db/ERD.md` against the schema dump, `CHANGELOG.md`
   SHAs against `git log`.

## 10. Next step (proposal only)

After the 00.8 review: the orchestrator writes `reports/phase-00/GATE_PACKET_FA.md`, tags `phase-00-rcN` and
STOPS for the employer's Gate-0 decision. Before the Gate: the employer signs `docs/adr/ADR-001.md` (G4). PHASE_01 starts only after the employer accepts Gate-0.
