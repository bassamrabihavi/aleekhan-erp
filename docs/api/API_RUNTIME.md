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

There are no business endpoints and no users/roles in PHASE_00 (PHASE_01; DEC-003: users only created
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
| `ALEEKHAN_NUM_PROXIES` | no | `0` | trusted reverse proxies for `X-Forwarded-For`; `0` = use `REMOTE_ADDR` only (XFF ignored) |
| `ALEEKHAN_REDIS_URL` | recommended staging/prod | unset → local memory | shared rate-limit counters (see §5) |
| `ALEEKHAN_TRUST_PROXY_TLS_HEADER` | no | `0` | trust `X-Forwarded-Proto: https` from the proxy |
| `ALEEKHAN_SSL_REDIRECT` | no | `1` in staging/prod | `/api/v1/health/*` exempt (internal probes) |
| `ALEEKHAN_HSTS_SECONDS` | no | `31536000` in prod, `0` otherwise | prod refuses < 86400 |
| `ALEEKHAN_HSTS_INCLUDE_SUBDOMAINS` | no | `0` | |
| `ALEEKHAN_MAX_BODY_BYTES` | no | `1048576` | |

`backend/.env.example` should list these names with placeholders (not updated in 00.4: the file is outside
this step's readable scope — orchestrator follow-up).

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
