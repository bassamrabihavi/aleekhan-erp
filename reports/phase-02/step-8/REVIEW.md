VERDICT: PASS
PHASE/STEP: PHASE_02 / 02.8 Report & Review    COMMIT: b359715 (code; step code also in 68b3362, 91b921a), reports 9850210, status e084df5
REVIEWER: aleekhan-reviewer (independent, read-only on code), 2026-11-16, machine work-windows
ADVISORY: DEC-036 is not approved yet, so this verdict is advisory. The employer confirms the step and decides the Gate. R14 is left to the employer.

## What I re-ran myself
- `git show --stat` for 68b3362 / 91b921a / b359715 / 9850210 / e084df5, and the full diff of b359715 (`tools/ci_local.sh`, +4/-2: the perf stage also runs `test_perf_phase02.py`) and the code part of 68b3362 (`planning_import.py`, 0028 docstring, `devtools/`, tests).
- `git rev-parse <commit>:<dir>` for 68b3362 / 91b921a / b359715 against the tree ids in `logs/ci/summary.md`:
  - backend `7d60380` is identical in 68b3362, 91b921a and b359715;
  - frontend `ae7a29f` is identical in 91b921a and b359715;
  - tools `08bc3f0` is b359715; 68b3362 / 91b921a = `b3901ca`;
  - ops / docs / .github are identical in all three.
- `ruff check backend` -> "All checks passed!"; `ruff format --check backend` -> "251 files already formatted".
- `python tools/secret_scan.py --history` on HEAD e084df5 -> 164 history commits, `findings=0 -> PASS` (1 known allowlisted test literal). This also covers 91b921a, b359715 and 9850210; the CI security stage ran at 05:47Z, before those commits existed.
- Leak grep over the 9850210 files:
  - The only 14-digit numbers are synthetic test fixtures that are already in the repo (`test_phase02_coderule.py:76`, `00000000000123`, `12345678901234`, etc.).
  - The `PASSWORD=` / `TOKEN=` matches are minified JS in `playwright-report/index.html`.
  - No user or account path appears; junit hostnames are `redacted-host`.
- Targeted DB tests `pytest test_phase02_step7_ops.py -k disputed` -> 4 ERROR at setup in my sandbox. PostgreSQL port 5433 is open, but my environment has no PG credentials (the run took 261 s, which fits connection timeouts). **I did not get an independent DB test result.** For DB evidence I rely on the committed CI logs, as briefed:
  - `pytest-unit-integration.xml` has failures="0" errors="0", 1761 tests.
  - The three new tests (`test_same_disputed_value_in_norder_and_codding_is_one_item`, `test_resolved_disputed_value_carries_over_to_a_later_import`, `test_dismissed_disputed_value_is_raised_again`) are present there and passed.
- Full pytest was not run (memory limit; brief).
- Screenshots: I viewed `phase02-page29-order-confirmed-1440-desktop.png` and `phase02-page02-serial-order-390-mobile.png`. Both are Persian RTL, carry the synthetic-data banner, and show the footer build `91b921ab3d23`, which has the same frontend tree as b359715. 16 PHASE_02 sets × 4 sizes are present (`ls screenshots | grep phase02`).

## CHECKS
- R01 ✔ Scope is right.
  - 02.8 delivers report, commit hash, migrations, tests, snapshots, Trace Map and issues: `PHASE_REPORT.md`, `TRACE_MAP.md`, `GATE_PACKET_FA.md`, `UAT_HOWTO_FA.md`, `logs/ci/`.
  - The code changes are only listed review fixes: REV-0271/0272/0273/0275, the E2E seed import and the CI perf stage.
  - No new migration (`git show --stat 68b3362` has no new file under migrations; 0028 is docstring only). No PHASE_03 work.
- R02 ✔ Nothing is invented.
  - The carry-over rule traces to DECISION_LOG 2026-11-16 (d1d2f57, `control/decisions/DECISION_LOG.md` last section).
  - "One decision per distinct value" traces to DECISION_LOG 2026-11-15.
  - "DISMISSED re-raises" is an interpretation that is flagged openly (REPORT §2, `planning_import.py` docstring). It is conservative (it never suppresses a conflict), so it does not count as an invented rule. It goes to the employer below.
- R03 ✔ Database evidence holds.
  - `05_migration.log`: up/zero/up ROUNDTRIP OK, schema diff EMPTY over 10548 lines, `makemigrations --check` "No changes detected".
  - `rollback/rehearsal_report.json`: A–D all PASS, run on commit 68b3362, whose backend tree equals b359715. D refuses at 0022 by design, and the PHASE_02 invariants hold after forward.
  - The conflict key changed format (`<sheet>!value:` -> `value:`). No production DB exists, so no data migration is needed (see REV-0283).
- R04 ✔ Integrity rules hold.
  - Carry-over writes one audit row per reused value with the item reference and no raw value (`planning_import.py` `_raise_disputed`).
  - The test asserts the value is absent from `audit.after` (`test_phase02_step7_ops.py`, REV-0271 test).
  - Serial race ID-02 (100 concurrent confirms, every 10th failing) passed in C8 unit (`pytest-unit-integration.xml`, 14.2 s) and in `orch/race_x3.log` (38 passed ×3).
  - `perf_phase02.json` `serial_allocation_concurrency`: workers 8, serials 200, gapless true.
- R05 ✔ The engine evidence is still valid.
  - `coderule.py` is unchanged since the 02.4 golden run (`git log 14b49e4..b359715 -- coderule.py` is empty). `codes.py` was changed only in 02.7 (stored summary; the 02.7 review verified that the gate is unchanged).
  - Real golden run: `step-4/logs/orch-rework1/golden_real.log` cases=2313 not_reproduced=0, per family [179, 253, 302, 364, 1215], c77_disagree=0.
  - The real-golden test is SKIPPED in CI with a reason (`04_unit.log:36`).
- R06 ✔ API checks pass.
  - `06_contract.log`: 18 passed, OpenAPI 0.8.4-draft unchanged in 02.8.
  - `07_authz.log`: 1481 passed.
  - No route or permission change in 02.8.
- R07 ✔ UI evidence is in place.
  - `09_e2e.log`: 32 passed on a real backend (channel msedge, line 14), plus 1 backend-down.
  - 16 PHASE_02 screenshot sets at 1440/1180/768/390. Spot-checked: RTL, synthetic banner, "در دست ساخت" labels.
  - The cosmetic remarks are in `control/UI_POLISH_BACKLOG.md` UIP-003.
- R08 ✔ Security checks pass.
  - Secret scan: 0 (my re-run on HEAD).
  - pip-audit runtime: 0 and npm audit: 0 (`11_security.log`). The 12 `pip` 25.0.1 advisories are in the dev venv only and are informational, under the same rule as PHASE_01.
  - Reports hold counts only (`orch/real_import.json`).
  - The checklist sign-off rows are blank for the employer.
- R09 ✔ Module ownership is respected.
  - `planning_import` only reads `integration.ConflictItem` (`_resolved_disputed`).
  - It writes conflicts through `integration.conflicts.raise_conflict` / `state.conflict`, with no direct write to another module's table.
  - Product code does not import `platform_core.devtools`. Only `ops/backup/drill_seed.py` and the tests do (grep).
- R10 ✔ Integration evidence holds.
  - Real import on a throw-away DB: APPLIED; 6 types, 111 categories, 2841 legacy codes, 226 conflicts (222 disputed values / 640 rows) (`orch/real_import.json`).
  - Conflicts are never auto-resolved. Carry-over applies only to RESOLVED items.
- R11 ✔ Operations evidence holds.
  - `10_perf.log`: 1 + 6 + 4 passed; PHASE_02 perf has now been added to CI by b359715.
  - `12_ops.log`: roles PASS, drill PASS, rehearsal A–D PASS.
- R12 ✔ The test evidence is reproducible, with REV-0280 against it.
  - All 13 CI stage logs are committed with a pinned command echo.
  - Each stage's tree is provably equal to b359715 for the code that stage exercises (tree-id comparison above).
  - The first-run failures are kept (`*_attempt1*.log`).
  - One evidence-hygiene defect: `commit.txt` was overwritten after the run (REV-0280, P2).
- R13 ✔ Documentation is updated.
  - `CHANGELOG.md` 02.8 section.
  - `docs/ops/BACKUP_RESTORE.md` has the devtools path.
  - The 0028 docstring was corrected.
  - TRACE_MAP §9 maps the mandatory outputs.
- R14 n/a The employer decides at the Gate (security checklist signature, T-004 UAT, Gate approval).

## Phase Gate evidence assessment (PHASE_02.md «Gate پذیرش»)
- **G1, 20+ real samples per family or block:** evidenced.
  - Five families have at least 179 cases each (S4 `golden_real.log`).
  - Family 06 has no samples and is blocked by `GOLDEN_CASES_INSUFFICIENT` / `TYPE_NOT_IN_RULE_SCOPE`. These are tested in the C8 unit suite.
- **G2, 100 concurrent requests without a duplicate serial:** evidenced (C8 unit plus race ×3).
- **G3, order/revision trace:** evidenced by E2E 17 (page 33 change -> version 2) and the screenshots of page 2 (snapshot, versions, timeline).
- **G4 and G8, roles and matrix:** matrix v2.2 is recorded, and the privacy test compares 16 roles × 69 operations. The employer still has to confirm it at the Gate.
- **G5, no open P0/P1:** confirmed. The open items are P3 (REV-0203, REV-0254) plus the matrix-row question.
- **G6, skips:** both skips have reasons.
- **G7, rollback:** evidenced, including the refusal-with-data boundary that the employer must acknowledge.
- **G9, CI linked to the commit:** substantively true by tree id. The `commit.txt` artifact itself was edited (REV-0280).
- **G10–G11:** evidenced.
- **G12, employer and auditor acceptance plus the signed checklist:** open, for the employer.

Conclusion: the Gate packet is complete and honest enough for the employer to decide. Nothing technical blocks the Gate.

## ISSUES
- REV-0280 [P2] `reports/phase-02/step-8/logs/ci/commit.txt:1` — the committed file is a machine-generated artifact that was edited by hand.
  - **Problem:** it reads `b3597158…`, but the stage that writes it logged `commit 68b33622…, modified tracked files: 1` (`logs/ci/13_artifacts.log:42`, `ci_run.out:1853`). `summary.md` says `91b921ab…`, and b359715 did not exist until 06:18:52Z, after the run ended (06:18:21Z). The substantive claim survives: the per-directory tree ids equal b359715, and backend stages ran on a tree identical to b359715. However, the CI run was a composite over three worktree states, and the artifact misstates that.
  - **Repro:** `cat logs/ci/commit.txt; grep -n "^commit " logs/ci/13_artifacts.log; head -3 logs/ci/summary.md`.
  - **Expected fix:** do not edit CI artifacts. Either restore the original value and add a short `EVIDENCE_NOTE.md` that maps each stage to its tree, or, from PHASE_03 on, run the Gate CI once on a clean committed HEAD (`worktree_modified_files.txt` = 0).
  - **Regression:** `ci_local.sh` should refuse, or loudly label, a run whose worktree is dirty or whose HEAD changes between stages. Suggested: record HEAD per stage in each log header.
- REV-0281 [P3] `reports/phase-02/TRACE_MAP.md` (C8 paragraph) and `GATE_PACKET_FA.md` (header: "بررسی خودکار کامل روی همین commit در ۱۳ مرحله از ۱۳ قبول شد") — the wording says one full CI run on b359715.
  - **Problem:** the run actually spans 68b3362 + worktree for stages 1–7 and 11–13, 91b921a for frontend/e2e, and 91b921a + modified `ci_local.sh` for perf. TRACE_MAP partly discloses this; the Persian Gate packet does not.
  - **Expected fix:** one line in the Gate packet: «اجرای ترکیبی؛ هم‌ارزی با b359715 با شناسه درخت کد اثبات شده».
  - No test needed.
- REV-0282 [P3] `reports/phase-02/step-8/REPORT.md` §6 — the text says "T-004 is added for the employer".
  - **Problem:** T-004 is not in `control/PROJECT_STATUS.json` (only T-001..T-003). That is correct per the loop, which adds it after PASS, but the sentence claims it is already done.
  - **Expected fix:** run `status.py test-add` for T-004 after this PASS.
- REV-0283 [P3] `backend/platform_core/product_identity/planning_import.py` `disputed_conflict_key` — the conflict key format changed from `<sheet>!value:<h>` to `value:<h>`.
  - **Problem:** a DB that holds items under the old key will not match them for carry-over or for "already open". No production or staging DB exists, so the impact is nil now.
  - **Expected fix:** note in `docs/ops/ROLLBACK.md` or the 02.8 REPORT that any pre-02.8 test DB must be re-imported. From the Gate on, key-format changes need a data migration (consistent with REV-0274).
  - **Regression:** none required now.
- REV-0284 [P3] `reports/phase-02/GATE_PACKET_FA.md:3` — the text says «هر ۸ گام فاز قبول شده است» while 02.8 is still IN_REVIEW. The next bullet and the table qualify it.
  - **Expected fix:** after this review, update the line to cite this file.

No P0/P1. REV-0280 (P2) does not invalidate any result, because tree equivalence is independently provable (commands above). It should be fixed before or with the step PASS bookkeeping.

## EMPLOYER ATTENTION
- **DISMISSED:** طبق تصمیم ۲۵ آبان، مقدار مشکوکی که «حل‌شده» باشد در فایل‌های بعدی دوباره پرسیده نمی‌شود. اما اگر موردی «رد/بی‌اثر» (DISMISSED) شده باشد، دوباره در صف می‌آید. سؤال: آیا همین را می‌خواهید؟ (پیشنهاد مجری: بله، چون رد کردن تصمیم درباره مقدار نیست.)
- **تصمیم‌های Gate:**
  - آزمون T-004 در مرورگر؛
  - امضای چک‌لیست امنیتی فاز ۲ (پذیرش با شرط برای موارد وابسته به سرور نهایی)؛
  - پاسخ REV-0203 (یک درخواست تغییرِ باز برای هر سفارش، و انقضا)؛
  - پاسخ REV-0254 (نمایش نام درخواست‌کننده)؛
  - پذیرش مرز برگشت پایگاه داده (با داده فاز ۲، فقط بازیابی از پشتیبان)؛
  - حذف یا نگه‌داشتن ردیف `identity.serial.allocate` در ماتریس.
- **R14:** پذیرش نهایی فاز فقط با شماست.
