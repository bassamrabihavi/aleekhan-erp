# REPORT — PHASE_02 / 02.6 Integration

```
PROJECT: Aleekhan
PHASE: PHASE_02
STEP: 02.6
COMMIT SHA: fe0058c
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-15
IMPLEMENTER: Claude Code (aleekhan-implementer); real-data run, verification and report by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 02.5 PASS (5f65fc9); Planning intake sha 113f5400… (DEC-037); DECISION_LOG 2026-11-15
```

## 1. Purpose & acceptance
Step text: "فقط Source/Events مربوط؛ staging, retries, backoff, compensation, freshness and conflict queue؛ بدون تغییر مستقیم ماژول دیگر".

**Scope:**
- the server-side Planning master-data import: product types, categories, legacy 14-digit code registry;
- a code-rule golden-case loader;
- a legacy serial guard report;
- the integration mechanics: staging, retry/backoff, compensation, freshness, conflict queue, events.

**Out of scope:** bulk legacy order/serial migration. It stays blocked by DEC-025/DEC-035 (PHASE_12). Customer and staff names are never imported (DEC-028/DEC-060).

Owed 02.5 review items closed here: REV-0251, REV-0252, REV-0255.

## 2. Actual changes
- **`integration/imports.py`:** `apply_batch` moves VALIDATED → APPLIED in one transaction.
  - The owning module applier writes its own rows, then the batch row, audit and outbox are written.
  - Compensation = rollback: a failure leaves no official rows, and the staging rows are kept for a re-run.
  - `apply_batch_with_retry` retries transient SQLSTATEs (40001/40P01/55P03) with the existing backoff, and records `batch_apply_failed` when it gives up.
  - Every other source still returns RULE_NOT_APPROVED.
- **`product_identity/planning_import.py`:**
  - Refuses a path inside the repo, and a SHA-256 that differs from `--expected-sha256`. The hash is streamed before the file is loaded.
  - 128 MiB limit for this source only; the generic 50 MiB upload limit is unchanged.
  - In-memory, macros never executed, `data_only`, optional msoffcrypto decryption from env (never printed).
  - **Sorce:** 2 header rows. Product types come only from the first unbroken block of column E. Categories are type-keyed (BE..BI headers → type).
  - **Units:** from DEC-058. A type outside the list → conflict, not created.
  - **Legacy codes:** NOrder!FZ + Codding (operator-chosen column) are registered as LEG, RESERVED / ERP_PENDING. Style 0000 is allowed; the 14-digit code is authoritative for belts.
  - **Conflicts:** non-14 values → `legacy_code_disputed`; a code with more than one (product, style) → conflict. A changed value raises a conflict and never overwrites.
  - Idempotent per file hash.
- **Commands:** `import_planning_catalogue`, `load_code_rule_golden` (DRAFT revision through the 02.3 engine; harness-only fields refused) and `legacy_serial_guard` (counts only).
- **Migrations:**
  - `0026_phase02_planning_catalogue_source`: a READ_ONLY source; no hash stored.
  - `0027_dec057_matrix_v22`: the conflict-queue grants from the employer decision of 2026-11-15:
    - steward and owner: freshness, conflict read and conflict resolve;
    - `management_viewer`: freshness only, plus an `open_conflicts` count.
  - Both are reversible.
- **Security fix found during fix3:** the four PHASE_00 integration views had no authentication class, so they answered 401 to every caller. They now use the PHASE_01 session authentication, with the permission check unchanged. Contract **0.8.4-draft**.
- **UI:**
  - The serial header collapses at ≤ 900 px, so the 768 px title fits on one line (REV-0251).
  - The two reference panels have distinct titles (REV-0252).
- **Dependencies:** `openpyxl==3.1.5`, `msoffcrypto-tool==6.1.0` (+ `et_xmlfile`, `olefile` in the lock).

## 3. Data integrity
- Imported rows carry provenance IMP/LEG plus a staging row (INV-02-09).
- A batch is applied whole or not at all.
- A second run of the same file is a no-op (verified on real data).
- Conflicts are never auto-resolved.

## 4. Security evidence
- **Real-data run by the orchestrator** on a throw-away DB (`test_aleekhan_import02/03`, both dropped after the run). Output was counts only and no real value entered the repo.
- The repo stores no workbook hash or path; the operator passes the hash.
- Secret scan: findings=0.
  - The pre-commit guard first flagged a synthetic in-test workbook password variable. It was renamed; the guard was not bypassed.
- Leak grep: 0 hits.

## 5. Test evidence (orchestrator, `logs/orch/`)
| Check | Result | Log |
|---|---|---|
| ruff / mypy / makemigrations --check | PASS / PASS / no changes | `ruff.log`, `mypy.log`, `makemigrations.log` |
| OpenAPI validation | OK (0.8.4-draft) | `openapi_validate.log` |
| pytest -m "not perf" | 3124 passed, 2 skipped, 7 deselected | `pytest.log` |
| race ×3 | 38 passed in each run | `race_x3.log` |
| db_roundtrip.sh | ROUNDTRIP OK | `db_roundtrip.log` |
| roles_check.sh | 78/78 | `roles_check.log` |
| frontend eslint / tsc / vitest / build | rc 0 / 0 / 73 passed / 0 | `eslint.log`, `typecheck.log`, `vitest.log`, `build.log` |
| E2E full (Edge) | 32 passed + backend-down 1 passed | `e2e.log` |
| **Real legacy serial guard** | 3920 values, 3779 plain integers, **0 ≥ 63000**, `safe_for_start: true` | `real_serial_guard.json` |
| **Real catalogue import (final, fresh DB)** | 6 types, 111 categories, 2841 legacy codes, 228 conflicts (224 disputed codes, 2 multi product/style, 2 duplicate accessory category names) | `real_import_final.json` |
| Real re-run (same file) | `already_applied: true`, no change | `real_import_2_rerun.json` |

- The first real run raised 9 false conflicts: a second English header row in Sorce, and a non-type list below the type block in column E. Both were fixed (fix2), and the final run on a fresh DB is clean.
- The real-data golden loader (`load_code_rule_golden`) was **not** run on real data in this step. The real golden evidence remains the harness run in 02.4 (2313 cases).
- The 768 px screenshot of page 2 was viewed after the fix.

## 6. Demo (employer)
Hands-on UAT is now possible on a UAT DB after an operator import. The UAT how-to is part of 02.8 (Gate packet).

## 7. Issues / decisions
1. **Decided 2026-11-15:**
   - conflict-queue access (matrix v2.2);
   - imported types and categories are ACTIVE.
2. **Real conflicts for the steward:**
   - 224 disputed legacy values;
   - 2 codes linked to more than one (product, style);
   - 2 accessory category names that appear twice with different codes.
3. **No products or styles are imported,** so legacy codes stay unlinked (0 links) until styles exist. The full legacy migration is PHASE_12.
4. `source_formula` is not filled, because cached values only are read.
5. The 14-day release rule for the two new pins is not verified (they were already in the venv). To check in 02.7 (dependency scan).
6. **Still open:** REV-0203, REV-0223, REV-0244 (`golden_summary` performance, 02.7), REV-0254 (requester name; employer question at the Gate).

## 8. Rollback
`migrate platform_core 0025` (0027 and 0026 reverse; tested in the roundtrip, and 0027 also by its own test), then `git revert fe0058c`. The contract goes back to 0.8.3-draft.

## 9. Review request
PASS requested, against R01–R14.

## 10. Next step
02.7 Security & Ops: secret and dependency scan, privacy/permission tests, performance, backup/rollback and job monitoring, signed security checklist.
