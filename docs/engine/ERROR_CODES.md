# Error codes — PHASE_00 / 00.3

Status: DRAFT (part of the Gate-0 contract). Source of truth in code: `backend/platform_core/engine/errors.py`.
Contract: `docs/api/openapi-draft.yaml` (`components.schemas.ErrorCode`, `components.schemas.Problem`,
`x-aleekhan-conventions.error_codes`).

## Rules

1. **Codes and HTTP statuses are stable.** Clients branch on `code` only. Persian text (`message_fa`) and
   `title`/`detail` may change.
2. Every error response is `application/problem+json` (RFC 9457) with: `type`
   (`https://errors.aleekhan.invalid/<CODE>`), `title`, `status`, `code`, `message_fa`, `request_id`, optional
   `detail`, `decision_id` (only with `RULE_NOT_APPROVED`) and `errors[]` (`field`, `code`, optional
   `message_fa`; at most 100 items).
3. No stack traces, SQL, hostnames, secrets or personal data in any field. Engine `detail` texts are
   generic. Publisher/driver exception text is never stored or returned.
4. A record outside the caller's scope is reported as `NOT_FOUND` (404), not `ACCESS_DENIED` — this prevents
   enumeration (BOLA/IDOR, SEC-01).
5. Adding, removing or renumbering a code is a breaking contract change: update `errors.py`,
   `openapi-draft.yaml`, this file and `backend/platform_core/tests/golden/error_codes.golden.json` in one
   reviewed commit. Tests enforce that the four agree:
   `test_error_catalogue_golden`, `test_catalogue_matches_openapi_enum_and_status_mapping`,
   `test_to_problem_matches_openapi_problem_schema`.

## Catalogue

| Code | HTTP | Exception class | When | `message_fa` |
|---|---|---|---|---|
| `VALIDATION_FAILED` | 400 | `ValidationFailed` | Input invalid (field details in `errors[]`); malformed `If-Match` / `Idempotency-Key` | مقدار ورودی معتبر نیست. |
| `AUTHENTICATION_REQUIRED` | 401 | `AuthenticationRequired` | No authenticated principal (any mutating request without a user) | برای این کار باید وارد سامانه شوید. |
| `MFA_REQUIRED` | 401 | `MfaRequired` | Step-up MFA needed (PHASE_01, DEC-003/DEC-042) | برای این کار تأیید هویت دومرحله‌ای لازم است. |
| `ACCESS_DENIED` | 403 | `AccessDenied` | Authenticated but the role/action is not allowed | شما مجوز انجام این کار را ندارید. |
| `NOT_FOUND` | 404 | `NotFound` | Missing record, or record outside the caller's scope | مورد درخواستی پیدا نشد. |
| `METHOD_NOT_ALLOWED` | 405 | `MethodNotAllowed` | HTTP method not supported on the route | این نوع درخواست برای این مسیر مجاز نیست. |
| `PRECONDITION_REQUIRED` | 428 | `PreconditionRequired` | Update without `If-Match` | نسخه رکورد (If-Match) ارسال نشده است؛ ابتدا رکورد را دوباره بارگذاری کنید. |
| `VERSION_CONFLICT` | 412 | `VersionConflict` | `If-Match` is stale or weak (optimistic concurrency) | این رکورد در این فاصله توسط کاربر دیگری تغییر کرده است؛ آن را دوباره بارگذاری کنید. |
| `IDEMPOTENCY_KEY_REQUIRED` | 428 | `IdempotencyKeyRequired` | Mutating request without `Idempotency-Key` | کلید یکتای درخواست (Idempotency-Key) ارسال نشده است. |
| `IDEMPOTENCY_KEY_REUSED` | 422 | `IdempotencyKeyReused` | Same key, different request (method, endpoint or body) before expiry | این کلید یکتا قبلاً برای درخواست دیگری به کار رفته است. |
| `IDEMPOTENCY_IN_PROGRESS` | 409 | `IdempotencyInProgress` | Same key + same request while the first one is still running; also a holder whose lease was taken over | همین درخواست هنوز در حال پردازش است؛ کمی بعد دوباره تلاش کنید. |
| `RULE_NOT_APPROVED` | 409 | `RuleNotApproved` | The action depends on a business rule whose decision (`decision_id`, `DEC-###`) is not approved | قاعده کسب‌وکاری این کار هنوز تصویب نشده است و سامانه آن را انجام نمی‌دهد. |
| `STATE_TRANSITION_NOT_ALLOWED` | 409 | `StateTransitionNotAllowed` | Transition not listed in the state machine | این تغییر وضعیت از وضعیت فعلی مجاز نیست. |
| `RATE_LIMITED` | 429 | `RateLimited` | Too many requests (with `Retry-After`, step 00.4) | تعداد درخواست‌ها زیاد است؛ کمی بعد تلاش کنید. |
| `PAYLOAD_TOO_LARGE` | 413 | `PayloadTooLarge` | Body above the size limit | حجم داده ارسالی بیش از حد مجاز است. |
| `DEPENDENCY_UNAVAILABLE` | 503 | `DependencyUnavailable` | A required dependency (DB, cache, broker) is down | یکی از سرویس‌های لازم در دسترس نیست؛ کمی بعد تلاش کنید. |
| `INTERNAL_ERROR` | 500 | `InternalError` | Anything unexpected (including `EngineContractError`, which is a programming error, not a client error) | خطای داخلی رخ داد؛ موضوع ثبت شد. |

`IDEMPOTENCY_IN_PROGRESS` is new in 00.3 (OpenAPI draft bumped to `0.2.0-draft`). The brief's working names
`CONFLICT_VERSION` and `PERMISSION_DENIED` correspond to the already-published OpenAPI codes
`VERSION_CONFLICT` and `ACCESS_DENIED`; the published names were kept to avoid breaking the 00.1 contract.

## Exception hierarchy

```
AleekhanError (code, http_status, message_fa, detail, errors, decision_id, to_problem(request_id))
├── ClientError (4xx)
│   ├── ValidationFailed, AuthenticationRequired, MfaRequired, AccessDenied, NotFound, MethodNotAllowed,
│   │   PreconditionRequired, VersionConflict, IdempotencyKeyRequired, IdempotencyKeyReused,
│   │   RateLimited, PayloadTooLarge
│   └── ConflictError (409)
│       └── IdempotencyInProgress, RuleNotApproved (decision_id required), StateTransitionNotAllowed
└── ServerError (5xx)
    └── DependencyUnavailable, InternalError
EngineContractError (RuntimeError) – engine misuse by code; mapped to INTERNAL_ERROR by the API layer.
```

Mapping exceptions to HTTP responses (DRF exception handler, `X-Request-ID`, `Retry-After`) is step 00.4.

## RULE_NOT_APPROVED

`platform_core.engine.rules.require_approved_rule(decision_id, rule=...)` (and the `@rule_gated(...)`
decorator, and `StateMachine.rule_gates`) raise `RULE_NOT_APPROVED` with `decision_id` until the decision is in
`APPROVED_RULE_DECISIONS`. That registry is an in-code constant (changeable only by a reviewed commit, no
environment toggle) and is **empty in PHASE_00** — guarded by `test_no_business_rule_approved_in_phase_00`.
