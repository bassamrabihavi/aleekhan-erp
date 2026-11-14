# API runtime — PHASE_00 / 00.4, PHASE_01 / 01.4, PHASE_02 / 02.4

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
  `PublicEndpoint` is allowed only for the three probes and the two pre-login operations (contract test).
  `ScopedPermission` = view `required_action` + MFA step-up + record scope through the `ACCESS_POLICY`;
  PHASE_00 policy `DenyAllPolicy` denied all, 01.4 installs `RbacPolicy` (section 9).
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
| `ALEEKHAN_RATE_LOGIN_IP` / `_LOGIN_USER` | no | `20/min` / `10/min` | 01.4: `POST /auth/login` per client IP / per attempted username (technical defaults; lockout = DEC-051) |
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

## 9. PHASE_01 implemented (contract 0.6.0-draft, step 01.4)

All 99 PHASE_01 operations are served (`backend/platform_core/api/phase01/`, routes in `phase01/urls.py`); the
`x-aleekhan-status: planned` markers are gone and route parity covers all 88 paths.

- **Authentication**: cookie `aleekhan_session` (random 256-bit token, only its SHA-256 stored; HttpOnly,
  Secure outside dev/test, SameSite=Lax, path `/`), validated per request by `identity.sessions.authenticate`
  (timeouts, network policy, MFA pending, forced password change). A failed authentication is raised by the
  permission check, i.e. after the throttles. No bearer tokens (C-35).
- **CSRF**: `getLoginContext` sets `csrftoken`; `login` and every unsafe method of a session need
  `X-CSRFToken` (Django `CsrfViewMiddleware` logic) -> 403 `ACCESS_DENIED`.
- **Policy**: `ACCESS_POLICY = RbacPolicy` over the APPROVED matrix v1.0 (DEC-049). Action level 403; MFA
  step-up of the permission (DB flag `mfa_step_up`, window 15 min) 401 `MFA_REQUIRED` -> `stepUpMfa`; record
  level 404 (SEC-01) for every `{id}` family, lists filtered with the same rule (`scope_q`, or the per-record
  check of `paginate_filtered` for task / approval inboxes). Session-only operations (`auth`, `me`) use
  `SessionOperation`.
- **Writes**: `Idempotency-Key` checked right after the permission (428/400), If-Match parsed next
  (428/400/412); the row is locked inside the idempotent transaction and the scope is checked BEFORE the
  version (an out-of-scope id never answers 412). Service write + audit + outbox + idempotency record commit
  together. Authentication ceremonies (`login`, `verifyMfa`, `stepUpMfa`, `logout`, `changeMyPassword`, MFA
  enrolment) are exempt (C-27). One-time passwords (`createUser`, `resetUserPassword`) are shown once; the
  idempotency record stores `[REDACTED]` instead (`StoredResponse.secret_free_body`).
- **Rate limits**: `anon` per IP, `principal` per user, plus `login_ip` (20/min) and `login_user` (10/min, key
  = SHA-256 of the normalised username) on `POST /auth/login` - technical defaults; the business rule is the
  DEC-051 lockout. A user has at most 3 live sessions (Q-0101 END_OLDEST_SESSION).
- **Documents (SEC-03)**: multipart upload -> size (413), allow-list + magic + macro check (415), encrypted,
  `WORKING/QUARANTINED` (202); download only CLEAN (409 `FILE_NOT_RELEASED`), always attachment,
  `application/octet-stream`, `nosniff`, sandbox CSP; every download audited. The idempotency hash of an upload
  covers the file digest and metadata, never the bytes.
- **DEC-055**: `POST /workflow/approvals/{approval_id}/bootstrap-approve` (`bootstrapSelfApproveRequest`) - a
  separate operation, so `approveRequest` never accepts maker == checker.
- **Not supported yet (400 `NOT_SUPPORTED`, never silently ignored)**: `RoleAssignmentCreateRequest.valid_from`
  (assignments start now), `OrgUnitCreateRequest.valid_from` / `OrgUnitMoveRequest.effective_from` / tree
  `as_of` other than now (+-5 min, never back-dated), task reassignment to a unit/position, ENUM parameter
  definitions (no allowed-value list in the contract).

## 10. PHASE_01 / 01.5 changes (contract 0.6.1-draft)

- **Policy** runs over the APPROVED matrix **v1.1** (DEC-056, migration `0014`): `owner_admin` reads every approval
  request and holds `platform.workflow.approval.decide`. It is the only TECHNICAL + business-approval pair the
  engine (`policy.counts_for_business_approval`) and the DB guards accept. Maker != checker is unchanged: the
  owner gets 403 `SELF_APPROVAL_FORBIDDEN` on his own requests (DEC-055 bootstrap stays a separate operation).
  Every decision's audit row names the deciding role (`scope.via_role`).
- **CSRF** token rotated after a successful `login` and `verifyMfa` (REV-0123); clients read `csrftoken` before
  every unsafe call.
- `uploadDocumentRevision`: `parent_revision_id` is checked under the document row lock (REV-0120): of two
  concurrent uploads on the same parent exactly one gets 202, the other 409 `STATE_TRANSITION_NOT_ALLOWED`.
- `withdrawRequest` stores its reason (closing note + audit reason, REV-0121); `publishParameterValue` stores the
  optional note as the audit reason (REV-0122).
- `ParameterValueRevision.row_version` (optional, additive): the If-Match of `publishParameterValue`.

## 11. PHASE_01 / 01.6 changes (contract 0.6.2-draft)

- `getHealthDetail` (page 36) returns the optional `integration` object: event delivery lag, `stale` flag,
  aggregates blocked by a dead letter and the events held behind them, open conflicts, compensation records that
  need a human, last acknowledgement (counts only; docs/integration/README.md section 9). Additive.
- Every outbox event follows the event catalogue (docs/integration/EVENT_CATALOGUE.md) and carries provenance
  (`producer`, `build_commit`, `schema_migration`); delivery is ordered per aggregate.
- Policy runs over matrix **v1.2** (DEC-056 extension 2026-11-10, migration `0015`): `owner_admin` also holds
  `platform.document.approve` (approve / reject document revisions: `approveRequest` / `rejectRequest` on a
  `document_revision` request, `approveDocumentRevision` / `rejectDocumentRevision`) and
  `platform.config.parameter.publish` for **BUSINESS_RULE** values (`publishParameterValue`; a TECHNICAL value
  answers 403 `ACCESS_DENIED` for an owner without a BUSINESS publishing role; BUSINESS_RULE values still answer
  409 `RULE_NOT_APPROVED` while their decision is open). Maker != checker unchanged: own request / upload /
  proposal -> 403 `SELF_APPROVAL_FORBIDDEN` (now also for rejecting one's own BUSINESS_RULE proposal).

## 12. PHASE_01 / 01.7 changes (contract 0.6.3-draft)

- `getHealthDetail` (page 36): optional `jobs.housekeeping` (per housekeeping job type: last state, last
  success / failure, `overdue`, `failing`, `max_age_seconds`, error code only) and `jobs.housekeeping_alerts`.
  `integration.blocked_aggregates` counts only aggregates with events waiting behind a dead letter (REV-0130).
  Additive.
- Upload size before parsing (REV-0124): `UploadSizeLimitMiddleware` answers 413 `PAYLOAD_TOO_LARGE`
  (problem+json, with `X-Request-ID`) for a `multipart/form-data` request whose `Content-Length` exceeds
  `document_upload_max_bytes` + 64 KiB, before any byte is read (the CSRF check of the session authentication
  would otherwise parse - and spool - the body first). Proxy limit: docs/ops/DEPLOYMENT_LIMITS.md.
- List endpoints with a per-record check (`paginate_filtered`: task / approval inboxes) read the caller's grants
  and scope facts once per request (`authz.policy.request_cache`; perf evidence
  `reports/phase-01/step-7/logs/perf.json`). Same answers, fewer queries.
- Policy runs over matrix **v1.3** (DEC-056 extension 2, migration `0017`): `owner_admin` also holds
  `platform.document.read` (`listDocuments`, `getDocument`, `listDocumentRevisions`, `getDocumentRevision`; every
  sensitivity) and `platform.document.download` (`downloadDocumentRevision`, CLEAN only -> otherwise 409
  `FILE_NOT_RELEASED`; every download audited). Not business-approval permissions.
- Outbox delivery state `DISCARDED` (migration `0018`, REV-0129) - console only (`manage.py outbox_dead_letter`),
  not exposed by any operation.

## 13. PHASE_02 planned operations (contract 0.7.0-draft, step 02.1)

- 63 operations on 48 paths under `/identity/...` (customers, brands, product classes, products, styles and
  revisions, product codes, code rule revisions, serials, external references, historical order records) and
  `/commercial/...` (customer orders, lines, versions, change requests). All `x-aleekhan-status: planned`,
  `x-aleekhan-step: '02.4'`; none is routed (route parity covers implemented paths only).
- Permissions `identity.*` / `commercial.*` are proposals; no role holds them before DEC-057, so the deny-by-default
  policy answers 403 once 02.4 routes them.
- Blocked (409 `RULE_NOT_APPROVED` + `decision_id`): code preview/issue and code rule revisions (DEC-005), serial
  allocation and order confirmation (DEC-006), change requests (DEC-059), approvals (DEC-057).
- `validateProductCode` and `previewProductCode` are side-effect free POSTs without Idempotency-Key
  (`x-aleekhan-conventions.side_effect_free_operations`); the 14-digit code stays out of URLs and access logs.
- Planned error codes (join `ErrorCode` in 02.3): `SERIAL_ALREADY_ALLOCATED`, `PRODUCT_CODE_TAKEN`,
  `POSSIBLE_DUPLICATE`, `ORDER_VERSION_STALE` (all 409).
- `/version` reports `contract_version` 0.7.0-draft; runtime behaviour of the implemented operations is unchanged.
- Superseded by section 14 (02.4): every operation is implemented; the blocked markers and the four planned
  error codes are gone.

## 14. PHASE_02 implemented (contract 0.8.0-draft, step 02.4)

All 66 PHASE_02 operations are served (`backend/platform_core/api/phase02/`, routes in `phase02/urls.py`) on top
of the 02.3 use cases; route parity covers all 139 paths and no path is planned any more. Contract tests:
`test_api_phase02_contract.py` (body specs == request schemas, routed permission == `x-aleekhan-permission`,
seeded matrix == operations + MFA flags, refusal reasons == engine catalogue, real-session 428 / 412 / 400 on
every write, employee 403 on every operation, management_viewer 403 on every write) and
`test_api_phase02_flows.py` (happy path of every operation with response-schema validation, role matrix, MFA,
412, replay, pagination, rate limit, ID-01..ID-04, concurrent confirms and style creations through API clients).

- **Authentication / permission**: session cookie + CSRF as section 9. `ScopedPermission` checks the action of
  matrix v2.1 (DEC-057 + amendments; 403), then the MFA step-up of the permission (401 `MFA_REQUIRED`):
  `identity.product_code.issue`, `identity.code_rule.approve` (approve / reject / activate),
  `commercial.order.confirm`, `commercial.change.decide`, `commercial.change.planning_approve`. The use cases
  check permission, MFA, version and state again inside their unit of work.
- **Record scope**: PHASE_02 records carry no org unit (DEC-057 answer 3: all customers). A record is visible
  only through a GLOBAL-scope assignment of the action: an object otherwise answers 404 and a list is empty.
  Request-level rules answer 404 as well (only the requester submits / withdraws a change request; a line or
  revision id under another order / style).
- **Writes**: `Idempotency-Key` on every mutation except `validateProductCode` / `previewProductCode` (pure,
  `side_effect_free_operations`); `If-Match` = the resource's `row_version` on PATCH and actions; line operations
  send the ORDER's `If-Match` (the order row version covers its lines); `createChangeRequest` sends the order
  version it saw in the body (`order_row_version`). `issueProductCode` uses the HTTP Idempotency-Key as the
  engine's issue key. Deterministic refusals are stored and replayed (section 2).
- **Errors**: stable top-level codes (`VALIDATION_FAILED` 400, `SELF_APPROVAL_FORBIDDEN` 403,
  `STATE_TRANSITION_NOT_ALLOWED` 409, `RULE_NOT_APPROVED` 409 with `decision_id` DEC-005, `VERSION_CONFLICT` 412,
  `IDEMPOTENCY_KEY_REUSED` 422, ...); the precise reason is `errors[0].code`
  (`x-aleekhan-conventions.phase02_refusal_reasons`, 55 reasons, golden `phase02_refusals.golden.json`).
- **Numbers** (DEC-058 amendment 2026-11-14): `CU-` / `SO-` / `CR-` + Jalali year of creation (Asia/Tehran) +
  `-` + at least 6 digits (`TechnicalNumber`), restarting every Jalali year; serials `^[1-9][0-9]*$` from 63001
  (`SerialNumber`, DEC-006); 14-digit codes and segments are text (`Code14`, 2/4-digit patterns).
- **Representative name** (DEC-058, PII): only `getCustomerOrder` returns it, from the engine's `get_order`
  (value for callers who may see it, every such read audited as `commercial.order.representative_read`;
  `[REDACTED]` for management_viewer). Lists never carry it; write responses show `[REDACTED]` when one is
  recorded, so the value never enters an idempotency record, a replay or an access log (logs carry the path
  without query string and never bodies, section 3).
- **Added operations** (additive): `updateCustomerBrand` (PATCH `/identity/customers/{customer_id}/brands/{brand_id}`,
  status + reason), `addCodeRuleGoldenCases` (POST `/identity/code-rule-revisions/{id}/golden-cases`, max 2000 per
  call, counts-only response), `decidePlanningChangeRequest` (POST `/commercial/change-requests/{id}/planning-decision`,
  `{decision: APPROVE | REJECT, note}`; DEC-059 amendments 2026-11-12 / 2026-11-14; one permission
  `commercial.change.planning_approve` for both outcomes; a rejection needs a note and closes the request REJECTED).
- **Decided refusals kept** (conservative, documented in the contract): `allocateSerial` always 409
  `SERIAL_ALLOCATED_AT_CONFIRM` (DEC-006 L-A); a confirmed order is cancelled only by a `CANCEL_ORDER` change
  request; held orders accept only resume or cancel (DEC-059 amendment 2026-11-14); product / style numbers are
  never typed in (computed by the DEC-005 rule); product types and categories are read-only (server import).
- **Search** (`q`): normalised contains (`ي`/`ی`, `ك`/`ک`, half-space -> space, lower case) on both sides; never a
  merge. `findSimilarStyles` ranks deterministically (1.0 same product + similar name, 0.5 similar name).
- **Rate limits / pagination / request id**: unchanged (section 2): `principal` bucket per user, cursor pages of
  1..100, `X-Request-ID` echoed (canonical UUID) and in every problem body.
