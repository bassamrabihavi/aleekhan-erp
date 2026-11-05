VERDICT: PASS
PHASE/STEP: PHASE_01 / 01.2 Database (rework round 1)    COMMIT: 153651f (report sha fix 1f21be8; status 7a0e3df)
REVIEWER: aleekhan-reviewer (independent, read-only), 2026-11-05, machine work-windows

History: round 0 reviewed 84e5acd and gave **REWORK** (REV-0105 P1, REV-0106 P2, REV-0107 P2, REV-0108 P3). All four are resolved in this round, as shown below.

## Reviewer re-runs (this review, reproduced by the reviewer)
This time the DB-backed evidence was reproduced by the reviewer. I used a throw-away PostgreSQL 17.9 cluster that I initialised myself in the session scratchpad:
- binaries from the local PG install;
- trust auth on 127.0.0.1 only, no password;
- the project's test credential file was not read;
- the cluster was stopped afterwards.

HEAD was 7a0e3df. `git diff --stat 153651f 7a0e3df` shows only REPORT.md/REPORT.json/PROJECT_STATUS.json, so the code is identical to 153651f.

| Command | Result |
|---|---|
| `pytest -m "not perf"` (full backend) | **699 passed**, 1 deselected, 88.7 s (matches `logs/orch/pytest.log`) |
| `pytest platform_core/tests/test_phase01_concurrency.py` x5 | 6 passed in each of the 5 runs (incl. new capacity race) |
| `backend/scripts/db_roundtrip.sh` | 0001..0010 up, zero, up; `schema diff: EMPTY (5926 lines compared)`; `ROUNDTRIP OK`, rc=0 |
| `ops/db/roles_check.sh` | `passed=49 failed=0`, rc=0 |
| `manage.py makemigrations --check --dry-run` | No changes detected |
| `mypy .` (backend) | Success: no issues in 112 source files |
| `ruff check .` / `ruff format --check .` | All checks passed / 192 files already formatted |
| `tools/secret_scan.py --history` | findings=0, PASS (1 allow-listed test literal) |
| `python -m unittest discover -s tools/tests` | Ran 42, OK |
| `tools/verify_handoff.py` | OK=300, KNOWN_DEFECT=1 (DEC-044), failures=0 |
| Privacy grep of `reports/phase-01/step-2/` (account name, mail domain, user path, `/home/`, hostname) | 0 hits |
| Ad-hoc SQL probes (reviewer, in a rolled-back transaction) | see REV-0109 |

## Resolution of round-0 issues
- **REV-0105 [P1] resolved.**
  - Code (0008_phase01_db_guards.py:344-384):
    - `platform_role_kind_guard` allows only DRAFT→ACTIVE and ACTIVE→RETIRED.
    - `kind` and `matrix_version` are frozen once a role is not DRAFT.
    - RETIRED is refused while PENDING_APPROVAL/ACTIVE assignments exist.
    - RETIRED is terminal (TERMINAL["role"], 0008:69).
  - Remaining bypass paths checked, none open:
    - assignment insert needs an ACTIVE role (0008:416);
    - grants change only while DRAFT (0008:325);
    - the app role cannot UPDATE `platform_permission.business_approval` (grants.sql:39).
  - `unseed` (0010:707-713) disables the trigger only inside the owner-run migration. Roundtrip OK; roles check confirms the app role cannot DISABLE TRIGGER.
  - Regression tests: test_phase01_roles.py:211-251, including the exact repro failing at step 3.
- **REV-0106 [P2] resolved by employer answer Q-0103** (recorded in docs/discovery/STATE_TRANSITIONS.md:212).
  - An OWNER_POLICY value needs an ACTIVE `owner_admin` holder for both propose and publish, plus a reason of at least 3 characters. Seed rows are exempt (0008:279-296).
  - `platform_holds_owner_admin` is SECURITY INVOKER with a pinned search_path. EXECUTE is granted to the app role (grants.sql:42).
  - Test: test_phase01_params_jobs.py:234-256.
- **REV-0107 [P2] resolved** for org units and positions.
  - `ck_effective_from_not_backdated` requires effective_from ≥ now − 60 s on INSERT and whenever it changes (0008:529-536).
  - Content changes without a new date are auto-stamped `now` (0008:516-520).
  - Test: test_phase01_org.py:90-102. Assignments: see REV-0109.
- **REV-0108 [P3] resolved.** REPORT.md:7 and REPORT.json:4 carry `153651f`; both are committed in 1f21be8.
- **Q-0104 applied.** 26214400 bytes (0010_seed:512-523). Tests at test_phase01_schema.py:286 and :335; workflow_docs:168-173.
- **Q-0106 applied.**
  - Schema: `primary_capacity` ≥ 1, and 1 for unit heads (0007 constraints, org/models.py:199-227).
  - Enforcement: exact peak count under a per-position advisory lock (0008:637-652, 753-762). The lock order is person, then position, so there is no cycle.
  - A capacity decrease is checked (0008:683-690), and history carries the column.
  - Tests: test_phase01_org.py:174-201; concurrency test with capacity 2 → exactly 2 win (stable over 5 reviewer runs).

## CHECKS
- R01 ✔ Rework only touches the REV items and employer answers (migrations 0007/0008/0010, org model, tests, docs, grants). There is no engine/API behaviour/UI (`git show --stat 153651f`).
- R02 ✔ Every new rule cites an employer answer: Q-0103 (STATE_TRANSITIONS.md:212), Q-0104 (:213), Q-0106 (:215) and no back-dating (:194). The 60 s value is labelled a technical clock tolerance (0008:529-531). The "unit heads always 1" detail is an implementer refinement; see EMPLOYER ATTENTION.
- R03 ✔ Named constraints and exclusions are in place; roundtrip up/down/up gives an empty schema diff (reviewer run); `makemigrations --check` is clean.
- R04 ✔ Approval/role invariants hold in the DB (REV-0105 above). Capacity and one-PRIMARY rules are race-safe (concurrency x5 reviewer runs). Audit chain columns are unchanged from round 0.
- R05 n/a The engine is 01.3.
- R06 ✔ OpenAPI adds `primary_capacity` (openapi-draft.yaml:6331/6383/6409). Grants seed and matrix tests are still green (699 passed).
- R07 n/a No UI in this step.
- R08 ✔ The app role cannot bypass triggers (roles 49/0). New functions pin `search_path`. Secret scan finds 0. There is no PII in logs (grep 0 hits).
- R09 ✔ All changes are inside `platform_core` sub-modules.
- R10 n/a No integration work.
- R11 ✔ Protected job types are unchanged (test_phase01_params_jobs.py still passes).
- R12 ✔ The DB-backed suite, roundtrip, roles check and concurrency were all reproduced by the reviewer (table above).
- R13 ✔ ERD.md:240/306/307/316, DATA_TABLE.md:187-189, STATE_TRANSITIONS.md:189-217 and CHANGELOG.md:129-131 are updated.
- R14 n/a Left to the employer at Gate time.

## ISSUES
- REV-0109 [P2] backend/platform_core/migrations/0008_phase01_db_guards.py:736-764 (platform_position_assignment_guard).
  - Problem: the "never back-dated" rule (REV-0107 / employer answer) covers unit and position rows only. Person-to-position assignments, which are part of the org tree history ("who held which position when"), can still be back-dated or ended retroactively:
    - `valid_from` on INSERT is not checked against now;
    - `valid_to` can be UPDATEd to any past time.
    - The row is updated in place, so the DB keeps no history of the old `valid_to`.
  - Repro (reviewer, psql as owner, rolled back):
    1. Create a unit, a position and a user.
    2. `INSERT platform_position_assignment(kind='PRIMARY', valid_from=now()-'30 days', ...)`. It is accepted.
    3. `UPDATE ... SET valid_to = now()-'10 days'`. It is accepted.
  - Expected fix:
    - On INSERT, require `valid_from >= statement_timestamp() - 60 s`. This uses the same tolerance; future-dated starts stay allowed, since tests use them.
    - On UPDATE, allow `valid_to` changes only to a value ≥ now − 60 s (a past end is never written retroactively).
    - Alternative: the employer explicitly confirms that assignments may be back-dated (see EMPLOYER ATTENTION).
    - Can be done in 01.3 or as a small follow-up before Gate. Not blocking: no approval routing reads assignments yet.
  - Regression test: back-dated insert refused; retroactive end refused; ending "now" accepted.
- REV-0110 [P3] control/decisions/ (DECISION_LOG.md/.csv).
  - Problem: the employer answers Q-0101..Q-0106 and the no-back-dating rule are recorded only in docs/discovery/STATE_TRANSITIONS.md:210-217 and the code comments. The decision log has no entry, so a later reader cannot trace them from the decision record.
  - Expected fix: the orchestrator adds the answers to the decision log (or as DEC-048..054 resolution notes) via the normal decision channel.
  - Regression test: none (documentation).

## EMPLOYER ATTENTION
- انتساب افراد به سمت (چه کسی از چه تاریخی در کدام سمت است) هنوز با تاریخ گذشته قابل ثبت یا پایان‌دادن است. آیا قاعده «بدون تاریخ گذشته» شامل این انتساب‌ها هم می‌شود؟ پیشنهاد ممیز: بله.
- در پاسخ Q-0106، «سمت مدیر واحد همیشه فقط یک دارنده اصلی دارد» را پیاده‌کننده افزوده است. لطفاً تأیید کنید.
- R14 (پذیرش مالک) در زمان Gate با شماست.
