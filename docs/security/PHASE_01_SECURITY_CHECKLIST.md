# PHASE_01 security checklist (step 01.7)

Baseline: `handoff/05_SECURITY/SECURITY_BASELINE_FA.md` (OWASP ASVS 5.0.0 as review reference - **not a claim of
certification**). PHASE_01 scope: users / roles / scopes / MFA / sessions (DEC-003, DEC-049..DEC-056), org tree
(DEC-043), audit hash chain, outbox events, jobs, tasks / approvals / workflow, documents with quarantine
(DEC-053), parameters and dynamic field drafts; pages 36, 39, 40, 42, 46. No deployment server yet (DEC-045 A):
deployment items stay OPEN with their owner named.

Status values: **DONE** (evidence exists), **PARTIAL** (part done, rest named), **N/A-P01** (feature does not
exist in PHASE_01; owner phase named), **OPEN** (gap - listed in the 01.7 report).

Evidence paths are repository files. `logs/` = `reports/phase-01/step-7/logs/` (redacted with
`tools/redact_paths.py`). Items carried unchanged from `PHASE_00_SECURITY_CHECKLIST.md` say so.

## 1. Identity, authentication, authorization

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1.1 | Users only inside the system, no AD/LDAP/SSO (DEC-003) | DONE | `identity/users.py` (owner creates users, one-time password shown once), `bootstrap_owner` console command; no external IdP code or setting |
| 1.2 | MFA for admins / approvers; step-up on sensitive actions (DEC-050, DEC-049 item 5) | DONE | `identity/totp.py`, `identity/mfa.py`, `authz.policy.require_step_up`; `tests/test_phase01_step7_privacy.py::test_mfa_flagged_operations_need_a_fresh_step_up_for_every_holder_role` (every MFA-flagged operation x every holder role -> 401 `MFA_REQUIRED`), `test_api_phase01_auth.py` |
| 1.3 | Password policy, session expiry, concurrent-session limit, lockout (DEC-051) | DONE | `identity/passwords.py`, `identity/sessions.py`; `test_phase01_auth_engine.py`, `test_phase01_totp_passwords.py`; login rate limits `test_api_phase01_auth.py` |
| 1.4 | Deny by default, every route and every role | DONE | `api/permissions.py` + `authz/policy.py`; route parity `test_authz_route_parity.py`; **01.7**: `test_phase01_step7_privacy.py::test_every_role_is_refused_every_operation_the_matrix_does_not_grant` (11 roles x 86 PHASE_01 operations with a permission, matrix v1.3 = `identity.roles.approved_matrix_grants`) |
| 1.5 | Per-record scope, BOLA/IDOR (SEC-01, P0) | DONE | `test_api_bola.py` (every `{id}` family x every method, list == object); **01.7**: document sensitivity caps -> 404 above the cap (`test_documents_above_the_sensitivity_cap_do_not_exist_for_the_role`) |
| 1.6 | Admin != business approval (DEC-003) with the explicit DEC-056 owner exception only | DONE | DB guard `ck_role_technical_no_business_approval` (0015: exactly three owner pairs; 0017 does not widen it - `test_v13_migration_does_not_replace_the_guard_functions`); `test_phase01_authz_engine.py::test_technical_roles_never_pass_business_approval_checks` |
| 1.7 | Maker-checker (DEC-032), second approver for owner grants | DONE | `workflow/approvals._check_decider`, DB CHECK `ck_approval_request_maker_checker`; `test_phase01_step6_dec056.py` (owner never decides his own request / upload / proposal) |
| 1.8 | Permission matrix approved and equal to the seed | DONE | `docs/security/PERMISSION_MATRIX_DRAFT.md` APPROVED v1.3 (employer decisions in `control/decisions/DECISION_LOG.md`); `test_phase01_schema.py::test_seeded_grants_equal_the_approved_matrix_document`; golden `tests/golden/permission_decisions.golden.json` (matrix 1.3) |
| 1.9 | Field redaction / never-exposed columns | DONE | `authz.policy.NEVER_EXPOSED`, `api/phase01/serializers.py`; **01.7**: `test_no_get_response_contains_a_never_exposed_field_or_value` (no hash / secret / storage key name or value in any GET response of the contract) |
| 1.10 | Emergency (break-glass) access | OPEN (before production, DEC-054 A) | console recovery of the owner exists (`bootstrap_owner --recover`); a break-glass account is decided for go-live |

## 2. Confidentiality and data

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 2.1 | No secrets in Git / logs / reports (public repository, DEC-046) | DONE | `tools/secret_scan.py --history` -> `findings=0` (`logs/ci/11_security.log`, `logs/ci/secret_scan.json`: 978 text files incl. untracked, 95 commits); pre-commit guard `control/tools/precommit_guard.py`; synthetic test passwords only as `SYN_PW_*` |
| 2.2 | Secrets from environment only | DONE (carried) | `aleekhan/settings.py`; `test_settings_env.py` |
| 2.3 | `.env.example` lists every variable (REV-0014) | DONE | `backend/.env.example` was readable in 01.7 and lists every `ALEEKHAN_*` / `DJANGO_*` variable read by `settings.py`; `test_settings_env.py::test_env_example_lists_every_settings_variable` passes (no skip; `logs/pytest.log`). 01.7 adds no new variable |
| 2.4 | Secrets never stored in plaintext, never logged (passwords, one-time passwords, TOTP secrets, OTP codes, recovery codes, session tokens) | DONE | **01.7**: `test_phase01_step7_privacy.py::test_no_password_otp_recovery_code_or_token_in_any_table_or_log` (full ceremony, then a grep over every row of every `platform_*` table via `row_to_json` and every log record); `test_log_redaction.py`; idempotency replay stores `[REDACTED]` (`test_api_phase01_auth.py`) |
| 2.5 | Sensitive-field deny-list incl. Persian; audit before/after redacted; outbox payloads S1 only | DONE | `engine/redaction.py`, `test_redaction_persian.py`; event catalogue schemas S1 with `additionalProperties: false` (`engine/events.py`, `test_integration_events.py`) |
| 2.6 | HTTPS/TLS, secure cookies, HSTS | PARTIAL (carried) | settings + `docs/ops/DEPLOYMENT_LIMITS.md` section 3; TLS at the proxy needs the staging server (DEC-042, DEC-045 A) |
| 2.7 | Encrypted backups | PARTIAL (carried) | `docs/ops/BACKUP_RESTORE.md` section 3 (design); applied with the staging server |
| 2.8 | Private factory sources never in repo; no execution of legacy files | DONE (carried) | `.gitignore`, pre-commit guard, `tools/verify_handoff.py`; documents are never executed or rendered (attachment download, `nosniff`, sandbox CSP header on downloads) |
| 2.9 | Append-only audit with integrity proof; least-privilege DB roles | DONE | audit hash chain (`engine/audit_chain.py`, `test_phase01_audit_chain.py`), integrity job; `ops/db/roles_check.sh` (`logs/roles_check.log`) |
| 2.10 | Synthetic test data only | DONE | `tests/engine_fixtures.py`, `phase01_factories.py` (label `محیط آزمایشی — داده ساختگی`); drill / rehearsal seed `ops/backup/drill_seed.py` (`synthetic_drill`, random credential never printed) |
| 2.11 | Files at rest encrypted, stored under random keys | DONE | `documents/storage.py` (AES-256-GCM per object, AAD = storage key) |

## 3. Application / API

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 3.1 | SQL injection | DONE | ORM; raw SQL constant or parameterised; ruff `S` rules (`logs/ruff.log`); the one f-string SQL in a test reads table names from `information_schema` (`noqa: S608` with reason) |
| 3.2 | XSS | DONE | React escaping, no `dangerouslySetInnerHTML`; eslint strict (`logs/eslint.log`) |
| 3.3 | CSRF incl. login CSRF and token rotation | DONE | `api/session_auth.py`; `test_api_phase01_auth.py::test_login_context_sets_csrf_cookie_and_login_requires_csrf` |
| 3.4 | Content Security Policy for the UI | OPEN (deployment, carried) | proxy header, `docs/ops/DEPLOYMENT_LIMITS.md` section 3 |
| 3.5 | Unsafe file upload: quarantine, no execution (SEC-03, P0) | DONE | `documents/service.py` (allow-list + magic bytes + OOXML macro check -> QUARANTINED -> ClamAV -> CLEAN / REJECTED; download CLEAN only); `test_phase01_documents_engine.py`; real ClamAV contract test skipped locally (no clamd: `logs/pytest.log` skip reason) |
| 3.6 | Upload size limit before the body is parsed (REV-0124) | DONE (app) / OPEN (proxy) | `api/upload_limit.py` (413 from `Content-Length` before any read); `test_phase01_step7_ops.py::test_oversized_upload_is_refused_from_content_length_before_parsing`; proxy limit to configure: `docs/ops/DEPLOYMENT_LIMITS.md` section 1 |
| 3.7 | Pagination / rate limits / error codes / idempotency / optimistic concurrency | DONE | `docs/api/API_RUNTIME.md`; `test_api_phase01_contract.py` (428 / 412 / 400 on every write), `test_api_phase01_race.py` |
| 3.8 | OpenAPI contract tests | DONE (contract) / PARTIAL (fuzz, carried) | `test_api_phase01_contract.py`, response validation in every HTTP test; contract `0.6.3-draft` (additive) |
| 3.9 | SCA / dependency scan | DONE | `pip-audit` on `backend/requirements.lock`: no known vulnerabilities; `npm audit --omit=dev`: 0 vulnerabilities (`logs/ci/11_security.log`, `logs/ci/pip_audit_runtime.json`). The informational audit of the whole dev venv was **not performed** (network unavailable after retries) - not a gate, stated honestly |
| 3.10 | No new dependency without need | DONE | 01.7 adds no Python or npm dependency (`git diff` of `requirements*.txt`, `package*.json` empty) |
| 3.11 | Signed build artifacts | OPEN (carried) | release pipeline with the staging server |
| 3.12 | SAST | DONE (carried) | ruff `S` + eslint strict-type-checked |
| 3.13 | Containers non-root / image scan | N/A-P01 | no images yet (deployment) |

## 4. Data integrity, reliability, operations

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 4.1 | Atomic write + audit + outbox; producer contract | DONE | `engine/uow.py` (`check_emit`), `test_integration_events.py` |
| 4.2 | Backup + restore drill incl. PHASE_01 tables, migrations 0011-0018, audit chain | DONE (local, synthetic) | `ops/backup/drill.sh` + `drill_seed.py`; `logs/backup_drill.log`, `logs/drill/drill_report.json` (fingerprint identical, sha256 verified, PHASE_01 rows, 0011-0018 recorded, chain verifies) |
| 4.3 | Rollback rehearsal to 0010 on throw-away DBs | DONE | `ops/backup/rollback_rehearsal.sh`, `docs/ops/ROLLBACK.md` section 3a; `logs/rollback_rehearsal.log`, `logs/rollback/rehearsal_report.json` (scenario A down to 0010 + forward, schema diffs empty; scenario B: 0011 reverse refused by design while job runs exist, consistent state); migration round-trip `logs/db_roundtrip.log` |
| 4.4 | Job monitoring and alerting | DONE (library + commands) / OPEN (scheduler) | `ops.monitoring.housekeeping_health`, `manage.py job_status --fail-on warn`, `run_housekeeping`, page 36 block, `GET /admin/health` `jobs.housekeeping`; `test_phase01_step7_ops.py`; no worker / timer installed yet (deployment) |
| 4.5 | Dead letters: replay and owner-only discard (REV-0129) | DONE | `ops/dead_letters.py`, `manage.py outbox_dead_letter`, state DISCARDED (0018); `test_phase01_step7_ops.py` (only `owner_admin`, reason required, audited, aggregate released) |
| 4.6 | Orphan stored bytes cleanup | DONE | `documents.service.purge_orphans` (job `document_orphan_cleanup`, 24 h grace, audited, idempotent); `test_orphan_cleanup_removes_only_old_bytes_without_a_row` |
| 4.7 | Environment isolation, throw-away DB guard | DONE (carried) | `conftest.assert_throwaway_test_db`; drill / rehearsal refuse non-throw-away names |
| 4.8 | RPO / RTO | PARTIAL (carried) | DEC-004 (1 h / 4 h); only a small synthetic drill measured locally |
| 4.9 | Performance evidence (TECHNICAL DEFAULT budgets, not SLA) | DONE (evidence) | `tests/test_perf_phase01.py`; `logs/perf.log`, `logs/perf.json` (machine named); before the 01.7 request cache: `logs/perf_before_request_cache.json`. Residual: a full 1000-row inbox scan still takes about 2 s on this machine (report section 7) |
| 4.10 | Concurrency (multi-user) | DONE | race tests x3 (`logs/concurrency_x3.log`); audit chain contiguous under 8 writers (`logs/perf.json`) |
| 4.11 | Job safe cancel only; no force kill (SEC-02 is PHASE_11) | DONE (carried from 01.3/01.4) | `jobs.service.force_kill` -> `RULE_NOT_APPROVED` (DEC-024) |

## 5. Gate evidence pack (SECURITY_BASELINE 5)

RBAC/ABAC: 1.4-1.9 | secret scan: 2.1 | SCA: 3.9 | upload: 3.5, 3.6 | data flow / sensitive fields: 2.4, 2.5 |
backup / rollback: 4.2, 4.3 | monitoring: 4.4-4.6 | perf: 4.9 | sample redacted logs: `logs/` (redacted, grep for
account / host name = 0).

Known open items (no P0/P1 identified by the implementer; the reviewer decides): 1.10 break-glass, 2.6 TLS at the
proxy, 2.7 encrypted backups, 3.4 CSP, 3.6 proxy body limit, 3.11 artifact signing, 4.4 scheduler, 4.8 RPO/RTO on
staging - all need the staging server or a go-live decision.

## Sign-off (each row is filled only from the signer's own statement; the orchestrator records it)

| Role | Name | Decision (accept / reject / accept with conditions) | Date | Signature |
|---|---|---|---|---|
| Employer (کارفرما) | | | | |
| Security reviewer / auditor | | | | |
| IT (operations) | | | | |
