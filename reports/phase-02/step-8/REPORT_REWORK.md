# PHASE_02 step 02.8 — Gate follow-up rework report (REV-0290..0295, DEC-061)

Step 02.8 was reopened (PASS → REWORK) on 2026-11-17 for the items in `GATE_FOLLOWUP_REVS.md`. Machine: work-windows.
Earlier part (REV-0290..0294): `REPORT_FOLLOWUP.md` (commit e9962b4).

## Items
| REV | Decision | Commits | Status |
|---|---|---|---|
| REV-0290 one open change request + 30-day expiry | DEC-059 amendment 2026-11-17 | e9962b4 | done |
| REV-0291 requester display name | DEC-032 amendment 2026-11-17 | e9962b4 | done |
| REV-0292 DISMISSED carries over | DEC-005 amendment 2026-11-17 | e9962b4 | done |
| REV-0293 ACTIVE product for style activation + code issue | DEC-005 amendment 2026-11-18 (option A) | 54a40b3 | done (reason `MASTER_NOT_ACTIVE`, UI hint) |
| REV-0294 UAT how-to | — | e9962b4 | done |
| REV-0295 ≥95% fidelity of pages 1, 2, 4, 29, 33 + shell | DEC-061 + amendment 2026-11-18 | e7bec06, 0e0d927, 5cbb254, d3c08d2, dd1f8f6, b0cba1a, 735040f | done |

## DEC-061 fidelity harness (measurement)
- Harness: `frontend/e2e/fidelity/` (README explains method). Harness-only commits, each separate from app code:
  54a40b3 (created), deea35a (amendment: tablet shell targets for 01/02 + extra-section penalty), a3d2d98 (tightened: visual form checks + blurred SSIM structure), 33b0686 + f9b4dc6 (mockup horizontal-overflow crop correction, orchestrator-authorised).
- Weights: presence 0.30, layout 0.25, form 0.20, structure 0.10, style 0.15; extra-section penalty; threshold 0.95 per page per width.
- Orchestrator freeze: `reports/phase-02/step-8/fidelity/FROZEN_SHA256.txt` (re-frozen after f9b4dc6).
- Tightening was triggered by the orchestrator's visual inspection: the first harness gave ≥95% while the side-by-side shots did not look like the mockups. Baselines: `BASELINE.md` (first harness, 37.6–58.3%), `BASELINE2.md` (tightened, 81.1–94.6%).

## Final fidelity (FIDELITY_ENFORCE=1, rc=0 — `logs/rework6/fidelity_final_enforce.log`, `fidelity/FINAL.md`)
| Page | 1440 | 1180 | 768 | 390 |
|---|---|---|---|---|
| 01 | 96.0 | 96.0 | 96.0 | 95.8 |
| 02 | 96.3 | 96.1 | 95.8 | 95.9 |
| 04 | 96.8 | 96.8 | 95.4 | 96.4 |
| 29 | 98.6 | 99.0 | 98.4 | 98.3 |
| 33 | 98.4 | 96.3 | 98.9 | 98.3 |
Margins are thin (page 4 @768 +0.4; pages 1/2 ≈ +0.8). Side-by-side shots: `fidelity/shots/*-final.jpg` (orchestrator inspected page-02-1440 and page-01-390).

## Guardrails
No mock numbers: later-phase values show «—» + «در دست ساخت» + owning phase; image slot «تصویر محصول ثبت نشده». Header actions are real or disabled with a visible reason. New read-only endpoint `GET /commercial/change-requests/counts` and style-tracking counts/filters (RBAC, tests, OpenAPI 0.8.5-draft). Fidelity seed creates 7 synthetic confirmed orders for page 4 (documented in the harness README).

## Reliability
- Dev server listen backlog (10) caused ECONNREFUSED under e2e bursts → stale banner and the intermittent page-33 "1 snapshot instead of 2" failure. Fix: `runserver_e2e` (5cbb254), probe `logs/rework5/backlog_probe.log`.

## Evidence
- Backend pytest 3196 passed, 2 skipped (clamd; golden file not set) — `logs/rework5/backend_pytest.log`; ruff/mypy clean — `logs/rework5/`.
- Frontend lint/typecheck, vitest 98 — `logs/rework5/`.
- Full e2e phase01+02: 32 + 1 (backend-down) passed twice — `logs/rework5/e2e_full_run1.log`, `run2.log`; after 735040f — `logs/rework6/e2e_full.log`.
- Screenshots 1440/1180/768/390: `reports/phase-02/step-8/screenshots/`.

## Open / notes for the reviewer
1. Pages 1/2 targets are hand-authored from concept PNGs (no HTML mockup); page-2 order tab and 768 are assumptions — to be confirmed in the employer's mockup review.
2. Serial pages use CSS `zoom: 0.8` between 901–1200 px; route-specific top bar on serial pages.
3. `PHASE_02_SECURITY_CHECKLIST.md` §7 still lists REV-0203 as undecided (signed file, not edited; superseded by DEC-059 amendment).
