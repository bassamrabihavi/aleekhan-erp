# PHASE_00 security checklist (step 00.7)

Baseline: `handoff/05_SECURITY/SECURITY_BASELINE_FA.md` (OWASP ASVS 5.0.0 as review reference - **not a claim of
certification**). PHASE_00 scope: platform skeleton only - no users/login (PHASE_01, DEC-003), no business
data, no file upload, no deployment server yet (DEC-045 A).

Status values: **DONE** (evidence exists), **PARTIAL** (part done, rest named), **N/A-P00** (feature does not
exist in PHASE_00; owner phase named), **OPEN** (gap in PHASE_00 scope - listed in the 00.7 report).

Evidence paths are repository files. "CI log `NN_<stage>.log`" = output of `bash tools/ci_local.sh <dir>` (the
orchestrator stores it under `reports/phase-00/step-7/logs/`) or the same stage of `.github/workflows/ci.yml`.

## 1. Identity, authentication, authorization

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1.1 | MFA for admins/finance/HR/approvers | N/A-P00 (PHASE_01, DEC-003) | no login exists: `settings.REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES = []` |
| 1.2 | Rate limiting / brute-force protection | DONE (API level) | `platform_core/api/throttling.py`; tests `test_rate_limit_per_ip_returns_429_problem_with_retry_after`, `test_x_forwarded_for_with_one_trusted_proxy_separates_clients`; REV-0015 fail-fast `test_deployed_refuses_trusted_tls_header_without_proxies` |
| 1.3 | Session expiry, password policy | N/A-P00 (PHASE_01) | - |
| 1.4 | Deny by default on backend, every route | DONE | `api/permissions.py` (`DenyByDefault`, `DenyAllPolicy`); `tests/test_authz_route_parity.py` (all production routes x GET/POST/PUT/PATCH/DELETE: anonymous -> 401, authenticated without permission -> 403, generated from the URLconf); CI log `07_authz.log` |
| 1.5 | Per-record scope, BOLA/IDOR (SEC-01) | DONE (framework) | `ScopedPermission` -> 404 out of scope; `test_api_integration.py` (scope tests), `test_api_utilities.py::test_out_of_scope_record_is_404_not_403` |
| 1.6 | Allow/deny across distinct users | DONE (synthetic principals) | test harness `tests/api_harness.py` (distinct synthetic principals with different actions/scopes), `test_api_integration.py` |
| 1.7 | Maker-checker, emergency access, admin is not approver | N/A-P00 (PHASE_01+) | DEC-003 recorded; access-gate stub never returns ALLOW (`AccessGateCheckView`) |

## 2. Confidentiality and data

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 2.1 | No secrets in Git / logs / reports (repository is PUBLIC by DEC-046, so every commit, log and artifact is world-readable) | DONE | `tools/secret_scan.py` (tracked + untracked files + full git history, values never printed; placeholders exempt only as a whole value, REV-0702 in 00.8) + `tools/tests/test_secret_scan.py`; `control/tools/precommit_guard.py`; CI log `11_security.log`, `secret_scan.json`; public-visibility threats T-75..T-78 in `THREAT_MODEL_DELTA_00.6_00.7.md` (REV-0703). Accepted residual risk (REV-0803): values with the self-declaring prefix `example-` / `synthetic-` / `not-a-real-` are exempt; mitigated by diff review, the pre-commit guard and the CI history scan (T-78) |
| 2.2 | Secrets from environment only | DONE | `aleekhan/settings.py` (no defaults for secrets in staging/prod); `test_settings_env.py` |
| 2.3 | `.env.example` lists every variable (REV-0014) | OPEN | file not accessible to the implementing agent; `test_env_example_lists_every_settings_variable` is skipped with that reason until the orchestrator updates the file |
| 2.4 | Secrets never in logs | DONE | `api/logging.py` (allowlisted fields, no exception messages); `tests/test_log_redaction.py` (query string, Authorization header, cookie, JSON body, exception messages with synthetic markers -> none in log lines) |
| 2.5 | Sensitive-field deny-list incl. Persian (REV-0602) | DONE (technical deny-list) | `engine/redaction.py` (`normalize_key`: NFKC, Arabic yeh/kaf, ZWNJ, bidi, tatweel); `tests/test_redaction_persian.py` (audit redaction, outbox rejection, staging refusal; innocent words not flagged). Full classification: DEC-028 / PHASE_01 field matrix |
| 2.6 | HTTPS/TLS, secure cookies, HSTS | PARTIAL | settings (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS prod, SSL redirect); TLS termination at the internal proxy (DEC-042) is a deployment item (staging server not yet available) |
| 2.7 | Encrypted backups | PARTIAL (design) | `docs/ops/BACKUP_RESTORE.md` section 3 (age/gpg, sha256, separate volume) - TECHNICAL DEFAULT, applied when the staging server exists |
| 2.8 | Private factory sources never in repo; no execution of legacy files | DONE | `.gitignore`, precommit guard (blocked extensions), secret scan rule `env-file`; `tools/verify_handoff.py`; no parser/upload in PHASE_00 |
| 2.9 | SHA-256 of files, append-only logs under restricted roles | DONE | import provenance (`imports.receive_file`), audit append-only triggers (migration 0002) + least-privilege roles `ops/db/roles_check.sh` (app cannot DELETE/UPDATE/TRUNCATE audit, cannot DISABLE/DROP trigger, cannot set `session_replication_role`); CI log `12_ops.log`, `roles/roles_check.json` |
| 2.10 | PII in test data | DONE | synthetic fixtures only (`tests/factories.py`, drill seed labelled `synthetic_drill`) |

## 3. Application / API

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 3.1 | SQL injection | DONE | ORM only; the 3 raw statements are constant or parameterised (`views._check_database`, `context.db_now`, `consumers._INBOX_INSERT` with parameters); ruff `S` (bandit) rules enabled, CI log `01_lint.log` |
| 3.2 | XSS / template injection | DONE (PHASE_00 UI) | React escaping, no `dangerouslySetInnerHTML` in `frontend/src`; eslint strict; no server templates (`TEMPLATES = []`) |
| 3.3 | CSRF | DONE | `CsrfViewMiddleware`, problem+json failure view; DRF session auth enforces CSRF (PHASE_01) |
| 3.4 | Content Security Policy | OPEN (deployment) | no CSP header yet; to be set on the reverse proxy for the static UI (staging server, DEC-042) - listed in the 00.7 report |
| 3.5 | SSRF, path traversal, file upload, CSV formula injection | N/A-P00 / DONE where applicable | no outbound HTTP, no upload, no export; `imports.safe_basename` (basename only, bidi/control stripped); SEC-03 quarantine before any upload (PHASE_06/12) |
| 3.6 | Pagination limits, rate limits, explicit error codes, idempotency, optimistic concurrency, DB constraints | DONE | `docs/api/API_RUNTIME.md`; `test_api_utilities.py`, `test_engine_idempotency.py`, `test_engine_uow_concurrency.py`, `test_schema.py` |
| 3.7 | OpenAPI contract tests / fuzz | PARTIAL | contract validation of real responses (`test_api_contract.py`, CI log `06_contract.log`); property-based tests (hypothesis) for engine inputs; no generic OpenAPI fuzzer yet |
| 3.8 | SCA / dependency scan | DONE | `pip-audit` on `backend/requirements.lock` (runtime, direct + transitive pinned, `tools/lock_runtime.py`) and `npm audit --omit=dev`; CI log `11_security.log` (see 00.7 report for the actual results of this run) |
| 3.9 | SBOM, pinned versions | DONE | exact pins (`requirements*.txt`, `requirements.lock`, `package-lock.json`); CycloneDX SBOMs from the `artifacts` stage (`sbom-python-runtime.cdx.json`, `sbom-frontend.cdx.json`) |
| 3.10 | Signed build artifacts | OPEN | only SHA-256 of the frontend bundle (`frontend-dist.sha256`); signing needs the release pipeline (staging) |
| 3.11 | Containers non-root, image scan | N/A-P00 | no container images yet (deployment phase) |
| 3.12 | SAST | DONE (baseline) | ruff `S` rules (flake8-bandit) on backend + tools, eslint strict-type-checked on frontend; S101 (assert) ignored with justification in `ruff.toml` |
| 3.13 | CI pipeline in contract order, no unexplained skips | DONE (local + GitHub Actions run 41790868012, see 00.7 REVIEW.md) | `.github/workflows/ci.yml` (DEC-045 A, `permissions: contents: read`, no secrets); `tools/ci_local.sh` writes `summary.md` with skip reasons; actions pinned to full commit SHAs with `# vX.Y.Z` comments (REV-0704, `reports/phase-00/step-8/logs/rev0704_action_shas.log`); fork PRs: `pull_request` only, read-only token, no secrets (T-77) |

## 4. Data integrity, reliability, operations

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 4.1 | Atomic write + audit + outbox | DONE | `engine/uow.py`; `test_engine_uow_concurrency.py` |
| 4.2 | Backup consistency + restore proof | DONE (local test environment, DEC-045 A) | `ops/backup/drill.sh`, `docs/ops/BACKUP_RESTORE.md`; `drill/drill_report.json` (fingerprint of every table identical, dump sha256 verified, migrations clean, audit trigger enforced). Staging drill with production-sized data: PHASE_01/12 |
| 4.3 | Rollback instructions | DONE | `docs/ops/ROLLBACK.md`; migration round-trip `backend/scripts/db_roundtrip.sh` (CI log `05_migration.log`) |
| 4.4 | Job checkpoint / safe states / monitoring | DONE (outbox) | outbox lease + `recover_stale`, dead letters; `manage.py outbox_status` + `docs/ops/JOB_MONITORING.md`; `tests/test_ops_monitoring.py` |
| 4.5 | Environment isolation | DONE | `ALEEKHAN_ENV` mandatory; `settings_test.py`; throw-away DB guard (`conftest.assert_throwaway_test_db`); drill/roles scripts refuse non-throw-away names |
| 4.6 | Least-privileged service accounts | DONE (scripted + tested) | `ops/db/roles.sql`, `ops/db/grants.sql`, `docs/ops/DB_ROLES.md`, `ops/db/roles_check.sh` |
| 4.7 | RPO/RTO approved before production | PARTIAL | DEC-004 approved (RPO 1 h / RTO 4 h); measured only on a tiny synthetic dataset locally; WAL archiving design documented, not configured (no server) |
| 4.8 | Compensation, duplicate import handling | DONE (framework) | `consumers.record_compensation`, inbox dedup; `imports.receive_file` idempotent by sha256 (`test_concurrent_duplicate_imports_create_exactly_one_batch`) |
| 4.9 | Stale data timestamps visible; never move backwards (REV-0601) | DONE | `imports.supersedes_freshness` + row lock; `tests/test_integration_freshness_monotonic.py` (incl. 6-way concurrent validation); basis = import time, TECHNICAL DEFAULT pending DEC-016 |
| 4.10 | Performance smoke | DONE (evidence, not SLA) | `tests/test_perf_smoke.py` (`pytest -m perf`), `perf.json`; TECHNICAL DEFAULT budget p95 < 250 ms in-process |
| 4.11 | Readiness probe cost (REV-0016) | DONE | 10 s per-process cache of the migrations check; `test_readiness_caches_migrations_check_within_ttl` |

## 5. Gate evidence pack (SECURITY_BASELINE 5)

Threat changes: `docs/security/THREAT_MODEL_DELTA_00.6_00.7.md` | RBAC/ABAC tests: 1.4-1.6 | SAST/SCA: 3.8, 3.12 |
secret scan: 2.1 | data-flow / sensitive fields: 2.4, 2.5, threat-model delta section 2 | API/IDOR tests: 1.5, 3.7
| migration/backup/rollback: 4.2, 4.3 | sample redacted logs: CI logs pass `tools/redact_paths.py` (REV-0502) and
the structured-log test 2.4 | severity table: 00.7 REPORT + REVIEW.

Known open items in PHASE_00 scope (no P0/P1 identified by the implementer; the reviewer decides): 2.3
(REV-0014), 3.4 CSP, 3.10 artifact signing, staging drill. Closed in 00.8: action SHA pinning (REV-0704), public
visibility threats (REV-0703), whole-value placeholder rule (REV-0702); first GitHub Actions run done (00.7 REVIEW.md).

## Sign-off (each row is filled only from the signer's own statement; the orchestrator records it)

| Role | Name | Decision (accept / reject / accept with conditions) | Date | Signature |
|---|---|---|---|---|
| Employer (کارفرما) | بسام ربیهاوی | accept with conditions (پذیرش با شرط): all OPEN and PARTIAL items (2.3, 2.6, 2.7, 3.4, 3.7, 3.10, 4.7) are closed before deployment on the production server and before the Pilot | 2026-11-04 | given by the employer in the Claude Code session (answer to Gate packet item 4-c); recorded by the orchestrator |
| Security reviewer / auditor | | | | |
| IT (operations) | | | | |
