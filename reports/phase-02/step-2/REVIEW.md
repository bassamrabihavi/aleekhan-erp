VERDICT: PASS
PHASE/STEP: PHASE_02 / 02.2 (Database)   COMMIT: c8b3dff (report 0f7f6a5, status 1d92d76)
REVIEWER: aleekhan-reviewer (independent, fresh context, read-only on source), 2026-11-12, work-windows
NOTE: advisory until the employer confirms (CLAUDE.md); R14 is left to the employer at Gate time.

## Reviewer re-runs (not taken from the report)
| Command | Result |
|---|---|
| `pytest test_phase02_schema.py test_phase02_serial_allocation.py` (incl. ID-02 100-confirm race, ID-04 race) | 61 passed, 0 skipped, 46.9s |
| `pytest` on the 6 changed PHASE_01/contract test files (authz_engine, phase01_schema, step5_backend, step7_dec056_v13, test_schema, api_contract_planned_phase02) | 90 passed |
| `ruff check .` / `ruff format --check .` (backend) | All checks passed / 205 files formatted |
| `mypy .` (backend) | Success: no issues found in 205 source files |
| `manage.py makemigrations --check --dry-run` (ALEEKHAN_ENV=test) | No changes detected |
| `backend/scripts/db_roundtrip.sh` on throw-away DB `aleekhan_rt_review` (PG 17.9) | up -> zero -> partial -> up; schema diff EMPTY (10423 lines); ROUNDTRIP OK |
| `ops/db/roles_check.sh` on throw-away DB `aleekhan_roles_review` | passed=66 failed=0 (incl. new identity_/commercial_ grants, trigger-disable refused for app role) |
| `tools/secret_scan.py` (with test env values loaded) | findings=0 -> PASS |
| grep `reports/phase-02/step-2/` for account/path leaks | 0 hits |
| Full `pytest -m "not perf"` | NOT re-run (8 GB machine, per caller instruction); orchestrator log `logs/orch/pytest.log` shows 2029 passed, 1 skipped (clamd) |

## CHECKS
- R01 ✔ Scope = 02.2 DB layer only: migrations 0019-0022, models, one allocation primitive (`product_identity/serials.py`), tests, docs, grants; no API/UI; OpenAPI unchanged (`logs/openapi_unchanged.log`). Tables match PHASE_02.md domain list (Customer, Product/Style, CodeRuleRevision, Order header/line, Serial, Snapshot, External Ref).
- R02 ✔ Every rule traced to an APPROVED decision in `control/PROJECT_STATUS.json`: counter 63001 / legacy <63000 / plain integer / gapless (DEC-006, `0021_phase02_seed_catalogue.py:43-50`, `0020:336-351`); 4 order types = DECISION_LOG.md:200 (DEC-058); matrix rows = DEC-057_PACKET.md:34-54 cell by cell (`0022:84-107`) + owner direct-decide (DEC-057 resolution "owner may decide directly except own requests"); DEC-059 transitions (`0020:489-501`); undecided items (one open CR, 30-day expiry) explicitly NOT enforced (ERD.md §7.4, REV-0203).
- R03 ✔ Named PK/FK/unique/check/index; every PHASE_02 FK PROTECT + indexed (`test_every_phase02_foreign_key_is_protect_and_indexed`); Code14 varchar(14)+`^[0-9]{14}$` (ID-01 tests :234-271); migrate up/down + schema diff reproduced by reviewer; partial rollback to 0018 evidenced in `logs/phase02_partial_rollback.log`.
- R04 ✔ Allocation under `SELECT ... FOR UPDATE` of the single counter row, +1 only (`serials.py:76-80`, guard `0020:327-330`); serial, snapshot v1, audit and outbox in the caller's UoW (`serials.py:81-121`); deferred commit-time checks for gapless / snapshot v1 / exactly one line (`0020:337-412`); ID-02 (100 confirms, 10% forced failures, no dup, no gap) and ID-04 (6 duplicate confirms, single effect) re-run green.
- R05 ✔ (DB level) No code-issue engine yet; DB requires ACTIVE rule revision for system-issued codes and code = 02 + style segments (`test_issuing_needs_an_active_rule...`). Golden tests with real Planning data correctly deferred to 02.3 (not faked).
- R06 ✔ n/a for API (02.4). Permission seed per action verified: `test_matrix_v20_seed_equals_section_7_of_the_matrix_document_cell_by_cell` + reviewer comparison with DEC-057 packet; 4 fresh-MFA actions exactly as packet.
- R07 n/a — no UI in this step.
- R08 ✔ secret_scan findings=0; roles_check 66/0 (app role cannot DELETE serial, UPDATE snapshots/versions, INSERT counter, or disable guard triggers); seeds generic only (`test_seed_is_generic_only...`); rep name stored as name only, no contact columns (`test_representative_name_is_only_a_name...`), masking deferred to 02.3/02.4 (stated). No private source read; only 14-digit literals in diff are `00012345678901` and `02010790010001` (test/negative fixtures).
- R09 ✔ Identity owns `identity_*` (serials.py writes only Serial/SerialSnapshot/SerialCounter + audit/outbox); Commercial owns the single pairing column `commercial_customer_order_line.serial_id` (ERD.md §7.1, REV-0201). Cross-module write in `phase02_factories.confirm_order` is test-only.
- R10 ✔ (schema only) imported rows carry raw-row/batch provenance (`test_imported_rows_point_to_their_raw_row...`); legacy serial >= 63000 refused by trigger so import must route to conflict queue (02.6, stated). Pipeline itself is 02.6.
- R11 ✔ (step level) race tests x3 green in orchestrator log (`logs/orch/race_x3.log`, 29 passed each); rollback plan documented (REPORT §8). Perf/backup is 02.7.
- R12 ✔ Tests reproducible against real PostgreSQL (reviewer re-run). Minor: `logs/orch/pytest.xml` is not well-formed XML (see REV-0221).
- R13 ✔ ERD.md §7, DATA_TABLE.md, STATE_TRANSITIONS.md, PERMISSION_MATRIX_DRAFT.md v2.0, EVENT_CATALOGUE.md, CHANGELOG.md updated in c8b3dff; OpenAPI drift owed to 02.4 is listed (REPORT §7.4).
- R14 n/a — owner acceptance is the employer's at Gate time.

## ISSUES (none P0/P1)
- REV-0220 [P2] backend/platform_core/product_identity/serials.py:73-75 — idempotent replay returns the existing serial by key only; it does not compare the replayed request (customer/style/revision/order) with the stored serial, so a reused key with a different payload silently returns the wrong line's serial. Repro: call `allocate_serial` twice in one UoW with the same `idempotency_key` but a different `style_id` -> second call returns `replayed=True` with the first style. Expected fix (02.3): on replay, compare the identifying fields and raise a conflict error (e.g. IDEMPOTENCY_KEY_REUSED) on mismatch. Regression test required: same key + different payload -> refused, no new number, no event.
- REV-0221 [P3] reports/phase-02/step-2/logs/orch/pytest.xml:1 — not well-formed XML (`hostname="<host>"` written by redaction), so the junit artifact cannot be parsed by CI tooling. Repro: `ElementTree.parse(...)` -> "not well-formed (invalid token): line 1, column 214". Expected fix: redact to an XML-safe token (e.g. `hostname="redacted-host"`) in `redact_paths.py`; already proposed in REPORT §7.10. Regression test: redaction output of a junit file parses.
- REV-0222 [P3] backend/platform_core/migrations/0020_phase02_db_guards.py:489-501 — an order ON_HOLD whose previous state is CONFIRMED (not yet released) cannot be CANCELLED directly; it must be resumed first. Not contradicting DEC-059 (cancel only before release), but this is an implicit rule. Expected: confirm with the employer at 02.3 or document it in STATE_TRANSITIONS.md. No test needed unless the rule changes.
- REV-0223 [P3] backend/scripts/db_roundtrip.sh — the post-rollback check counts generic functions only; add `identity_%`/`commercial_%`/`phase02_%` function counts (REPORT §7.10). The implementer's separate partial-rollback log shows "PHASE_02 functions left: 0", so evidence exists today.

## Open items carried (from REPORT §7, verified as honestly stated, not defects of 02.2)
- Owner holds 3 PHASE_02 decide/confirm permissions but no PHASE_02 read permission (DEC-057 table as written).
- DEC-059 due-date planning approval is enforced in DB (`ck_commercial_cr_due_date_planning_approved`, planner != requester) but no matrix permission grants it yet; whether planner may equal the deciding manager is open.

## EMPLOYER ATTENTION
- مالک طبق DEC-057 می‌تواند سفارش را تأیید کند و درباره درخواست تغییر و قاعده کد تصمیم بگیرد، ولی هنوز اجازه «دیدن» سفارش، مشتری و سریال را ندارد. آیا مالک باید اجازه مشاهده این‌ها را هم داشته باشد؟
- تغییر تاریخ تحویل به تأیید برنامه‌ریزی نیاز دارد (DEC-059). باید روشن شود کدام نقش این تأیید را می‌دهد. همچنین آیا همان مدیری که درباره درخواست تصمیم گرفته، می‌تواند این تأیید را هم بدهد؟
- سفارشی که متوقف شده و هنوز به برنامه‌ریزی ارسال نشده، فعلاً مستقیم لغو نمی‌شود: اول باید از توقف خارج شود. آیا همین قاعده درست است؟
- در این گام چیزی برای تست کاربر (UAT) آماده نیست.
