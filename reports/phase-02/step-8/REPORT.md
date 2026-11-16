# REPORT — PHASE_02 / 02.8 Report & Review

```
PROJECT: Aleekhan
PHASE: PHASE_02
STEP: 02.8
COMMIT SHA: b359715 (pre-gate fixes 68b3362, E2E follow-up 91b921a, CI perf b359715)
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-16
IMPLEMENTER: Claude Code (aleekhan-implementer) for the pre-gate fixes; CI, screenshot review, real-data run and reports by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 02.7 PASS (859b951); DECISION_LOG 2026-11-16
```

## 1. Purpose & acceptance
Step text: report template, git commit hash, migrations, test results, UI snapshots, Trace Map and issues; **STOP** and wait for PASS/REWORK/BLOCKED.

**Deliverables:**
- `reports/phase-02/PHASE_REPORT.md` and `.json`
- `reports/phase-02/TRACE_MAP.md`
- `reports/phase-02/GATE_PACKET_FA.md`
- `reports/phase-02/UAT_HOWTO_FA.md` (T-004)

## 2. Actual changes
**Employer decision, 2026-11-16 (REV-0271):** a resolved disputed legacy value carries over to later Planning imports.

**Pre-gate fixes, 68b3362:**
- **REV-0271:** a resolved disputed value is not raised again.
  - The import counts it as `legacy_values_disputed_reused` / `legacy_rows_disputed_reused`.
  - Each reused value gets an audit row that references the earlier item and carries no raw value.
  - A DISMISSED item is raised again: a dismissal is not a decision on the value. This is a conservative reading that the reviewer may question.
- **REV-0272:** one item per value across NOrder and Codding, with key `value:<sha256[:24]>` and sheet-qualified cell references.
- **REV-0273:** the 0028 docstring now matches the code.
- **REV-0275:** the synthetic factories moved to `platform_core/devtools/`, so `drill_seed.py` no longer imports tests.

**Follow-ups found by the orchestrator's CI run:**
- **91b921a:** the E2E seed still imported the moved factories, so E2E failed in the first CI run. Its import now points at `platform_core.devtools`.
- **b359715:** the CI perf stage now also runs the PHASE_02 perf tests.

**Other:**
- **REV-0253:** the orchestrator viewed all 16 PHASE_02 screenshot sets at 1440/1180/768/390. There were no functional defects; cosmetic remarks went to `control/UI_POLISH_BACKLOG.md` UIP-003. The footer build is the tested frontend (REV-0256).
- **REV-0276:** the 14-day line for msoffcrypto-tool 6.0.0 was added to `step-7/logs/orch/dependency_audit.log`.

## 3. Data integrity
Real Planning import on a fresh throw-away DB (`test_aleekhan_import05`, dropped afterwards):
- 6 types, 111 categories, 2841 legacy codes;
- 226 conflicts: **222** disputed values over 640 rows, 2 codes with more than one product/style, 2 duplicate category names.

The disputed count was 224 per sheet. It is now 222 per value, because 2 values appear in both NOrder and Codding (REV-0272). The output is counts only.

## 4. Security evidence
- Secret scan: 0.
- Leak grep: 0.
- No real value in the repo.
- `handoff/` is unchanged.

## 5. Test evidence
| Check | Result | Log |
|---|---|---|
| Full local CI on b359715, 13 stages | 13/13 PASS; tree ids match the commit | `logs/ci/summary.md`, `commit.txt` |
| First CI run on 68b3362 | 12 PASS; E2E FAIL (seed import), fixed in 91b921a | `logs/ci/09_e2e_attempt1_seed_import.log` |
| Orchestrator pytest -m "not perf" | 3160 passed, 2 skipped | `logs/orch/pytest.log` |
| perf / race ×3 | 11 passed / 38 in each run | `logs/orch/perf.log`, `race_x3.log` |
| roundtrip / roles / drill / rehearsal | OK / 78/78 / PASS / PASS | `logs/orch/` |
| Real import | as §3 | `logs/orch/real_import.json` |
| Implementer targeted runs | 52 + 24 passed; drill PASS | `logs/impl_*.log` |

## 6. Demo
T-004 is added for the employer (`status.py test-add` after the 02.8 PASS, REV-0282): `reports/phase-02/UAT_HOWTO_FA.md`. The orchestrator prepares the environment when the employer is ready.

## 7. Issues / decisions
Employer items at the Gate (`GATE_PACKET_FA.md` §4):
- T-004;
- the checklist signature;
- REV-0203;
- REV-0254;
- the rollback boundary;
- the unused `identity.serial.allocate` row.

Not changed, by decision:
- The signed PHASE_00/PHASE_01 checklists still name the old test-factory paths, now in `platform_core/devtools/`. Signed documents are not edited.

## 8. Rollback
- `git revert b359715 91b921a 68b3362`. No migration was added in 02.8.
- The carry-over behaviour then disappears, and the employer decision of 2026-11-16 stays unimplemented.

## 9. Review request
PASS requested, against R01–R14.

## 10. Next step
**STOP:** the employer's Gate decision for PHASE_02.
