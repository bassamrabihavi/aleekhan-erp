# REPORT — PHASE_02 / 02.5 UI

```
PROJECT: Aleekhan
PHASE: PHASE_02
STEP: 02.5
COMMIT SHA: 5f65fc9
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-15
IMPLEMENTER: Claude Code (aleekhan-implementer); E2E, screenshots and checks re-run by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 02.4 PASS (14b49e4); DEC-027 APPROVED P-A (2026-11-15); approval-inbox decision 2026-11-15
```

## 1. Purpose & acceptance
Step text: "صفحات مربوط، Farsi RTL responsive، state loading/error/empty/stale، keyboard, screenshots چهار سایز و تست E2E".

Pages, per UI_PAGE_PHASE_MAP:
- 1 مرکز کنترل سریال — نمای خلاصه
- 2 مرکز کنترل سریال — تب سفارش
- 4 ردیابی محصولات و استایل‌ها
- 29 ثبت سفارش و کدگذاری
- 33 تغییرات سفارش (the PHASE_02 part)

Also added: customers, code rules, and the PHASE_02 decisions tab in the approval inbox.

ID-01..04 are covered end to end in a browser:
- the code is shown as text with leading zeros;
- the serial is allocated at confirm and shown on pages 1/2;
- one serial per line;
- the order wizard keeps its Idempotency-Key on retry.

## 2. Actual changes
**Frontend pages**
- `SerialCenterPage` (pages 1/2):
  - Header: serial, product, code, customer, brand, status, quantity, dates.
  - «خلاصه» tab: later-phase sections (production stages, issues, progress, materials, location, grade) show «در دست ساخت — به داده واقعی متصل نیست» with their owning phase and **no numbers**. The tab also lists the serial's change requests.
  - «سفارش» tab: header, lines, snapshots, versions, external references, timeline.
- `OrdersPage` (page 29): 4-step wizard; validate with duplicate-PO acknowledgement; reopen, cancel, confirm, release; versions; external references.
- `ProductsPage` (page 4):
  - products: belt buckle + 2-digit width only for belt types;
  - styles: similar-style suggestions;
  - code preview and issue (fresh MFA), 14-digit checker;
  - serials per style.
- `ChangesPage` (page 33): change kinds allowed by order state; before/after; decide / planning decision / apply / withdraw.
- `CustomersPage`: duplicate-name acknowledgement, brands.
- `CodeRulesPage`: golden counts only; submit / approve / reject / activate.
- `DecisionInbox` tab «تصمیم‌های سفارش و کد» in the approval inbox.

**Shared frontend code**
- `api/phase02.ts` (guards; codes checked as text), `lib/jalali.ts`, `components/Phase02.tsx`.
- `ActionError`: 412 → «این داده در این فاصله تغییر کرده است» + reload; Persian text for refusal reasons.
- New `PageErrorBoundary` around every page.

**Backend:** `GET /me/decision-inbox` (contract **0.8.3-draft**), permission-scoped.
- ORDER_CONFIRM: never shown to the creator.
- CHANGE_DECIDE: never shown to the requester or the planner.
- CHANGE_PLANNING_DECISION: never shown to the requester or the decider.
- CODE_RULE_APPROVE: never shown to the maker.
- It returns ids, numbers and times only, with no names. 9 tests. No migration.

**Bug found by the orchestrator's E2E run, and fixed:**
- **Symptom:** the serial page crashed after the order page.
- **Cause:** a react-query cache entry was shared by two pages with different value shapes.
- **Fix:** cache the full response and use `select`. A vitest regression test fails on the old code.

## 3. Data integrity
- All writes go through the 02.4 API, with Idempotency-Key and If-Match.
- No client-side business rule replaces a server check. For example, confirm is offered to every holder of the permission, and the server refuses the creator.

## 4. Security evidence
- Every menu item is hidden by permission; the employee role sees no PHASE_02 page (E2E `forbidden-employee`).
- management_viewer is read-only, and the representative name is masked (E2E).
- The decision inbox never shows a user their own item (backend tests + E2E).
- All data is synthetic: `syn.*` users, test types 96/97, 40 synthetic golden cases. The test-environment banner is on every page.
- Secret scan: findings=0. Path/account leak grep: 0 hits (junit hostname redacted). `handoff/` is unchanged.

## 5. Test evidence (orchestrator re-run, `logs/orch/`)
| Check | Result | Log |
|---|---|---|
| eslint / typecheck / build | rc 0 / rc 0 / rc 0 | `eslint.log`, `typecheck.log`, `build.log` |
| vitest | 6 files, 72 passed | `vitest.log` |
| E2E full (`scripts/e2e.sh`, Edge, DB `test_aleekhan_e2e`) | 32 passed + backend-down 1 passed (PHASE_01 + PHASE_02 specs) | `e2e.log` |
| ruff / mypy / makemigrations --check | PASS / PASS / no changes | `ruff.log`, `mypy.log`, `makemigrations.log` |
| OpenAPI validation | OK (0.8.3-draft) | `openapi_validate.log` |
| pytest -m "not perf" | 3083 passed, 2 skipped, 7 deselected | `pytest.log` |
| secret scan | findings=0 | `secret_scan.log` |

- The first orchestrator E2E run had 27 passed, 1 failed and 3 not run because of the serial page crash above. After the fix, the full re-run passed.
- The orchestrator viewed the screenshots of page 1 at 390 and page 29 at 1440.

**Screenshots** (`screenshots/`): 16 PHASE_02 sets × 1440/1180/768/390 = 64 files.
- code-rule-review, inbox-decisions, customers, forbidden-employee
- page01-serial-summary, page02-serial-order, page04-product-style
- page29-wizard-step1, page29-order-draft, page29-order-confirmed, page29-orders-viewer
- page33-change-decide, page33-change-applied, page33-empty
- state-error, state-version-conflict

## 6. Demo (employer)
**Layout check now (DEC-027):** the employer reviews the screenshots of pages 1, 2, 4, 29 and 33 (`screenshots/`), sent to him directly.

**Hands-on UAT is deferred to after 02.6.** The full flow needs product types/categories and an ACTIVE code rule revision, and those come only from the server-side import (02.6). The E2E console seed stands in for that import in tests, but is not an employer tool. The UAT how-to will be written then, using `status.py test-add`.

## 7. Issues / decisions (conservative choices)
1. PHASE_02 decisions do not create `ApprovalRequest` rows; the inbox reads the live objects directly. "Apply change request" is not in the inbox, because it is not in the employer's list of four.
2. ADD_LINE change request: the backend supports it but the UI has no form yet; the page says so.
3. No UI for creating code-rule revisions or golden cases. These stay server-side, because real cases must never be typed into a browser.
4. Labels for order types, units and external-reference types are hardcoded from the DEC-058 seed, because the API has no list endpoint.
5. Page 33 before/after: "before" is the order's current value, with a note when the order has moved past the base version.
6. Excel export, column settings and the notification badge are not built: there is no approved export policy and no notification endpoint.
7. **Visual remarks for `control/UI_POLISH_BACKLOG.md`:**
   - the sticky top bar appears mid-page in full-page screenshots (existing PHASE_01 behaviour);
   - one build chunk is 530 kB.

## 8. Rollback
`git revert 5f65fc9`. There is no migration, and the contract goes back to 0.8.2-draft with it.

## 9. Review request
PASS requested, against R01–R14.

## 10. Next step
02.6 Integration: Planning/Rahkaran import staging, conflict queue, legacy serials (≥ 63000 → conflict) and the import rules recorded in DATA_TABLE.
