# PHASE_02 step 02.8 — Gate follow-up report (REV-0290..0294)

Commit: e9962b4 (implementer). Written by the orchestrator from the implementer's hand-back plus its own verification.
Source of the REV list: `reports/phase-02/step-8/GATE_FOLLOWUP_REVS.md`.

| REV | Status | Summary |
|---|---|---|
| REV-0290 | done | One open (SUBMITTED/APPROVED) change request per order: 409 `STATE_TRANSITION_NOT_ALLOWED` / `OPEN_CHANGE_REQUEST_EXISTS`; order row lock + partial UNIQUE `uq_commercial_cr_one_open_per_order`. 30-day expiry (`expires_at`, parameter `approval_request_expiry_days`) via housekeeping job `change_request_expiry_sweep` (same mechanism as DEC-032 `approval_expiry_sweep`), audit `commercial.change_request.expire`, outbox `commercial.change_request.expired`; decide/apply on an overdue request refused with `CHANGE_REQUEST_EXPIRED`. New reversible migration 0029 (backfill from `submitted_at`; stops with a count-only message if an order already has two open requests). Contract 0.8.5-draft. STATE_TRANSITIONS §5.5/§5.10 updated. |
| REV-0291 | done | `requested_by_name` (internal display name only) on decision inbox, approvals (page 39) and change requests (page 33); visibility unchanged; UI component `Requester`. |
| REV-0292 | done | DISMISSED disputed value carries over like RESOLVED; test replaced by `test_dismissed_disputed_value_carries_over_like_resolved`; docstrings/docs updated. |
| REV-0293 | decision needed | No spec rule requires an ACTIVE product to activate a style or issue a code (handoff contract has no Product/Style state machine; STATE_TRANSITIONS §5.10 only requires ACTIVE style+product+type on an order line). No code change; question goes to the employer. |
| REV-0294 | done | `UAT_HOWTO_FA.md`: steward first login before the golden load; `ALEEKHAN_INTERNAL_CIDRS` for the UAT server; usable belt cases only; activate product + style before code issue. |

## Evidence (implementer logs, `reports/phase-02/step-8/logs/followup/`)
- Backend full pytest: 3173 passed, 2 skipped (golden tests needing the private file), exit 0 — `be_pytest_full.log` (first attempt 3 failures in old multi-open-CR tests, fixed — `be_pytest_full_attempt1.log`).
- ruff — `be_ruff.log`; mypy "no issues found in 254 source files" — `be_mypy.log`.
- Migration up → zero → up + `makemigrations --check`: ROUNDTRIP OK — `migration_roundtrip.log`.
- Frontend lint/typecheck exit 0, vitest 75 passed — `fe_lint.log`, `fe_typecheck.log`, `fe_unit.log`.

## Orchestrator re-verification
- Targeted backend re-run (gate_followup, migration_0029, engine_race, dismissed, inbox, engine_changes): 121 passed — `orchestrator_targeted_pytest.log`.
- ruff check: all checks passed.
- Not yet run: Playwright E2E and 4-width screenshots — they run together with the DEC-061 UI fidelity rework of the PHASE_02 pages (same step).

## Open points
1. REV-0293 employer decision (see above).
2. `docs/security/PHASE_02_SECURITY_CHECKLIST.md` §7 still lists REV-0203 as undecided; the file is signed, so it is not edited — DEC-059 amendment 2026-11-17 supersedes that line.
3. A new submit expires an overdue open request on the spot (system actor), so an unswept request never blocks an order.
