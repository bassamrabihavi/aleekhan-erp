VERDICT: PASS
PHASE/STEP: PHASE_02 / 02.4 (Backend/API), re-review after rework 1   COMMIT: 14b49e4 (on ee9d4e7; report 1486a74, status 70545e5)
REVIEWER: aleekhan-reviewer (independent, fresh context, read-only on source), 2026-11-14, work-windows
NOTE: advisory until the employer confirms (CLAUDE.md). R14 is left to the employer at Gate time. The previous review is `REVIEW_r0.md` (REWORK: REV-0240 P1, REV-0241 P2, REV-0242/0243 P3). No P0/P1 remains. Two P3 items stay open (REV-0244 new, plus the carried ones).

## Reviewer re-runs (not taken from the report)
| Command | Result |
|---|---|
| `pytest test_api_phase02_contract.py test_api_phase02_flows.py test_phase02_golden_harness.py test_phase02_engine_identity.py test_authz_route_parity.py test_api_contract_planned.py test_phase02_coderule.py` | 1703 passed, 1 skipped (real golden file not set), 119 s |
| `ruff check .` / `ruff format --check .` (backend) | All checks passed / 233 files formatted |
| `mypy .` (backend) | Success: no issues found in 233 source files |
| `manage.py makemigrations --check --dry-run` (ALEEKHAN_ENV=test) | No changes detected |
| `git show --stat 14b49e4 -- handoff control backend/platform_core/migrations` | empty. The rework adds no migration and does not touch handoff or the status file. The control/ changes between ee9d4e7 and 14b49e4 are the separate decision commit 437d1ce |
| grep of 14-digit literals added by 14b49e4 | synthetic only (type 91 or fillers such as `00000000000123`, `99999999999999`) |
| grep of `logs/rework1`, `logs/orch-rework1` for passwords | 0 hits. junit hostname = `redacted-host` |
| db_roundtrip | not re-run in this cycle: the rework has no migration. Reviewer roundtrip of ee9d4e7 (`aleekhan_rt_rev024`, 0001..0025): ROUNDTRIP OK, empty schema diff (REVIEW_r0.md). Orchestrator `logs/orch-rework1/db_roundtrip.log`: ROUNDTRIP OK |
| Full `pytest -m "not perf"` | NOT re-run (8 GB machine, caller instruction). Orchestrator log `logs/orch-rework1/pytest.log`: 3064 passed, 2 skipped, 7 deselected |
| Real Planning golden run | NOT re-run (private data out of bounds). `logs/orch-rework1/golden_real.log` (counts only): 2313 cases, 5 families, not_reproduced=0, c77_checked=1218 c77_disagree=0, belt_checked=169, legacy_disputed=0, legacy_only_style_0000=14 (matches the 02.3 finding of 14) |

## Closure of the previous issues
- REV-0240 [P1] — CLOSED. The checks:
  - The server gate no longer skips any stored case: the `legacy_disputed` `continue` is removed from `golden_report` (`product_identity/codes.py` diff of 14b49e4).
  - The input is refused in two layers:
    - The engine accepts only `GOLDEN_INPUT_KEYS`; any other key is refused with `GOLDEN_FIELD_NOT_ALLOWED` (`codes.py` `add_golden_cases`, new lines 238-239).
    - The API refuses the harness-only fields before body validation (`identity_views.py` `_refuse_harness_only_fields`). They are also removed from `GoldenCaseInputs` (`bodies.py`).
  - The approver now sees `golden_summary`: total, per_family, belt_checked, legacy_only, not_reproduced and families_below_minimum (counts only; `serializers.py:201`).
  - Regression tests:
    - `test_phase02_engine_identity.py`: `test_rev0240_harness_only_golden_fields_are_refused_at_input`, `test_rev0240_a_stored_non_reproducing_case_blocks_submit_and_approve` (submit and approve both refuse `GOLDEN_CASE_MISMATCH`) and `test_rev0240_golden_summary_counts_belt_and_legacy_cases`;
    - HTTP: `test_api_phase02_flows.py:1258`.

    All pass in the reviewer run.
  - The docstring is aligned (`codes.py` `add_golden_cases`, `golden_report`) and the harness header now says it is offline evidence only.
- REV-0241 [P2] — CLOSED BY EMPLOYER DECISION (DECISION_LOG.md, "2026-11-14 — DEC-005 / DEC-006 follow-ups"):
  - The 14-digit code is authoritative for the 15 legacy belt rows.
  - Belt golden evidence uses only rows where the buckle agrees with the code.
  - The width is entered by the user for new belt products, and read from the code for legacy rows.
  - Golden v3 is consistent with this: legacy_disputed=0; family 02 count is 349 → 364 because the 15 rows are now counted as plain cases without belt fields; belt_checked=169.
  - Engine: belt create or preview without the width is refused with `BELT_SEGMENTS_REQUIRED` and the missing field named (`master.py:313-320`).
- REV-0242 [P3] — CLOSED. Each tracking block now checks its own read permission:
  - The style tracking view checks `identity.serial.read` and `commercial.order.read`.
  - The serial tracking view checks `commercial.order.read` and `commercial.change.read`.
  - A withheld block is empty or null and named in `withheld_sections` (`identity_views.py` diff).
  - Test: `test_api_phase02_flows.py:1371-1388`.
- REV-0243 [P3] — CLOSED. Stale-MFA 401 tests now cover code-rule reject, code-rule activate and the planning decision (`test_api_phase02_flows.py:1311,1328,1342`).
- Employer decision on allocateSerial — DONE. The operation is removed, `POST /identity/serials` answers 405 (`test_api_phase02_flows.py:692`), the contract is 0.8.2-draft with 65 operations, and the route parity and contract tests pass.

## CHECKS
- R01 ✔ The rework only touches the listed REV items and the two employer decisions of 2026-11-14 (`git show --stat 14b49e4`: api/phase02, product_identity, tests, docs, logs). There is no UI and no new migration.
- R02 ✔ Every rule changed by the rework traces to DECISION_LOG.md (2026-11-14 DEC-005/DEC-006 follow-ups). The undecided server-side exclusion (REV-0240) is removed.
- R03 ✔ The rework has no schema change and makemigrations is clean. 0025 was evidenced reversible in the previous cycle (reviewer roundtrip) and again in `logs/orch-rework1/db_roundtrip.log`. roles_check is 78/78 (`logs/orch-rework1/roles_check.log`).
- R04 ✔ Unchanged from REVIEW_r0. Race ×3: 38 passed in each run (`logs/orch-rework1/race_x3.log`). Concurrent confirm and replay through HTTP are in the reviewer run.
- R05 ✔ The publish gate checks and counts every stored case at submit and approve; the regression tests are listed above. The real golden run v3 shows not_reproduced=0, C-77 agreeing on 1218 cases and belt_checked=169 ≥ 20.
- R06 ✔ Route parity, the seeded permissions and MFA flags, and the Idempotency-Key and If-Match rules are all checked by contract tests on 65 operations. Field-level withholding is now per permission (REV-0242). 405 for the removed operation.
- R07 n/a — no UI in this step (02.5).
- R08 ✔ Security checks:
  - Fresh MFA is exercised on every MFA-flagged operation family.
  - The representative-name masking is unchanged.
  - Golden input is now an explicit allow-list.
  - secret_scan findings=0 (`logs/orch-rework1/secret_scan.log`); the reviewer leak grep is clean, and no private source was accessed.
- R09 ✔ No new cross-module write. `serializers.py` only reads `codes.golden_summary`.
- R10 ✔ (scope) No Rahkaran write. The legacy belt import rule is decided and will be implemented in 02.6.
- R11 ✔ (step level) See REV-0244 (list cost) for 02.7.
- R12 ✔ The tests are reproducible on real PostgreSQL (reviewer run). The real golden test skips with a stated reason when the file is absent.
- R13 ✔ CHANGELOG, API_RUNTIME, openapi 0.8.2-draft, DATA_TABLE, ERROR_CODES (`GOLDEN_FIELD_NOT_ALLOWED`, `SERIAL_ALLOCATED_AT_CONFIRM` removed), the refusal golden and the PERMISSION_MATRIX note are updated.
- R14 n/a — owner acceptance is the employer's at Gate time.

## ISSUES (none P0/P1)
- REV-0244 [P3] backend/platform_core/api/phase02/serializers.py:201 with identity_views.py `CodeRulesView.get` (`paginate(..., S.code_rule, ...)`) — `golden_summary` runs the full `golden_report` for every revision serialized: it builds the code of every stored case, up to thousands per revision. That includes every row of the list page and every write response.
  - Today there are few revisions, so this is not a correctness issue. On a list page it is O(revisions × cases) of query and CPU work.
  - Expected (by 02.7 perf): store the summary at submit/approve (as `golden_case_count` already is), or compute it only on the single-revision GET. Keep the counts identical.
  - Test: a list with N revisions issues a bounded number of queries.
- Open question (not a defect): the matrix row `identity.serial.allocate` is now unused after the removal of `allocateSerial`. It is kept so the approved matrix v2.1 does not change; dropping it is a matrix v2.2 decision for the employer.
- Carried, still open: REV-0203 (one open CR per order and CR expiry are undecided) and REV-0223 (roundtrip function counts). REV-0221 is resolved in the artifacts (junit hostname `redacted-host` in `logs/rework1/junit.xml`); the orchestrator may close it.

## EMPLOYER ATTENTION
- مجوز `identity.serial.allocate` پس از حذف `allocateSerial` دیگر به کاری نمی‌آید. اگر بخواهید آن را از ماتریس مجوزها حذف کنیم، ماتریس به نسخه 2.2 می‌رود و تصمیم شما لازم است.
- پرچم‌های مجوز «تصمیم برنامه‌ریزی روی تغییر تاریخ» (MFA، تأیید کسب‌وکار، تفکیک وظایف) هنوز پیشنهادی است و در Gate تأیید شما را لازم دارد.
- تصمیم‌های این فاز فعلاً در صندوق تأییدها (approval inbox) نمی‌آیند. این موضوع همراه رابط کاربری گام 02.5 باید روشن شود.
