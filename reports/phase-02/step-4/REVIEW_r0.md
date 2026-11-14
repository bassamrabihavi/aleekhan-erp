VERDICT: REWORK
PHASE/STEP: PHASE_02 / 02.4 (Backend/API)   COMMIT: ee9d4e7 (report 7b19faa, status 0bb1795)
REVIEWER: aleekhan-reviewer (independent, fresh context, read-only on source), 2026-11-14, work-windows
NOTE: advisory until the employer confirms (CLAUDE.md). R14 is left to the employer at Gate time. The API layer itself is in good shape. One P1 blocks PASS: the new server-side `legacy_disputed` exclusion in the code-rule publish gate (REV-0240).

## Reviewer re-runs (not taken from the report)
| Command | Result |
|---|---|
| `pytest test_api_phase02_contract.py test_api_phase02_flows.py test_phase02_jalali.py test_phase02_golden_harness.py test_authz_route_parity.py test_api_contract_planned.py` | 1617 passed, 1 skipped (real golden file not set), 155 s, rc=0 |
| `pytest test_phase02_engine_{changes,identity,orders,race}.py test_phase02_schema.py test_phase02_serial_allocation.py test_phase02_coderule.py test_schema.py test_phase01_schema.py` | 400 passed, 142 s, rc=0 |
| `ruff check .` / `ruff format --check .` (backend) | All checks passed / 233 files formatted |
| `mypy .` (backend) | Success: no issues found in 233 source files |
| `manage.py makemigrations --check --dry-run` (ALEEKHAN_ENV=test) | No changes detected |
| `backend/scripts/db_roundtrip.sh` on throw-away DB `aleekhan_rt_rev024` | ROUNDTRIP OK, schema diff EMPTY (10546 lines), DB dropped |
| `git show --stat ee9d4e7 -- handoff control` | empty: handoff and status file untouched by the step commit |
| grep of 14-digit literals added by the step commit (outside the OpenAPI file and reports) | 1 literal, `02910099990001`: synthetic type 91 |
| grep of step logs for passwords/PGPASSWORD | 0 hits. junit hostname = `redacted-host` |
| Full `pytest -m "not perf"` | NOT re-run (8 GB machine, caller instruction). Orchestrator log: 3060 passed, 2 skipped, 7 deselected |
| Real Planning golden run | NOT re-run (private data is out of bounds). `logs/orch/golden_real.log`: 2313 cases, not_reproduced=0, c77_checked=1218 c77_disagree=0, belt_checked=169, legacy_disputed=15 (counts only) |

RT: reviewer `db_roundtrip.sh` (PG_BIN=tools/pgsql/bin, DB `aleekhan_rt_rev024`, 0001..0025): up -> zero -> up, 0025 applied and unapplied OK, schema diff EMPTY (10546 lines compared), DB dropped, ROUNDTRIP OK (rc=0).

## CHECKS
- R01 ✔ The scope is the step text (permission scoped + rate limit + ETag + pagination + request id + OpenAPI + real tests), in `api/phase02/*` with 66 operations (`test_api_phase02_contract.py:74-76`). The engine changes trace to employer amendments of 2026-11-14 (DECISION_LOG.md:221-235) and to the 02.3 review items REV-0230/0231/0232. There is no UI.
- R02 ✘ Numbers with the Jalali year, held order, style first-free number and planning reject all trace to DECISION_LOG.md:223-234. **But** the `legacy_disputed` exclusion of golden cases (harness and server `golden_report`) has no decision behind it. DEC-005 Q-D (DECISION_LOG.md:150) covers only non-14-digit legacy rows imported as history ("planning decides each one"). It does not cover rule counterexamples such as the 15 BUCKLE_MISMATCH belt rows. See REV-0240/REV-0241.
- R03 ✔ Migration 0025 is reversible. Its parts:
  - counter PK (kind, jalali_year);
  - CHECKs on kind, year and value;
  - guard trigger: starts at 1, +1 only, no key change, no delete; plus a no-truncate trigger;
  - planning-reject pair, closes and independence CHECKs;
  - CR guard with exactly one more edge (`0025_phase02_api_numbers.py:47-55`).

  Reverse re-creates the 0023 sequences past the plain-format maximum. makemigrations is clean. The roundtrip is the reviewer re-run above. The orchestrator `roles_check` result is 78/0, including reset, +5, insert>1, delete and truncate refused (`ops/db/roles_check.sh:199-213`).
- R04 ✔ Every write goes through `write()`. That means the Idempotency-Key is scoped to principal + endpoint (`api/idempotent.py:48-61`), inside the 02.3 unit of work with audit and outbox.
  - Concurrent confirms through HTTP give exactly one 200 and contiguous serials with no duplicate (`test_api_phase02_flows.py:1184-1207`).
  - A replay returns the same body with one serial. A key reused with another body gives 422 (`:1085-1115`).
  - Race tests ×3 are green (orchestrator `race_x3.log`; reviewer re-ran `test_phase02_engine_race.py` once).
- R05 ✘ The Jalali conversion is checked against known Nowruz and leap dates, a day-by-day walk from 1395 to 1410 and the Tehran instant boundary (`test_phase02_jalali.py`). The reviewer spot-checked 2026-11-14 = 1405/08/23 by hand. C-77 now fails on any disagreement (`coderule.py` `c77_disagrees`; harness test). **But** the publish gate is weakened: `golden_report` skips any case whose inputs carry `legacy_disputed`, at both submit and approve (`codes.py:266-267`, callers `:306,:343`). See REV-0240. The belt width is not independent; see REV-0241.
- R06 ✔ The following tests cover the permission and contract rules:
  - Route parity: every routed permission equals the contract's `x-aleekhan-permission` (`test_api_phase02_contract.py:302`).
  - Seeded MFA flags equal the operations (`:316`).
  - Writes need Idempotency-Key and If-Match (`:353,:367`).
  - employee gets 403 everywhere and management_viewer 403 on every write (`:395,:409`).
  - The role-deny table covers 11 decisive writes (`flows.py:1040-1068`).
  - A non-GLOBAL assignment sees nothing (`:1071`).
  - 429 per principal (`:1174`), 412 on a stale ETag, cursor pagination and request id (`:1118`).

  BOLA: line operations check that the line belongs to the order in the path (`commercial_views.py:155-158`). OpenAPI is 0.8.0-draft and validated (orchestrator log). Responses are schema-validated in every flow test (`ok()`/`refused()`).
- R07 n/a — no UI in this step (02.5).
- R08 ✔ Security checks:
  - Session auth only; anonymous callers get 401 (`flows.py:1234`).
  - Fresh MFA is checked on issue, code-rule approve, confirm and decide (`flows.py:415-426, 617-621, 838-846`).
  - Representative name (DEC-058): only `getCustomerOrder` returns it, through the engine's masked and audited `get_order` (`commercial_views.py:118-124`). Write responses carry `[REDACTED]` (`serializers.py:372-375`), and summaries do not carry it.
  - secret_scan findings=0 (orchestrator log). Reviewer leak grep is clean, and no private source was accessed.

  Minor: REV-0242, REV-0243.
- R09 ✔ `product_identity/external.py` reads commercial models only to check that a target exists, and writes only `ExternalRef`. Commercial writes stay in `commercial/*`.
- R10 ✔ (scope) No Rahkaran write. Import is 02.6.
- R11 ✔ (step level) A rollback plan is given (REPORT §8): reverse to 0024 is refused while a planning-rejected CR exists, by design. Perf and backup are 02.7.
- R12 ✔ Tests run against real PostgreSQL with real sessions, and the reviewer re-runs are reproducible. The real golden test skips with a stated reason when the file is absent; it is not faked.
- R13 ✔ Updated: CHANGELOG, API_RUNTIME §14, STATE_TRANSITIONS (planning reject, held order DECIDED), DATA_TABLE, ERROR_CODES, EVENT_CATALOGUE (golden regenerated, test passes) and PERMISSION_MATRIX 02.4 note. Exception: the `add_golden_cases` docstring ("a case the engine does not reproduce blocks the submit, it is never corrected", `codes.py:203-204`) is now contradicted by the skip at `:266`.
- R14 n/a — owner acceptance is the employer's at Gate time.

## ISSUES
- REV-0240 [P1] backend/platform_core/product_identity/codes.py:266-267 (with api/phase02/bodies.py:114 and openapi-draft.yaml GoldenCaseInputs.legacy_disputed) — the server-side publish gate now silently ignores any golden case whose `inputs` carry `legacy_disputed`.
  - The rule maker (product_data_steward, `addCodeRuleGoldenCases`) can set that field freely, with any text of 3 or more characters.
  - A case that contradicts the rule is then neither checked nor counted, at submit or at approve.
  - `golden_case_count` excludes it (`codes.py:311`), and there is no endpoint that lists the cases. The approver (CRA, MFA) therefore cannot see that counterexamples were set aside.
  - No decision allows this. DEC-005 Q-D is about non-14-digit history rows, and there "planning decides each one". There is no server-side test of this path (grep of `test_phase02_engine_identity.py` / `test_phase02_coderule.py` gives 0 hits).
  - Repro:
    1. DRAFT revision.
    2. `addCodeRuleGoldenCases` with 20 reproducing cases of the type, plus 1 case whose `expected_code` does not reproduce, carrying `"legacy_disputed": "xyz"`.
    3. `submit-review` → accepted, and `golden_case_count`=20. The mismatching case is invisible.
  - Expected fix: until the employer decides, the server must not exclude cases. Either:
    - (a) refuse `legacy_disputed` in `addCodeRuleGoldenCases` (keep it only in the offline harness report); or
    - (b) treat a disputed case as blocking submit/approve until a recorded planning resolution exists.

    Whichever option, the count of disputed cases and their reasons must be visible in the revision read model and audited.

    Then align the docstring at `codes.py:203-204`.
  - Regression test: submit and approve with a non-reproducing case marked `legacy_disputed` are refused (or the field is refused with 400). The revision read model shows the disputed count.
- REV-0241 [P2] backend/platform_core/tests/test_phase02_golden_harness.py:148-151 + REPORT §5 — REV-0231 is only half closed.
  - The width is taken from `product_no[2:4]`, so `buckle + width == product_no` checks only the buckle half.
  - 15 of the 184 belt rows contradict the rule (BUCKLE_MISMATCH). The extraction relabeled them `legacy_disputed`, with no decision, so they are excluded from the minimum.
  - Expected:
    - an employer/planning decision on those 15 rows (counterexamples vs. bad legacy rows);
    - an independent width source, before any belt rule revision is activated and before the 02.6 import.
  - Regression: the real golden re-run with the decided labelling, with `legacy_disputed` limited to rows that have a recorded decision.
- REV-0242 [P3] backend/platform_core/api/phase02/identity_views.py:367-402 and :776-821 — two views return data protected by a second permission without checking it:
  - `getStyleTracking` (permission `identity.product.read`) returns serials;
  - `getSerialTracking` (`identity.serial.read`) returns order versions and change-request audit references.

  Matrix v2.1 gives identical role sets for these permissions, so nothing leaks today. A later matrix change would leak silently. Expected: check `identity.serial.read` / `commercial.order.read` / `commercial.change.read` for those sections, or list them as `unavailable_sections`. Test: a role holding only the first permission does not get the other sections.
- REV-0243 [P3] backend/platform_core/tests/test_api_phase02_flows.py — fresh MFA is exercised over HTTP for issue, code-rule approve, confirm and decide, but not for `decidePlanningChangeRequest`, `rejectCodeRuleRevision` or `activateCodeRuleRevision`. These are covered only by the seeded-flag equality test. Expected: one stale-MFA 401 case each.
- Carried, still open: REV-0203 (one open CR per order and CR expiry are undecided) and REV-0223 (roundtrip function counts). REV-0221 appears resolved in this step's artifacts (junit hostname `redacted-host`); the orchestrator may close it.
- Closed by this step: REV-0230 (C-77 counted and failing, `golden_real.log` c77_disagree=0 over 1218 cases) and REV-0232 (first free style number, audited, concurrent HTTP test `flows.py:1210`).

## EMPLOYER ATTENTION
- ۱۵ ردیف کمربند در داده واقعی با قاعده «شماره محصول = کد سگک + عرض» نمی‌خوانند. این ردیف‌ها بدون تصمیم شما «مورد اختلاف» علامت خورده و از آزمون کنار گذاشته شده‌اند. لازم است شما یا واحد برنامه‌ریزی بگویید این‌ها داده قدیمی غلط‌اند یا استثنای واقعی قاعده.
- عرض کمربند در فایل برنامه‌ریزی ستون جداگانه ندارد و فعلاً از خود شماره محصول خوانده می‌شود. لطفاً بگویید عرض کمربند از کجا باید خوانده شود.
- `allocateSerial` (تخصیص سریال جدا از تأیید سفارش) همیشه رد می‌شود. در قرارداد بماند یا حذف شود؟
- پرچم‌های مجوز «تصمیم برنامه‌ریزی روی تغییر تاریخ» (MFA، تأیید کسب‌وکار، تفکیک وظایف) هنوز پیشنهادی است و تأیید شما را لازم دارد.
- تصمیم‌های این فاز فعلاً در صندوق تأییدها (approval inbox) نمی‌آیند. این موضوع همراه رابط کاربری گام 02.5 باید روشن شود.
