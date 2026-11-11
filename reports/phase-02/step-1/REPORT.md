# REPORT — PHASE_02 / 02.1 Discovery & Contract

```
PROJECT: Aleekhan
PHASE: PHASE_02
STEP: 02.1
COMMIT SHA: PENDING
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-11
IMPLEMENTER: Claude Code (aleekhan-implementer); report written and verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; PHASE_01 Gate ACCEPTED (2026-11-11, tag phase-01-accepted)
```

## 1. Purpose & acceptance
Step text: "02.1 — Discovery & Contract: تعارض‌ها، جدول داده، state transitions، OpenAPI draft، mock/UI binding و خطرات را ثبت کن؛ برای P0 تصمیم بگیر، هنوز داده واقعی mutate نکن."

This step prepares the contract for acceptance cases ID-01 to ID-04 (all P0):
- ID-01: a 14-digit code with leading zeros is kept as an exact string.
- ID-02: multi-user serial allocation creates no duplicates.
- ID-03: each line of a PO with several lines can have its own serial.
- ID-04: a repeated request has a single effect.

Pages in scope: 1, 2, 4, 29 and 33. Page 33 is shared with PHASE_05.

**Private sources:** `ALEEKHAN_PRIVATE_DIR` was not set in this session.
- No private file was read and no legacy file was executed.
- All Planning evidence comes second-hand from the text in `handoff/`.
- Golden extractions are pending (§7).
- No code family, sample code or serial format was invented. Every unknown is BLOCKED behind its decision.

## 2. Actual changes
**Discovery** (`docs/discovery/`)
- `CONFLICTS.md`: C-47 to C-76.
- `DATA_TABLE.md`: PHASE_02 identity and commercial tables, with keys and constraints.
  - The source-provenance block covers: kind, import batch, staging row, sheet, cell, raw value, formula and transform version.
  - Invariants INV-02-01 to 09.
  - 14-digit codes are `Code14`: `varchar(14)` + regex + namespace. Code segments are not modelled before DEC-005.
  - The serial is `varchar(32)` with no pattern before DEC-006.
- `STATE_TRANSITIONS.md` §5: transitions for the order header, order line, code rule revision, serial, change request and product code registry. Each blocked guard names its decision.
- `MOCK_UI_BINDING.md` §7: binding for pages 1, 2, 4, 29 and 33.
- `RISKS.md`: R-36 to R-47.

**Decision packets** (Persian, `control/decisions/`)
- Existing decisions: DEC-005 (code rules) and DEC-006 (serial).
- DEC-027 (UI design system).
- New decisions, registered with `status.py add-decision`:
  - DEC-057: PHASE_02 permission matrix.
  - DEC-058: customer and order master data.
  - DEC-059: change after confirmation, cancel, hold.
  - DEC-060: real-looking customer names in `handoff/` inside the public repo.

**Contract**
- `docs/api/openapi-draft.yaml` is now **0.7.0-draft**, additive only:
  - 63 **planned** operations on 48 paths under `/identity/...` and `/commercial/...`. None is routed.
  - 14 of these operations are blocked by DEC-005, DEC-006, DEC-057 or DEC-059.
  - 4 planned error codes.
  - The 88 previous paths are unchanged.
- `validateProductCode` and `previewProductCode` are side-effect-free POSTs that take no Idempotency-Key. This is a new exemption and needs reviewer acceptance.
- `API_RUNTIME.md` §13 and `CHANGELOG.md` updated.

**Code** (contract plumbing only)
- `CONTRACT_VERSION` is "0.7.0-draft".
- New `test_api_contract_planned_phase02.py`.
- `test_api_contract_planned.py` now accepts planned paths, but no planned PHASE_01 path.
- The permission-seed test in `test_phase01_schema.py` compares implemented operations only.

## 3. Data integrity
- No migration.
- No business code.
- No real data touched.

## 4. Security evidence
- Secret scan of the tree and history: 0 findings.
- No handoff sample values were copied: the docs cite cell references only.
- The diff has 0 hits for the account name or hostname.
- DEC-060 flags a privacy issue in the published `handoff/` copy, for the employer to decide.

## 5. Test evidence
Orchestrator re-runs on work-windows (PG 17.9); logs are in `logs/orch/`.

| Command | Outcome | Log |
|---|---|---|
| ruff check + format --check (repo) | PASS (305 files formatted) | `logs/orch/ruff.log` |
| mypy strict | PASS, 193 files | `logs/orch/mypy.log` |
| `pytest -m "not perf"` full | **1967 passed, 1 skipped** (real ClamAV), 7 deselected | `logs/orch/pytest.log`, `pytest.xml` |
| OpenAPI validation | VALID, 0.7.0-draft, 136 paths | `logs/orch/openapi_validate.log` |
| secret scan (tree + history) | findings=0 | `logs/orch/secret_scan.log` |

Implementer runs, in `logs/`:
- tools unittest: 42 OK.
- verify_handoff: OK=300, KNOWN_DEFECT=1, failures=0.
- OpenAPI additive check against 4b490d2.
- REPORT.json schema: PASS.
- Golden extraction: SKIPPED, because the private source is not available (`golden_pending.log`).

## 6. Demo (employer)
Nothing to click. The employer reviews the decision packets one at a time.

## 7. Issues / decisions
**Pending until private-source access.** The Planning workbook is now at the employer's private folder. The env vars take effect after a Claude Code restart.
- DEC-005 extraction items E-1 to E-11, with at least 20 real cases per family.
- DEC-006 question 5: the largest legacy serials.
- The v2 workbook hashes (C-22 / C-74).

**Employer decisions** (asked one at a time):
- **DEC-005 (P0):**
  - approve the extraction list;
  - name the confirmers (planning + commercial);
  - code authority Q-B (recommended B1: the system reserves, Rahkaran confirms).
- **DEC-006 (P0):** serial namespace, allocation timing, gaps, and continuation after legacy numbers. Recommended S-A, L-A, G-A, P-A.
- **DEC-057 (P0):** PHASE_02 roles and permissions.
- **DEC-059 (P0):** change after confirmation, cancel (recommended C-A), hold/resume.
- **DEC-027 (P1):** pages 1 and 2 from the concept images, with PHASE_02 data only (recommended P-A).
- **DEC-058 (P1):** brands, PO-number uniqueness, external references, unit per family, order types.
- **DEC-060 (P1):** what to do about the real-looking names in the public `handoff/` copy.
- Technical resolutions to confirm: C-55, C-59, C-60, C-61, C-64, C-65, C-67, C-68.

**For the reviewer:**
- The relaxation of the PHASE_01 planned-contract test.
- The Idempotency-Key exemption for the two validation POSTs.

## 8. Rollback
`git revert <commit>`. There is no migration.

## 9. Review request
Request PASS. Reviewer attention:
- No rule was guessed: every unknown is BLOCKED and has a named decision.
- The contract change is additive.
- The provenance model in the data table.
- The two test relaxations and the new exemption.

## 10. Next step
02.2 Database. It can start for the decision-independent tables. Tables that depend on DEC-005, DEC-006 or DEC-058 wait for those decisions.
