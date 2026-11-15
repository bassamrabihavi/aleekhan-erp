VERDICT: PASS
PHASE/STEP: PHASE_02 / 02.5 (UI)  COMMIT: 5f65fc9 (report a469d10, status ea02229)
REVIEWER: aleekhan-reviewer (independent, read-only; verdict advisory until DEC-036)

Verdict basis: every applicable check has evidence and there are no P0 or P1 issues. Three P2 and three P3 issues remain open (below). The P2 issues should be fixed before the PHASE_02 Gate packet goes to the employer, because the employer will judge the page 1/2 layout from these screenshots (DEC-027).

## Re-run by the reviewer (this machine, 2026-11-15)
- `pytest platform_core/tests/test_api_phase02_inbox.py`: 9 passed.
- `npx vitest run`: 6 files, 72 passed.
- `npm run typecheck`: rc 0. `npx eslint .`: rc 0.
- `ruff check` and `mypy` on `inbox_views.py` and its test: clean.
- Not re-run on purpose (8 GB RAM limit): the full pytest suite and E2E.
  - Orchestrator logs `logs/orch/pytest.log`: 3083 passed, 2 skipped (both with a stated reason), `pytest.rc`=0.
  - Orchestrator log `logs/orch/e2e.log`: "32 passed", plus backend-down "1 passed", `e2e.rc`=0, on a real backend.
  - `logs/orch/openapi_validate.log`: OK. `makemigrations.log`: "No changes detected". `secret_scan.log`: findings=0.
- Screenshots viewed:
  - page01 at 1440, 768 and 390
  - page02 at 768
  - page04 at 390
  - page29 wizard at 1180
  - page33 decide at 1180
  - inbox at 1440

## CHECKS
- R01 Scope ✔ — The UI covers pages 1, 2, 4, 29 and 33 (PHASE_02 part), as in UI_PAGE_PHASE_MAP. The extras are customers, code rules and the inbox tab. All three are traced to PHASE_02 entities and to the employer decision of 2026-11-15 (inbox). `handoff/` is unchanged (`git show --stat` shows no handoff paths). No migration.
- R02 Source of truth ✔ — The inbox filters match the server rules:
  - order confirm: `commercial/orders.py:799` (creator refused);
  - change decide: `changes.py:380-382`;
  - planning decision: `changes.py:426-432`;
  - code rule: `product_identity/codes.py:369`.
  Serial 63001 in the screenshots comes from DEC-006 (`migrations/0021_phase02_seed_catalogue.py:47`). Report section 7 lists the conservative choices. Hardcoded labels from the DEC-058 seed are disclosed (item 4).
- R03 Database ✔ — The diff has no schema change. `makemigrations --check` reports no changes (`logs/orch/makemigrations.log`).
- R04 Transaction/ledger ✔ — The new endpoint is read-only (`inbox_views.py:68-160`, no writes). UI writes go through the existing 02.4 API with Idempotency-Key and If-Match. E2E covers the 412 state (`e2e/phase02.spec.ts:325`).
- R05 Engine n/a — No engine change in this step.
- R06 API ✔ — The endpoint is additive (contract 0.8.3-draft). It appears in `docs/api/openapi-draft.yaml:991`, `API_RUNTIME.md:313` and `CONTRACT_VERSION` (`api/views.py:32`), and the OpenAPI validation is OK. Each kind is gated by the caller's GLOBAL grant (`inbox_views.py:80,96,115,138`). Own items are excluded. The 9 tests pass.
- R07 UI ✔ (with REV-0251/0252/0253) — RTL and Jalali dates are correct. Codes and serials show as LTR text with leading zeros (`02970700010001`). The loading, empty, error and 412 states have screenshots (`state-error`, `state-version-conflict`, `page33-empty`). Pages are role-sensitive (`forbidden-employee`, `orders-viewer` with the masked representative). Later-phase sections on pages 1, 4 and 33 show «در دست ساخت — به داده واقعی متصل نیست» with their owning phase and **no numbers**: checked visually at 1440, 768 and 390. The only numbers shown come from the server: page 33 impact counts (`ChangesPage.tsx:336-339`, from `changes.py:259 impact_of`) and the real zero counts on page 4. Defect: the header of pages 1/2 breaks at 768 (REV-0251).
- R08 Security ✔ — `secret_scan` findings=0. The test passwords in E2E are env placeholders (`${SYN_PW_P2}`). The DB password is logged only as "set: yes". The inbox returns ids, numbers and times only (test `test_no_personal_data_in_the_feed`). The commit has no private paths or raw data. All data is synthetic (`syn.*`, the banner is on every page). Fresh MFA is required for confirm, issue and approve (E2E lines 46, 81, 228).
- R09 Module ownership ✔ — The inbox only reads `commercial` and `product_identity` models. It creates no `ApprovalRequest` rows and writes nothing to platform tables (`inbox_views.py`).
- R10 Integration n/a — This belongs to step 02.6.
- R11 Performance/ops ✔ — The feed is capped per kind (`PER_KIND=100`, `truncated` flag) and sends `no-store`. The 530 kB chunk is disclosed for the polish backlog.
- R12 Tests/evidence ✔ — E2E runs on a real backend in a throw-away DB `test_aleekhan_e2e`, and the logs carry rc files. The cache-shape crash has a regression test in vitest. The reviewer's vitest and pytest re-runs match the logs.
- R13 Docs ✔ — `CHANGELOG.md:399`, the OpenAPI description at line 120, and `API_RUNTIME.md` are updated. Rollback is in report section 8.
- R14 Owner acceptance — left to the employer at Gate time. Hands-on UAT is deferred to after 02.6, as the report says.

## ISSUES
- REV-0251 [P2] `frontend/src/styles/phase02.css:156-160` and `:191` — The header of pages 1 and 2 collapses to one word per line at tablet width.
  - **Cause:** between 601 and about 900 px, `.serial-head` uses `grid-template-columns: minmax(0,1fr) auto`. The `auto` chips column takes the chips' max-content width, so the title, product and code column shrinks to its min-content width.
  - **Repro:** `screenshots/phase02-page01-serial-summary-768-tablet.png` and `phase02-page02-serial-order-768-tablet.png` («صفحه / ۱ / و / ۲ …», «سریال / 63001», «کد / محصول:» stacked).
  - **Expected fix:** collapse to one column at ≤900 px, or bound the chips column (e.g. `fit-content(40%)` / `minmax(0, max-content)`).
  - **Regression test required:** an E2E or visual assertion at 768 that `#serial-title` is a single line, i.e. its bounding-box height is no more than about 1.5 × line-height. Re-shoot the 768 screenshots of page01 and page02.
- REV-0252 [P2] `frontend/src/pages/SerialCenterPage.tsx:311-312` — Two panels with the same title «ارجاع‌های بیرونی» (`OrdersPage.tsx:676`) appear one after the other on page 2: one for the serial, one for the order. The user cannot tell them apart.
  - **Repro:** `phase02-page02-serial-order-768-tablet.png`.
  - **Expected fix:** the title states the target («ارجاع‌های بیرونی سریال» / «… سفارش»), or a single panel with two groups.
  - **Regression test required:** a vitest check that the two headings are distinct.
- REV-0253 [P2] `reports/phase-02/step-5/REPORT.md` §5 — The report says the orchestrator viewed only page 1 at 390 and page 29 at 1440. That is why REV-0251 went unnoticed. Before the Gate packet, every PHASE_02 screenshot set at 768 and 1180 must be viewed, and the viewing recorded.
- REV-0254 [P3] `inbox_views.py` and the inbox UI — «درخواست‌کننده» shows a short UUID (`3907e736`), not a person; page 33 does the same. This is acceptable for privacy but poor for usability. Candidate for `control/UI_POLISH_BACKLOG.md`, or for a display-name lookup that the caller is allowed to see.
- REV-0255 [P3] `backend/platform_core/tests/test_api_phase02_inbox.py` — The tests have no backend case for an authenticated caller with none of the four permissions (expected: `items == []`). E2E `forbidden-employee` covers it only at the page level. Add the test.
- REV-0256 [P3] Screenshots — The footer shows build `b1858d398de6` (the parent commit), not `5f65fc9`: the shots were taken from the uncommitted working tree. This is cosmetic, but Gate screenshots should show the build being reviewed.

## EMPLOYER ATTENTION
- برای DEC-027، تصاویر صفحه ۱ و ۲ را در اندازه دسکتاپ و موبایل ببینید. در اندازه تبلت (۷۶۸)، بالای این دو صفحه به‌هم‌ریخته است (REV-0251) و پیش از Gate اصلاح می‌شود. لطفاً درباره ظاهر تبلت تا نسخه اصلاح‌شده قضاوت نکنید.
- در بخش‌های فازهای بعد (مراحل تولید، مشکلات، پیشرفت، مواد، موقعیت، گرید) فقط «در دست ساخت» نوشته شده و هیچ عددی نمایش داده نمی‌شود. آیا این شکل نمایش را می‌پذیرید؟
- در صندوق تصمیم‌ها و صفحه تغییرات، «درخواست‌کننده» به‌جای نام فرد با یک شناسه کوتاه نشان داده می‌شود. آیا نمایش نام کاربر به تأییدکننده مجاز است؟ این یک تصمیم حریم خصوصی است.
- آزمون دستی شما (UAT) بعد از گام ۰۲.۶ انجام می‌شود، چون به ورود قاعده کد و انواع محصول از سرور نیاز دارد.
