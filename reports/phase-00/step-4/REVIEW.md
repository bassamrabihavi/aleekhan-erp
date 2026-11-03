VERDICT: PASS
PHASE/STEP: PHASE_00 / 00.4 Backend/API   COMMIT: bd332cbb85cf6269533c63c33a0e85f8489b90bd
REVIEWER: aleekhan-reviewer (independent, read-only), machine work-windows, 2026-11-03
NOTE: This verdict is advisory until DEC-036 is APPROVED. The employer must confirm the step.

## Verification re-run by the reviewer (not copied from the report)
| Command | Result |
|---|---|
| `cd backend && pytest -q` (settings_test, PostgreSQL 17.9 @127.0.0.1:5433, Python 3.12.10) | 293 passed in 14.77s |
| `ruff check .` + `ruff format --check .` (repo root) | All checks passed / 93 files already formatted |
| `cd backend && mypy .` | Success: no issues found in 59 source files |
| `python -m unittest discover -s tools/tests` | Ran 12, OK |
| `manage.py makemigrations --check --dry-run` | No changes detected (the step has no migration, so up/down is n/a) |
| `env -u ALEEKHAN_ENV manage.py check` | ImproperlyConfigured "ALEEKHAN_ENV must be set explicitly" (REV-0011 closed) |
| `ALEEKHAN_ENV=prod ... manage.py check --deploy` (generated key, not logged) | Only W005/W021 (deliberate, settings.py:193-196) |
| Ad-hoc probe of the production URLconf with Django test client (dev settings) | `/access-gate/check` with `X-Test-Principal` gives 401 AUTHENTICATION_REQUIRED, so the harness auth does not leak. `/_test/...` gives 404. A CRLF-injected `X-Request-ID` is replaced by a fresh UUID. Bad JSON on a probe POST gives 405 problem. `Accept: text/html` gives 400 problem+json. |
| `git grep` of the commit for the local DB password | 0 hits. The only "password=" strings are synthetic test literals (test_api_platform.py:56,268; api_harness.py:175). |
| Pin dates, `pip show` | openapi-schema-validator 0.9.0, jsonschema 4.26.0, rfc3339-validator 0.1.4 match requirements-dev.txt:16-19 |

## CHECKS
- R01 Scope ✔. The step adds only the four draft endpoints (api/urls.py:11-16), which match openapi-draft paths (test_route_parity_with_openapi). There is no business endpoint, no auth backend (settings.py REST_FRAMEWORK DEFAULT_AUTHENTICATION_CLASSES=[]) and no users/roles (DEC-003 respected). The engine edits are the carry-over REV-0008..0012 items only.
- R02 Source of truth ✔. No business rule was invented. DenyAllPolicy (permissions.py:702-717) denies everything until the PHASE_01 matrix exists. APPROVED_RULE_DECISIONS is empty and read-only (rules.py:26-27). C-17 is recorded as a technical decision, to be re-checked in 00.7 (CONFLICTS.md C-17).
- R03 Database ✔ (n/a for schema). There is no migration, and makemigrations --check is clean. ATOMIC_REQUESTS=False is justified for the idempotency claim (settings.py:144).
- R04 Transaction/ledger ✔. The REV-0012 path stores the problem only after the business UoW has rolled back (idempotency.py run_idempotent except-block). Covered by test_run_idempotent_client_error_is_stored_and_replayed, test_run_idempotent_transient_client_error_is_retryable, test_replayable_classification_covers_every_client_error, test_out_of_scope_update_is_404_and_writes_nothing, and the concurrent same-key tests. All pass.
- R05 Engine ✔. REV-0010 immutable registry (rules.py:26-27). REV-0009 scope redaction (uow.py:69). There are no golden-rule changes (no rule approved in phase 0).
- R06 API ✔. The OAS 3.1 document validates. Top-level `security: sessionCookie`, and only the 3 probes have `security: []` (test_every_non_public_operation_declares_security; REV-0001 closed). Responses are validated against the schema from real Django test-client calls (test_contract_*, including 401/400/405/429/503). Idempotency-Key and If-Match are wired (test_update_with_if_match_and_idempotency_key_then_replay, test_if_match_preconditions). Per-action and per-record scope: test_scoped_list_only_shows_records_in_scope, test_out_of_scope_record_is_404_not_403. Throttle runs before permission (base.py:350-358): test_rate_limit_per_ip... gives gate=[401,401,401,429], and test_production_views_use_allowlisted_permissions... asserts every view subclasses AleekhanAPIView.
- R07 UI n/a. No UI in 00.4.
- R08 Security ✔. Deny by default (permissions.py:732-735). The test-only header auth exists only in tests/api_harness.py; my probe of the production URLconf gives 401. The test test_no_test_harness_in_production_urlconf also covers this. Problems leak nothing: unknown errors give 500 INTERNAL_ERROR (problems.py to_aleekhan_error). test_unexpected_errors_are_generic_500 and test_readiness_down_reports_503_without_details pass. Logs keep only allow-listed extras and drop exception messages (logging.py:482-529; test_json_log_*). X-Request-ID must be a strict canonical UUID (request_id.py:986-990). DEBUG is impossible in staging/prod, and deploys require secret, hosts and build sha (settings.py:71-102; test_settings_env.py). No secrets or PII in the repo or logs (git grep above). The orchestrator smoke log has no personal paths.
- R09 Module ownership ✔. Code is only in platform_core/api plus the platform_core engine and tests. No other module's tables are touched.
- R10 Integration n/a. No integration in 00.4 (00.6).
- R11 Performance/operations ✔ (phase-0 level). The readiness probe checks DB, migrations and cache and returns 503 + Retry-After. Throttles are per IP and per principal, with a separate probe bucket. See REV-0015/0016 for the 00.7 follow-ups.
- R12 Tests/evidence ✔. I reproduced everything locally (table above). The step logs exist under reports/phase-00/step-4/logs/. The E2E evidence is a real runserver smoke on a throwaway DB (orch_smoke_curl.log: 115×200 + 15×429). No mock is presented as real.
- R13 Docs ✔ (one gap). docs/api/API_RUNTIME.md (env vars, proxy, Redis, idempotency replay rule), docs/engine/README.md §2 (REV-0012 decision, "client sends a new key" at lines 59-61), openapi 0.3.0-draft, CONFLICTS C-17. Gap: backend/.env.example was not updated (REV-0014). The reviewer is also denied read access to that file, so it is not evidenced either way.
- R14 Owner acceptance n/a. Left to the employer at Gate time.

## ISSUES (no P0/P1/P2)
- REV-0013 [P3] backend/platform_core/api/permissions.py:56 and problems.py:108 — Problem: a 401 AUTHENTICATION_REQUIRED has no `WWW-Authenticate` header (RFC 9110 §15.5.2 requires one on 401). Repro: `curl -i /api/v1/access-gate/check?action=a.b` returns 401 with no WWW-Authenticate. Expected fix: in PHASE_01, when the session scheme exists, emit a WWW-Authenticate value (e.g. `Session realm="aleekhan"`) or use 403 per DRF convention, and document it in openapi. Regression test: a contract test asserting the header on every 401.
- REV-0014 [P3] backend/.env.example — Problem: it was not updated for the new variables (ALEEKHAN_ENV is now mandatory with no default; ALEEKHAN_BUILD_COMMIT, DJANGO_ALLOWED_HOSTS, ALEEKHAN_RATE_*, ALEEKHAN_NUM_PROXIES, ALEEKHAN_TRUST_PROXY_TLS_HEADER, ALEEKHAN_SSL_REDIRECT, ALEEKHAN_HSTS_*, ALEEKHAN_MAX_BODY_BYTES, ALEEKHAN_REDIS_URL). A fresh `manage.py runserver` from .env.example now fails at import. Expected fix (00.7, or earlier by the orchestrator, who has access): add the placeholders and keep them in sync with API_RUNTIME.md §4. Regression test: a test asserting that every `os.environ.get("ALEEKHAN_…")` name in settings.py appears in .env.example.
- REV-0015 [P3] backend/aleekhan/settings.py:240 — Problem: ALEEKHAN_NUM_PROXIES defaults to 0. Behind the DEC-042 reverse proxy, every client then shares the proxy's IP bucket (anon 60/min), so one noisy client throttles everyone. The setting also allows the inconsistent combination ALEEKHAN_TRUST_PROXY_TLS_HEADER=1 with NUM_PROXIES=0. Expected fix (00.7 deploy): set NUM_PROXIES=1 in the staging/prod config and fail fast in DEPLOYED when TRUST_PROXY_TLS_HEADER=1 and NUM_PROXIES=0. Regression test: a settings test for that combination, plus a throttling test with XFF and NUM_PROXIES=1.
- REV-0016 [P3] backend/platform_core/api/views.py:55-56 — Problem: the public /health/ready builds a MigrationExecutor (loading the migration graph from disk) on every call. That is relatively expensive for an unauthenticated endpoint; it is only bounded by 120/min per IP. Expected fix (00.7 perf): cache the migrations result for a few seconds, or restrict /health/ready to the private network at the proxy. Regression test: a perf check, or a unit test that a second call within the TTL does not instantiate the executor.

## Notes (no action needed for 00.4)
- REV-0012 semantics: after a final 4xx (403/404/409 RULE_NOT_APPROVED/412), the same Idempotency-Key replays the stored error even when the cause is fixed. The If-Match header is not part of the request hash. This is documented (docs/engine/README.md:59-61). The 00.5/PHASE_01 UI client must generate a new key after any 4xx.
- 406 is mapped to 400 VALIDATION_FAILED, and the anonymous throttle counter is per process until Redis is wired. Both are acknowledged in REPORT §7.

## EMPLOYER ATTENTION
- گام 00.4 فنی است و از نظر ممیز PASS است (مشورتی، تا وقتی DEC-036 تصویب نشده). تأیید شما لازم است.
- تصمیم فنی C-17: آدرس `/version` عمومی می‌ماند و فقط نسخه API، کد کوتاه commit و نام محیط را نشان می‌دهد. اگر با عمومی‌بودن آن مخالفید، در گام 00.7 اعلام کنید.
- در این گام آزمون کاربری (UAT) لازم نیست. هنوز کاربر و ورود به سامانه وجود ندارد (فاز ۰۱).
