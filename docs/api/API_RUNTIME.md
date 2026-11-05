# API runtime — PHASE_00 / 00.4

Contract: [openapi-draft.yaml](openapi-draft.yaml) (contract-first, hand-written; the backend is tested
against it). Code: `backend/platform_core/api/`. Error codes: [../engine/ERROR_CODES.md](../engine/ERROR_CODES.md).

## 1. Endpoints (all under `/api/v1`)

| Operation | Path | Auth | Notes |
|---|---|---|---|
| `getLiveness` | `GET /health/live` | public | `{"status":"ok"}`, touches no dependency, `Cache-Control: no-store` |
| `getReadiness` | `GET /health/ready` | public | database (`SELECT 1`), migrations (no pending plan), cache (set/get). 200 `ready` / 503 `not_ready` + `Retry-After: 5`. Component names and up/down/unknown only — never hostnames, DSNs, versions or error text |
| `getVersion` | `GET /version` | public | see §6 (C-17) |
| `checkAccess` | `GET /access-gate/check` | `sessionCookie` (PHASE_01) | no principal → 401 `AUTHENTICATION_REQUIRED`. PHASE_00 has no authentication backend, so production always answers 401. With a principal (test harness only): parameters validated (400), decision always `DENY` / `POLICY_NOT_DEFINED`. No code path returns `ALLOW` |

| `listIntegrationFreshness` | `GET /integration/freshness` | `sessionCookie` + `platform.integration.freshness.read` | 00.6, per-source fresh/stale/never, cursor by `source_code`, ETag; [../integration/README.md](../integration/README.md) §5 |
| `listIntegrationConflicts` | `GET /integration/conflicts` | `sessionCookie` + `platform.integration.conflict.read` | 00.6, conflict queue, `status`/`source_code` filters, cursor |
| `getIntegrationConflict` | `GET /integration/conflicts/{conflict_id}` | `sessionCookie` + `platform.integration.conflict.read` | 00.6, ETag = row version, out of scope → 404 |
| `resolveIntegrationConflict` | `POST /integration/conflicts/{conflict_id}/resolve` | `sessionCookie` + `platform.integration.conflict.resolve` | 00.6, `If-Match` + `Idempotency-Key`; records the human decision only (no business write) |

The integration endpoints answer 401 in PHASE_00 production (no authentication backend); their behaviour is
tested through the test-only harness. There are no business endpoints and no users/roles in PHASE_00 (PHASE_01; DEC-003: users only created
inside the system by the owner/admin, never AD/LDAP/SSO).

## 2. Cross-cutting behaviour

- **Request id**: `X-Request-ID` is accepted only as a canonical UUID (36 chars, 8-4-4-4-12 hex, normalised to
  lower case); anything else is replaced by a new UUID4 (never echoed verbatim). Every response carries it;
  every problem body has `request_id`; it is copied into audit/outbox rows (`RequestContext.request_id`).
- **Errors**: every error is `application/problem+json` (RFC 9457 + `code`, `message_fa`, `request_id`),
  including Django-level failures (unknown URL 404, bad `Host` 400, middleware 500). Unknown exceptions and
  `EngineContractError` → 500 `INTERNAL_ERROR` with a generic body. DRF validation errors list field paths and
  machine codes only (submitted values are never echoed).
- **Permissions** (`api/permissions.py`): DRF default is `DenyByDefault` (401 without principal, 403 with).
  `PublicEndpoint` is allowed only for the three probes (contract test). `ScopedPermission` = view
  `required_action` + record scope through the `ACCESS_POLICY`; PHASE_00 policy `DenyAllPolicy` denies all.
  A record outside the caller's scope is **404 `NOT_FOUND`**, indistinguishable from a missing record. There is
  no setting/env toggle that changes the policy; PHASE_01 replaces it in a reviewed commit.
- **Rate limits** (`api/throttling.py`): per client IP for anonymous callers (`anon`), per principal for
  authenticated callers (`principal`, active from PHASE_01), separate per-IP bucket for probes (`health`).
  Exceeded → 429 `RATE_LIMITED` with `Retry-After` (seconds, ≥ 1). All views derive from
  `api/base.AleekhanAPIView`, which **throttles before checking permissions** (DRF's default order would let
  rejected 401/403 requests through unthrottled).
- **Pagination** (`api/pagination.py`): cursor based, `page_size` 1..100 (default 25; out of range → 400,
  no silent clamping), opaque `cursor` ≤ 512 chars (malformed/tampered → 400). Body
  `{"items": [...], "page": {"page_size", "next_cursor"}}`. Views must order by a unique, stable key.
- **ETag / If-Match** (`api/concurrency.py` on `engine/concurrency.py`): `ETag: "<row_version>"`; updates need
  `If-Match` (missing 428, malformed 400, weak/stale 412) and `update_versioned` on a scoped queryset.
- **Idempotency** (`api/idempotent.py` on `engine/idempotency.py`): mutating requests need a UUID
  `Idempotency-Key` (missing 428, malformed 400). Same key + same request → stored response replayed with
  `Idempotent-Replayed: true`. Deterministic 4xx outcomes are stored and replayed too (REV-0012; see
  `docs/engine/README.md` §2). A replayed problem keeps the original `request_id` in its body; the
  `X-Request-ID` header is the current request's id. `ATOMIC_REQUESTS` is off on purpose.
- **Body size**: `ALEEKHAN_MAX_BODY_BYTES` (default 1 MiB) → 413 `PAYLOAD_TOO_LARGE`.
- **Renderers/parsers**: JSON only in every environment (no browsable API, no HTML).

These utilities are proven over HTTP against a **test-only** URLconf
(`backend/platform_core/tests/api_harness.py`, mounted with `pytest.mark.urls`); the production URLconf
(`aleekhan/urls.py`) does not include it, which a contract test asserts.

## 3. Logging

JSON lines on stdout (`api/logging.py`): `ts` (UTC), `level`, `logger`, `msg`, `request_id`, and only the
allowlisted keys `event, method, path, status, duration_ms, error_code, exc_type, component`. One access-log
line per request (`aleekhan.access`; path **without** query string). For exceptions only the type and the
stack frames (`file:line:function`) are logged — never the exception message, locals, SQL parameters,
bodies, headers or query strings. Rule for all code: no secrets or personal data in log messages.

## 4. Environment variables (names only; no values in Git)

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `ALEEKHAN_ENV` | **always** (REV-0011) | — | `dev`, `test`, `staging`, `prod`. Missing/empty → refuse to start. Tests use `aleekhan.settings_test`, which pins `test` explicitly and refuses any other value |
| `DJANGO_SECRET_KEY` | staging/prod | ephemeral in dev/test | |
| `DJANGO_ALLOWED_HOSTS` | staging/prod | `127.0.0.1,localhost` in dev/test | comma separated; `*` refused in staging/prod |
| `ALEEKHAN_BUILD_COMMIT` | staging/prod | `0000000` (= unknown build, dev/test only) | hex git sha, 7–40 chars; shown truncated to 12 |
| `DJANGO_DEBUG` | no | `0` | honoured only in dev/test |
| `ALEEKHAN_RATE_ANON` / `_PRINCIPAL` / `_HEALTH` | no | `60/min` / `600/min` / `120/min` | `<n>/<s\|m\|h\|d>` |
| `ALEEKHAN_NUM_PROXIES` | staging/prod behind the proxy: `1` | `0` | trusted reverse proxies for `X-Forwarded-For`; `0` = use `REMOTE_ADDR` only (XFF ignored). REV-0015 (00.7): staging/prod refuse to start with `ALEEKHAN_TRUST_PROXY_TLS_HEADER=1` and `NUM_PROXIES=0` (all clients would share the proxy's rate-limit bucket) |
| `ALEEKHAN_REDIS_URL` | recommended staging/prod | unset → local memory | shared rate-limit counters (see §5) |
| `ALEEKHAN_TRUST_PROXY_TLS_HEADER` | no | `0` | trust `X-Forwarded-Proto: https` from the proxy |
| `ALEEKHAN_SSL_REDIRECT` | no | `1` in staging/prod | `/api/v1/health/*` exempt (internal probes) |
| `ALEEKHAN_HSTS_SECONDS` | no | `31536000` in prod, `0` otherwise | prod refuses < 86400 |
| `ALEEKHAN_HSTS_INCLUDE_SUBDOMAINS` | no | `0` | |
| `ALEEKHAN_MAX_BODY_BYTES` | no | `1048576` | |

`backend/.env.example` lists these names with placeholders (empty = built-in default). REV-0014 was closed at
Gate-0 (2026-11-04) after the employer narrowed the agent read-deny rule to real `.env` files;
`test_settings_env.py::test_env_example_lists_every_settings_variable` now runs and fails if `settings.py` reads
an `ALEEKHAN_*`/`DJANGO_*` name the example does not declare.

`/health/ready` caches the migrations check per process for 10 s (REV-0016, `views.MIGRATIONS_CHECK_TTL_SECONDS`,
TECHNICAL DEFAULT): building the migration executor loads the migration graph from disk. Failures are never
cached. Database and cache checks still run on every call.

## 5. Cache backend

- dev/test: `LocMemCache` (per process). Limits are therefore per worker process.
- staging/prod: set `ALEEKHAN_REDIS_URL` → `django.core.cache.backends.redis.RedisCache`, so all workers share
  one counter per client/principal. The `redis` client library is pinned together with the deployment work
  (00.6/00.7); until then staging/prod without Redis fall back to per-process limits (documented risk).

## 6. `/version` exposure (C-17, decided in 00.4, re-checked in the 00.7 threat model)

Public, because reports and screenshots must be tied to a commit (HOW_REVIEW_WORKS). It returns exactly the
contract fields `api_version` (`v1`), `contract_version` (OpenAPI `info.version`), `build_commit` (short sha
from `ALEEKHAN_BUILD_COMMIT`) and `environment` (`dev|test|staging|production`). No Python/Django/PostgreSQL/OS
versions, hostnames, paths or dependency lists. If the 00.7 threat model decides otherwise, the operation
gets `security: [{sessionCookie: []}]` and leaves `PUBLIC_OPERATIONS` (contract test enforces both together).

## 7. Security settings

DEBUG is forced off in staging/prod; `ALLOWED_HOSTS` from env (required, no wildcard); secure + HttpOnly +
SameSite=Lax session cookie (`aleekhan_session`), secure CSRF cookie, HSTS (prod), SSL redirect, `nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, COOP `same-origin`, CSRF middleware (failure →
403 problem). `manage.py check --deploy` with prod settings leaves only W005 (HSTS include-subdomains) and W021
(HSTS preload), both deliberate for an internal host. Full hardening and scans: 00.7.

## 8. PHASE_01 planned operations (contract 0.5.0-draft, step 01.1)

01.2 update: contract `0.5.1-draft` - the employer APPROVED DEC-032 and DEC-048..054; the 18 formerly blocked
planned operations now carry `x-aleekhan-decided-by` instead of `x-aleekhan-blocked-by` (test
`test_blocked_operations_name_an_open_decision_and_declare_409`); REV-0101 `rejectDocumentRevision` declares the MFA
step-up of `platform.document.approve` (test `test_operations_sharing_a_permission_share_the_mfa_step_up`); enums
aligned with the 01.2 schema (account_kind, position assignment kind, parameter classification). Implemented
paths are unchanged.

`openapi-draft.yaml` 0.5.0-draft adds 97 PLANNED operations on 78 paths (auth, me, admin-identity, org, workflow,
audit, jobs, documents, parameters). They are marked `x-aleekhan-status: planned` + `x-aleekhan-step: '01.4'`
and are **not served**: `test_route_parity_with_openapi` compares the production URLconf with the implemented
paths only and asserts that no planned path is routed; `test_api_contract_planned.py` pins the rules for planned
operations (session security, `x-aleekhan-permission`, Idempotency-Key except the six authentication ceremonies
of `idempotency_exempt`, If-Match on PATCH, 409 on blocked operations, unique operation ids). The only planned
public operations are `getLoginContext` and `login` (CONFLICTS C-26). `CONTRACT_VERSION` in
`platform_core/api/views.py` is `0.5.0-draft`, so `/version` reports the document version; the behaviour of the
eight implemented endpoints is unchanged. New error codes needed later are listed in
`x-aleekhan-conventions.planned_error_codes` and are not part of `ErrorCode` until the engine implements them.
