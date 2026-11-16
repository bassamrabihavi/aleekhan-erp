# PHASE_02 Trace Map (step 02.8)

**Scope sources**
- `handoff/03_PHASE_PLAN/PHASE_02.md`: DB domain, backend/API, engine, steps 02.1–02.8, cross-cutting requirements, Gate, mandatory outputs.
- Acceptance cases with `minimum_phase` 2 (ID-01..ID-04): `handoff/06_TEST_AND_ACCEPTANCE/GLOBAL_ACCEPTANCE_CASES.csv`.
- UI pages 1, 2, 4, 29, 33: `handoff/08_UI_AND_UX/UI_PAGE_PHASE_MAP.csv`.
- Employer decisions recorded in `control/decisions/DECISION_LOG.md` from 2026-11-11 to 2026-11-16.

Each row runs: requirement → implementing files → tests → evidence → review → status.

**Status values**
- **DONE:** implemented, with evidence and a review PASS.
- **PARTIAL:** part done; the rest is named with an owner.
- **EMPLOYER:** needs an employer action, answer or signature; agents cannot close it.
- **CARRIED:** deliberately left to a later phase or to the staging server, with the reason.

Counts are copied from the cited logs; nothing is estimated.

## Evidence sets
**C8 = full local CI**, run with `bash tools/ci_local.sh reports/phase-02/step-8/logs/ci` on machine work-windows, against test PostgreSQL 17.9.
- **Where:** `reports/phase-02/step-8/logs/ci/`. `summary.md` shows 13/13 stages PASS.
- **Commit:** a combined run over three worktree states (68b3362 → 91b921a → b3597158), mapped stage by stage in `EVIDENCE_NOTE.md`; `commit.txt` (68b3362) is the unedited CI artifact. The six recorded git tree ids (backend, frontend, tools, ops, docs, .github) equal `git rev-parse b3597158:<dir>`.
- **First run, on 68b3362:** 12 stages passed. E2E failed because the E2E seed still imported the moved factories, and the perf stage did not include the PHASE_02 perf tests. Both were fixed (91b921a, b359715), and the e2e, frontend and perf stages were re-run on the final tree. The first-run logs are kept as `*_attempt1*.log`.
- **Backend tree:** identical between 68b3362 and b359715, so the unit, migration, contract, authz, security and ops stages ran on the same backend code.

**C8-shots** = `reports/phase-02/step-8/screenshots/`: 135 PNG files. Of these, 16 are PHASE_02 sets × 1440/1180/768/390. The build footer reads `91b921ab3d23`, so the frontend is identical to b359715. The orchestrator viewed all 16 sets at all four sizes (REV-0253).

**Sn** (n = 1..7) = per-step evidence in `reports/phase-02/step-n/logs/`, plus the reviewer re-runs in `step-n/REVIEW.md`.

**O8** = orchestrator runs in 02.8: `reports/phase-02/step-8/logs/orch/`.
- Full pytest, perf, race ×3, roundtrip, roles, drill and rollback rehearsal.
- The real Planning import on a throw-away DB.

## C8 results
| Stage | Log | Result |
|---|---|---|
| ruff check + format | `01_lint.log` | PASS: all checks passed; 377 files formatted |
| mypy strict | `02_type.log` | PASS: no issues in 251 source files |
| tools unittest | `03_tools.log` | PASS: 42 tests |
| pytest unit + integration | `04_unit.log`, `pytest-unit-integration.xml` | PASS: 1759 passed, 2 skipped (real ClamAV: clamd not configured; real golden file: path not set in CI), 11 perf deselected |
| migrations up / zero / up + `makemigrations --check` | `05_migration.log` | PASS: ROUNDTRIP OK; schema diff EMPTY over 10548 lines |
| OpenAPI + API contract | `06_contract.log` | PASS: 0.8.4-draft, 140 paths / 173 operations, valid 3.1.0; 18 contract tests |
| authorization (route parity, redaction) | `07_authz.log` | PASS: 1481 passed |
| frontend (npm ci, eslint, typecheck, vitest, build) | `08_frontend.log` | PASS |
| Playwright E2E (real Django + PostgreSQL, Edge) | `09_e2e.log` | PASS: 32 passed, plus 1 in the backend-down run |
| perf | `10_perf.log`, `perf*.json` | PASS: PHASE_00 smoke 1, PHASE_01 6, PHASE_02 4 |
| secret scan, pip-audit, npm audit | `11_security.log` | PASS: findings 0; runtime lock: no known vulnerabilities; npm: 0 |
| DB roles, backup drill, rollback rehearsal | `12_ops.log` | PASS: roles 78/78; drill PASS (PHASE_02 invariants); rehearsal A–D, 0 failures |
| SBOMs, dist hashes | `13_artifacts.log` | PASS |

The informational dev/QA venv audit lists 12 advisories for `pip` 25.0.1. That is a tool and is not shipped, so it is not a gate (same rule as PHASE_01).

**Full suite (O8):**
- `pytest -m "not perf"`: 3160 passed, 2 skipped (`logs/orch/pytest.log`).
- perf: 11 passed.
- race ×3: 38 passed in each run.

## 1. Phase sections (PHASE_02.md)
| # | Requirement | Implementing files | Tests | Evidence | Review | Status |
|---|---|---|---|---|---|---|
| D1 | Customer (+ brand, representative name as PII) | `product_identity/models.py`, `commercial/`, migrations 0019–0022, `api/phase02/` | `test_phase02_engine_*`, `test_api_phase02_flows.py`, `test_phase02_step7_pii.py` | C8 `04_unit.log` | 02.2–02.7 PASS | DONE (DEC-058) |
| D2 | Product / Style | `product_identity/master.py`, `usecase.py` | `test_phase02_engine_race.py` (contiguous numbers, first free style no.), `test_api_phase02_flows.py` | C8 | 02.3/02.4 PASS | DONE |
| D3 | CodeRuleRevision + golden | `product_identity/coderule.py`, `codes.py`, 0028 stored summary | `test_phase02_coderule.py`, `test_phase02_golden_harness.py`, `test_phase02_step7_ops.py` | S4 `logs/orch-rework1/golden_real.log` (real data) | 02.3/02.4/02.7 PASS | DONE |
| D4 | PO header / line, versions | `commercial/orders.py`, `changes.py` | `test_phase02_engine_orders.py`, `test_phase02_engine_changes.py` | C8 | 02.3/02.4 PASS | DONE |
| D5 | Serial (transactional, gapless from 63001) | `product_identity/serials.py`, DB guards 0020/0023 | `test_phase02_serial_allocation.py`, `test_phase02_engine_race.py` | C8 `04_unit.log`; race ×3 (O8) | 02.2–02.4 PASS | DONE (DEC-006 L-A: allocated at confirm) |
| D6 | Historical snapshot | `serials.py` (`add_snapshot`), snapshot v1 at confirm | ID-02 test (one snapshot per line), change apply → new snapshot | C8 | 02.3 PASS | DONE |
| D7 | External reference | `product_identity/external.py` | `test_api_phase02_flows.py` | C8 | 02.4 PASS | DONE (Rahkaran read-only) |
| D8 | Source provenance, migration/commit, backward compatibility | provenance IMP/LEG + staging rows, outbox `schema_migration`, additive contract 0.7.0 → 0.8.4-draft | `test_phase02_planning_import.py`, contract tests | C8 `06_contract.log` | 02.6 PASS | DONE |
| B1 | Order CRUD / version | `api/phase02/` (ETag/If-Match, Idempotency-Key) | `test_api_phase02_flows.py` | C8 | 02.4 PASS | DONE |
| B2 | Code validate / issue under approval | `codes.py` (`active_rule_for`: no ACTIVE revision → refused; type outside the revision scope → `TYPE_NOT_IN_RULE_SCOPE`) | `test_phase02_coderule.py` | C8 | 02.3/02.4 PASS | DONE |
| B3 | Serial allocate atomically | allocation inside the confirm transaction; `allocateSerial` removed (employer, 2026-11-14) | ID-02/ID-04 tests | C8 | 02.4 PASS | DONE |
| B4 | 360 tracking (pages 1/2/4) | `api/phase02/identity_views.py` (`withheld_sections`) | `test_api_phase02_*` | C8, C8-shots | 02.4/02.5 PASS | DONE (later-phase sections show «در دست ساخت — به داده واقعی متصل نیست», DEC-027 P-A) |
| B5 | Change requests | `commercial/changes.py` (decide → planning approve/reject → apply) | `test_phase02_engine_changes.py`, race tests | C8 | 02.3/02.4 PASS | DONE; REV-0203 (one open CR per order, expiry) **EMPLOYER** |
| E1 | Verified 14-digit code from Planning golden | `coderule.py` | real golden v3: 2313 cases, `not_reproduced=0` | S4 `golden_real.log` | 02.4 rework PASS | DONE |
| E2 | Race / idempotency protection | UoW, idempotency records, DB guards | race suite ×3, ID-04 | O8 `race_x3.log` | 02.3/02.4 PASS | DONE |
| E3 | Every rule has a golden test and a decision owner; unknown → block | DEC-005/006/058/059 log entries; unknown family → refused | `GOLDEN_CASES_INSUFFICIENT`, `TYPE_NOT_IN_RULE_SCOPE` tests | C8 | 02.3 PASS | DONE |

## 2. Steps 02.1–02.8
| Step | Commit | Report | Review | Rework |
|---|---|---|---|---|
| 02.1 Discovery & Contract | 1c69e99 | `step-1/REPORT.md` | PASS | 0 |
| 02.2 Database | c8b3dff | `step-2/REPORT.md` | PASS | 0 |
| 02.3 Domain Engine | 3fb0162 | `step-3/REPORT.md` | PASS | 0 |
| 02.4 Backend/API | 14b49e4 (first ee9d4e7) | `step-4/REPORT.md` | PASS | 1 (REV-0240 P1) |
| 02.5 UI | 5f65fc9 | `step-5/REPORT.md` | PASS | 0 |
| 02.6 Integration | fe0058c | `step-6/REPORT.md` | PASS | 0 |
| 02.7 Security & Ops | 859b951 | `step-7/REPORT.md` | PASS | 0 |
| 02.8 Report & Review | b359715 | `step-8/REPORT.md` | (this review) | — |

All reviewer verdicts are advisory until DEC-036 is approved.

## 3. Cross-cutting requirements
| Area | Evidence | Status |
|---|---|---|
| DB: migration + FK/check/index + audit/outbox + rollback | migrations 0019–0028, all reversible; C8 `05_migration.log`; rehearsal C/D | DONE. Rollback with PHASE_02 data is refused at 0022 by design; the way back is restore from backup (`docs/ops/ROLLBACK.md` §3b), so **EMPLOYER** acknowledges it. |
| API: OpenAPI compatibility, idempotency, auth, errors | `docs/api/openapi-draft.yaml` 0.8.4-draft; C8 `06_contract.log`, `07_authz.log` | DONE |
| UI: RTL, 4 sizes, a11y, role-sensitive, real screenshots | C8-shots; E2E keyboard / forbidden-employee / viewer masking | DONE |
| ENGINE: deterministic contract, golden tests, traceability | golden harness (real), property tests | DONE |
| SEC: RBAC/ABAC, threat analysis, redaction, secure logs, scan | `docs/security/PHASE_02_SECURITY_CHECKLIST.md`; `test_phase02_step7_privacy.py` (16 roles × 69 operations), `test_phase02_step7_pii.py` | DONE (sign-off **EMPLOYER**) |
| QA: unit / integration / E2E / race / property / migration / security + independent evidence | C8 + per-step reviewer re-runs | DONE |

## 4. Gate criteria (PHASE_02.md «Gate پذیرش»)
| # | Criterion | Evidence | Status |
|---|---|---|---|
| G1 | 20+ real samples for every known family, or invalid ones blocked | Real golden v3 per family: 01 = 1215, 02 = 364, 03 = 302, 05 = 253, 04 = 179 (S4 log, private counts only). Family 06 (ست) has no real sample code in the baseline; a revision whose scope includes it cannot be submitted (`GOLDEN_CASES_INSUFFICIENT`, < 20), and issuing for a type outside the ACTIVE revision is refused (`TYPE_NOT_IN_RULE_SCOPE`). | DONE |
| G2 | 100 concurrent requests, no duplicate serial | `test_phase02_serial_allocation.py::test_id02_100_concurrent_confirms_no_duplicate_no_gap_one_snapshot_per_line_race`: REQUESTS = 100 over 32 workers, every 10th fails after allocation; no duplicate, no gap, one snapshot per line. Perf: 8 planners, 200 serials, gapless. | DONE (C8, race ×3) |
| G3 | Order / revision trace | order versions + snapshots + timeline (page 2), change-request chain, audit | DONE |
| G4 | Roles accepted | matrix v2.2 (DEC-057 + amendments 2026-11-12..15); privacy test equals the migrated grants | DONE; employer confirms at the Gate (**EMPLOYER**) |
| G5 | No known open Critical/P0 | none open (section 8) | DONE |
| G6 | No mandatory test FAIL / unexplained SKIP | 2 skips with reasons (ClamAV; real golden file not on the CI path; the real run is in S4) | DONE |
| G7 | Migrations reversible or approved compensation | roundtrip + rehearsal A–D; with data, restore from backup | DONE (**EMPLOYER** acknowledges) |
| G8 | Permission matrix approved | v2.2, recorded 2026-11-15 | DONE |
| G9 | CI report linked to the commit | C8 tree ids equal b3597158 for every stage (`EVIDENCE_NOTE.md`, REV-0280) | DONE |
| G10 | Real, non-demo UI | every PHASE_02 page bound to the real API; later-phase blocks labelled «در دست ساخت» with no numbers | DONE |
| G11 | Whole scope traceable | this file | DONE |
| G12 | Employer and auditor acceptance; checklist signed | sign-off rows blank on purpose | **EMPLOYER** |

## 5. Acceptance cases (minimum_phase 2)
| Case | Test | Status |
|---|---|---|
| ID-01 14-digit code with leading zeros | `test_id01_code_with_leading_zeros_is_stored_and_read_back_as_the_same_text`, `test_id01_db_refuses_*`, `test_id01_field_never_coerces_an_integer`; E2E page 4/29 | DONE |
| ID-02 multi-user serial allocation | `test_id02_100_concurrent_confirms_…_race` | DONE |
| ID-03 PO with independent lines | `test_id03_one_po_many_independent_lines_each_with_its_own_serial` | DONE |
| ID-04 duplicate request idempotency | `test_id04_*` (engine + HTTP replay) | DONE |

## 6. UI pages
| Page | Implementation | Screenshots (C8-shots) | Status |
|---|---|---|---|
| 1 Serial control centre — summary | `SerialCenterPage` «خلاصه» | `phase02-page01-serial-summary-*` | DONE |
| 2 Serial control centre — order tab | `SerialCenterPage` «سفارش» | `phase02-page02-serial-order-*` | DONE |
| 4 Products and styles | `ProductsPage` | `phase02-page04-product-style-*` | DONE |
| 29 Order entry and coding | `OrdersPage`, `CustomersPage`, `CodeRulesPage` | `phase02-page29-*`, `phase02-customers-*`, `phase02-code-rule-review-*` | DONE |
| 33 Order changes (PHASE_02 part) | `ChangesPage` | `phase02-page33-*` | DONE (engineering ECR/ECO: PHASE_05, CARRIED) |
| Approval inbox, PHASE_02 tab | `DecisionInbox` | `phase02-inbox-decisions-*` | DONE |

## 7. Decisions relevant to PHASE_02
- DEC-005: code rule; the Q-D clarifications of 2026-11-15/16.
- DEC-006: serial at confirm.
- DEC-025/035: bulk legacy migration in PHASE_12.
- DEC-027 P-A.
- DEC-028/060: no customer or staff names imported.
- DEC-037: intake.
- DEC-057: matrix v2.x.
- DEC-058: units and numbers; representative name as PII.
- DEC-059: due-date approver; cancel from hold.
- The DECISION_LOG amendments of 2026-11-12, 13, 14, 15 and 16.

All are recorded via `status.py decide`. Two employer questions remain open for the Gate (section 8).

## 8. Review issues raised in PHASE_02
- **P1, closed:** REV-0240 (02.4 rework).
- **P2:** REV-0201, 0220, 0230, 0231, 0241, 0251, 0252, 0253, 0261, 0262 and 0271 are closed.
- **P3:** all are closed, except:
  - REV-0203: one open change request per order, and expiry. Not enforced; needs an employer rule (**EMPLOYER**).
  - REV-0254: approvers see the requester as an id, not a name (**EMPLOYER**).
  - REV-0274: a reviewed migration (0025) was edited before any production DB existed. From the Gate on, fixes go into new migrations only (rule noted).
- REV-0276 is closed: the 14-day check for msoffcrypto-tool 6.0.0 is recorded in `step-7/logs/orch/dependency_audit.log`.
- The matrix row `identity.serial.allocate` is unused since `allocateSerial` was removed. Keep or drop it: **EMPLOYER** (a matrix v2.3 question).

## 9. Mandatory outputs
| Output | Where |
|---|---|
| CHANGELOG | `CHANGELOG.md` PHASE_02 section |
| Migration IDs | 0019–0028 (`docs/db/ERD.md`) |
| Updated ERD / OpenAPI | `docs/db/ERD.md`, `docs/api/openapi-draft.yaml` 0.8.4-draft |
| tests.xml / logs | C8 `pytest-*.xml`, per-step logs |
| Security artifacts | C8 `secret_scan.json`, `pip_audit_runtime.json`, SBOMs; `docs/security/PHASE_02_SECURITY_CHECKLIST.md` |
| UI screenshots | C8-shots |
| Recorded conflicts | `docs/discovery/CONFLICTS.md`; real import conflict counts (`step-8/logs/orch/real_import.json`: 222 disputed values / 640 rows, 2 multi product/style, 2 duplicate category names) |
| Signed checklist | **EMPLOYER** (blank sign-off rows) |
| New decisions | `control/decisions/DECISION_LOG.md` 2026-11-11..16 |
| Rollback | `docs/ops/ROLLBACK.md` §3b, each step's REPORT §8 |

## 10. Notes from the 02.8 review
- REV-0283: the disputed-item key changed in 02.8 from `<sheet>!value:` to `value:`. No production or staging DB exists, so nothing needs migrating; any later key change needs a data migration.
- A DISMISSED disputed value is raised again on the next import; only RESOLVED values carry over (to confirm with the employer).
