# REPORT — PHASE_00 / 00.3 Domain Engine

```
PROJECT: Aleekhan
PHASE: PHASE_00
STEP: 00.3
COMMIT SHA: a6efb53cff09aefdacb50ef48e092ec0041ced6f
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-03T16:48:37Z
IMPLEMENTER: Claude Code (aleekhan-implementer), verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0 (verify_handoff OK=300, KNOWN_DEFECT=1, EXCLUDED=46)
```

## 1. Purpose & acceptance IDs
Step text: calculation/State/Conflict/Idempotency logic + Error Codes; unit/property/golden tests before UI.
Phase-0 = platform engine only; no business rule (all gated by RULE_NOT_APPROVED, approved-rule list empty). No acceptance case for phase 0, no UI.

## 2. Actual changes
- backend/platform_core/engine/: errors.py (17 codes, message_fa, HTTP map, RFC 9457 body), rules.py (require_approved_rule / @rule_gated), state.py (StateMachine, decision-gated transitions), uow.py (write + audit + outbox in one transaction; redaction; sensitive payload rejected), context.py (db clock), concurrency.py (ETag/If-Match 428/400/412, versioned update/lock → VERSION_CONFLICT), idempotency.py (begin/complete/replay/lease/expiry), outbox.py (PENDING/DISPATCHED/ACKED/FAILED/DEAD_LETTER, deterministic backoff, SKIP LOCKED claim, stale recovery, audited DLQ replay), testing.py (in-memory publisher, refused outside dev/test).
- Tests: 100 new (unit, hypothesis property, golden snapshots of error codes / outbox machine / backoff, PostgreSQL race tests).
- docs/engine/README.md, ERROR_CODES.md; openapi-draft 0.2.0-draft (+IDEMPOTENCY_IN_PROGRESS); STATE_TRANSITIONS notes.
- Code names kept as published in 00.1 OpenAPI (VERSION_CONFLICT, ACCESS_DENIED) — no contract break.
- REV-0005 Python 3.12 (venv 3.12.10, pyproject/ruff target); REV-0006 ruff excludes control/ explicitly; REV-0007 platform-table exemption documented.
- requirements-dev: hypothesis 6.170.4 (≥14 days), sortedcontainers 2.4.0.

## 3. Data integrity
No migration (schema unchanged; round-trip on 3.12 OK). Atomic write+audit+outbox; rollback leaves none (tested). Idempotent replay; versioned updates.
Race tests (PostgreSQL, separate connections): 8 clients same key → handler once; 6 bodies same key → 1 ok / 5 KEY_REUSED; 8 writers same version → 1 / 7 VERSION_CONFLICT; 4 dispatchers × 60 events → each published once.

## 4. Security evidence
Audit before/after redaction of sensitive keys; outbox rejects sensitive payload keys; last_error stores safe code only; test publisher refuses non-test env. Test-only fixture disables audit trigger on throw-away test DB for cleanup (never outside test DB). No secrets in logs (grep negative).

## 5. Test evidence (orchestrator re-run, reports/phase-00/step-3/logs/orch_*)
| Command | Outcome | Log |
|---|---|---|
| ruff check . + format --check . (whole repo) | PASS | logs/orch_ruff.log |
| mypy strict | PASS (40 files) | logs/orch_mypy.log |
| pytest PostgreSQL 17.9, Python 3.12.10 | PASS 175/175, 0 skipped | logs/orch_pytest.log |
| race tests repeated 3× | PASS 5/5 each | logs/orch_race_repeat.log |
| unittest tools/tests | PASS (12) | logs/orch_tools.log |
| verify_handoff.py | PASS failures=0 | logs/orch_verify_handoff.log |
| db_roundtrip.sh (implementer) | PASS diff EMPTY | logs/db_roundtrip.log |

## 6. Demo
None for employer (engine only).

## 7. Issues / decisions
- Technical defaults (idempotency 24h, lease 5min, outbox max 10 attempts, backoff 2s×2 cap 1h) are parameters, not business rules → confirm with ops in 00.7.
- Audit of DENIED/FAILED attempts needs separate-transaction writer → 00.4.
- No real broker (00.6/00.7); recover_stale lacks partial index → later reversible migration.
- Transitive deps unlocked → 00.7.

## 8. Rollback
`git revert a6efb53cff09aefdacb50ef48e092ec0041ced6f` (code only; no migration).

## 9. Review request
PASS. Check transaction boundaries in uow/idempotency, SKIP LOCKED claim, race tests, golden files, rule gate cannot be bypassed.

## 10. Next step (proposal)
00.4 Backend/API: DRF wiring, error handler, X-Request-ID, rate limit, ETag, pagination, REV-0001.
