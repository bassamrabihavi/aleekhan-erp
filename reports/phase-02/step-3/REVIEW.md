VERDICT: PASS
PHASE/STEP: PHASE_02 / 02.3 (Domain Engine)   COMMIT: 3fb0162 (report 606e8e2, status 790b6b5)
REVIEWER: aleekhan-reviewer (independent, fresh context, read-only on source), 2026-11-13, work-windows
NOTE: advisory until the employer confirms (CLAUDE.md). R14 is left to the employer at Gate time. The PASS carries two P2 items (REV-0230, REV-0231) that must be closed before the PHASE_02 Gate (02.8) and before any code rule revision is activated on the server.

## Reviewer re-runs (not taken from the report)
| Command | Result |
|---|---|
| `pytest test_phase02_coderule.py test_phase02_golden_harness.py test_phase02_engine_identity.py test_phase02_engine_orders.py` | 221 passed, 1 skipped (real golden file not set on this run), 54.8s |
| `pytest test_phase02_engine_changes.py test_phase02_engine_race.py test_phase02_schema.py` | 136 passed, 65.9s |
| `pytest` on the changed contract/PHASE_01 files (integration_events with the regenerated event catalogue, api_contract_planned_phase02, phase01_schema, phase01_step5_backend, phase01_step7_dec056_v13) | 84 passed |
| `ruff check .` / `ruff format --check .` (backend) | All checks passed / 221 files formatted |
| `mypy .` (backend) | Success: no issues found in 221 source files |
| `manage.py makemigrations --check --dry-run` (ALEEKHAN_ENV=test) | No changes detected |
| `backend/scripts/db_roundtrip.sh` on throw-away DB `aleekhan_rt_rev023` (0001..0024) | up -> zero -> up; schema diff EMPTY (10464 lines); ROUNDTRIP OK; DB dropped |
| `ops/db/roles_check.sh` on throw-away DB `aleekhan_roles_rev023` | passed=73 failed=0 (app role may `nextval` but not `setval` on the 3 new sequences); DB and roles dropped |
| `tools/secret_scan.py` | findings=0 -> PASS |
| `git show --stat 3fb0162 -- docs/api handoff control` | empty: OpenAPI, handoff and status file are not touched by the step commit |
| grep on the 3 step commits for 14-digit literals | synthetic only (types 90-93 or obvious fillers like `00000000000123`); no real code, customer, person or serial |
| Full `pytest -m "not perf"` | NOT re-run (8 GB machine, per caller instruction). The orchestrator log `logs/orch/pytest.log` shows 2331 passed, 2 skipped, 7 deselected |
| Real Planning golden run | NOT re-run (private data is out of bounds for the reviewer). `logs/orch/golden_real.log` shows: 2313 cases, 5 families, not_reproduced=0, malformed=0, legacy_only_style_0000=14, counts only |

## CHECKS
- R01 ✔ Scope is the 02.3 engine only: use cases in `product_identity/{coderule,codes,master,serials,refusals,usecase}.py` and `commercial/{orders,changes}.py`, migrations 0023/0024, tests and docs. No HTTP, no UI, OpenAPI unchanged (verified by `git show --stat`). The extras (0023 guard edge, 0024 grants) implement employer amendments of 2026-11-12/13 (DECISION_LOG.md:204-219).
- R02 ✔ (with flagged proposals) The rules trace to APPROVED decisions: DEC-005 segments/max+1/belt/count+1 (`coderule.py:1-22`, DECISION_LOG.md:141-153); style 0000 legacy-only (amendment, DECISION_LOG.md:214-219, `coderule.py:83-100`, CHECKs `0023:96-123`); DEC-058 representative masked for management_viewer (DECISION_LOG.md:194-195, `orders.py:252-289`); DEC-059 amendments: planner ≠ requester ≠ decider (`changes.py:377-381,417-420`, `0023:69-80`), cancel from hold before release (`orders.py:101-104,140-147`, guard `0023:39-47`). The unconfirmed choices are conservative refusals and are listed as PROPOSED in REPORT §7 (number format, held-order kinds, last-line cancel, no planning reject). See EMPLOYER ATTENTION.
- R03 ✔ Migrations 0023/0024 are reversible. Reviewer roundtrip gives an empty schema diff. New named CHECKs `ck_commercial_cr_planner_not_decider` and `ck_identity_product_code_sys_no_style_0000`. The sequences are non-cycling bigint, used only for technical numbers, never for the factory serial (`0023:15-17`). Concurrency: numbering is done under a row lock on the counting row (`master.py:300,336,444`). Race tests pass (reviewer re-run, `test_phase02_engine_race.py`).
- R04 ✔ Confirm allocates every line's serial, writes `line.serial_id`, version 1, audit and outbox in one UoW (`orders.py:782-838`). Allocation keys are derived per (order, line) (`orders.py:758-759`). REV-0220 is closed: a replay with another payload is refused with `IDEMPOTENCY_PAYLOAD_MISMATCH` (`serials.py:88-95`). Regression test: `test_phase02_engine_orders.py:418`. Apply writes version n+1, the next snapshot of each touched serial and cancels serials without reuse (`changes.py:457-628`, `serials.py:162-238`). A stale base is refused (`changes.py:468-473`). The race tests (one apply only, two CRs on one base, duplicate confirms) pass.
- R05 ✔ (engine) The pure rule has property tests and refuses wrapping past 9999 (`coderule.py:150-170`). The golden harness prints counts only and refuses a path inside the repo (`test_phase02_golden_harness.py:175-180`). Real run: 2313/2313 (orchestrator log). Publish is blocked: issuing needs an ACTIVE revision with the implemented spec, ≥20 reproducing golden cases per type, and approval by someone other than the maker with fresh MFA (`codes.py:244-421`). Open gaps: C-77 and belt coverage on real data (REV-0230, REV-0231).
- R06 ✔ (engine level; HTTP is 02.4) There is a permission per action through `authorize(...)` on every use case. Matrix 2.1: `commercial.change.planning_approve` is granted to planning_officer only, and the owner gets 9 read permissions (`0024:35-56`). There are per-role permission tests (`test_phase02_engine_orders.py:269`, `test_phase02_engine_changes.py:476`). Record not-found tests exist (`test_phase02_engine_orders.py:410`). Idempotency for confirm, issue and allocate holds, and a replay through the command layer has a single effect (`test_phase02_engine_race.py:204`). The OpenAPI work owed to 02.4 is listed in REPORT §7.12.
- R07 n/a — no UI in this step.
- R08 ✔ secret_scan findings=0; roles_check 73/0. Representative name: digits and `@` are refused (`orders.py:292-297`). It is not in events, audit values, version images or snapshots (`orders.py:181-212`). Every unmasked read is audited (`orders.py:276-285`), with tests at `test_phase02_engine_orders.py:297,319`. Real golden data stays outside the repo, and the reviewer grep found no real values. Private sources were not accessed by the reviewer.
- R09 ✔ Commercial writes only `commercial_*` tables and `line.serial_id`. Identity serial changes go through the Identity functions `allocate_serial`, `add_snapshot` and `cancel_serial`. A grep found no direct Identity-table write in `commercial/*.py`. Customer master writes are only in `product_identity/master.py`.
- R10 ✔ (scope) The ERP match is limited to a system actor and records the import batch (`codes.py:571-612`). Nothing is written to Rahkaran (DEC-005 B1). The import pipeline itself is 02.6.
- R11 ✔ (step level) The race tests ×3 are green in `logs/orch/race_x3.log`. The rollback plan is documented (REPORT §8). A partial rollback to 0022 is evidenced in `logs/phase02_partial_rollback_0024_0022.log`. Perf and backup are 02.7.
- R12 ✔ The tests are reproducible against real PostgreSQL (reviewer re-runs above). The real-data golden test skips with a stated reason when the file is absent; it is not faked.
- R13 ✔ The step commit updates STATE_TRANSITIONS.md §5.10, DATA_TABLE.md, ERD.md, PERMISSION_MATRIX_DRAFT.md v2.1, ERROR_CODES.md, EVENT_CATALOGUE.md and CHANGELOG.md. The event catalogue golden is regenerated and its test passes. Exception: the harness docstring on C-77 contradicts the report (part of REV-0230).
- R14 n/a — owner acceptance is the employer's at Gate time.

## ISSUES (none P0/P1)
- REV-0230 [P2] backend/platform_core/tests/test_phase02_golden_harness.py:21-22 — DEC-005 (DECISION_LOG.md:152) requires that "golden tests must assert that both [category lookups] give the same code" (C-77).
  - The harness docstring says C-77 "is checked by the extraction that produces the file", but REPORT §5 and §7.13 say C-77 is not covered by this run and stays open.
  - Neither the harness nor `logs/orch/golden_real.log` gives any C-77 evidence.
  - Repro: `grep C-77 logs/orch/golden_real.log` gives no hit.
  - Expected fix: before 02.8, the extraction emits both category values per case (on the work machine, outside the repo). The harness counts disagreements (counts only) and fails on any disagreement. The docstring is corrected to match.
  - Regression test: synthetic cases where the two category values differ fail the harness with a counted mismatch.
- REV-0231 [P2] backend/platform_core/product_identity/coderule.py:247-255 and backend/platform_core/product_identity/codes.py:244-266 — the belt rule (product number = buckle + width) is only checked when a case carries `buckle_type_code`/`belt_width_code`. Neither the harness summary nor `golden_report` reports or requires belt-checked cases. DEC-005 Q-C (DECISION_LOG.md:149) says "Belt is tested on its own".
  - The real run log has no belt-checked count, so the belt rule is not evidenced on real data.
  - Also, a rule revision can be submitted and approved with belt-type golden cases that carry no belt segments.
  - Repro: `golden_real.log` shows no belt counter. In `golden_report`, belt-type cases without the two fields produce no problem.
  - Expected fix:
    - The harness reports a `belt_checked` count and fails if the belt family has fewer than 20 belt-checked cases.
    - `golden_report` refuses (`BELT_SEGMENTS_REQUIRED`) a golden case of a `BELT_BUCKLE_WIDTH` type without both segments.
    - The orchestrator re-runs the real golden file with the belt fields.
  - Regression tests:
    - submit refused for belt-type cases without the segments;
    - the harness fails when the belt family has no belt-checked cases.
- REV-0232 [P3] backend/platform_core/product_identity/master.py:449-451 — the max+1 / count+1 numbering is not compared with the legacy distribution, for example styles of a (product, category) that are not contiguous. A collision is refused (`STYLE_NO_COLLISION`) with no decided resolution path (REPORT §7.7). This is acceptable as a conservative refusal. Expected: measure on the Planning baseline how often count+1 collides (counts only) and bring the result to the employer before 02.6 import. No test needed until the rule changes.
- Carried, still open (not defects of 02.3): REV-0221 [P3] (junit hostname redaction), REV-0223 [P3] (roundtrip function counts), REV-0203 (one open CR per order and CR expiry are not enforced, because they are not decided).
- Closed by this step: REV-0220 (see R04). REV-0222 is resolved by the DEC-059 amendment, guard `0023:39-47` and test `test_phase02_engine_changes.py:288`.

## EMPLOYER ATTENTION
- شماره‌های داخلی مشتری، سفارش و درخواست تغییر فعلاً پیشنهادی است: `CU-` و `SO-` و `CR-` با دست‌کم ۶ رقم. ممکن است در این شماره‌ها جاافتادگی باشد. لطفاً این قالب را تأیید یا اصلاح کنید.
- سفارشِ متوقف فقط ادامه یا لغو می‌شود. تغییر تعداد، تغییر تاریخ و افزودن ردیف روی آن پذیرفته نمی‌شود. آیا همین درست است؟
- لغو آخرین ردیف سفارش با «لغو ردیف» ممکن نیست و باید «لغو کل سفارش» زده شود. برنامه‌ریزی هم فقط می‌تواند تغییر تاریخ را تأیید کند و گزینهٔ رد ندارد. آیا این دو قاعده را تأیید می‌کنید؟
- اگر شمارهٔ استایل بعدی (تعداد + ۱) قبلاً در داده‌های قدیمی گرفته شده باشد، سیستم آن را رد می‌کند و شمارهٔ دیگری حدس نمی‌زند. روش حل این حالت باید با شما مشخص شود.
- پیش از Gate دو بررسی فنی روی دادهٔ واقعی برنامه‌ریزی باید کامل شود: یکی‌بودن دو جدول کد دسته (C-77) و آزمون جداگانهٔ قاعدهٔ کمربند. این کار با هماهنگ‌کننده است و از شما فقط تأیید نهایی خواسته می‌شود.
- در این گام چیزی برای تست کاربر (UAT) آماده نیست.
