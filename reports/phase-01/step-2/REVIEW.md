VERDICT: REWORK
PHASE/STEP: PHASE_01 / 01.2 Database    COMMIT: 84e5acd
REVIEWER: aleekhan-reviewer (independent, read-only), 2026-11-05, machine work-windows

## Reviewer re-runs (this review)
| Command | Result |
|---|---|
| `ruff check .` and `ruff format --check .` | All checks passed; 191 files already formatted |
| `cd backend && mypy .` | Success: no issues in 112 source files |
| `python -m unittest discover -s tools/tests` | Ran 42, OK |
| `tools/secret_scan.py --history` | findings=0, PASS (1 allow-listed history test literal) |
| `tools/verify_handoff.py` | OK=300, KNOWN_DEFECT=1 (DEC-044), failures=0 |
| `manage.py makemigrations --check --dry-run` | No changes detected (no DB connection; history-consistency check was skipped with a warning) |
| pytest (692), `db_roundtrip.sh`, `roles_check.sh`, concurrency x5 | **NOT reproduced by the reviewer.** This sandbox has no PostgreSQL libpq env, and loading the test DB credential file was refused by the permission system. The orchestrator logs in `logs/orch/` are internally consistent: junit shows tests=692, failures=0, errors=0; the roundtrip log shows all 10 migrations up, down to zero, partial rollback to 0006, up again; `schema_diff.txt` is 0 bytes; roles check passed=49, failed=0. They count as orchestrator evidence, not reviewer-reproduced evidence. |

## CHECKS
- R01 ✔ Scope matches 01.2: migrations, constraints, guards, a non-sensitive seed and up/down tests (`git show --stat 84e5acd`: models, migrations 0007–0010, tests, ops, docs). There is no engine, API behaviour or UI. `api/views.py` only changes CONTRACT_VERSION.
- R02 ✘ Seed values match DECISION_LOG DEC-032/048–054 (0010_seed:242-560: 8/90/72h/5/15/15, 120min/12h, 480min, 3 sessions, 15min, 10 codes, 30 days, 24 months, depth 6). However, the new `OWNER_POLICY` classification (0010_seed:660) is an undecided contract change. It moves every policy parameter outside DEC-032's maker-checker while Q-0103 is still open (REV-0106). The rule "history is never back-dated" is stated but only partly enforced (REV-0107).
- R03 ✘ Named PK/FK/unique/check/index and exclusion constraints are present and tested (test_phase01_schema.py:49). Roundtrip is evidenced by the orch log. The role lifecycle has no DB guard, which breaks the DEC-032/DEC-049 invariants claimed in REPORT §3 (REV-0105).
- R04 ✔ Approval: maker≠checker CHECK, decided⇒decider, one PENDING per (resource, revision, action) (workflow/models.py:283-325). Terminal-state triggers (0008:52-62). Audit chain columns are backward-compatible (models.py AuditEvent). Per-user advisory locks come before the GiST exclusions (0008:361, 658). Concurrency tests exist (test_phase01_concurrency.py:30-102); the stability claim relies only on orch logs.
- R05 n/a Engine is 01.3.
- R06 ✔ OpenAPI 0.5.1-draft: decided-by tags added and REV-0101 MFA on rejectDocumentRevision (openapi diff). Grants seed is checked against the matrix document and the contract (test_phase01_schema.py:183, 223). Per-action enforcement belongs to 01.4.
- R07 n/a No UI in this step.
- R08 ✔ Secrets are stored only as hashes or ciphertext (identity/models.py:156, 198, 233, 293). App role: append-only and history tables revoked, catalogues read-only (ops/db/grants.sql diff). SECURITY DEFINER functions pin `search_path = pg_catalog, pg_temp` (0008:624-626). Secret scan has 0 findings. Grep of step logs and migrations for account, home-path, domain and host names: 0 hits.
- R09 ✔ Models are split by sub-module inside `platform_core`. Nothing writes to tables owned by another module.
- R10 n/a No integration work.
- R11 ✔ Protected job types (migrate/backup/restore) cannot be cancelled (0008 platform_job_run_guard; test_phase01_params_jobs.py:168).
- R12 ✘ Not fully reproducible by the reviewer: the DB-backed suite could not be run here (see above). This is not counted as a defect of the step, but the PASS depends on the orchestrator logs.
- R13 ✔ ERD §4–6, DATA_TABLE, STATE_TRANSITIONS §4.12, CONFLICTS, DB_ROLES, API_RUNTIME and CHANGELOG are all updated in the commit. Minor gap in REPORT.md (REV-0108).
- R14 n/a Left to the employer at Gate time.

## ISSUES
- REV-0105 [P1] backend/platform_core/migrations/0008_phase01_db_guards.py:316 (platform_role_kind_guard), with :356-384 and 0010_seed:706.
  - Problem: the role lifecycle DRAFT → ACTIVE → RETIRED (STATE_TRANSITIONS §4.8) is not enforced at all in the DB. `platform_role` is not in TERMINAL, and no trigger blocks ACTIVE→DRAFT or RETIRED→ACTIVE. Retiring a role with live assignments is also allowed. The app role keeps UPDATE on `platform_role` and full DML on `platform_role_permission`.
  - Consequence: the claimed invariants "grants change only while DRAFT" and DEC-032 "BA-role assignment needs a second person" can both be bypassed with plain DML. `requires_second_approval` is computed only when the assignment row is written.
  - Repro, as the app role:
    1. Create a BUSINESS role R, then set it ACTIVE.
    2. Insert an ACTIVE role_assignment of R for user U. It is accepted without approval, because R has no BA permission yet.
    3. `UPDATE platform_role SET status='DRAFT' WHERE id=R`.
    4. `INSERT platform_role_permission (R, 'platform.document.approve')`.
    5. `UPDATE platform_role SET status='ACTIVE'`.
    6. Result: U now holds a business-approval permission and no second person ever approved it.
  - Expected fix:
    - Add a role status-transition guard: only DRAFT→ACTIVE and ACTIVE→RETIRED; RETIRED is terminal; RETIRED is allowed only with no PENDING_APPROVAL or ACTIVE assignment. Optionally refuse ACTIVE→ACTIVE with a changed matrix_version.
    - Adjust `unseed` so it still reverses. For example, delete the grants while the guard trigger is disabled inside the migration (migration owner only), or drop the guard in 0008 reverse before 0010 reverse runs. The order already allows this: 0010 reverses first, so 0010's reverse needs its own owner-only bypass.
  - Regression tests required:
    - ACTIVE→DRAFT is refused; RETIRED→ACTIVE is refused; RETIRED with a live assignment is refused.
    - The repro above fails at step 3.
    - `db_roundtrip.sh` is still OK.
- REV-0106 [P2] backend/platform_core/migrations/0010_seed_phase01_catalogue.py:660 and 0008:270.
  - Problem: the new enum value `OWNER_POLICY` is not in the handoff contract and has no approved decision. All 32 seeded DEC-048..054 policy values use it. The DB maker-checker applies only to BUSINESS_RULE, so one person can propose and publish a new lockout threshold or password length. Q-0103 is still open. For Q-0104 the implementer chose the stricter reading, but here the more permissive one.
  - Repro: insert a DRAFT value for `lockout_max_failures` with decision_id set, then update it to PUBLISHED with published_by_id = proposed_by_id. It is accepted.
  - Expected fix: until the employer answers Q-0103, apply the maker-checker to OWNER_POLICY as well (exempt only provenance=MIGRATION_SEED rows), or get the classification confirmed through a DEC.
  - Regression test: OWNER_POLICY self-publish is refused; the seed rows still load.
- REV-0107 [P2] 0008_phase01_db_guards.py:470-485 (platform_effective_from_guard).
  - Problem: the claim "never back-dated" is only checked against OLD.effective_from, not against now. An update can set effective_from to any past time after the last change. That closes the previous history row retroactively, so the shown tree for past dates changes.
  - Repro: create a unit with effective_from = now-7d (allowed: past and not future). Then update name_fa with effective_from = now-3d. It is accepted.
  - Expected fix:
    - Either enforce `NEW.effective_from >= statement_timestamp() - tolerance` on UPDATE, and on INSERT unless provenance is MIGRATION/IMPORT,
    - or document that retroactive dating is intended and get the employer to confirm it (DEC-048 item 7 only says «تاریخچه با تاریخ اثر»).
  - Regression test for the chosen rule.
- REV-0108 [P3] reports/phase-01/step-2/REPORT.md:7.
  - Problem: "COMMIT SHA: see status file / REPORT.json (filled after commit)". The sha fill in REPORT.json is an uncommitted working-tree change (`git status`: M REPORT.json).
  - Expected fix: put `84e5acd` in REPORT.md and commit both files.
  - Regression test: none (documentation).
- Note (not a defect): DB-backed evidence (692 tests, roundtrip, roles 49/0, concurrency) must be re-run after the REV-0105 fix. The rework report should state the run that the reviewer can reproduce (or the employer's machine with DB env).

## EMPLOYER ATTENTION
- Q-0103: آیا تغییر پارامترهای سیاستی (مثل تعداد تلاش ناموفق یا طول رمز) هم باید با تأیید نفر دوم منتشر شود؟ پیشنهاد ممیز: تا پاسخ شما، بله (سخت‌گیرانه).
- Q-0104: «۲۵ مگابایت» یعنی ۲۵٬۰۰۰٬۰۰۰ بایت (فعلاً ثبت‌شده) یا ۲۶٬۲۱۴٬۴۰۰ بایت؟
- Q-0106: آیا یک سمت می‌تواند هم‌زمان چند دارنده اصلی داشته باشد (مثلاً چند اپراتور در یک سمت)؟ فعلاً سامانه اجازه می‌دهد.
- تاریخ اثر: آیا ثبت تغییر درخت سازمانی با تاریخ گذشته (اثر عطف به ماسبق) مجاز است یا نه؟
- R14 (پذیرش مالک) در زمان Gate با شماست.
