# PHASE REPORT — PHASE_02 Order & Product Identity

```
PROJECT: Aleekhan
PHASE: PHASE_02 (مشتری، محصول، استایل، ثبت سفارش و سریال)
COMMIT SHA: b3597158ecb4e5bb56759d7a082210e3cdaf1fae (candidate; tag phase-02-rc1 on the Gate packet commit)
BRANCH/PR: main
STATUS: COMPLETE — GATE PENDING (employer)
TIME OF REPORT (UTC): 2026-11-16
IMPLEMENTER: Claude Code (aleekhan-implementer); verification, real-data runs and reports by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; PHASE_01 accepted; Planning intake sha 113f5400… (DEC-037); DECISION_LOG up to 2026-11-16
```

## 1. Purpose & acceptance IDs
PHASE_02 makes the product identity real:
- customers and brands;
- products and styles;
- the 14-digit code under an approved rule, reproduced from the real Planning golden cases;
- customer orders with versions;
- serials allocated atomically at confirm (gapless from 63001), with a snapshot per line;
- change requests;
- the Planning master-data import.

Acceptance: ID-01..ID-04 are all DONE (`TRACE_MAP.md` §5). Pages 1, 2, 4, 29 and 33 are built (§6).

## 2. Actual changes (whole phase)
- **DB:** migrations 0019–0028, all reversible.
  - Tables: identity, commercial, number counters, code rules with golden cases, import and conflict support.
  - DB guards: gapless serial; one serial per line; maker-checker CHECKs.
- **Engine:** `product_identity/` (code rule, codes, serials, master data, Jalali, external references, Planning import) and `commercial/` (orders, changes).
- **API:** contract 0.8.4-draft, with all PHASE_02 operations routed.
  - Session auth and matrix v2.2.
  - ETag/If-Match, Idempotency-Key, rate limit, pagination, request id.
  - Fresh MFA on sensitive actions.
- **UI:** the serial centre (pages 1/2), products and styles (4), orders and coding (29), customers, code rules, changes (33), and the PHASE_02 inbox tab.
  - Persian RTL, four sizes.
- **Integration:** server-side Planning catalogue import, with staging, compensation, retry/backoff, freshness, and a conflict queue (steward + owner).
- **Ops:** PHASE_02 job monitoring; backup drill and rollback rehearsal with PHASE_02 data.
- **Security:** the security checklist, the permission and PII suites, and the dependency pins under the 14-day rule.

Details per step are in `step-1..8/REPORT.md`; the commits are in `CHANGELOG.md`.

## 3. Data integrity
- Serials are allocated inside the confirm transaction:
  - no duplicate and no gap, even under 100 concurrent confirms with failures;
  - a failed confirm consumes no number.
- Numbers `SO-/CU-/CR-<Jalali year>-NNNNNN` come from counters that cannot be reset. After a rollback and a forward they continue from the highest issued number.
- **Codes:**
  - 14 ASCII digits stored as text;
  - issued only under an ACTIVE revision with at least 20 golden cases per family in scope;
  - legacy codes are registered, not re-issued.
- **Imports:** all-or-nothing and idempotent per file hash.
  - Conflicts are never auto-resolved.
  - A resolved disputed value carries over to later imports (employer, 2026-11-16).

## 4. Security evidence
- **Permissions:** 16 roles × 69 operations equal the matrix v2.2; fresh MFA is checked for every holder role.
- **Representative name** (DEC-058 PII):
  - stored only in its own column, which the test proves;
  - masked for management_viewer;
  - every read audited.
- **No real data in Git.** Real Planning values exist only in `F:/aleekhan/private-extract/` (outside the repo) and in throw-away test DBs, which were dropped. Reports hold counts only.
- **Scans:** secret scan of tree + history: 0. pip-audit runtime: 0. npm audit: 0.
- **Checklist:** `docs/security/PHASE_02_SECURITY_CHECKLIST.md` has 50 items. The sign-off rows are blank for the Gate.

## 5. Test evidence
Full local CI on b3597158 is 13/13 PASS (`step-8/logs/ci/summary.md`):
- unit/integration: 1759 passed;
- authz: 1481 passed;
- contract: 18;
- E2E: 32 + 1;
- perf: 1 + 6 + 4;
- roles: 78/78;
- drill and rehearsal: PASS.

Orchestrator full suite (O8): 3160 passed, 2 skipped; race ×3: 38 each.

**Real data:**
- golden v3: 2313 cases, `not_reproduced=0`, C-77 0 disagreements in 1218 checked, belt 169 (S4);
- legacy serial guard: 0 values ≥ 63000;
- catalogue import: 6 types, 111 categories, 2841 codes, 222 disputed values over 640 rows (O8).

The mapping is in `TRACE_MAP.md`.

## 6. Demo
The employer's hands-on UAT is T-004 (`reports/phase-02/UAT_HOWTO_FA.md`). The orchestrator prepares the UAT environment, with the real catalogue import and the code rule from the real golden cases, when the employer is ready.

## 7. Issues / decisions
- **Open for the employer at the Gate:**
  - REV-0203: rules for open change requests;
  - REV-0254: requester name versus id;
  - the unused `identity.serial.allocate` matrix row;
  - the security checklist signature.
- **Carried to the staging server or production:** break-glass access, TLS/CSP/encrypted backups, artifact signing, the scheduler, RPO/RTO on staging.
- **Data for the steward after go-live:** 222 disputed legacy values, 2 codes with more than one (product, style), 2 duplicate category names. Bulk legacy migration is in PHASE_12.
- **Family 06 (ست):** no real sample codes in the baseline, so its codes stay blocked until at least 20 approved cases exist.

## 8. Rollback
- **Before production:** `migrate platform_core 0018` (tested in rehearsal C), then revert the PHASE_02 commits.
- **With PHASE_02 business data:** the rollback is refused at 0022 by design. The way back is restore from backup, which is drilled (`docs/ops/ROLLBACK.md` §3b, `docs/ops/BACKUP_RESTORE.md` §7).

## 9. Review request
The 02.8 review covers this report, `TRACE_MAP.md` and the Gate packet. Gate decision: employer.

## 10. Next step (proposal only)
After Gate acceptance: PHASE_03, as the employer starts it.
