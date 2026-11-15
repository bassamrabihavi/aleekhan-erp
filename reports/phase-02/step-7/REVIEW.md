VERDICT: PASS (advisory until DEC-036 is APPROVED; the employer confirms)
PHASE/STEP: PHASE_02 / 02.7 Security & Ops   COMMIT: 859b951 (report commit c55b131)
REVIEWER: aleekhan-reviewer (fresh context, read-only)   DATE: 2026-11-15

## Reviewer reproduction (what I ran myself)
- `ruff check backend` -> "All checks passed!"; `ruff format --check backend` -> "248 files already formatted".
- `git diff --stat 3cf4868 c55b131 -- handoff` -> empty, so `handoff/` is unchanged.
- `pytest platform_core/tests/test_phase02_step7_{privacy,pii,ops}.py test_phase02_planning_import.py`.
  - Result: 2 passed (non-DB) and 60 errors.
  - Every error is `django.db.utils.OperationalError: connection timeout expired`. PostgreSQL could not be reached from the reviewer sandbox. This is an infra limit, not a test failure.
  - Because of this, I could not re-execute the DB-backed tests. Their result rests on the orchestrator's junit file, which I parsed:
    - `logs/orch/pytest.xml`: tests=3159, failures=0, errors=0, skipped=2.
    - test_phase02_step7_privacy: 24/24 passed. test_phase02_step7_pii: 1/1. test_phase02_step7_ops: 8/8. test_phase02_planning_import: 29/29.
  - The orchestrator should re-run these 4 files once more on a machine with a reachable DB before the Gate. This is not blocking.
- `pip show msoffcrypto-tool` in the venv -> 6.0.0, which matches `requirements.txt` and `requirements.lock`.
- `REPORT.json` parses. Its commit_sha is 859b951 and its status is COMPLETE.

## CHECKS
- R01 ✔ The scope matches the step text in PHASE_02.md:24.
  - Covered: secret scan, dependency scan, privacy/permission, perf, backup/rollback, job monitoring and the checklist.
  - The extra code changes close owed REVs from 02.4–02.6 (REV-0223/0244/0261/0262/0264/0265/0266) plus a defect found by the drill (0025). There is no new feature or page.
- R02 ✔ Every rule cites an APPROVED decision.
  - The disputed-value granularity and the rule that the raiser cannot resolve follow DECISION_LOG.md:263-268.
  - The steward and owner access follows :257-261.
  - REV-0203 is listed as undecided and is not enforced (checklist §7).
  - Perf budgets are labelled TECHNICAL DEFAULT, not SLA.
- R03 ✔ 0028 adds a nullable jsonb column with a CHECK that the value is an object, and it reverses exactly (migrations/0028:28-50).
  - `logs/orch/db_roundtrip.log` ends with "schema diff: EMPTY (10548 lines compared) ... ROUNDTRIP OK".
  - The REV-0223 function-family check is in scripts/db_roundtrip.sh:66-72.
  - `rollback_rehearsal.log` shows A–D PASS with "failures: 0", and every schema_diff_*.txt is empty.
- R04 ✔ The 0025 forward backfills the counters from issued numbers before the guard exists (migrations/0025:80-93).
  - Rehearsal D: "PHASE_02 invariants after forward (gapless serials, versions, snapshots, number counters, imports)".
  - Freshness now advances inside the apply transaction (integration/imports.py:609-613), so a failed apply rolls it back (test_phase02_step7_ops.py:167-215).
- R05 ✔ The golden gate is unchanged: approve still recomputes `golden_report` (codes.py:401-402).
  - The stored summary is used only for lists and write responses. The single GET is live (identity_views.py:643).
  - The approver page reads the single GET (CodeRulesPage.tsx:76).
- R06 ✔ The privacy test derives its matrix from the 0022/0024/0027 constants and asserts it equals the migrated DB (test_phase02_step7_privacy.py:44-55, 111).
  - It walks 16 roles × 69 ops and checks fresh MFA per holder role.
  - The OpenAPI contract is unchanged (`logs/orch/openapi_validate.log` OK).
- R07 n/a No UI change in this step (only e2e.sh/env.ts tooling).
  - The E2E regression run is in `logs/orch/e2e.log`: real backend rc=0, backend-down rc=0.
  - The screenshots were written to step-7's own folder (REV-0264).
- R08 ✔ `logs/orch/secret_scan.log`: "findings=0 -> PASS", tree plus 154 history commits.
  - `dependency_audit.log`: pip-audit and npm audit both report 0 vulnerabilities.
  - The 14-day rule violation of msoffcrypto-tool 6.1.0 was detected and re-pinned to 6.0.0 (released 2026-01-12, per logs/dependency_audit.log:15).
  - The PII test scans all application rows and logs for the full name and its parts (test_phase02_step7_pii.py:154-163).
  - The golden loader enforces maker ACTIVE + permission and writes an audit row (planning_import.py golden_maker / applied_planning_batch). Tested in test_phase02_step7_ops.py:124-163.
  - The junit hostname is redacted.
  - The real-data outputs (`real_import.json`, `real_serial_guard.json`) hold counts and masks only, with no raw value.
- R09 ✔ Monitoring reads integration/outbox tables only, with SELECTs (ops/monitoring.py import_health / event_families).
  - The Planning applier stays in product_identity.
  - Freshness stays owned by integration/imports.py.
  - No cross-owner writes were added.
- R10 ✔ The raw values stay in the staging rows. The disputed item key is value-free (a sha256 prefix), which is tested in test_phase02_step7_ops.py:92.
  - Freshness is deferred to APPLIED.
  - A re-run of the real file gives `already_applied: true` (`real_import_rerun.json`).
- R11 ✔ Backup drill PASS: the PHASE_02 counts are identical before the dump and after the restore, and IMPORT_APPLY_FAILED survives the restore (`backup_drill.log`).
  - `perf.log`: 11 passed.
  - Monitoring reason IMPORT_APPLY_FAILED reaches `job_status --fail-on warn` (ops test :188-192).
- R12 ✔ Evidence comes from the real PostgreSQL suite: orch `pytest.log` "3157 passed, 2 skipped, 11 deselected", consistent with the junit file.
  - race ×3 and roles_check 78/78 pass.
  - The DB re-run by the reviewer was not possible (see above).
- R13 ✔ Updated: CHANGELOG.md, docs/db/ERD.md, EVENT_CATALOGUE.md (schema_migration 0028), docs/ops/{BACKUP_RESTORE,JOB_MONITORING,ROLLBACK}.md, docs/integration/README.md (console operator rules), requirements comments, and SCHEMA_MIGRATION_HEAD (engine/events.py:46).
- R14 n/a Left to the employer at the Gate. The checklist sign-off rows are blank (docs/security/PHASE_02_SECURITY_CHECKLIST.md:109+). The step text says the checklist must be signed ("امضا شود"), which happens at the 02.8 Gate.

## ISSUES
- REV-0271 [P2] backend/platform_core/product_identity/planning_import.py:824 + tests/test_phase02_step7_ops.py:112-120
  - Problem: after a disputed value is RESOLVED, a later Planning file with the same value opens a NEW item for the same `conflict_key`. The steward or owner must decide the same value again on every new file. DEC-005 Q-D says "one decision per distinct value" but does not say whether that decision carries over to later imports.
  - Repro: the test itself (`again.count() == 1` after resolution).
  - Expected fix: ask the employer (see below). If the decision should carry over, skip raising an item for a value whose last item is RESOLVED, or link to it.
  - Regression test: re-import after resolve, then assert the expected behaviour.
- REV-0272 [P3] planning_import.py:824
  - Problem: the key is per (sheet, value). The same disputed value in NOrder and in Codding gives two items, while the decision text says one per distinct value. The real baseline count (224) matches the decision, so there is no practical impact today.
  - Expected fix: document it as intended, or key by value only.
  - Regression test: one value in both sheets, then assert the chosen count.
- REV-0273 [P3] migrations/0028_phase02_golden_summary.py:4-5
  - Problem: the docstring says the summary is stored at "create, golden cases added, submit, approve, reject, activate". The code stores it only at golden-add, submit and approve (codes.py:258, 370, 407). Not storing at reject/activate is harmless because content is frozen after DRAFT, so only the documentation is wrong.
  - Expected fix: correct the docstring.
  - Regression test: none.
- REV-0274 [P3] backend/platform_core/migrations/0025_phase02_api_numbers.py:77-93
  - Problem: the forward SQL of an already reviewed migration was edited. This is acceptable because no production or staging DB exists, the change is disclosed in REPORT §2 and the CHANGELOG, and the roundtrip and rehearsal pass.
  - Expected fix: from PHASE_02 Gate onward, fix such issues only with new migrations, and add this rule to the Gate packet.
  - Regression test: rehearsal D (already present).
- REV-0275 [P3] ops/backup/drill_seed.py:223-224
  - Problem: the ops drill script imports `platform_core.tests` factories and test modules. The report lists this as a known limit.
  - Expected fix: before staging, move the synthetic seed into a non-test module or keep the drill dev-only.
  - Regression test: the drill run.
- REV-0276 [P3] reports/phase-02/step-7/logs/orch/dependency_audit.log
  - Problem: the orchestrator log after the re-pin has no 14-day re-check line for msoffcrypto-tool 6.0.0. The compliant release date appears only in the implementer's log (logs/dependency_audit.log:15).
  - Expected fix: in 02.8, re-run the 14-day check on the final lock and save it.
  - Regression test: none.
- NOTE (not an issue in the code): the reviewer could not re-run the DB tests because PostgreSQL timed out from the sandbox. The orchestrator should re-run the 4 targeted files at 02.8 and save the log.

No P0 or P1 issues found.

## EMPLOYER ATTENTION
- کد قدیمی مورد اختلاف: وقتی مسئول داده برای یک مقدار تصمیم گرفت، اگر فایل بعدی Planning همان مقدار را داشته باشد، سیستم دوباره همان مقدار را برای تصمیم باز می‌کند. آیا تصمیم قبلی باید برای فایل‌های بعدی هم معتبر بماند؟ (REV-0271)
- در Gate فاز ۲: فهرست کنترل امنیتی (`docs/security/PHASE_02_SECURITY_CHECKLIST.md`) باید امضا شود. موارد باز آن برای زمان راه‌اندازی سرور است: دسترسی اضطراری، TLS، پشتیبان رمزشده، زمان‌بندی کارها و RPO/RTO.
- سؤال‌های باز قبلی (REV-0203 و REV-0254) همچنان منتظر تصمیم شما هستند.
