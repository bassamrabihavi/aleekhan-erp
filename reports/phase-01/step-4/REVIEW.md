VERDICT: PASS

PHASE/STEP: PHASE_01 / 01.4 Backend/API   COMMIT: f6a60a5 (status/report commit 1bedc79 touches only control/ and reports/)
REVIEWER: aleekhan-reviewer (independent, read-only on source). Machine: work-windows, PG test 127.0.0.1:5433, DB test_aleekhan_rev014.
Advisory until DEC-036 is APPROVED: the employer still has to confirm this step.

## Reviewer re-runs (my own runs, not copied from the report)
| Command | Result |
|---|---|
| `pytest -q -m "not perf"` (backend, full suite) | 1846 passed, 1 skipped (clamd not configured), 1 deselected, 179.94s, exit 0. Same counts as `logs/orch/pytest.log` |
| `ruff check .` / `ruff format --check .` | All checks passed / 173 files already formatted |
| `mypy .` (strict config) | Success: no issues found in 173 source files |
| `manage.py makemigrations --check --dry-run` (ALEEKHAN_ENV=test) | No changes detected |
| `git diff ed48706 f6a60a5 --stat -- backend/**/migrations/*` | empty: no migration in this step, so I did not re-run db_roundtrip (orchestrator log `logs/orch/db_roundtrip.log` = ROUNDTRIP OK) |
| `grep -c operationId` / `grep -c x-aleekhan-planned` in docs/api/openapi-draft.yaml | 107 / 0 (matches the claim "107 operations, 0 planned"); info.version 0.6.0-draft |
| privacy grep of reports/phase-01/step-4 for account name, user-profile paths, hostname; secret-literal grep of the diff | 0 hits |

## CHECKS
- R01 ✔ Scope: only the 01.4 API layer plus thin services that the planned contract operations needed (identity/users.py:update_user, identity/roles.py:update_role, workflow/approvals.py:can_decide). The two new operations are justified: `stepUpMfa` is needed to make the DEC-051 step-up usable, and `bootstrapSelfApproveRequest` implements the approved DEC-055 as a separate operation (workflow_views.py:305). No UI, integration or business-module code.
- R02 ✔ No invented P0 rule. The login rate limits are labelled TECHNICAL defaults (settings.py `login_ip`/`login_user`) and raised to the employer. Server-generated one-time passwords and the owner's missing `approval.read` are listed as employer questions in REPORT §7. The not-yet-supported fields answer 400 NOT_SUPPORTED instead of guessing (common.py:452; identity_views.py:317).
- R03 ✔ No schema change (makemigrations clean). Writes lock the row, check scope and then If-Match inside the idempotent transaction (common.py:546-560). The HTTP race tests pass in the full run. One weakness in the optimistic guard: REV-0120.
- R04 ✔ Every write goes through run_idempotent → unit_of_work. The audit row is mandatory even with `require_event=False` (engine/uow.py:151). One-time passwords never reach the idempotency record (`StoredResponse.body_to_store`, engine/idempotency.py; identity_views.py:100-111). Audit gap: REV-0121.
- R05 n/a: no engine or algorithm work in this step.
- R06 ✔ Every action checks its permission (ScopedPermission plus required_action/write_action, common.py:68-88), then MFA step-up from the DB flag (permissions.py ScopedPermission), then record scope (404). Body-referenced ids are scope-checked too (org_views.py:272, 348). Idempotency is keyed per (actor, key) (engine/idempotency.py:3, 73). If-Match/ETag, pagination and request-id are present. The OpenAPI changes are additive for planned operations (createUser → UserCreated, which was never implemented before), and the contract tests validate responses.
- R07 n/a: no UI in this step (01.5).
- R08 ✔ Deny by default; PUBLIC_OPERATIONS = 3 probes + getLoginContext + login (permissions.py). CSRF covers login and authenticated unsafe calls (session_auth.py enforce_csrf; tested in test_api_phase01_auth.py:48-71, where logout without the header gets 403). Cookie: HttpOnly, SameSite=Lax, Secure outside dev/test. Throttles run before the permission check (api/base.py:26-28). TOTP step-up failures count toward the lockout (identity/auth.py:434-436). SEC-01: test_api_bola.py covers all `{id}` families with an all-permission, unit-scoped probe. SEC-03: upload goes to quarantine and download sends attachment + nosniff (document_views.py). No PII, passwords or host names in the reports. Minor items: REV-0122 and REV-0123.
- R09 ✔ The API views call the module services (identity, org, workflow, documents, params, jobs). No direct cross-owner table writes were found in api/phase01. Reads used for scope or serialisation only.
- R10 n/a: no integration in this step (01.6).
- R11 n/a for this step: the per-record inbox scan has a 1000-row cap (common.py:477), and the report defers the perf check to 01.7. Accepted as disclosed.
- R12 ✔ Tests run against real PostgreSQL over HTTP with the Django test Client, and I reproduced the counts myself (table above). There is one coverage gap: REV-0121.
- R13 ✔ CHANGELOG.md, docs/api/API_RUNTIME.md, docs/api/openapi-draft.yaml (0.6.0-draft with a changelog paragraph) and docs/engine/PHASE01_ENGINE.md are updated in f6a60a5.
- R14 n/a: owner acceptance is left to the employer at Gate time.

## ISSUES
- REV-0120 [P2] backend/platform_core/api/phase01/document_views.py:188-192 — The `parent_revision_id` guard ("is the latest revision") reads the latest revision without a lock. The document row is locked only later, in documents/service.py:359 (`_lock_doc`). So two concurrent uploads that send the same, currently-latest `parent_revision_id` both pass the check. Both then create revisions: N+1, and N+2 whose parent is N+1, not the parent the client asserted. The lost-update protection the field promises is bypassed. Repro: two threads/clients POST `/documents/{id}/revisions` at the same time with the same `parent_revision_id` = latest; both get 202. Expected fix: do the parent check after `_lock_doc` inside `upload_revision` (pass `expected_parent_id` to the service), so the second request gets 409. Regression test required: an HTTP race test in test_api_phase01_race.py where exactly one 202 and one 409 come back.
- REV-0121 [P2] backend/platform_core/api/phase01/workflow_views.py:329-333 — `withdrawRequest` validates the required `ReasonRequest.reason` (the contract requires it, openapi-draft.yaml ~3207) and then throws it away. `approvals.withdraw` has no reason parameter (workflow/approvals.py:364), so the audit row of a workflow state change carries no justification. REPORT §7 lists the dropped notes of `submitDocumentRevision` and `revokeMySession` but not this one, so it is undisclosed. Besides the BOLA negative case (test_api_bola.py:162), no HTTP test calls `/withdraw` at all. Repro: POST withdraw with a reason, then read the audit event: reason is empty. Expected fix: pass the reason to `approvals.withdraw` → `close(...)` audit reason, or disclose it and make the field optional in the contract. Regression test required: a happy-path withdraw over HTTP that asserts 200, status WITHDRAWN, If-Match/ETag and the audit reason.
- REV-0122 [P3] backend/platform_core/api/phase01/config_views.py:147 — The optional `note` of `publishParameterValue` is accepted and then dropped silently, and this is not disclosed in REPORT §7. Expected fix: store it in the publish audit reason, or disclose it. Test: assert the audit reason, or add a report entry.
- REV-0123 [P3] backend/platform_core/api/phase01/auth_views.py:58-75 — The CSRF token is not rotated on a successful login (no `rotate_token`; Django's own `login()` does rotate it). The impact is low because of SameSite=Lax, an HttpOnly session and a host-only cookie. It is still a cheap hardening step against CSRF-token fixation. Expected fix: call `django.middleware.csrf.rotate_token(request._request)` after a successful login and after MFA verification. Test: the csrftoken cookie value changes after login.
- REV-0124 [P3] backend/platform_core/api/phase01/document_views.py:175 — The upload size is checked only after DRF/Django has parsed the multipart body. Django spools large files to a temp file, so an oversized upload is written to disk before the 413. This relies on the DEC-042 reverse-proxy body limit. Expected fix: check `CONTENT_LENGTH` before parsing, or confirm the proxy limit in 01.7 (security & ops). Test: a request with an oversize Content-Length gets 413 without reading the body.

None of these is P0/P1. REV-0120 and REV-0121 should be fixed before the 01.8 Gate packet; tracking them into 01.7 is acceptable.

## EMPLOYER ATTENTION (برای کارفرما)
- مالک در ماتریس v1.0 مجوز `approval.read` ندارد و درخواستی را که باید خودش تأیید اولیه (bootstrap) کند، نمی‌تواند باز کند. لازم است تصمیم بگیرید که این مجوز به نقش مالک اضافه شود یا نه.
- سقف تلاش ورود (۲۰ بار در دقیقه برای هر IP و ۱۰ بار برای هر نام کاربری) پیش‌فرض فنی است و تأیید شما را می‌خواهد.
- رمز یک‌بارمصرف را سیستم می‌سازد و فقط یک بار به مدیر نشان می‌دهد. تأیید کنید که روال مورد نظرتان همین است.
- برای این گام تست UAT ندارید (رابط کاربری ندارد). تأیید نهایی شما برای Gate می‌ماند.
