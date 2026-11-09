# REPORT — PHASE_01 / 01.5 UI

```
PROJECT: Aleekhan
PHASE: PHASE_01
STEP: 01.5
COMMIT SHA: ef4902a
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-09
IMPLEMENTER: Claude Code (aleekhan-implementer); report written and verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 01.4 PASS (reports/phase-01/step-4/REVIEW.md)
```

## 1. Purpose & acceptance
Step text: "01.5 — UI: صفحات مربوط، Farsi RTL responsive، state loading/error/empty/stale، keyboard, screenshots چهار سایز و تست E2E."

Pages in scope (UI_PAGE_PHASE_MAP): 36, 39, 40, 42 and 46, plus the org tree (DEC-043/048).

**DEC-027 does not block this step** (CONFLICTS C-40):
- The PHASE_01 part of the design system is the shared RTL shell built on `docs/ui/DESIGN_TOKENS.md` (UAT T-002 PASS).
- Pages 1 and 2 stay in PHASE_02.

## 2. Actual changes
**Frontend** (bound to the real API; every screen with synthetic data carries «محیط آزمایشی — داده ساختگی»)

*Shell*
- Login flow: password → MFA → forced password change → TOTP enrolment, with 10 recovery codes shown once.
- Session expiry and logout.
- Navigation by `/me/permissions`. This only hides menu items; the server stays authoritative and E2E asserts it still answers 403.
- MFA step-up dialog: on 401 `MFA_REQUIRED` it prompts for a code and retries the action once with a new Idempotency-Key.

*Pages*
- **Page 46, Security & Users:**
  - users: server one-time password shown once; lock/unlock; password and MFA reset; sessions; effective permissions;
  - roles;
  - assignments: explicit self-assignment confirmation; DEC-032 pending notice.
- **Org tree:** WAI-ARIA tree with RTL keyboard navigation. Units, the unit-head position (capacity 1) and holders, all effective from now only.
- **Page 39, Tasks & Approvals:**
  - approval inboxes;
  - approve, reject and withdraw with a reason;
  - the DEC-055 bootstrap approval;
  - task start, complete, block and unblock.
- **Page 40, Documents:** upload into quarantine with the parent-revision check; download only when CLEAN; submit, approve and reject.
- **Page 42, Parameters:** grouped by classification. OWNER_POLICY parameters are owner-only. A blocked BUSINESS_RULE shows `RULE_NOT_APPROVED` with its DEC id.
- **Page 36, System health & Jobs:** health counters, audit integrity and safe cancel. Protected jobs are shown as not cancellable.

*Every page*
- Loading, error (with error code and request id), forbidden, empty and stale states.
- RTL, visible focus, keyboard navigation.
- axe accessibility check: 0 violations in the E2E flows.

*Other*
- Hash router; no new dependency.
- The PHASE_00 status page moved to `#/status`.
- Vite dev proxy: `changeOrigin: false`, needed by Django's CSRF Origin check.

**Backend (Scope B)**
- **DEC-056, permission matrix v1.1:** migration `0014_dec056_owner_approval_rights` (reversible).
  - `owner_admin` gets approval.read and approval.decide.
  - The three "TECHNICAL role holds no business approval" DB guards allow exactly one exception: the pair (`owner_admin`, `approval.decide`).
  - Maker ≠ checker is unchanged: the owner gets `SELF_APPROVAL_FORBIDDEN` on his own requests.
  - The audit row of each decision records the deciding role (`scope.via_role`).
  - Side effect handled: `requires_second_approval` is fixed when the assignment is created. The console bootstrap of the owner is exempt. An in-app grant of `owner_admin` to another person waits for a second person.
- **REV-0120:** the parent-revision check now runs under the document row lock. HTTP race test: exactly one 202 and one 409.
- **REV-0121:** the withdraw reason is stored in the audit row; HTTP happy-path test.
- **REV-0122:** the publish note becomes the audit reason.
- **REV-0123:** the CSRF token is rotated after login and after MFA verify.
- **Contract 0.6.1-draft** (additive): optional `ParameterValueRevision.row_version`. The UI needs it to send If-Match on `publishParameterValue`.

**E2E**
- `frontend/e2e/phase01.spec.ts`, helpers (RFC 6238 TOTP) and global setup.
- The global setup creates the owner with `bootstrap_owner --password-stdin` and adds synthetic job runs.
- `scripts/e2e.sh`, for the local run only: a random data key that is never printed, temporary storage outside the repo, and loopback treated as the factory network.

**UAT guide:** `reports/phase-01/step-5/UAT_HOWTO_FA.md`.

## 3. Data integrity
- Every UI write goes through the API's unit of work (write + audit + outbox).
- Every write carries an Idempotency-Key, and every versioned write carries If-Match.
- Migration 0014 passes the roundtrip.

## 4. Security evidence
- Hidden navigation is not a security boundary. E2E asserts that the server still answers 403.
- The CSRF token is rotated after login and MFA verify.
- The one-time password is shown once, and Escape cannot close its dialog.
- Secret scan: 0 findings in the tree and in history.
- Logs and screenshots: grep for the account name and hostname finds 0 hits.

## 5. Test evidence
Orchestrator re-runs on work-windows (PG 17.9, installed Edge); logs in `logs/orch/`.

| Command | Outcome | Log |
|---|---|---|
| ruff check + format --check | PASS | `logs/orch/ruff.log` |
| mypy strict | PASS, 175 files | `logs/orch/mypy.log` |
| `pytest -m "not perf"` full | **1858 passed, 1 skipped** (real ClamAV), 1 deselected | `logs/orch/pytest.log`, `pytest.xml` |
| `db_roundtrip.sh` (includes 0014) | ROUNDTRIP OK | `logs/orch/db_roundtrip.log` |
| `roles_check.sh` | passed=50, failed=0 | `logs/orch/roles_check.log` |
| frontend eslint / typecheck / build | PASS | `logs/orch/eslint.log`, `typecheck.log`, `build.log` |
| vitest | **34 passed** | `logs/orch/vitest.log` |
| Playwright E2E (real backend + real DB, Edge, workers=1) | **21 passed**, plus 1 passed in the backend-down run | `logs/orch/e2e.log` |

Implementer runs, in `logs/`:
- race tests ×3: 26 passed each run;
- makemigrations --check: clean;
- OpenAPI: valid, 0.6.1-draft;
- secret scans: 0;
- tools unittest: 42 OK;
- verify_handoff: failures 0.

**Screenshots:** 67 in `screenshots/`. That is 15 PHASE_01 views × 4 sizes (1440 desktop, 1180 laptop, 768 tablet, 390 mobile), plus the PHASE_00 status page. The orchestrator spot-checked the Security users view at 1440 and the org tree at 390: RTL, the synthetic-data banner, the keyboard hint, and no overflow.

## 6. Demo (employer)
This is the first step the employer can try in a browser. `UAT_HOWTO_FA.md` gives the exact steps:
- URL `http://127.0.0.1:5173/`;
- how to start the backend and the frontend;
- creating the owner with `bootstrap_owner`;
- steps for each page.

## 7. Issues / decisions
**Known gaps** (not in the UI yet)
- Task create, reassign, verify-close and cancel.
- Dynamic fields.
- Role create, activate and retire.
- Moving a unit; ending a position assignment.
- The audit query page.
- A QR code for MFA enrolment. The key is shown as text, to avoid a new dependency.

**Not tested end to end**
- ClamAV is not configured here, so uploads stay QUARANTINED. The CLEAN download path is tested in the backend only.

**Text to fix**
- The Security page subtitle still says admin rights ≠ business approval. Since DEC-056 this is no longer true for the owner.

**Employer questions** (asked one at a time):
- An in-app grant of `owner_admin` to another person needs a second approver.
- The owner cannot withdraw his own requests: he has no approval.request.
- The owner has no task.read.

## 8. Rollback
- DB: `manage.py migrate platform_core 0013`.
- Code: `git revert <commit>`.

## 9. Review request
Request PASS. Reviewer attention:
- the DEC-056 DB guard exception and the assignment side effect;
- the contract bump to 0.6.1-draft;
- the server-authoritative E2E checks;
- the E2E environment script (data key and network settings).

## 10. Next step
01.6 Integration: Source/Events only; staging, retries, backoff, compensation, freshness and the conflict queue.
