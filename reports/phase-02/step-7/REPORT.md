# REPORT — PHASE_02 / 02.7 Security & Ops

```
PROJECT: Aleekhan
PHASE: PHASE_02
STEP: 02.7
COMMIT SHA: 859b951
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-15
IMPLEMENTER: Claude Code (aleekhan-implementer); verification re-run, dependency re-pin, real-data run and report by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 02.6 PASS (fe0058c); DECISION_LOG 2026-11-15 (DEC-005 Q-D); Planning intake sha 113f5400… (DEC-037)
```

## 1. Purpose & acceptance
Step text: security checklist, secret and dependency scan, privacy/permission tests, performance, backup/rollback and job monitoring for PHASE_02.

**Owed review items closed here:**
- REV-0223: roundtrip function counts.
- REV-0244: `golden_summary` performance.
- REV-0261: one conflict per disputed value.
- REV-0262: golden loader maker checks.
- REV-0264: screenshot folder per step.
- REV-0265: freshness only at APPLIED.
- REV-0266: the source batch must be APPLIED.

REV-0203 is only listed (checklist §7). It needs an employer rule.

## 2. Actual changes
- **Checklist** `docs/security/PHASE_02_SECURITY_CHECKLIST.md`:
  - 50 items in the PHASE_01 format.
  - Each item cites an existing test or log.
  - The sign-off rows are blank for the employer at the Gate.
- **Permission test** (`test_phase02_step7_privacy.py`):
  - The matrix is built from the 0022/0024/0027 constants and asserted equal to the migrated DB.
  - Every one of the 16 roles is walked over all 69 PHASE_02 + integration operations.
  - Without a grant the answer is 403 ACCESS_DENIED; with a grant it is never 401 or ACCESS_DENIED.
  - Fresh MFA is checked for 7 operations × every holder role.
- **PII test** (`test_phase02_step7_pii.py`):
  - It runs a full HTTP order lifecycle, including an idempotent replay and a change request.
  - It then scans every `platform_*`/`identity_*`/`commercial_*` row and every log record.
  - The representative name appears only in its own column.
- **Perf** (`test_perf_phase02.py`, 4 tests; budgets are technical defaults, not SLAs).
- **REV-0244:** migration `0028_phase02_golden_summary`, a reversible jsonb column with a CHECK.
  - The summary is stored when golden cases are added, at submit and at approve.
  - Lists read the stored value; the single GET recomputes it live.
- **REV-0261:** one `legacy_code_disputed` item per sheet and distinct value.
  - The key is value-free: `<sheet>!value:<sha256 prefix>`.
  - Each item carries `row_count` and up to 100 cell references.
  - Resolving the item settles all rows with that value. This matches DEC-005 Q-D (one decision per distinct value).
- **REV-0262:** the `--maker` must exist, be ACTIVE and hold `identity.code_rule.manage`.
  - The console load is audited as `identity.code_rule.console_load` and shares a request id with the create row.
- **REV-0266:** `--source-sha256` must match an APPLIED Planning batch (`SOURCE_BATCH_NOT_APPLIED`).
- **REV-0265:** a source with an apply policy advances freshness only at APPLIED, inside the apply transaction.
- **Job monitoring:**
  - `import_health` and `event_families` added to `ops/monitoring.py`.
  - `outbox_status` and `job_status` gain `imports`.
  - New reason `IMPORT_APPLY_FAILED` (warn).
  - Docs: `docs/ops/JOB_MONITORING.md`.
- **Backup and rollback:**
  - The drill seed now writes PHASE_02 rows.
  - `ops/backup/drill_verify_phase02.py` checks the invariants before the dump and after the restore.
  - Rehearsal scenario C rolls back head → 0018 → head with no PHASE_02 rows.
  - Scenario D, with PHASE_02 data, is refused at 0022 by design, stays consistent, and passes the invariants after the forward.
- **Defect found by the rollback rehearsal, fixed:**
  - **Symptom:** after a rollback past 0025 and a forward again, the number counters were empty, so CU-/SO-/CR- numbers would be issued again.
  - **Fix:** the forward of 0025 now positions each (kind, Jalali year) counter at the highest number already issued, before its guard exists.
  - A fresh DB inserts nothing, and the roundtrip schema diff is empty.
  - **Note:** this changes the forward SQL of a migration reviewed in 02.4. No production DB exists yet.
- **REV-0223:** `db_roundtrip.sh` fails if any function of the four PHASE_02 families is left after rollback.
- **REV-0264:** `e2e.sh` with `E2E_STEP=phase-XX/step-Y` writes to that step's folder. It refuses a folder holding committed screenshots, unless `E2E_SCREENSHOT_OVERWRITE=1`.
  - The step-5 screenshots are unchanged.
  - This step's run wrote to `reports/phase-02/step-7/screenshots/`.
- **Dependencies (orchestrator):** msoffcrypto-tool 6.1.0 was first uploaded 2026-11-03, 12 days before the pin, which breaks the ≥ 14-day rule (ADR-001).
  - It is re-pinned to **6.0.0** (2026-01-12) in `requirements.txt` and `requirements.lock`.
  - The full suite and the real import were re-run with 6.0.0.
  - The other new pins comply: openpyxl 3.1.5, et_xmlfile 2.0.0, olefile 0.47.

## 3. Data integrity
- Backup restore: fingerprint identical; serials gapless from 63001; line/serial pairing, snapshots, versions and counters intact.
- Rollback forward: counters restored from issued numbers, so no number is re-issued.
- Import apply is still all-or-nothing. Freshness moves only with an applied batch.

## 4. Security evidence
- The permission matrix equals v2.2 for every role and operation; no anonymous route.
- The representative name stays in its column only, and it is absent from the audit, outbox, idempotency records and logs.
- **Real-data run by the orchestrator** on throw-away DB `test_aleekhan_import04`, dropped afterwards. Output is counts only, and no real value entered the repo.
- Secret scan, tree + history: findings=0.
- Leak grep: 0 hits. The junit hostname is redacted.
- pip-audit (runtime lock) and npm audit (`--omit=dev`): 0 vulnerabilities.
- `handoff/` is unchanged.

## 5. Test evidence (orchestrator, `logs/orch/`)
| Check | Result | Log |
|---|---|---|
| ruff / mypy (248 files) / makemigrations --check | PASS / PASS / no changes | `ruff.log`, `mypy.log`, `makemigrations.log` |
| OpenAPI validation | OK (unchanged 0.8.4-draft) | `openapi_validate.log` |
| pytest -m "not perf" | 3157 passed, 2 skipped, 11 deselected | `pytest.log` |
| pytest -m perf | 11 passed (budgets asserted) | `perf.log` |
| race ×3 | 38 passed in each run | `race_x3.log` |
| db_roundtrip.sh | ROUNDTRIP OK, schema diff empty | `db_roundtrip.log` |
| roles_check.sh | 78/78 | `roles_check.log` |
| backup drill | PASS | `backup_drill.log`, `drill/` |
| rollback rehearsal A–D | PASS, failures 0 | `rollback_rehearsal.log`, `rollback/` |
| pip-audit / npm audit | 0 / 0 | `dependency_audit.log` |
| frontend eslint / tsc / vitest / build | rc 0 / 0 / 73 passed / 0 | `eslint.log`, `typecheck.log`, `vitest.log`, `build.log` |
| E2E full (Edge, `E2E_STEP=phase-02/step-7`) | 32 passed + backend-down 1 passed | `e2e.log` |
| Real serial guard | 3920 values, **0 ≥ 63000**, `safe_for_start: true` | `real_serial_guard.json` |
| Real catalogue import (msoffcrypto-tool 6.0.0, fresh DB) | 6 types, 111 categories, 2841 codes, 228 conflicts; 224 disputed values over 640 rows | `real_import.json` |
| Real re-run (same file) | `already_applied: true` | `real_import_rerun.json` |

- The 640 disputed rows (634 in the DEC-005 Q-D note) differ because identical repeated rows are now counted. The number of distinct values, 224, is unchanged.
- Measured perf numbers come from the implementer's verbose run (`logs/perf_phase02.json`, work-windows):
  - confirm, 100 lines: 1336 ms;
  - 8 concurrent planners: 45.6 serials/s, gapless;
  - baseline-like Planning import: 8.85 s;
  - list p95, page size 100: ≤ 111 ms;
  - code-rule list (REV-0244): p95 30.8 ms, against a 374.5 ms p50 for the old live rebuild.
- The orchestrator's perf run used `-q`, so its numbers are not printed; the budgets are asserted in the tests.
- The first orchestrator test run was stopped by the OS for low memory at 88%, with no failure up to that point. The full re-run above passed.

## 6. Demo (employer)
Nothing new to try hands-on.

At the Gate, the employer will read and sign the security checklist (`docs/security/PHASE_02_SECURITY_CHECKLIST.md`). The UAT how-to comes with the 02.8 Gate packet.

## 7. Issues / decisions
1. **Carried open (production readiness, checklist §8):**
   - break-glass access;
   - TLS / CSP / encrypted backups;
   - artifact signing;
   - a job scheduler;
   - RPO/RTO measured on staging.
2. **Employer questions at the Gate:**
   - REV-0203: one open change request per order, and expiry;
   - REV-0254: whether approvers see the requester's name;
   - the unused `identity.serial.allocate` matrix row.
3. **REV-0263** (the raiser cannot resolve) was confirmed in DECISION_LOG 2026-11-15, so it can be closed.
4. **Known limits:**
   - An already open disputed item keeps its first `row_count` when a later file brings the same value.
   - `drill_seed.py` uses the test factories.
   - The PHASE_00 perf smoke test overwrites the shared perf JSON (logged, unchanged).

## 8. Rollback
`migrate platform_core 0027` (0028 reverses; tested in the roundtrip and the rehearsal), then `git revert 859b951`. The 0025 forward change has no effect on a DB that is already migrated.

## 9. Review request
PASS requested, against R01–R14.

## 10. Next step
02.8 Report & Review:
- phase report and Trace Map;
- Gate packet `reports/phase-02/GATE_PACKET_FA.md` with the UAT how-to;
- tag `phase-02-rc1`;
- STOP for the employer's Gate decision.
