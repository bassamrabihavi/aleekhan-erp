VERDICT: PASS
PHASE/STEP: PHASE_02 / 02.1 Discovery & Contract   COMMIT: 1c69e9911b89affd11d37dafc4ef32b882a7d4d5 (fee0ed4 = status/report sha only)
REVIEWER: aleekhan-reviewer (independent, read-only), machine work-windows, 2026-11-11
INPUTS: `git show 1c69e99`, `git show fee0ed4`, reports/phase-02/step-1/REPORT.md + REPORT.json, handoff/03_PHASE_PLAN/PHASE_02.md, REVIEW_CHECKLIST R01-R14, handoff/05_SECURITY/*
Private sources: not read. ALEEKHAN_PRIVATE_DIR was not used by the reviewer, so golden extraction is not evidenced (it is correctly declared SKIPPED/pending, golden_pending.log).

## Reproduced by the reviewer
| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` (backend) | All checks passed / 193 files already formatted (the report's 305 is the repo-wide count) |
| `mypy .` (backend) | Success: no issues found in 193 source files |
| `pytest test_api_contract_planned_phase02.py test_api_contract_planned.py test_api_contract.py test_phase01_schema.py` | 74 passed |
| `pytest -m "not perf"` full suite, PG test DB (PGDATABASE=test_rev021 -> pytest-django test_test_rev021) | **1967 passed, 1 skipped, 7 deselected**. This matches logs/orch/pytest.log. The skip is the real-ClamAV contract test (clamd not configured) |
| `openapi_spec_validator docs/api/openapi-draft.yaml` | OK |
| Semantic OpenAPI diff 4b490d2 -> 1c69e99 (own yaml script) | 0.6.3 -> 0.7.0-draft. 88 old paths: none removed, **none changed**. No component removed or changed. Changed top-level keys: only `info`, `tags`, `x-aleekhan-conventions`. Added: 48 paths / 63 ops, 14 carry `x-aleekhan-blocked-by` (DEC-005/006/057/059). The textual 2213 "deletions" are reformatting only |
| `tools/secret_scan.py --history` | findings=0 -> PASS (1 allowlisted test literal) |
| `tools/verify_handoff.py` | OK=300, KNOWN_DEFECT=1 (DEC-044), failures=0 |
| `git diff --stat 4b490d2 1c69e99 -- handoff` | empty: handoff/ is untouched |
| REPORT.json against handoff REPORT_SCHEMA.json (jsonschema) | valid; commit_sha 1c69e99 |
| junit hostname in logs/pytest.xml + logs/orch/pytest.xml | `hostname="<host>"` (sanitised; REV-0103 lesson applied) |

## CHECKS
- R01 ✔ Scope. The diff holds docs/discovery, decision packets, the OpenAPI draft, 3 contract test files and the `CONTRACT_VERSION` constant (backend/platform_core/api/views.py:32). It has no migration, no business code and no routed endpoint. Route parity still asserts that no planned path is served (test_api_contract.py). The step text "هنوز داده واقعی mutate نکن" is respected.
- R02 ✔ No P0 rule is guessed. Code segments are not modelled (DATA_TABLE §1 and test_product_code_segments_are_not_modelled_while_dec_005_is_open). The serial has no pattern (SerialNumber schema, test at test_api_contract_planned_phase02.py:212). Every packet labels its recommendation "فقط پیشنهاد". C-49/C-52/C-53 explicitly refuse to derive a rule from single samples. Minor unlabelled assumptions: REV-0203.
- R03 n/a No migration in this step (02.2). DATA_TABLE §2-§5 gives the PK/unique/check design, including UNIQUE(namespace, number), UNIQUE(order_line_id) and UNIQUE(allocation_idempotency_key), and INV-02-01..09 for 02.2/02.3.
- R04 n/a No write path. The design is consistent with ID-02/03/04: snapshot v1 + outbox in the allocation transaction, never `MAX()+1` (STATE_TRANSITIONS §5.4, R-40). The cross-module ownership gap is REV-0201.
- R05 n/a Engine in 02.3. Blocked guards answer 409 RULE_NOT_APPROVED with a decision_id. The test pins the P0 guards (REQUIRED_BLOCKS, test_api_contract_planned_phase02.py:38-50).
- R06 ✔ OpenAPI diff checked semantically (above). The new tests pin session + proposed permission + 401/403/429 on every op, 404 on `{id}` paths, Idempotency-Key + 409/422/428 on mutations, If-Match/412 on PATCH and actions, MFA uniformity per permission, MFA on issue/approve/confirm/decide, Code14 typing (ID-01) and no numeric code/serial fields. Idempotency exemption of `validateProductCode`/`previewProductCode` is **accepted**: they are pure computations with no write, outbox or business audit, and POST keeps S2 codes out of URLs. The exemption is pinned to exactly those 2 ops (`side_effect_free_operations` + test). Relaxation of the PHASE_01 planned test is **accepted**: the new test asserts `planned_paths() == phase02_paths`, so no PHASE_01 path can silently become planned again. The seed test now compares implemented ops, and `test_no_planned_phase02_permission_is_seeded_before_dec_057` covers the gap. Weak spot: REV-0202.
- R07 n/a No UI in this step. MOCK_UI_BINDING §7 binds pages 1/2/4/29/33 and marks every production/material/QC widget LATER with a placeholder and no number. Export and notifications are REJECTED, not faked.
- R08 ✔ Secret scan 0 findings (history). No raw sample values: CONFLICTS cites cells only (C-72), and the OpenAPI diff adds no `example` values. No customer contact columns (DEC-028, C-54/R-47). Golden cases are designed to live in the server DB only (DATA_TABLE CodeRuleGoldenCase, R-38). The privacy defect in published handoff/ is escalated as DEC-060, not edited. Hostnames are sanitised. The only author e-mail is git commit metadata (pre-existing practice), not content.
- R09 ✔ (design note) The code touches only platform_core tests/constant. The data design declares identity_* vs commercial_* ownership (DATA_TABLE §1). One cross-module write path is left undefined: REV-0201 (P2, must be settled before 02.2 DDL).
- R10 n/a No integration. The provenance block (DATA_TABLE §1.1) keeps raw value + formula + staging row + batch hash (via import_batch.file_sha256), with CHECKs that forbid fake provenance.
- R11 n/a No ops change.
- R12 ✔ Lint, type, the full DB-backed suite and the OpenAPI/handoff/secret checks were reproduced (above). The golden tests are honestly SKIPPED: the private source is absent, the reason is given and nothing is faked.
- R13 ✔ Updated: CHANGELOG.md, API_RUNTIME.md §13, CONFLICTS C-47..C-76, RISKS R-36..R-47, DATA_TABLE PHASE_02, STATE_TRANSITIONS §5, MOCK_UI_BINDING §7, DECISIONS_ADDENDUM rows DEC-057..060 + PROJECT_STATUS decision entries (event log shows `decision_added`).
- R14 n/a Left to the employer at Gate time.

## ISSUES
- REV-0201 [P2] docs/discovery/DATA_TABLE.md:258 (`commercial_customer_order_line.serial_id` "mirrors `identity_serial.order_line_id`") + :249 (identity_serial FK -> commercial_customer_order_line); STATE_TRANSITIONS.md:244 and :260 (line -> SERIAL_ALLOCATED by `allocateSerial`); DEC-057_PACKET.md:72 (recommends confirm + serial creation "در همان تراکنش").
  - Problem: the design has bidirectional FKs across the Identity and Commercial modules and a mirrored column. Who writes it is not stated. Either Identity's `allocateSerial` writes a Commercial table (line `serial_id`/status), or Commercial's `confirmCustomerOrder` writes Identity serials/snapshots. That is a direct cross-module write (R09 / ARCHITECTURE_OVERVIEW "never mutate other modules' authoritative data via direct table writes"), or else an undefined eventual-consistency window. That window conflicts with the "one transaction" claim of L-A.
  - Repro: read the cited lines and look for the writer of `commercial_customer_order_line.serial_id`. None is named.
  - Expected fix: before the 02.2 DDL, pick and document one owner. Options:
    - (a) no mirror column; the line's serial is derived from `identity_serial.order_line_id`;
    - (b) a documented in-process domain-service call where the owning module's service writes its own rows within one UnitOfWork (explicit ADR/convention);
    - (c) event-driven update, with the L-A wording corrected.
  - Regression test required: in 02.2/02.3, a test that each module's tables are written only by that module's service (or a DB trigger/consistency check between `serial_id` and `order_line_id`).
- REV-0202 [P3] backend/platform_core/tests/test_api_contract_planned_phase02.py:63-66, :135.
  - Problem: `_decision_status()` reads DECISION_LOG.csv, which contains decided entries only. `status.get(d) != "APPROVED"` is therefore true for any ID, including a typo or a non-existent DEC-999. So "blocked operations name OPEN decisions" is not really asserted.
  - Repro: change one `x-aleekhan-blocked-by` to `DEC-999`; the test still passes.
  - Expected fix: also assert that every referenced ID exists in the decision register (PROJECT_STATUS.json decisions / DECISIONS_ADDENDUM.csv / handoff DECISION_REGISTER.csv) with a non-APPROVED status.
  - Regression test required: yes, the strengthened assertion itself.
- REV-0203 [P3] docs/discovery/STATE_TRANSITIONS.md:291 ("only one SUBMITTED/APPROVED request per order") and :296 (change-request EXPIRED after 30 days "same expiry as platform approvals (DEC-032)"); also :242 ("uom of the family", which depends on DEC-058 q.5).
  - Problem: these are business rules. They are presented as guards without a PROPOSED/decision tag. DEC-032 approved 30 days for platform approval requests, not for order change requests.
  - Expected fix: tag them as proposals and add them as explicit questions in DEC-059 (and the uom point under DEC-058), or have the employer confirm them in 02.3.
  - No test needed now; 02.3 engine tests must reference the approved values.

## EMPLOYER ATTENTION
- تصمیم‌های P0 باز (DEC-005 قاعده کد، DEC-006 سریال، DEC-057 نقش‌ها، DEC-059 تغییر/لغو سفارش) جلوی گیت فاز ۲ را می‌گیرند. لطفاً یکی‌یکی و با بسته‌های `control/decisions/` تصمیم بگیرید.
- گام‌های بعدی بدون این تصمیم‌ها تا طراحی جدول‌ها و موتور پیش می‌روند، ولی صدور کد و ساخت سریال تا تصمیم شما بسته می‌ماند.
- استخراج نمونه‌های واقعی (حداقل ۲۰ نمونه برای هر خانواده محصول) فقط روی دستگاهی انجام می‌شود که منابع خصوصی دارد. این کار هنوز انجام نشده است.
- DEC-060: نام‌هایی که واقعی به نظر می‌رسند در فایل‌های handoff مخزن عمومی آمده‌اند. تصمیم با شماست.
- تأیید نهایی (R14) با شما در زمان Gate است.
