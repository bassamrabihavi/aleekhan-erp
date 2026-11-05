# Error codes — PHASE_00 / 00.3 (PHASE_01 codes added in 01.3)

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
| `SOURCE_READ_ONLY` | 409 | `SourceReadOnly` | Any attempt to write to an external source system (every PHASE_00 source is READ_ONLY; Rahkaran write-back needs its own ADR) — `integration.sources.require_writable` | این سامانه منبع فقط‌خواندنی است؛ نوشتن در آن (مثلاً راهکاران) مجاز نیست. |
| `SOURCE_DISABLED` | 409 | `SourceDisabled` | Import from a source whose `is_enabled` is false | دریافت داده از این منبع فعلاً غیرفعال است. |
| `INVALID_CREDENTIALS` | 401 | `InvalidCredentials` | Login / MFA / password-change ceremony failed: unknown user, wrong password, disabled or locked account, expired one-time password, wrong MFA code - always the same answer (no enumeration) | نام کاربری یا رمز عبور نادرست است یا این حساب در دسترس نیست. |
| `NETWORK_POLICY_DENIED` | 403 | `NetworkPolicyDenied` | INTERNAL_ONLY / operator account used from outside the factory network (EXTERNAL, UNKNOWN or VPN; DEC-042, DEC-052) | ورود با این حساب فقط از شبکه داخلی کارخانه مجاز است. |
| `PASSWORD_CHANGE_REQUIRED` | 403 | `PasswordChangeRequired` | Session of a user whose one-time or expired password must be changed first (DEC-051); only the password change is accepted | ابتدا باید رمز عبور خود را تغییر دهید. |
| `SELF_APPROVAL_FORBIDDEN` | 403 | `SelfApprovalForbidden` | Maker-checker (DEC-032): the decider is the requester / uploader / proposer / completer, or the grantee or grantor of a role assignment | تصمیم درباره درخواستی که خودتان ثبت کرده‌اید یا به خودتان مربوط است مجاز نیست. |
| `PASSWORD_POLICY_VIOLATION` | 422 | `PasswordPolicyViolation` | New password breaks DEC-051 (`errors[].code`: MIN_LENGTH, MAX_LENGTH, UPPERCASE_REQUIRED, DIGIT_REQUIRED, SYMBOL_REQUIRED, RECENTLY_USED); the password is never echoed | رمز عبور با سیاست رمز سازمان سازگار نیست. |
| `FILE_TYPE_NOT_ALLOWED` | 415 | `FileTypeNotAllowed` | Upload outside the DEC-053 allow-list, magic bytes not matching the type, OOXML with macros, parser bomb (`errors[].code`: TYPE_NOT_ALLOWED, MAGIC_MISMATCH, MACRO_CONTENT, CONTAINER_TOO_COMPLEX, EMPTY_FILE, FILENAME_INVALID) | نوع این فایل مجاز نیست یا محتوای آن با نوع اعلام‌شده نمی‌خواند. |
| `FILE_NOT_RELEASED` | 409 | `FileNotReleased` | Download / review of a revision whose scan status is not CLEAN, or whose bytes were purged (STATE_TRANSITIONS 4.6) | این فایل هنوز از بررسی امنیتی عبور نکرده یا رد شده است و قابل دانلود نیست. |
| `JOB_PROTECTED` | 409 | `JobProtected` | Cancel of a protected or non-cancellable job type (migrations, backup, restore; DEC-024 list in PHASE_11) | این کار پس‌زمینه محافظت‌شده است و لغو آن مجاز نیست. |
| `RATE_LIMITED` | 429 | `RateLimited` | Too many requests (with `Retry-After`, step 00.4) | تعداد درخواست‌ها زیاد است؛ کمی بعد تلاش کنید. |
| `PAYLOAD_TOO_LARGE` | 413 | `PayloadTooLarge` | Body above the size limit | حجم داده ارسالی بیش از حد مجاز است. |
| `DEPENDENCY_UNAVAILABLE` | 503 | `DependencyUnavailable` | A required dependency (DB, cache, broker) is down | یکی از سرویس‌های لازم در دسترس نیست؛ کمی بعد تلاش کنید. |
| `INTERNAL_ERROR` | 500 | `InternalError` | Anything unexpected (including `EngineContractError`, which is a programming error, not a client error) | خطای داخلی رخ داد؛ موضوع ثبت شد. |

The eight PHASE_01 codes (`INVALID_CREDENTIALS` .. `JOB_PROTECTED`) are new in 01.3 (OpenAPI draft
`0.5.2-draft`; additive). Seven of them were `x-aleekhan-conventions.planned_error_codes` in 0.5.1;
`PASSWORD_CHANGE_REQUIRED` is new (the session contract of DEC-051 needs a distinct answer so the UI can route
to the password change). `NETWORK_POLICY_DENIED` and `PASSWORD_CHANGE_REQUIRED` depend on the caller's network /
credential state and are therefore *transient* for idempotency (never stored for replay, like
`AUTHENTICATION_REQUIRED` / `MFA_REQUIRED`).

`IDEMPOTENCY_IN_PROGRESS` is new in 00.3 (OpenAPI draft bumped to `0.2.0-draft`). `SOURCE_READ_ONLY` and
`SOURCE_DISABLED` are new in 00.6 (OpenAPI draft `0.4.0-draft`; additive, no existing code changed). The brief's working names
`CONFLICT_VERSION` and `PERMISSION_DENIED` correspond to the already-published OpenAPI codes
`VERSION_CONFLICT` and `ACCESS_DENIED`; the published names were kept to avoid breaking the 00.1 contract.

## Exception hierarchy

```
AleekhanError (code, http_status, message_fa, detail, errors, decision_id, to_problem(request_id))
├── ClientError (4xx)
│   ├── ValidationFailed, AuthenticationRequired, MfaRequired, AccessDenied, NotFound, MethodNotAllowed,
│   │   PreconditionRequired, VersionConflict, IdempotencyKeyRequired, IdempotencyKeyReused,
│   │   RateLimited, PayloadTooLarge,
│   │   InvalidCredentials, NetworkPolicyDenied, PasswordChangeRequired, SelfApprovalForbidden,
│   │   PasswordPolicyViolation, FileTypeNotAllowed (01.3)
│   └── ConflictError (409)
│       └── IdempotencyInProgress, RuleNotApproved (decision_id required), StateTransitionNotAllowed,
│           SourceReadOnly, SourceDisabled (00.6), FileNotReleased, JobProtected (01.3)
└── ServerError (5xx)
    └── DependencyUnavailable, InternalError
EngineContractError (RuntimeError) – engine misuse by code; mapped to INTERNAL_ERROR by the API layer.
```

Mapping exceptions to HTTP responses (DRF exception handler, `X-Request-ID`, `Retry-After`) is step 00.4.

## Row-level import codes (00.6, not API error codes)

Staging rows carry machine codes in `error_codes[]` (pattern `^[A-Z][A-Z0-9_]{2,63}$`): `EMPTY_ROW`,
`DUPLICATE_PAYLOAD` (structural, `integration/imports.py`) plus codes returned by per-source validators (none
approved in PHASE_00). Rows refused before staging are reported as `VALIDATION_FAILED` with `errors[].code`:
`SENSITIVE_FIELD`, `DUPLICATE_POSITION`, `OUT_OF_RANGE`, `TOO_LARGE`, `NOT_JSON`, `NOT_AN_OBJECT`, `INVALID`;
file-level `EMPTY_FILE`; `TIMEZONE_REQUIRED` for a naive `source_as_of`. See docs/integration/README.md.

## RULE_NOT_APPROVED

`platform_core.engine.rules.require_approved_rule(decision_id, rule=...)` (and the `@rule_gated(...)`
decorator, and `StateMachine.rule_gates`) raise `RULE_NOT_APPROVED` with `decision_id` until the decision is in
`APPROVED_RULE_DECISIONS`. That registry is an in-code constant (changeable only by a reviewed commit, no
environment toggle) and is **empty in PHASE_00** — guarded by `test_no_business_rule_approved_in_phase_00`.
It stays empty in PHASE_01 / 01.3: the PHASE_01 decisions (DEC-032, DEC-048..054) are platform/security policy
whose values are OWNER_POLICY parameters, not business rules; BUSINESS_RULE parameters stay blocked by their
own decision id.

## Database-guard refusals (01.3)

`platform_core.engine.dbrules.db_rules()` maps an `IntegrityError` raised by a named DB guard (`ck_*`, `ex_*`,
`immutable_column`, `append_only`, `terminal_immutable`) to 409 `STATE_TRANSITION_NOT_ALLOWED` and a duplicate
(`uq_*`) to 400 `VALIDATION_FAILED`, with the rule name (upper case) as `errors[].code`. The DB message text is
never copied into the response.
