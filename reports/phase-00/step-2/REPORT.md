# REPORT — PHASE_00 / 00.2 Database

```
PROJECT: Aleekhan
PHASE: PHASE_00
STEP: 00.2
COMMIT SHA: 7cf1f10066aec4c7cda8e6794eab43e748af644e
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-03T16:12:51Z
IMPLEMENTER: Claude Code (aleekhan-implementer), verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0 (verify_handoff: OK=300, KNOWN_DEFECT=1, EXCLUDED=46)
```

## 1. Purpose & acceptance IDs
Step text: migration version, PK/FK/unique/check/index, audit, outbox, rollback, non-sensitive seed; migrate up/down + schema diff.
No GLOBAL_ACCEPTANCE case for phase 0; no UI. Out of scope: users/roles (PHASE_01), DRF/API (00.4), dispatcher/idempotency behaviour (00.3).

## 2. Actual changes
- backend/ Django 5.2.18 project `aleekhan`, app `platform_core` (only installed app); DB config from env, PostgreSQL only; .env.example placeholders.
- Models: AuditEvent (uuid PK, append-only), OutboxEvent (uq event_id, status check, partial dispatch/DLQ indexes), IdempotencyRecord (uq actor_id+key, expires_at index), SchemaMeta (single row). 31 named ck_* checks.
- Migrations: platform_core.0001_initial, 0002_db_triggers (audit UPDATE/DELETE/non-empty TRUNCATE rejected, SQLSTATE 23001; touch trigger for row_version/updated_at), 0003_seed_schema_meta (one row, reversible).
- Code14 field/validator/check-constraint helper (varchar(14), ^[0-9]{14}$), unused by tables yet.
- backend/requirements.txt, requirements-dev.txt (pinned, ≥14 days old) — REV-0002.
- backend/scripts/db_roundtrip.sh, docs/db/README.md (conventions, ERD mermaid, rollback), ruff.toml.
- tools/verify_handoff.py rejects Windows drive paths + test (REV-0003); unused noqa removed (REV-0004).

## 3. Data integrity
Named PK/unique/check constraints; append-only audit enforced in DB; concurrency test: 2 threads same (actor,key) → exactly one insert. No FK yet (no referenced table in phase 0; actor_id → user in PHASE_01). No real data; seed is schema metadata only.

## 4. Security evidence
DB creds only in env (outside repo); grep of logs for the test password: no match. Only 127.0.0.1 test cluster. Owner can still disable triggers → separate DB roles + audit digest in 00.7.

## 5. Test evidence (orchestrator re-run, reports/phase-00/step-2/logs/orch_*)
| Command | Outcome | Log |
|---|---|---|
| ruff check backend tools; ruff format --check | PASS | logs/orch_ruff.log |
| mypy (strict, django-stubs) | PASS (22 files) | logs/orch_mypy.log |
| pytest (PostgreSQL 17.9) | PASS 75/75, 0 skipped | logs/orch_pytest.log |
| unittest tools/tests | PASS (12) | logs/orch_tools.log |
| db_roundtrip.sh: up → makemigrations --check → zero → up → schema diff | PASS, diff EMPTY (386 lines) | logs/orch_db_roundtrip.log, logs/orch_schema/ |
Environment: Windows 11, Python 3.11.13, PostgreSQL 17.9 portable at 127.0.0.1:5433. Not run on Ubuntu.

## 6. Demo
`set -a; . <pg-test.env>; set +a; export ALEEKHAN_ENV=test; cd backend && ../.venv/Scripts/python -m pytest`

## 7. Issues / decisions
- Python 3.11 used; ADR-001 says 3.12+ → upgrade venv before 00.4 (P2).
- Django 5.2.19 released 2026-11-03 (possible security fix) → re-check before Gate-0 (14-day rule).
- Transitive deps not locked (pip_freeze.log records actual) → constraints file in 00.7.
- DEC-045 APPROVED (GitHub Actions + local restore drill) → CI wiring in 00.7.

## 8. Rollback
`python manage.py migrate platform_core zero` (drops all phase-0 tables/triggers; audit data lost — none exists yet), then `git revert 7cf1f10066aec4c7cda8e6794eab43e748af644e`.

## 9. Review request
PASS. Check: trigger SQL and reverse, constraint naming, round-trip logs, no business tables, no secrets.

## 10. Next step (proposal)
00.3 Domain Engine: outbox dispatcher state machine, idempotency protocol, error codes, property tests.
