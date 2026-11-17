# PHASE_02 security checklist (step 02.7)

Baseline: `handoff/05_SECURITY/SECURITY_BASELINE_FA.md` (OWASP ASVS 5.0.0 as review reference - **not a claim of
certification**). PHASE_02 scope: customers / brands, product / style / revisions, 14-digit product codes and
the code rule with golden cases (DEC-005), factory serials (DEC-006), customer orders with versions, change
requests (DEC-059), external references, historical records, the Planning catalogue import, the conflict queue
and freshness (matrix v2.2, DEC-057 + amendments); pages 1, 2, 4, 29, 33. No deployment server yet (DEC-045 A):
deployment items stay OPEN, with their owner named, as in the PHASE_01 checklist.

Status values: **DONE** (evidence exists), **PARTIAL** (part done, rest named), **OPEN** (gap, listed in the
02.7 report), **CARRIED** (unchanged since the PHASE_01 checklist, `docs/security/PHASE_01_SECURITY_CHECKLIST.md`,
which the employer accepted with conditions on 2026-11-11).

Evidence paths are repository files. `tests/` = `backend/platform_core/tests/`; `logs/` =
`reports/phase-02/step-7/logs/` (redacted; junit hostname `redacted-host`). The test runs, counts and
measured numbers are in the 02.7 report and its logs.

## 1. Identity, authorization, approvals

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1.1 | Deny by default, every PHASE_02 + integration operation x every seeded role, exactly per matrix v2.2 | DONE | `tests/test_phase02_step7_privacy.py::test_every_role_gets_exactly_the_operations_the_matrix_grants` (16 seeded roles x 69 operations: 403 `ACCESS_DENIED` without the grant, never 401 / `ACCESS_DENIED` with it); the matrix comes from the seed: `test_migrated_grants_equal_the_seed_constants` (migrated DB == 0022 + 0024 + 0027 constants); `test_api_phase02_contract.py::test_employee_has_no_phase02_access`, `test_management_viewer_never_writes` |
| 1.2 | Permission matrix approved and equal to the seed (v2.2) | DONE | `docs/security/PERMISSION_MATRIX_DRAFT.md` (DEC-057 + amendments 2026-11-12 / 2026-11-15 in `control/decisions/DECISION_LOG.md`); `test_api_phase02_contract.py::test_seeded_phase02_permissions_equal_the_operations_and_mfa_flags`; `test_api_phase02_integration_access.py::test_matrix_v22_seed` |
| 1.3 | Fresh MFA for the five DEC-057 actions (issue, code-rule approve, order confirm, change decide, planning approve) | DONE | `test_phase02_step7_privacy.py::test_mfa_operations_need_a_fresh_step_up_for_every_holder_role` (7 operations x 5 holder roles -> 401 `MFA_REQUIRED`); `test_api_phase02_contract.py::test_operations_sharing_a_phase02_permission_share_the_mfa_flag`; `test_phase02_engine_orders.py::test_confirm_needs_fresh_mfa`; `test_api_phase02_flows.py::test_rev0243_stale_mfa_is_refused_on_reject_activate_and_planning_decision` |
| 1.4 | Maker-checker: order confirm (confirmer != creator, also the owner) | DONE | DB + engine: `test_phase02_engine_orders.py::test_confirmer_is_never_the_creator_not_even_the_owner`, `test_phase02_schema.py::test_order_confirmer_is_not_its_creator_and_confirmed_line_needs_a_serial`, `test_api_phase02_flows.py::test_confirmer_is_never_the_creator` |
| 1.5 | Maker-checker: change request decide (requester never decides) and planning decision (a third person) | DONE | `test_phase02_engine_changes.py::test_requester_never_decides_and_the_owner_decides_directly`, `test_due_date_change_needs_planning_approval_by_a_third_person`, `test_db_refuses_a_planning_approver_who_is_the_requester_or_the_decider`, `test_db_refuses_a_planning_rejection_that_is_not_final_or_not_independent`; `test_phase02_schema.py::test_change_request_maker_checker_and_due_date_needs_the_planning_approval` |
| 1.6 | Maker-checker: code rule approve (maker never approves; DEC-005 Q-A) | DONE | DB CHECK `ck_identity_code_rule_approved_by_other`; `test_phase02_schema.py::test_code_rule_maker_checker_and_lifecycle`, `test_phase02_engine_identity.py::test_code_rule_lifecycle_with_maker_checker_and_golden_gate` |
| 1.7 | Maker-checker: conflict resolve (the raiser never resolves; system-raised import items unaffected, DECISION_LOG 2026-11-15) | DONE | `integration/conflicts.py::_resolve`; `test_api_phase02_integration_access.py::test_the_user_who_raised_an_item_never_resolves_it` |
| 1.8 | Admin != business approval; owner decides directly only on the DEC-057 pairs, never his own request | DONE | DB guard `ck_role_technical_no_business_approval` (0022: six owner pairs); `test_phase02_schema.py::test_owner_decides_directly_but_technical_roles_hold_no_other_business_approval`; decision inbox `test_api_phase02_inbox.py::test_order_confirm_item_for_planning_and_owner_never_for_the_creator` |
| 1.9 | Per-record scope (BOLA/IDOR) | DONE | DEC-057: every PHASE_02 role sees all customers (no per-officer scope); unknown / out-of-scope ids answer 404 on every `{id}` operation (`test_api_bola.py::test_every_id_path_family_has_a_bola_case`; contract rule "404 on every `{id}` operation", `test_api_phase02_contract.py::test_every_phase02_operation_needs_session_and_a_decided_permission`) |
| 1.10 | Console commands act as an identified, active, permitted user (REV-0262) | DONE | `planning_import.golden_maker` (ACTIVE + `identity.code_rule.manage`); audit `identity.code_rule.console_load` (origin console); `test_phase02_step7_ops.py::test_golden_loader_maker_must_be_an_active_holder_and_the_console_is_audited`; operator rule "own account only": `docs/integration/README.md` section 10 |
| 1.11 | Emergency (break-glass) access | OPEN (CARRIED, before production, DEC-054 A) | PHASE_01 checklist 1.10 |

## 2. Personal data, confidentiality

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 2.1 | Customer representative = a name only, no contact data (DEC-058) | DONE | `commercial/orders.representative_name` refuses `@` and any digit; `test_phase02_engine_orders.py::test_representative_is_a_name_only`; no contact columns: `test_phase02_schema.py::test_representative_name_is_only_a_name_and_contact_columns_do_not_exist` |
| 2.2 | Representative masked for `management_viewer`, every unmasked read audited (without the value), never echoed by a write | DONE | `test_phase02_engine_orders.py::test_representative_name_masked_for_viewer_and_every_unmasked_read_audited`, `test_representative_change_is_audited_without_the_value`; `test_api_phase02_flows.py::test_order_lifecycle_representative_masking_serials_and_versions` |
| 2.3 | Representative never in logs, outbox payloads, audit values, idempotency records, version images, serial snapshots | DONE | `tests/test_phase02_step7_pii.py::test_representative_name_never_leaves_its_column` (HTTP lifecycle incl. an idempotent replay, a change request, owner / officer / viewer reads; then every row of every `platform_*` / `identity_*` / `commercial_*` table via `row_to_json` - the order column removed - and every log record: 0 hits of either synthetic name or its words) |
| 2.4 | No real factory data in the repository (public repo, DEC-060 / DEC-046, R-38) | DONE | synthetic only (`9x` segments, «ساختگی», random synthetic names); Planning workbooks are built in pytest's tmp dir; real-run evidence = counts only (`reports/phase-02/step-6/logs/orch/real_*.json`); secret scan tree + history `logs/secret_scan.log` |
| 2.5 | Secrets never in Git / logs; workbook password from env only, never printed | DONE | `planning_import.password_from_env`; `test_phase02_planning_import.py::test_encrypted_workbook_needs_the_password_env`; `tools/secret_scan.py --history` (`logs/secret_scan.log`); pre-commit guard |
| 2.6 | Outbox payloads S1 only (ids, statuses, counts), schemas closed | DONE | `engine/events.py` (PHASE_02 specs: no name, no code value, no serial number in the payload); `test_integration_events.py` (catalogue golden `tests/golden/event_catalogue.golden.json`) |
| 2.7 | Conflict items value-free (cell references, shapes, value hash prefix) | DONE | `planning_import.disputed_value_key`; `test_phase02_step7_ops.py::test_disputed_value_is_one_item_with_the_count_of_every_row` (value absent from key and details) |
| 2.8 | HTTPS/TLS, CSP, encrypted backups | OPEN / PARTIAL (CARRIED) | PHASE_01 checklist 2.6, 2.7, 3.4 - staging server (DEC-042, DEC-045 A) |

## 3. Data integrity of PHASE_02 identifiers

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 3.1 | 14-digit codes are text (`varchar(14)` + regex), leading zeros kept, never numeric in the API | DONE | `test_phase02_schema.py::test_id01_code_with_leading_zeros_is_stored_and_read_back_as_the_same_text`, `test_id01_db_refuses_any_code_that_is_not_14_ascii_digits`; `test_api_phase02_contract.py::test_14_digit_codes_are_code14_strings`, `test_no_phase02_schema_types_a_code_serial_or_number_as_a_number`; import: a numeric cell is disputed, never coerced (`test_phase02_planning_import.py::test_import_applies_types_categories_and_legacy_codes_with_provenance`, `NOT_TEXT`) |
| 3.2 | Serial gapless (DEC-006 G-B), from 63001, unique, transactional with the confirm, idempotent | DONE | DB: `test_phase02_schema.py::test_counter_moves_by_exactly_one_and_keeps_its_fixed_columns`, `test_a_serial_number_must_have_been_drawn_from_the_counter`, `test_serial_without_snapshot_or_line_cannot_commit`; engine: `test_phase02_serial_allocation.py::test_rollback_after_allocation_does_not_consume_a_number`, `test_id04_same_allocation_key_replays_the_same_serial_without_a_new_number`; race: `test_id02_100_concurrent_confirms_no_duplicate_no_gap_one_snapshot_per_line_race`, `test_api_phase02_flows.py::test_concurrent_confirms_through_the_api_one_wins_no_duplicate_serial_race` (`logs/race_x3.log`); perf under 8 writers, gapless: `tests/test_perf_phase02.py::test_perf_serial_allocation_throughput_under_concurrency` (`logs/perf.log`) |
| 3.3 | Technical numbers (CU- / SO- / CR- + Jalali year) unique and race-safe, never re-issued after a rollback | DONE | 0025 counter guard (`ops/db/roles_check.sh`: runtime role cannot reset); **02.7 fix**: the 0025 forward re-positions counters at the highest issued number (`docs/ops/ROLLBACK.md` section 3b; rehearsal scenario D + `ops/backup/drill_verify_phase02.py`, `logs/rollback_rehearsal.log`) |
| 3.4 | Confirmed orders change only through versions; snapshots append-only | DONE | `test_phase02_schema.py::test_confirmed_order_header_is_frozen_and_changes_only_with_a_new_version`, `test_confirmed_serial_is_immutable_never_deleted_and_cancel_is_terminal`; `test_phase02_engine_changes.py::test_quantity_change_keeps_the_serial_and_writes_version_2_and_snapshot_2` |
| 3.5 | Optimistic concurrency (ETag / If-Match) and idempotency on every write | DONE | `test_api_phase02_contract.py::test_every_write_requires_an_idempotency_key`, `test_every_versioned_write_requires_if_match` (428 / 412 / 400); `test_phase02_engine_orders.py::test_every_line_edit_moves_the_order_etag`; `test_api_phase02_flows.py::test_customers_brands_numbers_search_duplicate_warning_and_412` |
| 3.6 | Rate limits on PHASE_02 endpoints | DONE | `test_api_phase02_flows.py::test_rate_limit_per_principal_on_phase02_endpoints`; TECHNICAL DEFAULT rates `docs/api/API_RUNTIME.md` |
| 3.7 | Audit hash chain + outbox in the same unit of work for every PHASE_02 write | DONE | `engine/uow.py` (`check_emit`); `test_phase02_serial_allocation.py::test_allocation_writes_serial_snapshot_audit_and_outbox_together`; chain verifies after restore: `ops/backup/drill.sh` (`logs/backup_drill.log`, check "audit hash chain verifies after restore") |

## 4. Import safety (Planning catalogue, DEC-005 / DEC-037)

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 4.1 | File pinned by SHA-256 before load and again after the read; path outside the repository | DONE | `test_phase02_planning_import.py::test_sha_mismatch_is_refused_before_anything_is_written`, `test_file_changed_between_hash_and_read_is_refused`, `test_path_inside_the_repository_is_refused` |
| 4.2 | Macros never executed; data only; no external links | DONE | `open_workbook` (`read_only`, `keep_vba=False`, `data_only`, `keep_links=False`); `test_phase02_step7_ops.py::test_workbook_is_opened_as_data_only_without_macros_or_links`; `test_not_a_workbook_is_refused` |
| 4.3 | Never overwrite; changed values -> conflict queue; re-import idempotent | DONE | `test_phase02_planning_import.py::test_changed_file_raises_conflicts_and_never_overwrites`, `test_reimport_of_the_same_file_is_a_no_op` |
| 4.4 | Whole apply or nothing (compensation = rollback), retries only on transient errors | DONE | `test_failed_apply_leaves_no_partial_rows_and_can_be_resumed`, `test_transient_failures_are_retried_with_backoff`, `test_a_permanent_failure_is_not_retried` |
| 4.5 | Only the columns needed are read (no customer / person / serial values staged) | DONE | `test_phase02_planning_import.py::test_import_never_reads_other_columns` |
| 4.6 | Golden cases only from an APPLIED Planning import (REV-0266) | DONE | `planning_import.applied_planning_batch`; `test_phase02_step7_ops.py::test_golden_loader_refuses_a_hash_without_an_applied_planning_batch` |
| 4.7 | Disputed legacy values: one decision per distinct value, every row counted (REV-0261, DECISION_LOG 2026-11-15) | DONE | `test_phase02_step7_ops.py::test_disputed_value_is_one_item_with_the_count_of_every_row`; baseline-like volume (224 values / 634 rows, synthetic): `test_perf_phase02.py::test_perf_planning_import_and_paginated_lists` |
| 4.8 | Other sources stay blocked (bulk legacy order / serial migration DEC-025 / DEC-035; Rahkaran DEC-016) | DONE | `test_phase02_planning_import.py::test_other_sources_stay_rule_not_approved` |
| 4.9 | Size limit (TECHNICAL DEFAULT 128 MiB for this source only) | DONE | `test_planning_limit_still_refuses_larger_files_before_reading` |

## 5. Application / supply chain

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 5.1 | SQL injection / XSS / CSRF | DONE (CARRIED) | ORM + parameterised SQL, ruff `S` (`logs/ruff.log`); React escaping; PHASE_01 session auth with CSRF also on the integration views (02.6 fix3) |
| 5.2 | SCA / dependency scan | DONE | `pip-audit` on `backend/requirements.lock`: no known vulnerabilities (`logs/ci/pip_audit_runtime.json`, `logs/dependency_audit.log`); `npm audit --omit=dev`: 0 |
| 5.3 | Repository rule: only versions released >= 14 days before the pin date | DONE (fixed by orchestrator) | `logs/dependency_audit.log` (PyPI upload times): openpyxl 3.1.5 (2024-06-28), et_xmlfile 2.0.0 (2024-10-25), olefile 0.47 (2023-12-01) OK; msoffcrypto-tool 6.1.0 (first uploaded 2026-11-03, 12 days before the pin) broke the rule and is re-pinned to **6.0.0** (2026-01-12) in `backend/requirements.txt` / `requirements.lock`; full suite and the real Planning import re-run with 6.0.0 (`logs/orch/`) |
| 5.4 | Secret scan (tree + history) | DONE | `tools/secret_scan.py --history` -> findings 0 (`logs/secret_scan.log`) |
| 5.5 | Artifact signing, container image scan | OPEN / N/A (CARRIED) | release pipeline with the staging server |

## 6. Operations

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 6.1 | Backup + restore drill incl. PHASE_02 tables, serial counter, number counters, import batches; invariants after restore | DONE (local, synthetic) | `ops/backup/drill.sh` + `drill_seed.py` + `drill_verify_phase02.py`; `logs/backup_drill.log`, `logs/drill/drill_report.json`, `logs/drill/phase02_before.json` / `phase02_after.json` |
| 6.2 | Rollback rehearsal 0028 -> 0027 -> 0018 -> head on populated DBs | DONE | `ops/backup/rollback_rehearsal.sh` scenarios C and D; `docs/ops/ROLLBACK.md` section 3b; `logs/rollback_rehearsal.log`, `logs/rollback/rehearsal_report.json`; migration round trip incl. `identity_%` / `commercial_%` / `phase02_%` function counts (REV-0223): `logs/db_roundtrip.log` |
| 6.3 | Job monitoring of PHASE_02 events and import failures | DONE (commands) / OPEN (scheduler, CARRIED) | `ops.monitoring.import_health`, `event_families`; `manage.py outbox_status` / `job_status` reason `IMPORT_APPLY_FAILED`; `test_phase02_step7_ops.py::test_freshness_counts_only_an_applied_batch_and_a_failed_apply_is_monitored`, `test_event_families_cover_the_phase02_events`; `docs/ops/JOB_MONITORING.md` "02.7 additions" |
| 6.4 | Freshness honest for applied sources (REV-0265) | DONE | `integration/imports.py` (advance at APPLIED); same test as 6.3; `test_sources_without_an_apply_policy_still_refresh_at_validation` |
| 6.5 | Performance evidence (TECHNICAL DEFAULT budgets, not SLA) | DONE (evidence) | `tests/test_perf_phase02.py` (confirm with 100 lines, serials under 8 writers, baseline-like import, paginated lists on ~2.8k codes / 1000 orders, code-rule list with stored golden summary - REV-0244); `logs/perf.log`, `logs/perf.json` |
| 6.6 | RPO / RTO on staging | PARTIAL (CARRIED) | DEC-004 (1 h / 4 h); only the small synthetic drill is measured locally |

## 7. Business rules still undecided (not enforced, by design)

REV-0203: "only one SUBMITTED / APPROVED change request per order" and "change request EXPIRED after 30 days"
(`docs/discovery/STATE_TRANSITIONS.md`) are not decided by the employer; the system does not enforce them and
does not guess them. They stay listed until a decision exists.

## 8. Gate evidence pack (SECURITY_BASELINE 5)

RBAC/ABAC: 1.1-1.10 | PII: 2.1-2.3 | secret scan: 5.4 | SCA: 5.2, 5.3 | import safety: 4.1-4.9 | identifiers:
3.1-3.7 | backup / rollback: 6.1, 6.2 | monitoring: 6.3, 6.4 | perf: 6.5 | sample redacted logs: `logs/`.

Known open items: 1.11 break-glass, 2.8 TLS / CSP / encrypted backups, 5.5
artifact signing, 6.3 scheduler, 6.6 RPO/RTO on staging. No P0/P1 identified by the implementer; the reviewer
decides.

## Sign-off (each row is filled only from the signer's own statement at the Gate; the orchestrator records it)

| Role | Name | Decision (accept / reject / accept with conditions) | Date | Signature |
|---|---|---|---|---|
| Employer (کارفرما) | بسام ربیهاوی | accept with conditions (پذیرش با شرط): the known open items (1.11 break-glass, 2.8 TLS / CSP / encrypted backups, 5.5 artifact signing, 6.3 scheduler, 6.6 RPO/RTO) are closed when the staging/production server is set up, before the Pilot | 2026-11-17 | given by the employer in the Claude Code session (answer to Gate packet item 4-b); recorded by the orchestrator |
| Security reviewer / auditor | | | | |
| IT (operations) | | | | |
