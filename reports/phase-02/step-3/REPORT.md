# REPORT — PHASE_02 / 02.3 Domain Engine

```
PROJECT: Aleekhan
PHASE: PHASE_02
STEP: 02.3
COMMIT SHA: 3fb0162
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-13
IMPLEMENTER: Claude Code (aleekhan-implementer); verification re-run, real golden run and report by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 02.2 PASS (c8b3dff); DEC-005 (+ amendment 2026-11-13 style 0000), DEC-006, DEC-057 (+ amendment owner read), DEC-058, DEC-059 (+ amendment due-date approver, cancel from hold); Planning intake sha 113f5400…
```

## 1. Purpose & acceptance
Step text: "منطق محاسبه/State/Conflict/Idempotency و Error Codes؛ unit/property/golden tests قبل از UI".

This step adds the engine and use cases only. There is no HTTP (that is 02.4) and no UI (02.5).

Acceptance at engine level:
- **ID-01:** code segments are exact-width text, and leading zeros are kept (property tests).
- **ID-02:** serial allocation in the confirm unit of work, with race tests.
- **ID-03:** one serial per line; ADD_LINE draws a new serial.
- **ID-04:** idempotent confirm, issue and allocate. Reusing a key with a different payload is refused (REV-0220).

## 2. Actual changes
**Identity** (`backend/platform_core/product_identity/`):
- `coderule.py`: the pure DEC-005 rule.
  - Code = `02` + type + category + product + style; belt product number = buckle + width.
  - New product number = max + 1 per type; new style = count + 1. It refuses instead of wrapping past 9999.
  - Style `0000` is legacy-only: the build path refuses it, and the `legacy=True` parse accepts it.
- `codes.py`: code rule revision lifecycle and product codes.
  - Lifecycle: golden cases (≥20 per type) → submit → approve (maker ≠ checker, fresh MFA) → activate.
  - Preview has no side effects. Issue gives RESERVED/ERP_PENDING, or `RULE_NOT_APPROVED` without an ACTIVE revision.
  - ERP match (system actor) → ACTIVE/ERP_MATCHED.
- `master.py`: customers, brands, products, styles and revisions, with locked numbering.
- `serials.py`: REV-0220 fix (`IDEMPOTENCY_PAYLOAD_MISMATCH`), plus `add_snapshot` and `cancel_serial`.
- `refusals.py`: 53 stable refusal reasons under existing top-level codes. No new top-level code, so OpenAPI is unchanged.
- `usecase.py`: shared helpers.

**Commercial** (`backend/platform_core/commercial/`):
- `orders.py`: draft, validate, confirm, release, hold/resume and cancel.
  - Confirm is done by planning_officer or the owner, with confirmer ≠ creator. Serials are allocated in the same unit of work.
  - A duplicate PO number of the same customer needs acknowledgement.
  - Representative name is PII: masked for management_viewer, every read audited, never put in events, snapshots or images.
- `changes.py`: the 7 change kinds.
  - Flow: decide (commercial_manager) → planning approval for due-date changes → apply (version n+1 and snapshots).
  - The planning approver is planning_officer and must differ from the requester and the decider.
  - Direct cancel from ON_HOLD is allowed when the stored state is pre-release.

**Migrations**
- `0023_phase02_engine`:
  - ON_HOLD→CANCELLED edge;
  - CHECK that the planner is not the decider;
  - number sequences for customers, orders and change requests;
  - style `0000` allowed only for IMP/LEG provenance;
  - CHECK that a system code or style never ends in `0000`.
- `0024_dec057_dec059_matrix_v21`:
  - new permission `commercial.change.planning_approve` → planning_officer;
  - owner gets the 9 PHASE_02 read permissions;
  - matrix 2.1.
- Both are reversible.

**Events:** 36 new outbox events; the golden event catalogue was regenerated.

**Docs:**
- `STATE_TRANSITIONS.md` §5.10
- `DATA_TABLE.md` (02.3 result)
- `ERD.md`
- `PERMISSION_MATRIX_DRAFT.md` v2.1
- `ERROR_CODES.md`
- `EVENT_CATALOGUE.md`
- `CHANGELOG.md`

**Tests:** 303 new tests:
- `test_phase02_coderule.py`, using hypothesis property tests;
- `test_phase02_golden_harness.py`;
- `test_phase02_engine_identity.py`;
- `test_phase02_engine_orders.py`, which tests every pair of the order machine;
- `test_phase02_engine_changes.py`;
- `test_phase02_engine_race.py`.

## 3. Data integrity
- Every state change goes through the unit of work, with audit and outbox in the same transaction.
- The deferred commit checks from 0020 are fired in the engine tests.
- Change requests apply against a base version: of two changes on one base, only one applies (race test).
- Numbering locks the counting row, and a collision with a legacy style is refused rather than guessed.

## 4. Security evidence
- **Real golden data:**
  - The file was built by the orchestrator from the Planning baseline, in memory, with macros not executed.
  - It is written to `F:/aleekhan/private-extract/` (outside the repo, never committed).
  - The harness refuses a path inside the repo and prints indexes and counts only.
- The repo holds no real code, category, customer, person or serial; test data is synthetic.
- Secret scan: findings=0. Leak grep on `reports/phase-02/step-3`: 0 hits.
- `roles_check.sh`: 73 passed. The app role may `nextval` but not `setval`, and cannot disable the order guard.

## 5. Test evidence (orchestrator re-run, `logs/orch/`)
| Check | Result | Log |
|---|---|---|
| ruff check + format | PASS | `logs/orch/ruff.log` |
| mypy (221 files) | PASS | `logs/orch/mypy.log` |
| makemigrations --check | No changes | `logs/orch/makemigrations.log` |
| pytest -m "not perf" | 2331 passed, 2 skipped (clamd; golden file not set in that run), 7 deselected | `logs/orch/pytest.log` |
| **Golden, real Planning data** (`ALEEKHAN_GOLDEN_FILE` set) | 2313 cases, 5 families (179/253/302/364/1215), not_reproduced=0, legacy_only_style_0000=14 | `logs/orch/golden_real.log` |
| race tests ×3 | 36 passed in each run | `logs/orch/race_x3.log` |
| db_roundtrip.sh | see log | `logs/orch/db_roundtrip.log` |
| roles_check.sh | see log | `logs/orch/roles_check.log` |
| secret scan | findings=0 | `logs/orch/secret_scan.log` |
| partial rollback 0024→0022 | schema diff empty (implementer) | `logs/phase02_partial_rollback_0024_0022.log` |

**Golden source:** built from distinct 14-digit stored `NOrder!FZ` values.
- Inputs are taken independently of the stored code: the type code is looked up `Sorce!E`→`O` from `NOrder!A`; the category is `FY`; product and style are `C` and `D`.
- 637 non-14-digit rows are DISPUTED (DEC-005) and excluded; 967 repeated codes were removed.
- C-77 (whether the two category lookups agree) is not covered by this run and stays open.

## 6. Demo (employer)
Nothing for the employer to test in this step; there is no UI or API yet.

## 7. Issues / decisions (implemented conservatively; to confirm with the employer at the Gate or in 02.4)
1. **Number format (PROPOSED):**
   - `CU-`, `SO-`, `CR-` + at least 6 digits, from a sequence;
   - unique, with gaps allowed.
2. **Permission `commercial.change.planning_approve`:** its name and flags are proposed.
3. **Held orders:**
   - Only resume or cancel is accepted.
   - Quantity, due-date and add-line changes are refused (`ORDER_ON_HOLD`).
4. **Cancelling the last line:** CANCEL_LINE refuses to cancel the last live line; CANCEL_ORDER must be used.
5. **Planning approval:** it can only approve; there is no planning rejection.
6. **Apply:** it has no maker-checker rule of its own.
7. **Product and style numbers:**
   - Manual entry (allowed by the legacy workbook) is not supported.
   - A collision with a legacy style is refused.
8. **Readiness for order lines:** products and styles start DRAFT; a line needs them ACTIVE.
9. **Representative name:** digits and `@` are refused.
10. **Not enforced (REV-0203):** the one-open-change-request-per-order rule and change-request expiry.
11. **Approval inbox:** PHASE_02 decisions do not create platform `ApprovalRequest` rows, so nothing appears in the approval inbox. This is a question for 02.4/02.5.
12. **Owed to 02.4 (OpenAPI):**
    - the planning-approval operation;
    - refusal reasons;
    - number formats;
    - the earlier contract drift from 02.2.
13. **Still open:**
    - REV-0221 (junit hostname redaction);
    - REV-0223 (roundtrip function counts);
    - C-77.

## 8. Rollback
`migrate platform_core 0022` (tested) restores matrix 2.0 and the 0020 guard body exactly. It is refused if a legacy `0000` style already exists, which is an intended guard. Then `git revert` the step commit.

## 9. Review request
PASS requested, against R01–R14.

## 10. Next step
02.4 Backend/API: endpoints, permission scope, rate limit, ETag/version, pagination, request id, and the OpenAPI update.
