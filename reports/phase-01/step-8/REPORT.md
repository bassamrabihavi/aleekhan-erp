# REPORT — PHASE_01 / 01.8 Report & Review

```
PROJECT: Aleekhan
PHASE: PHASE_01
STEP: 01.8
COMMIT SHA: PENDING
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-10
IMPLEMENTER: Claude Code (aleekhan-implementer); report written and verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 01.7 PASS (reports/phase-01/step-7/REVIEW.md)
```

## 1. Purpose & acceptance
Step text: "01.8 — Report & Review: Template گزارش، git commit hash، migrations، نتایج Test، UI snapshots، Trace Map و مشکلات؛ STOP و انتظار PASS/REWORK/BLOCKED."

Deliverables:
- the phase report set: `reports/phase-01/PHASE_REPORT.md` and `.json`, and `reports/phase-01/TRACE_MAP.md`;
- the full local CI evidence on the final tree: `step-8/logs/ci/`, 13 stages;
- screenshots regenerated from the final tree: `step-8/screenshots/` (closes REV-0127 and REV-0135).

It also closes the 01.7 carried items REV-0132, REV-0133 and REV-0134.

## 2. Actual changes
- **REV-0132:** new `tests/test_authz_request_cache.py` (8 tests) for the per-request permission cache. They cover:
  - nothing is cached outside the block;
  - copies are handed out;
  - the cache is cleared after the block and after an exception;
  - nested blocks restore the outer cache;
  - each user in one block gets their own grants;
  - a revocation between two requests is seen by the second one.

  No production code changed.
- **REV-0133** (employer, 2026-11-10): in `ops/dead_letters.py`, replay is allowed for an active `owner_admin` or `it_ops`; discard is allowed for `owner_admin` only. The role check runs in the same transaction as the write.
  - `outbox_dead_letter` takes `--user`; `--owner` stays as an alias.
  - 4 new tests, and the refusal test now covers 4 more roles.
  - Docs updated: integration README, JOB_MONITORING, STATE_TRANSITIONS §1.1, checklist row 4.5.
- **REV-0134:** every `tools/ci_local.sh` stage log starts with its command and ends with its exit code. `summary.md` has an exit-code column and the git tree id of each tested directory. The CI stages now also cover the PHASE_01 additions:
  - OpenAPI validation;
  - PHASE_01 perf;
  - the rollback rehearsal;
  - `makemigrations --check`.
- **Docs:** ERD gains migration rows 0014–0018; CHANGELOG has a 01.8 entry; `docs/ops/CI.md` describes the new log format.
- **No change** to migrations, the API contract or the UI.

## 3. Data integrity
- No schema change.
- Dead-letter actions still go through the engine functions. A refused caller writes nothing.

## 4. Security evidence
- Security stage:
  - secret scan of 1087 files and 98 history commits: 0 findings;
  - pip-audit on the runtime lock: no known vulnerabilities;
  - `npm audit --omit=dev`: 0.
- The informational pip-audit of the full dev venv was **not performed** because the network was unreachable. It is not counted as a pass.
- verify_handoff: OK=300, KNOWN_DEFECT=1 (DEC-044), failures=0 (`logs/impl/verify_handoff.log`).
- A grep for the account name, the hostname and the DB password value finds 0 hits in the added files.

## 5. Test evidence
**Local CI.** `bash tools/ci_local.sh reports/phase-01/step-8/logs/ci` ran on work-windows. The summary is in `logs/ci/summary.md`. All 13 stages exited 0.

| Stage | Result |
|---|---|
| lint | PASS (290 files formatted) |
| type | mypy PASS, 192 files |
| tools | 42 tests passed |
| unit | 1070 passed, 1 skipped (real ClamAV), 7 deselected (perf) |
| migration | ROUNDTRIP OK, schema diff empty; partial rollback OK; makemigrations clean |
| contract | OpenAPI 0.6.3-draft valid (88 paths, 107 operations); 18 tests passed |
| authz | 961 passed |
| frontend | eslint, typecheck, vitest 44/44, build: PASS |
| e2e | 22 passed, plus 1 passed in the backend-down run |
| perf | smoke 1 passed; PHASE_01 6 passed (inbox p95 2638 / 2086.5 ms; budget 5000 ms) |
| security | as in §4 |
| ops | roles 50/0; backup drill PASS (14 checks); rollback rehearsal PASS (17 checks) |
| artifacts | SBOMs and dist hashes |

The unit and authz stage counts overlap and must not be added together.

**Orchestrator re-run on the same tree** (`logs/orch/`):

| Command | Outcome | Log |
|---|---|---|
| ruff check + format --check | PASS | `logs/orch/ruff.log` |
| mypy strict | PASS, 192 files | `logs/orch/mypy.log` |
| `pytest -m "not perf"` full | **1951 passed, 1 skipped** (real ClamAV), 7 deselected | `logs/orch/pytest.log`, `pytest.xml` |

**Implementer, targeted run:** REV-0132/0133 tests, 32 passed (`logs/impl/pytest_rev0132_0133.log`).

**Screenshots:** 71 files in `screenshots/`. That is 16 PHASE_01 views × 4 sizes (1440 desktop, 1180 laptop, 768 tablet, 390 mobile), plus 7 PHASE_00 status shots. The footers show build `e3d56a0`, because the run was on the uncommitted tree. `frontend/` is unchanged since `e3d56a0`.

## 6. Demo (employer)
- An IT user can replay a failed event:
  `manage.py outbox_dead_letter replay --user <it_ops user> --event-id <uuid> --reason "<why>"`.
- Discard is owner-only.
- UAT T-003 covers the pages.

## 7. Issues / decisions (open for the Gate; no P0/P1 open)
1. UAT T-003 has no result yet.
2. The PHASE_01 security checklist is unsigned (employer, auditor, IT).
3. Deployment items must close before production and the pilot: checklist 1.10, 2.6, 2.7, 3.4, 3.6, 3.11, 4.4, 4.8.
4. Technical defaults to confirm:
   - login rate 20/min per IP and 10/min per user;
   - housekeeping overdue after 26 h; orphan grace 24 h;
   - 64 KiB multipart allowance; 25 MB upload limit;
   - perf budgets;
   - notification retention 180 days;
   - 60 s back-dating tolerance.
5. The scope splits C-33, C-34 and C-46 need employer confirmation.
6. Rollback boundary: reversing 0011 is refused while job runs exist, so the way back is restore from backup.
7. The real ClamAV test is skipped here; it needs the staging server.
8. **New P3 finding (REV-0013 / C-42):** a 401 sends `WWW-Authenticate: Cookie`, while C-42 proposed `Session realm="aleekhan"`. No test pins the header. Not changed.
9. Later contract items:
   - an HTTP operation for dead-letter replay/discard;
   - moving the inbox row filter into SQL.
10. DEC-016 stays OPEN for PHASE_06; PHASE_01 does not use it.

## 8. Rollback
`git revert <commit>`. There is no migration.

## 9. Review request
Request PASS for 01.8. Reviewer attention:
- that TRACE_MAP covers every PHASE_01 requirement, acceptance case, page, decision and REV issue, with honest status;
- that the CI evidence matches the committed tree (compare the tree ids in `summary.md` with `git rev-parse <sha>:<dir>`).

## 10. Next step
STOP: Gate PHASE_01 pending. The orchestrator writes `reports/phase-01/GATE_PACKET_FA.md`, tags `phase-01-rc1`, and the employer decides.
