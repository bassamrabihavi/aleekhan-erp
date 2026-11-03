# REPORT — PHASE_00 / 00.4 Backend/API

```
PROJECT: Aleekhan
PHASE: PHASE_00
STEP: 00.4
COMMIT SHA: bd332cbb85cf6269533c63c33a0e85f8489b90bd
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-03T19:22:22Z
IMPLEMENTER: Claude Code (aleekhan-implementer), verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0
```

## 1. Purpose & acceptance IDs
Step text: permission scoped + rate limit + ETag/version + pagination + request-id + OpenAPI and real test.
Phase-0 only: no business endpoints, no users/roles (PHASE_01, DEC-003). No acceptance case for phase 0.

## 2. Actual changes
- backend/platform_core/api/: base view (throttle BEFORE permission check so 401/403 are rate-limited too), request_id (canonical UUID only, else generated), JSON logging (allow-listed fields only), problems (RFC 9457, unknown → 500 INTERNAL without details), permissions (deny-by-default + scoped base denying all until PHASE_01; out-of-scope → 404), throttling (429 + Retry-After), cursor pagination (max 100), concurrency (ETag/If-Match), idempotent helper, views, urls.
- Endpoints /api/v1: health/live, health/ready (db/migrations/cache), version (api_version, contract_version, build_commit, environment — C-17: public, re-check in 00.7), access-gate/check (401 problem; never ALLOW).
- settings: ALEEKHAN_ENV mandatory (REV-0011), settings_test for pytest/mypy; DEBUG off outside dev; ALLOWED_HOSTS from env; secure cookies/HSTS for staging/prod; no browsable API in prod; staging/prod require real build commit.
- OpenAPI 0.3.0-draft: global security sessionCookie, only 3 probes `security: []` (REV-0001) + test.
- Engine fixes: REV-0008 (cleanup fixture asserts test DB), REV-0009 (scope/reason/resource_id redaction), REV-0010 (immutable approved-rule registry), REV-0012 (deterministic 4xx stored and replayed; transient 401/409/429 and 5xx released).
- docs/api/API_RUNTIME.md (env vars, Redis for staging/prod), CONFLICTS C-17 updated.
- Test value in a redaction test changed from a credential-looking literal to `<synthetic-not-a-secret>` after the pre-commit secret guard flagged it (guard not bypassed).

## 3. Data integrity
No migration (makemigrations --check: no changes). Idempotent replay semantics extended (REV-0012), tested.

## 4. Security evidence
Deny-by-default; throttling covers unauthenticated/denied requests; problem bodies leak no internals; logs allow-list only (password/body excluded, tested); X-Request-ID strict UUID; `check --deploy` prod-like: only W005/W021 (HSTS subdomains/preload, deliberate for internal host). No secrets in logs (grep negative).

## 5. Test evidence (orchestrator re-run, reports/phase-00/step-4/logs/orch_*)
| Command | Outcome | Log |
|---|---|---|
| ruff check . + format --check . | PASS | logs/orch_ruff.log |
| mypy strict | PASS (59 files) | logs/orch_mypy.log |
| pytest PostgreSQL 17.9 / Python 3.12.10 | PASS 293/293 (re-run after guard fix: 293) | logs/orch_pytest.log, logs/orch_pytest_after_guardfix.log |
| OpenAPI contract tests (real responses vs schema) | PASS 18/18 | logs/orch_contract.log |
| unittest tools/tests | PASS (12) | logs/orch_tools.log |
| makemigrations --check | PASS no changes | logs/orch_makemigrations.log |
| real runserver smoke (throwaway DB): live 200, ready 200, version 200, gate 401 problem; valid UUID X-Request-ID echoed, non-UUID replaced; 130 requests → 115×200 + 15×429 | PASS | logs/orch_smoke_curl.log |
| new pins release date (≥14 days) | PASS | logs/orch_pin_dates.log |

## 6. Demo
Technical only: `curl http://127.0.0.1:8000/api/v1/health/ready` on a dev server.

## 7. Issues / decisions
- backend/.env.example not updated with new env names (implementer's permission settings deny reading it); names listed in docs/api/API_RUNTIME.md §4 → 00.7.
- Redis not wired (rate limit per process in dev) → 00.6/00.7.
- Audit of denied/failed attempts in separate transaction → PHASE_01 with auth.
- 401 without WWW-Authenticate until PHASE_01 auth scheme.
- 406 mapped to 400 VALIDATION_FAILED (no dedicated code).

## 8. Rollback
`git revert bd332cbb85cf6269533c63c33a0e85f8489b90bd` (code only).

## 9. Review request
PASS. Check throttle-before-permission order, problem handler non-leakage, REV-0012 semantics, contract tests use real responses, test-only URLconf not routed in prod.

## 10. Next step (proposal)
00.5 UI: smoke page with design tokens, Farsi RTL, 4 viewport screenshots (requires Node.js + Playwright on this machine).
