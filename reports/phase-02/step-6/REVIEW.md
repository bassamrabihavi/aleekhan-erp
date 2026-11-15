VERDICT: PASS
PHASE/STEP: PHASE_02 / 02.6 (Integration)  COMMIT: fe0058c (report 5c227d2, status f9aba9b; decision commit 6795d65 precedes it)
REVIEWER: aleekhan-reviewer (independent, read-only; verdict advisory until DEC-036)

Verdict basis: every applicable check has evidence and there are no P0 or P1 issues. Two P2 and five P3 issues remain open (below). The P2 issues should be closed or explicitly accepted before the PHASE_02 Gate packet.

## Re-run by the reviewer (work-windows, 2026-11-15)
- Targeted pytest: `test_phase02_planning_import.py`, `test_api_phase02_integration_access.py`, `test_integration_imports.py`, `test_integration_freshness_conflicts.py` and `test_integration_events.py` gave **121 passed in 65.05s**. The env came from `pg-test.env` with `ALEEKHAN_ENV=test`, and the password was never printed.
- `ruff check .`: "All checks passed!". `ruff format --check .`: "243 files already formatted".
- `manage.py makemigrations --check --dry-run`: "No changes detected".
- `mypy` on `planning_import.py`, `imports.py` and `integration_views.py`: "Success: no issues found in 3 source files".
- `tools/secret_scan.py`: findings=0, PASS.
- Not re-run on purpose (8 GB RAM limit): the full pytest suite, E2E, race x3 and the DB roundtrip. Orchestrator logs:
  - `logs/orch/pytest.log`: "3124 passed, 2 skipped, 7 deselected", `pytest.rc`=0. Both skips give a reason (clamd, real golden file).
  - `logs/orch/e2e.log`: real backend, `e2e.rc`=0. The tail shows "real-backend rc=0, backend-down rc=0" and the throw-away DB was dropped.
  - `logs/orch/race_x3.log`: 38 passed in each of the 3 runs.
  - `logs/orch/db_roundtrip.log`: 0026 and 0027 were applied, unapplied and applied again (lines 34-35, 139-140, 227-234, 284-285). The schema diff is "EMPTY", ending "ROUNDTRIP OK".
  - `logs/orch/roles_check.log`: "passed=78 failed=0".
- Screenshot viewed: `reports/phase-02/step-5/screenshots/phase02-page02-serial-order-768-tablet.png`.
  - REV-0251 is fixed: the serial title is on one line.
  - REV-0252 is fixed: the panels are titled «ارجاع‌های بیرونی سریال» and «ارجاع‌های بیرونی سفارش».

## CHECKS
- R01 Scope ✔ — The step text (PHASE_02.md:23) is "Source/Events, staging, retries, backoff, compensation, freshness, conflict queue, without changing another module directly". The commit covers exactly this:
  - one PHASE_02 source (0026);
  - an apply with compensation, retry and backoff (`imports.py` `apply_batch`, `apply_batch_with_retry`);
  - freshness `open_conflicts`;
  - the conflict queue access.
  - Bulk legacy order/serial migration stays gated: `test_other_sources_stay_rule_not_approved` asserts DEC-025 and DEC-016, and `SOURCE_APPLY_POLICIES == {"planning_catalogue_xlsm"}`.
  - `handoff/` is untouched.
  - The extras trace to approved decisions: the serial guard to DEC-006 P-A ("the import must verify this") and the golden loader to DEC-005.
- R02 Source of truth ✔ (with P3 notes) — Each rule cites an APPROVED decision:
  - units: DEC-058 (`planning_import.py:116-123` = DECISION_LOG 2026-11-12, "Units");
  - status: B1 RESERVED/ERP_PENDING (`:862-863`);
  - style 0000: legacy only;
  - catalogue ACTIVE: decided 2026-11-15 (`:650`, `:739`);
  - Q-D: never corrected, and the item goes to the conflict queue (`:806-814`).
  - Unknown units, duplicate names or codes, and changed values all become conflicts and are never guessed (`:606-613`, `:526-548`, `:625-642`).
  - The maker-checker flag on `conflict.resolve` is not in the decision text (REV-0263).
- R03 Database ✔ — 0026 is reversible, and its reverse deletes only while no batch or conflict exists. 0027 is an exact inverse, tested by `test_migration_0027_reverse_is_exact_and_forward_restores_it` (passed in the re-run). The roundtrip is OK (log above). No schema change.
- R04 Transactions ✔ — Apply runs in one `unit_of_work` (`imports.py` `_apply`), with audit and outbox in the same transaction.
  - Rollback is proven: `test_failed_apply_leaves_no_partial_rows_and_can_be_resumed` checks that there are no ProductClass, ProductCode or ConflictItem rows, that the batch is VALIDATED with its staging rows kept, that the failure audit and event exist, and that a re-run resumes.
  - Idempotency: `test_reimport_of_the_same_file_is_a_no_op`, plus the real re-run log `real_import_2_rerun.json` ("already_applied": true, attempts 0).
  - Never overwrite: `test_changed_file_raises_conflicts_and_never_overwrites`.
- R05 Engine ✔ — The golden loader goes through the 02.3 engine (`create_rule_revision` / `add_golden_cases`), and the result is a DRAFT revision. It refuses harness-only fields, and it is all or nothing (`test_golden_loader_*`, 5 tests). The real-data golden run was not done, and the report says so (REPORT.md §5).
- R06 API ✔ — The OpenAPI diff is additive (0.8.4-draft: `open_conflicts` plus `x-aleekhan-permission` on the 4 operations), and `openapi_validate.log` is OK.
  - Permissions per role are tested over HTTP (`test_api_phase02_integration_access.py`):
    - steward and owner: read and resolve;
    - viewer: freshness and count, with list, detail and resolve each giving 403;
    - employee, commercial, planning and code-rule roles: 403 on all four operations;
    - anonymous: 401;
    - the user who raised an item: 403 SELF_APPROVAL_FORBIDDEN.
  - Resolve keeps If-Match and Idempotency-Key.
- R07 UI ✔ — There are no new pages. REV-0251 has a CSS fix (`phase02.css`, ≤900px) and an E2E assert (`expectSerialTitleOneLine`). REV-0252 has `OrdersPage.tsx` `REFS_TITLE`, a vitest case and an E2E heading check. The 768 screenshot was viewed (see above). Note the screenshot-folder issue in REV-0264.
- R08 Security ✔ — Integration views auth change: `SessionCookieAuthentication` is the same class the PHASE_01 views use (`phase01/common.py:73`). It enforces CSRF on unsafe methods (`session_auth.py:110-111`), and `ScopedPermission` is unchanged. This change opens no new path for anyone without a grant (anonymous gets 401, and other roles get 403 by test).
  - Source quarantine: path outside the repo (`:212-219`), SHA-256 pinned before load and again after the read (`:259-263`), size limit, `keep_vba=False` and `data_only`, password only from env and never echoed (`:283-284`).
  - Secret scan: 0. The reviewer grep of the step logs found no password, private path or intake hash.
- R09 Module ownership ✔ — The integration framework never writes Identity tables. The applier is passed in by Identity (`SourceApplyPolicy.owner = platform_core.product_identity`), and Identity uses only the public integration API (`receive_file`, `stage_rows`, `validate_batch`, `raise_conflict`).
- R10 Integration ✔ (P2 note) — The data is handled in these ways:
  - The raw value is kept: in the staging payload and in `source_raw_value`.
  - Provenance is kept: batch, staging row, cell reference and transform version (`:484-493`).
  - Re-runs are safe: the staging → validate → apply flow can be resumed.
  - Failures are rolled back.
  - Freshness is tracked, with an open-conflict count.
  - Formulas are not kept: `source_formula` stays empty because only cached values are read, and the report says so (§7.4).
  - Reconciliation of disputed rows against PLANNING_EXTRACTION_SUMMARY is missing (REV-0261).
- R11 Operations ✔ — Retry covers only the transient SQLSTATEs 40001, 40P01 and 55P03, with exponential backoff, and is tested (`test_transient_failures_are_retried_with_backoff` expects sleeps [0.5, 1.0]). A permanent error is not retried. When retries give up, the failure is recorded with attempts and error code only. Backup and job monitoring are in 02.7 scope.
- R12 Tests/evidence ✔ — The orchestrator logs show real backend E2E with rc 0. The real-data run evidence is counts only (`real_import_final.json`, `real_serial_guard.json`). The reviewer re-ran the targeted tests (121 passed).
- R13 Docs ✔ — Updated docs:
  - `CHANGELOG.md`, `API_RUNTIME.md`, `openapi-draft.yaml`, `EVENT_CATALOGUE.md` with the event golden, `docs/integration/README.md`, `DATA_TABLE.md` and `PERMISSION_MATRIX_DRAFT.md`;
  - the dependency pins in `requirements.txt` and `requirements.lock`.
  - The 14-day release rule for the new pins is deferred to 02.7 (REV-0267).
- R14 Owner acceptance n/a — left to the employer at the Gate.
- Privacy / DEC-060 ✔
  - Tests use synthetic type segments `9x`, «ساختگی» labels and tmp-dir workbooks (`test_phase02_planning_import.py:1-8, 55-108`).
  - The only Persian words are the DEC-058 generic unit terms.
  - The 14-digit strings in the diff are all synthetic (`029x07...`).
  - The real-run JSON holds counts and shape masks only, with no value, hash or path.
  - Customer and staff columns are never read; `test_import_never_reads_other_columns` checks this, including that the serial column is not staged.
- Matrix v2.2 vs the 2026-11-15 decision ✔ — The decision commit 6795d65 says: "steward and the owner may read the conflict queue and resolve items; management_viewer sees counts and data freshness only". The grants in 0027 `ADDED_GRANTS` match this exactly:
  - `freshness.read`: steward, owner and viewer;
  - `conflict.read` and `conflict.resolve`: steward and owner.
  - The seed test asserts the holders equal `ADDED_GRANTS`.

## ISSUES
- REV-0261 [P2] reports/phase-02/step-6/REPORT.md:81 and `planning_import.py:797-814` — Disputed legacy rows are not reconciled. DEC-005 Q-D (DECISION_LOG 2026-11-12) says "the 634 legacy rows whose code is not 14 digits are … flagged DISPUTED … planning decides each one", but the real run created only 224 `legacy_code_disputed` items.
  - Cause: `validate_batch` marks NOrder rows with an identical payload as `ROW_DUPLICATE_PAYLOAD` ERROR (`imports.py:356-357`; `error_row_count` 1375 in `real_import_final.json`), so the applier never sees them.
  - The conflict key is per cell, so one item stands for N identical rows. The report states neither the mapping nor the counts.
  - Repro: `real_import_final.json` shows `norder_rows` 3917 = 3283 + 634, but `legacy_values_disputed` 224.
  - Expected fix:
    - in the report and DATA_TABLE, state the reconciliation 634 rows → 224 items + K duplicate rows (with the counts from the real run);
    - or attach the duplicate row refs or count to each item's details, so that "each one" is traceable.
  - Regression test: a synthetic workbook with 2 identical disputed NOrder rows. Assert 1 item and that its details/count cover both rows (or the count reported).
- REV-0262 [P2] management/commands/load_code_rule_golden.py:48-56; `planning_import.py:1113` — `--maker <uuid>` lets a console operator act as any user (`Caller(user_id=maker_id)`).
  - The audit then names that user as the maker of the DRAFT revision, although he did not act. That user is also barred from approving it later (maker-checker); under DEC-005 Q-A the approver is the employer himself.
  - Repro: run the command with another user's id. The revision's `created_by` and the audit actor are that user.
  - Expected fix:
    - record the console origin in the audit (for example, a system actor "on behalf of", or a mandatory `--operator-note` in the audit scope);
    - refuse a maker who holds `identity.code_rule.approve`, or document the consequence in the runbook.
  - Regression test: the audit row of a console load shows the console origin.
- REV-0263 [P3] migrations/0027_dec057_matrix_v22.py:46 and `integration/conflicts.py:204-206` — The maker-checker flag and the SELF_APPROVAL_FORBIDDEN rule on `conflict.resolve` are not in the 2026-11-15 decision text.
  - It is restrictive and it never fires for import items, because those are raised by `Actor.system()` (`planning_import.py:931-932`).
  - Expected fix: confirm it with the employer, or record it as a TECHNICAL DEFAULT in DECISION_LOG.
  - Regression test: already present (`test_the_user_who_raised_an_item_never_resolves_it`).
- REV-0264 [P3] reports/phase-02/step-5/screenshots/*.png (134 files) — The 02.6 E2E run overwrote the evidence screenshots of the already-PASSed step 02.5. 02.6 has no screenshot folder of its own, and the report does not mention the overwrite. The old images survive only in git history.
  - Expected fix: write future runs to `reports/phase-02/step-6/screenshots` (`E2E_SCREENSHOT_DIR`), and note the refresh in REPORT.md.
  - Regression test: none (process).
- REV-0265 [P3] integration/imports.py:399-400 — Freshness (`last_success_*`) advances at VALIDATE, not at APPLY. If a Planning apply fails, the source still shows "fresh" while no official row was written.
  - Expected fix: for sources with an apply policy, advance freshness at APPLIED; or show `batch_apply_failed` in the freshness item.
  - Regression test: after a failed apply, freshness does not report the batch as the last success (or it flags the failure).
- REV-0266 [P3] planning_import.py:1111 — `load_code_rule_golden --source-sha256` accepts any well-formed hash; it is not checked against an imported or registered batch.
  - Expected fix: require that a `planning_catalogue_xlsm` batch with that `file_sha256` exists, or document it.
  - Regression test: an unknown hash is refused.
- REV-0267 [P3] backend/requirements.txt — The 14-day release rule for `openpyxl==3.1.5` and `msoffcrypto-tool==6.1.0` is not verified. The report itself states this (§7.5). Close it in 02.7 (dependency scan).

Still open from earlier reviews (not re-judged here): REV-0203, REV-0223, REV-0244, REV-0254.

## EMPLOYER ATTENTION
- **تصمیم ۱۴۰۵/۰۸/۲۴ و DEC-005 (Q-D):** طبق Q-D «برنامه‌ریزی» درباره کدهای قدیمی مشکوک تصمیم می‌گیرد. طبق تصمیم امروز، این کار با «مسئول داده محصول» و مالک است و `planning_officer` به صف تعارض دسترسی ندارد. آیا همین درست است؟
- **۲۲۴ مورد کد مشکوک:** این ۲۲۴ مورد جای ۶۳۴ ردیف را گرفته‌اند، چون ردیف‌های تکراری یکی شده‌اند. آیا رسیدگی «به ازای هر مقدار» کافی است، یا هر ردیف جدا لازم است؟
- **قاعده تفکیک وظایف:** برای رسیدگی به تعارض یک قاعده اضافه شده است: کسی که موردی را ثبت کرده، خودش آن را حل نمی‌کند. این قاعده در متن تصمیم نبود. آیا تأیید می‌کنید؟
- **UAT:** صف تعارض‌ها (۲۲۸ مورد) فعلاً فقط از راه API در دسترس است. تست عملی آن در بسته Gate (۰۲.۸) و روی پایگاه UAT انجام می‌شود.
