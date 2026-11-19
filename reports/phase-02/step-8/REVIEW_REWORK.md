VERDICT: PASS
PHASE/STEP: PHASE_02 / 02.8 Gate follow-up rework (REV-0290..0295)    COMMIT: 87e96f3 (report + re-freeze); reviewed range e9962b4~1..87e96f3 (code e9962b4, 54a40b3, e7bec06, 0e0d927, 5cbb254, d3c08d2, dd1f8f6, b0cba1a, 735040f; harness 54a40b3, deea35a, a3d2d98, 33b0686, f9b4dc6)
REVIEWER: aleekhan-reviewer (independent, read-only on code), 2026-11-19, machine work-windows
ADVISORY: DEC-036 is not approved yet, so this verdict is advisory. The employer confirms the step. R14 is left to the employer at Gate time.

## What I re-ran myself (at HEAD 87e96f3; clean tree except the untracked session lock)
- `ruff check backend` -> "All checks passed!". `ruff format --check backend` -> "256 files already formatted". `mypy .` (backend) -> "Success: no issues found in 256 source files".
- `npm run check` (frontend: eslint --max-warnings=0, tsc both projects, vitest) -> rc 0, **99 passed** (7 files). The report says 98. The extra test is the overflow unit test that 33b0686 added after the rework5 log was taken (see REV-0298).
- `sha256sum -c reports/phase-02/step-8/fidelity/FROZEN_SHA256.txt` -> all 10 files OK (5 specs, score/measure/config/structure/fidelity.spec).
- Harness separation: after 54a40b3, only harness-only commits touched `frontend/e2e/fidelity/*` (a3d2d98, 33b0686, f9b4dc6: `git show --name-only` has no file outside the harness). The one exception is the app commit e7bec06, which changed `fidelity.spec.ts` (seed +6 synthetic orders). At that time that file was not in the freeze list (REV-0297). No app commit touched specs, scorer, weights or threshold.
- `pytest platform_core/tests/test_runserver_e2e.py` -> 3 passed (no DB needed).
- `python tools/secret_scan.py --history` -> findings=0 -> PASS (1 known allowlisted test literal).
- Leak grep over the report/log files of the range: the 14-digit matches in `fidelity/*.json` are float fractions of scores. Three rework3 e2e logs contain a local Windows profile temp path (REV-0296).
- **Not re-run independently:** DB-backed pytest, migration round trip, e2e and the fidelity run. PostgreSQL on 5433 needs credentials, and my environment has none (no PG* env, no pgpass). For these I rely on the committed logs:
  - `logs/rework5/backend_pytest.log`: 3196 passed, 2 skipped, rc=0. It was taken after the last backend commit, 5cbb254.
  - `logs/followup/migration_roundtrip.log`: 0029 applied/unapplied/applied, schema diff EMPTY over 10565 lines, "No changes detected". Migrations are unchanged since e9962b4.
  - `logs/rework6/e2e_full.log`: 32 passed + 1 backend-down, rc=0.
  - `logs/rework6/fidelity_final_enforce.log`: "2 passed", fidelity rc=0.
- Visual check of the side-by-side shots: `page-01-1440-final.jpg`, `page-04-1440-final.jpg`, `page-33-1440-final.jpg`, `page-02-390-final.jpg`.
  - Layout order and regions follow the mockups.
  - Later-phase values show «—» / «در دست ساخت» + the owning phase. I found no demo number copied from a mockup.
  - Page 4 extra sections (style detail, code, revisions, products) sit below all mockup content, as the DEC-061 amendment 2026-11-18 requires.

## CHECKS
- R01 ✔ Scope is right.
  - Code maps 1:1 to the reopened items in `GATE_FOLLOWUP_REVS.md` (REV-0290..0295).
  - The new read endpoint `GET /commercial/change-requests/counts` (`api/phase02/urls.py:82`) feeds the page-33 KPI cards. The style-tracking counts and filters (`identity_views.py` StyleTrackingView) feed the page-4 KPIs and filter bar. Both serve REV-0295.
  - The top-bar global search (`AppShell.tsx:308-333`) is a catalogue shell element. It reuses the existing list endpoints only.
  - No PHASE_03+ work.
- R02 ✔ Every rule traces to a recorded decision.
  - One open CR + 30-day expiry: DECISION_LOG 2026-11-17 DEC-059 amendment (`DECISION_LOG.md:276`).
  - Requester display name: DEC-032 amendment (`:283`).
  - DISMISSED carry-over: DEC-005 amendment (`:289`).
  - ACTIVE product rule: DEC-005 amendment 2026-11-18 option A (`:305`).
  - Fidelity: DEC-061 + amendment (`:296`, `:311`).
  - Two KPI definitions were chosen by the team, not by a decision (REV-0299, display only, for the employer):
    - «سفارش‌های فعال» = CONFIRMED / RELEASED_TO_PLAN / ON_HOLD / PARTIAL_FULFILLED (`identity_views.py` ACTIVE_ORDER_STATES).
    - Page-33 «باز» includes DRAFT (`commercial_views.py` ChangeRequestCountsView).
- R03 ✔ Migration 0029 holds up.
  - It is additive and reversible: nullable `expires_at`, partial UNIQUE `uq_commercial_cr_one_open_per_order`, two CHECKs and a partial index.
  - The backfill uses `platform_param_value_at`. If duplicates already exist, the migration stops with a count-only message and never closes records itself (`0029_dec059_cr_open_expiry.py:38-52`). The reverse is the exact inverse.
  - Round trip evidence: see above. The model mirrors the constraints (`commercial/models.py` Meta). `test_phase02_migration_0029.py` is present.
- R04 ✔ Transactions, audit and outbox hold.
  - Submit holds the order row lock (`changes.py` `lock(CustomerOrder, ...)` in submit; create already locks the order).
  - The DB backstop is mapped to `OPEN_CHANGE_REQUEST_EXISTS` (`_one_open_backstop`).
  - Expiry runs per row in a system unit of work with `skip_locked` and writes audit + outbox (`_expire_locked`/`_expire_one`/`expire_due`). It is registered as housekeeping job `change_request_expiry_sweep` (`jobs/service.py:225,239`).
  - Decide, planning-decide and apply refuse an overdue request.
  - Race test: `test_concurrent_submits_of_drafts_of_one_order_leave_one_open_request_race` (`test_phase02_engine_race.py:148`).
  - REV-0293 locks style -> product (`master.py require_active_product`, `codes.py:610`).
- R05 ✔ Engine refusals are covered and registered.
  - New reasons are registered under STATE_TRANSITION_NOT_ALLOWED (`refusals.py:80-82,154-155`) and the golden refusals/event catalogue were updated.
  - Product DRAFT/RETIRED is refused for style activation and code issue, and a replay survives a later retire (`test_phase02_engine_identity.py` rev0293 tests).
  - DISMISSED carry-over is tested (`test_phase02_step7_ops.py:187`). Golden-file test skipped: the file is not set on this run, and that is disclosed.
- R06 ✔ API contract and RBAC hold.
  - OpenAPI 0.8.5-draft documents `/commercial/change-requests/counts` (`openapi-draft.yaml:7624`), `requested_by_name` (`:9643,:10299`), `orders_active` (`:12726`) and the new refusal codes (`:140`).
  - The counts view requires CHANGE_READ and uses the same `scoped()` set as the list.
  - Order facts and order counts are withheld without order read (`see_orders`).
  - `user_name()` returns the display name only (`phase01/common.py:123`).
  - API tests: `test_rev0295_change_request_counts_follow_the_states_and_the_read_permission`, `test_rev0295_style_tracking_...`.
- R07 ✔ UI evidence is present (minor notes REV-0300).
  - Persian RTL; the 4 widths have screenshots in `screenshots/`. The e2e includes axe via `phase01-helpers.ts` and passes after the contrast fixes (b0cba1a).
  - Disabled actions carry a visible reason, e.g. «ابتدا محصول را فعال کنید» for REV-0293.
  - Fidelity per page per width is ≥95% (`fidelity/FINAL.md`, enforce rc=0). Thin margins: page 4 @768 is 95.4.
- R08 ✔ Security checks pass.
  - The secret scan is clean.
  - No new write endpoint. The global search goes through server-checked endpoints.
  - The requester name is the internal display name only (no username or contact data).
  - Minor log-path hygiene item: REV-0296.
- R09 ✔ Module ownership holds.
  - Commercial writes only commercial tables. Identity checks the product through its own `master.require_active_product`. The jobs service only registers the commercial function.
- R10 ✔ Integration behaviour is correct and audited.
  - DISMISSED/RESOLVED carry-over is counted and audited without the raw value (`planning_import.py`).
  - No Rahkaran write.
- R11 ✔ E2E reliability fix is evidenced.
  - `runserver_e2e` with a larger listen backlog (`management/commands/runserver_e2e.py`, test 3 passed).
  - Probe: `logs/rework5/backlog_probe.log`.
  - Two clean full e2e runs plus one more after 735040f.
- R12 ✔ Evidence is real and mostly reproducible.
  - Real-backend e2e and fidelity logs are committed.
  - Static checks reproduce exactly.
  - DB-backed results are not reproduced by me (no credentials), see above.
  - The report's vitest count is stale: REV-0298.
- R13 ✔ Docs are updated, with one stale line (signed file, not edited).
  - Updated: STATE_TRANSITIONS (EXPIRED decided), ERROR_CODES, EVENT_CATALOGUE, ERD, JOB_MONITORING, ROLLBACK, API_RUNTIME and the harness README.
  - The stale line: `PHASE_02_SECURITY_CHECKLIST.md` §7 still lists REV-0203 as undecided. It is disclosed in the report.
- R14 n/a Owner acceptance: left to the employer (Gate / DEC-061 mockup review).

## ISSUES
- REV-0296 [P3] `reports/phase-02/step-8/logs/rework3/e2e_full_run1_failed.log:1091-1099` (same in `e2e_full_run2_flaky_econnrefused.log`, `e2e_full_run3_failed_versions.log`)
  - Problem: committed logs contain the local Windows profile temp path (8.3 short form of the account name) of the work machine.
  - Repro: `grep -c Users reports/phase-02/step-8/logs/rework3/*.log` -> 4 per file.
  - Expected fix: redact these paths with `tools/redact_paths.py` in a follow-up log-hygiene commit, and run the redaction on future e2e logs before commit.
  - Regression test: extend the leak grep (or secret_scan) with a `C:\\Users\\` / `/c/Users/` path pattern over `reports/`.
- REV-0297 [P3] `frontend/e2e/fidelity/fidelity.spec.ts` (seed) changed inside app commit e7bec06; `FROZEN_SHA256.txt` stale from a3d2d98 to 87e96f3
  - Problem: the measurement seed was edited in an app commit. BASELINE2 and the FINAL runs ran on harness files that were not in the freeze. I re-checked the content: only harness-only commits changed them, and no threshold or weight changed. So there is no integrity breach, but this is a process gap.
  - Expected fix: freeze `fidelity.spec.ts` + `structure.ts` (done now). Re-freeze in the same commit as every harness change, and write the harness tree hash into each fidelity log header.
  - Regression test: none (process). Optionally the fidelity script refuses to run when `sha256sum -c` fails.
- REV-0298 [P3] `reports/phase-02/step-8/REPORT_REWORK.md` "Evidence"
  - Problem: "vitest 98" is the rework5 count. HEAD has 99 tests (33b0686 added one). Backend logs carry no commit sha header.
  - Expected fix: cite the HEAD count (or add a fresh vitest log), and stamp `git rev-parse HEAD` into each verification log.
  - Regression test: none.
- REV-0299 [P3] `backend/platform_core/api/phase02/identity_views.py` ACTIVE_ORDER_STATES; `commercial_views.py` ChangeRequestCountsView
  - Problem: the KPI definitions «سفارش‌های فعال» (4 order states) and page-33 «باز» (incl. DRAFT) were chosen by the team. They are display aggregations, not enforced rules.
  - Expected fix: the employer confirms or corrects them at the mockup review. Change the constant only if he does.
  - Regression test: the existing rev0295 API tests then assert the confirmed set.
- REV-0300 [P3] `frontend/src/styles/pages.css:1666-1670` (`zoom: 0.8` on `.serial-center` at 901-1200 px), `:1787` (9px), `:1855` (9.5px)
  - Problem: on laptops the 12px xs text renders at about 9.6px, and the phone stage labels are 9.5px. Readability on the shop floor is at risk. In the full-page 390 shot the docked section tabs overlap card content (`page-02-390-final.jpg`); this may be a screenshot artifact of fixed elements.
  - Expected fix: add these to `control/UI_POLISH_BACKLOG.md`. Check on a real phone that the docked tabs do not hide content.
  - Regression test: a Playwright check that no visible text in the serial-center is below 11px at 1180/390 (polish phase).

No P0/P1/P2 issue remains.

## EMPLOYER ATTENTION
- معیار ۹۵٪ برای صفحه‌های ۱ و ۲ با هدف‌هایی سنجیده شده که تیم خودش از روی تصویرهای کانسپت ساخته است، چون این دو صفحه HTML موکاپ ندارند. تب سفارش صفحه ۲ و نمای تبلت هم فرض تیم است. در بازبینی موکاپ لطفاً این دو صفحه را با چشم خودتان تأیید کنید.
- دو تعریف شمارنده را تیم انتخاب کرده و باید تأیید شما را بگیرد:
  - «سفارش‌های فعال» در صفحه ۴ = سفارش‌های تأییدشده، ارسال‌شده به برنامه‌ریزی، متوقف و نیمه‌تحویل.
  - «درخواست‌های باز» در صفحه ۳۳ پیش‌نویس‌ها را هم می‌شمارد.
- حاشیه قبولی چند صفحه کم است: صفحه ۴ در تبلت ۹۵٫۴٪ و صفحه‌های ۱ و ۲ حدود ۹۵٫۸٪. هر تغییر ظاهری کوچک بعدی ممکن است آن‌ها را زیر ۹۵٪ ببرد.
- تست کاربری (UAT) پیشنهادی:
  - برای یک سفارش دو درخواست تغییر ارسال کنید. دومی باید رد شود.
  - استایلِ محصولِ پیش‌نویس را فعال کنید. باید با پیام «ابتدا محصول را فعال کنید» رد شود.
