# REPORT — PHASE_02 / 02.4 Backend/API

```
PROJECT: Aleekhan
PHASE: PHASE_02
STEP: 02.4
COMMIT SHA: ee9d4e7
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-14
IMPLEMENTER: Claude Code (aleekhan-implementer); verification re-run, real golden run and report by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 02.3 PASS (3fb0162); DECISION_LOG amendments 2026-11-12..14; Planning intake sha 113f5400…
```

## 1. Purpose & acceptance
Step text: "permission scoped + rate limit + ETag/version + pagination + request-id + OpenAPI و test واقعی".

The step also carries engine follow-ups from the employer's amendments of 2026-11-14 and from the 02.3 review:
- number format with the Jalali year;
- style collision → first free number (REV-0232);
- planning may reject a due-date change;
- C-77 check (REV-0230);
- belt check (REV-0231).

Acceptance cases ID-01..ID-04 are now also tested through the HTTP layer, including a concurrent confirm through API clients.

## 2. Actual changes
- **API** (`backend/platform_core/api/phase02/`): all 66 PHASE_02 operations are routed.
  - Session cookie, permission per matrix v2.1, record scope (outside scope = 404).
  - Fresh MFA on issue, code-rule approve/reject/activate, confirm, decide and planning decision.
  - Rate limit, ETag + If-Match, pagination, request id, and Idempotency-Key on mutations.
  - Refusal reasons are returned in `errors[].code`.
- **Contract `0.8.0-draft`:**
  - no planned paths remain;
  - 3 operations added: `updateCustomerBrand`, `addCodeRuleGoldenCases`, `decidePlanningChangeRequest`;
  - `SerialNumber` pattern `^[1-9][0-9]*$` and new `TechnicalNumber`;
  - the drift owed from 02.2/02.3 is closed;
  - API_RUNTIME §14 added.
- **Numbers:** `SO-/CU-/CR-<Jalali year>-<6+ digits>`.
  - `product_identity/jalali.py` uses no new dependency and is tested day by day from 1395 to 1410, including the Nowruz and Tehran midnight boundaries.
  - Counter table `platform_number_counter` keyed by (kind, year): atomic +1, guarded against reset or delete.
- **Planning reject:** a reason is required; the change request closes REJECTED and the old due date stays. DB CHECKs prevent the requester or the deciding manager from rejecting.
- **Style collision:** `first_free_style_no`, with an audit reason. The 5-way concurrent creation test gets contiguous numbers.
- **Golden harness:**
  - C-77 (`category_code_order_form`): any disagreement fails.
  - Belt (`buckle_type_code`/`belt_width_code`): requires ≥20 belt-checked cases per belt family. `legacy_disputed` cases are reported and not counted toward the minimum.
  - Belt families come from data or from `ALEEKHAN_GOLDEN_BELT_FAMILIES`.
- **Engine fixes:**
  - new `external.py` for creating and ending external references;
  - a reason on line removal and on rule activation;
  - snapshot image `order_version` bug fixed.
- **Migration `0025_phase02_api_numbers`** (reversible): counter table + guard, planning-reject columns/CHECKs, change-request guard edge.

## 3. Data integrity
- Every mutation goes through the 02.3 use cases inside a unit of work, with audit and outbox.
- An idempotent replay returns the same response with one effect; reusing a key with a different body gives 422.
- 412 on an ETag mismatch.
- Concurrent confirms through the API give one 200, no duplicate serial and no gap.

## 4. Security evidence
- **Representative name (DEC-058 PII):**
  - only `getCustomerOrder` returns it, and every unmasked read is audited;
  - `[REDACTED]` for management_viewer, in lists and in every write response, so it never reaches an idempotency record, a replay or a log.
- No route allows anonymous access. Every write is refused (403) for management_viewer and employee (contract test on every operation).
- The app DB role cannot reset or delete number counters (`roles_check.sh` 78/78).
- Secret scan: findings=0. Leak grep: 0 hits. `handoff/` is unchanged.
- **Real golden data:** built in memory from the Planning baseline, macros never executed. It is stored only in `F:/aleekhan/private-extract/`, outside the repo, and was never committed.

## 5. Test evidence (orchestrator re-run, `logs/orch/`)
| Check | Result | Log |
|---|---|---|
| ruff check + format | PASS | `logs/orch/ruff.log` |
| mypy (233 files) | PASS | `logs/orch/mypy.log` |
| makemigrations --check | No changes | `logs/orch/makemigrations.log` |
| OpenAPI validation | OK (0.8.0-draft) | `logs/orch/openapi_validate.log` |
| pytest -m "not perf" | 3060 passed, 2 skipped (clamd; golden file not set in that run), 7 deselected | `logs/orch/pytest.log` |
| **Golden, real Planning data (v2)** | 2313 cases, not_reproduced=0, c77_checked=1218 c77_disagree=0, belt_checked=169 (family 02), legacy_disputed=15, legacy_only_style_0000=9 | `logs/orch/golden_real.log` |
| race tests ×3 | 38 passed in each run | `logs/orch/race_x3.log` |
| db_roundtrip.sh | ROUNDTRIP OK | `logs/orch/db_roundtrip.log` |
| roles_check.sh | passed=78 failed=0 | `logs/orch/roles_check.log` |
| secret scan | findings=0 | `logs/orch/secret_scan.log` |

**Golden v2 notes:**
- C-77 is checked only where the Order form path resolves the category name in `Sorce!BZ`. That is 1218 cases; the other 1095 cannot be resolved by that path.
- Belt buckle code comes from `NOrder!BR` → `Sorce!BN` → `Sorce!O`.
- No separate width column was found, so the width is taken from `product_no[2:4]`. **Only the buckle half of the belt rule is independently evidenced.**
- 15 belt codes whose buckle code differs from the product prefix are `legacy_disputed` (BUCKLE_MISMATCH), the same treatment as the other legacy anomalies under DEC-005.

## 6. Demo (employer)
Nothing for the employer to test in this step; it has no UI (that is 02.5).

## 7. Issues / decisions
1. **`allocateSerial`:** it always returns 409 `SERIAL_ALLOCATED_AT_CONFIRM` (DEC-006 L-A). Keep or remove it in the contract?
2. **Flags of `commercial.change.planning_approve`** (MFA + business approval + maker-checker): proposed, not yet confirmed.
3. **Approval inbox:** PHASE_02 decisions create no platform `ApprovalRequest`, so nothing appears in the approval inbox. To settle with the 02.5 UI.
4. **Not supported, and refused explicitly:**
   - manual product or style numbers;
   - renaming a product or style;
   - editing types or categories (server import only).
5. **Similar-style suggestion:** a simple deterministic score; the real rule is not decided.
6. **Belt width source:** to be confirmed with the employer, or found in the workbook, before the 02.6 import.
7. **Still open:**
   - REV-0203 (one open change request per order; expiry);
   - REV-0221 (junit hostname redaction);
   - REV-0223 (roundtrip function counts).

## 8. Rollback
`migrate platform_core 0024` (tested in roundtrip). It is refused once a planning-rejected request exists, which is intended. Then `git revert ee9d4e7`; the contract goes back to 0.7.0-draft with it.

## 9. Review request
PASS requested, against R01–R14.

## 10. Next step
02.5 UI: pages 1, 2, 4, 29 and 33 in Farsi RTL, responsive, with loading/error/empty/stale states, Playwright screenshots at 1440/1180/768/390 and E2E tests.
