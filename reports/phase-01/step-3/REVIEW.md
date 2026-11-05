VERDICT: PASS
PHASE/STEP: PHASE_01 / 01.3 Domain Engine (rework round 1)   COMMIT: 3f1f3ab (status commit 2a9dfb8 touches only control/* and REPORT.*; first submission 6fc3eea)
REVIEWER: aleekhan-reviewer (independent, read-only on source). Date 2026-11-05, work-windows.
Advisory until DEC-036 is APPROVED: the employer confirms this step.

## Reproduced verification (reviewer's own runs, logs kept outside the repo)
- `pytest -q` (settings_test, test DB `test_aleekhan_review_013r1`, PG on 127.0.0.1:5433): **868 passed, 1 skipped, 1 deselected**, exit 0. The skip is the real-ClamAV contract test (`test_phase01_documents_engine.py:277`, clamd not configured). This matches `logs/orch-rework1/pytest.log` (868/1/1).
- `ruff check .`: All checks passed. `ruff format --check .`: 155 files already formatted. `mypy .` (strict): Success, no issues in 155 source files.
- `backend/scripts/db_roundtrip.sh` (ROUNDTRIP_DB=test_review_rt013, includes 0012 + 0013 and `makemigrations --check`): `schema diff: EMPTY (6042 lines compared)`, `ROUNDTRIP OK`, exit 0.
- `ops/db/roles_check.sh` (ROLES_DB=test_review_roles013): `passed=50 failed=0`, exit 0. `grants.sql` grants EXECUTE on the new `platform_param_value_at` to the app role (`ops/db/grants.sql`, diff of 3f1f3ab).
- Committed tree: `git grep` for the DB password from the test env, the Windows user path and the company domain gave 0 hits in this step's files; `logs/rework1/secret_scan.log` findings=0.

## Status of earlier issues
- REV-0111 [P1] CLOSED. `revision_scope` (`documents/service.py`, new `is_released_for_task_holders`) gives ○ task-holders only the current APPROVED + CLEAN revision; a pinned `related_revision` counts only while it is the current approved one. `download` and the new `get_revision` both use it; `revision_list_q` / `document_list_q` mirror the object check. Matrix check: only OPT has ○ on document.read/download (`docs/security/PERMISSION_MATRIX_DRAFT.md:91-92`), so dropping `created_by` from the owner set affects nobody (DOCC holds ●). Tests: `test_phase01_rework1.py:87` (WORKING, IN_REVIEW, REJECTED, quarantined, SUPERSEDED -> NotFound; current approved -> bytes), `:125` (pinned + superseded), `:143` (cancelled task), `:159` (list == object check for 8 roles).
- REV-0112 [P1] CLOSED. `grant_q` uses `MATCH_ALL = ~Q(pk__in=[])` for GLOBAL; `sensitivity_q` applies the cap per grant and fails closed when a capped grant is used without a sensitivity field (`authz/policy.py`, diff 3f1f3ab). Tests: `test_phase01_rework1.py:197` (GLOBAL / ORG_UNIT / SUBTREE x SCOPE / OWN / OWN_UNIT / OWN_AND_OWN_UNIT, list == `can`), `:247` (caps S1 / S1-S2 / all), `:267` (`RbacPolicy.scope_queryset` GLOBAL), `:366` (fail closed).
- REV-0113 [P2] CLOSED. Migration 0012 adds `platform_param_value_at`: a SUPERSEDED value counts only if `superseded_at > effective_from`; `platform_param_value` delegates to it. History rows are not rewritten. Reverse restores the 0008 body (roundtrip EMPTY). Test `test_phase01_rework1.py:286` covers the exact repro (value at now+2d = 20) and a later future value (30 at now+4d).
- REV-0114 [P3] CLOSED. `identity/auth.py:322` records `MFA_ENROLMENT_REQUIRED`; `_record_attempt` maps it to audit DENIED (`auth.py:144-149`); it is not in the "last OK" set of `_count_failure` (`auth.py:218`), so it does not reset the lockout window. CHECK rebuilt in 0012. Test `:312` asserts outcome, audit DENIED and lockout after 4+1 failures.
- REV-0115 [P3] CLOSED. `storage.delete` runs in `transaction.on_commit` (`documents/service.py`, purge_rejected). Test `:344` shows a rolled-back purge keeps the bytes and the marker unset.
- REV-0116 [P2, process] CLOSED. `control/decisions/DEC-055_PACKET.md` written; `PROJECT_STATUS.json` records DEC-055 APPROVED (option B) by the employer on 2026-11-05 through `status.py decide` (events entry at 18:12:46Z); `DECISION_LOG.md` / `.csv` updated. Implementation: `approvals.bootstrap_self_approve` (owner_admin, requester = grantor, fresh step-up, reason >= 3, role has a business-approval permission, no ACTIVE holder, never bootstrapped before, per-role advisory lock) and the DB guard in 0013 (trigger + two CHECKs + adjusted `platform_role_assignment_guard`). Tests `test_phase01_dec055.py:37,64,75,120,141,168` (once per role, owner as own first holder, step-up/reason, raw-SQL bypass refused, non-owner refused, 4-way race -> exactly one).

## CHECKS
- R01 ✔ Scope is 01.3 engine only; no views or API (the bootstrap endpoint is deferred to 01.4 as stated in REPORT §11). The DEC-055 work is in scope because the previous review asked for it as a Gate-1 prerequisite.
- R02 ✔ No invented rules: the operator rule follows matrix cell ○ "approved, linked to own tasks" (`PERMISSION_MATRIX_DRAFT.md:91`); the self-approval exception follows the recorded employer decision DEC-055 B (`PROJECT_STATUS.json:2321-2330`). The "pinned revision only while current" reading is an interpretation; see EMPLOYER ATTENTION.
- R03 ✔ 0012 and 0013 are reversible: reviewer roundtrip schema diff EMPTY (6042 lines). Reverse limits are documented (new outcome / flag rows block reverse, by design).
- R04 ✔ Writes stay in `unit_of_work` (audit + outbox). Bootstrap locks the request row and the assignment row (`select_for_update`) and takes the same per-role advisory lock as the DB trigger; the race test passes. Parameter history stays immutable (selection fix only).
- R05 ✔ Regression tests exist for every REV item, run against real PostgreSQL. The earlier golden files are unchanged and still pass.
- R06 ✔ The object check and the list scoping are tested equal: for approvals over all scope kinds and modes, and for documents/revisions over 8 roles. Sensitivity caps are enforced in lists. DenyAll API policy is unchanged.
- R07 n/a No UI in 01.3.
- R08 ✔ IDOR on draft or superseded revisions is closed. A refused login is now audited as DENIED. Bootstrap self-approval needs MFA step-up, is enforced in the DB (raw SQL bypass refused, test `:120`) and is audited with `scope.bootstrap_self_approval`. No secrets or PII in the step diff (see above).
- R09 ✔ Documents read WorkTask only (read-only `values_list`). Role-assignment activation still goes through the registered approval handler. Each module writes only its own tables.
- R10 n/a No integration in 01.3.
- R11 ✔ No new jobs. The purge delete is idempotent and runs after commit.
- R12 ✔ Reproducible: the reviewer's counts equal the orchestrator logs (868/1/1, roundtrip OK, roles 50/0). Test doubles are named as such.
- R13 ✔ `CHANGELOG.md`, `docs/engine/PHASE01_ENGINE.md`, `docs/db/ERD.md`, `REPORT.md` §11 and `REPORT.json` are updated (`git show --stat 3f1f3ab`).
- R14 n/a Left to the employer at Gate time.

## ISSUES (none blocking)
- REV-0117 [P3] `control/decisions/DEC-055_PACKET.md:5` still says "وضعیت: OPEN — بسته تصمیم", and the `DECISIONS_ADDENDUM.csv` row says OPEN, while the status file and DECISION_LOG say APPROVED. Repro: read the two files. Expected fix: add a closing line to the packet ("APPROVED 2026-11-05, option B"), or state that the addendum keeps the status at registration time. Regression test: none.
- REV-0118 [P3] `backend/platform_core/tests/test_phase01_rework1.py:179` uses `assert _visible_revisions(c) == set() or action == "platform.document.download"`. For download this is always true, so the branch checks nothing. Expected fix: compare `revision_list_q(c, action)` with `_object_allowed(c, action)` in that branch too. Regression test: the fixed assertion itself.
- REV-0119 [P3, earlier phase, outside this step] `reports/phase-00/step-5/logs/vite_build.log:26-30` contains the Windows account name from an `ls -l` listing. This is minor PII in the repo. Expected fix: in a later housekeeping commit, redact the owner column or drop the listing. Regression test: add the account-name pattern to the secret scan.

## EMPLOYER ATTENTION
- خودتأییدی یک‌باره مالک (DEC-055 گزینه B) پیاده و در پایگاه داده قفل شده است. لطفاً تأیید کنید که خودتان این تصمیم را گرفته‌اید. ثبت آن در فایل وضعیت به نام شما و با تاریخ ۲۰۲۶-۱۱-۰۵ است.
- قاعده اپراتور: فقط آخرین نسخه تأییدشده سندی را می‌بیند که به یک کار باز خودش وصل است. اگر کار به یک نسخه مشخص سنجاق شده باشد و نسخه تازه‌تری تأیید شود، اپراتور دیگر هیچ نسخه‌ای نمی‌بیند تا کار به‌روز شود. آیا این رفتار درست است؟ (در آزمون پذیرش بررسی شود.)
