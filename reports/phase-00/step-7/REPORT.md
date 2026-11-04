# REPORT — PHASE_00 / 00.7 Security & Ops

```
PROJECT: Aleekhan
PHASE: PHASE_00
STEP: 00.7
COMMIT SHA: d6b6de96784d8d4d715e5978a2552c3531798faa (implementation 5f3f5c3 + verification fix d6b6de9)
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-04
IMPLEMENTER: Claude Code (aleekhan-implementer), verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0
```

## 1. Purpose & acceptance
Step text: "00.7 — Security & Ops: secret scan, dependency scan, privacy/permissions tests, perf, backup/rollback & job monitoring؛ security checklist امضا شود."

Gate-0 criteria served:
- "CI و backup restore drill در محیط آزمایشی" under DEC-045 A: GitHub-hosted CI, with the first drill run locally.
- DEC-004: RPO 1 h / RTO 4 h.

## 2. Actual changes
**CI**
- `.github/workflows/ci.yml`:
  - GitHub-hosted runner with a PG 17 service container (trust auth, no secrets).
  - `permissions: contents: read`.
  - Every stage calls `tools/ci_local.sh`, in the handoff order: lint → type → tools → unit/integration → migration → contract → authz → frontend → e2e → perf → security → ops → artifacts.
  - A stage that cannot run prints "SKIPPED: reason".
- `tools/ci_local.sh` runs the same stages on both machines. Logs are passed through `tools/redact_paths.py` (REV-0502).

**Secret scan**
- `tools/secret_scan.py` checks the working tree (tracked and untracked, non-ignored files) and the full git history.
- Only file:line and the rule name are printed, never the matched value.
- `tools/secret_scan_allowlist.txt` holds one exact fingerprint (full sha + path + rule) for a scanner self-test fixture in 5f3f5c3. It never applies to the working tree.

**Dependency scan**
- `backend/requirements.lock` (runtime transitive pins, `tools/lock_runtime.py`).
- `pip-audit==2.10.1` runs on the lock and is a gate.
- `npm audit --omit=dev`.
- CycloneDX SBOMs for Python and the frontend. If the network is down, `tools/offline_sbom.py` builds the Python SBOM from the lock instead.
- Django 5.2.19 exists (uploaded 2026-11-03). pip-audit reports no advisory for 5.2.18, so we stay on 5.2.18 (14-day pin rule, `docs/ops/CI.md`).

**Privacy and permissions**
- Deny-by-default route parity, built automatically from the URL conf: anonymous → 401, authenticated without permission → 403 (`test_authz_route_parity.py`, 166 tests in the authz stage).
- Structured-log redaction test.
- REV-0602: Persian sensitive keys are now detected, after normalising ی/ک, ZWNJ and spaces.

**Fixes from review**
- REV-0601: freshness is monotonic, the source row is locked, and an audit field records whether freshness advanced.
- REV-0603: browser preflight; the E2E log records the browser channel.
- REV-0015: fail fast when the TLS header is trusted and NUM_PROXIES=0.
- REV-0016: 10 s TTL cache on the `/health/ready` migrations check; failures are not cached.

**DB roles**
- `ops/db/roles.sql`, `grants.sql` and `roles_check.sh`, documented in `docs/ops/DB_ROLES.md`.
- Roles are owner, app (DML only) and readonly. All are NOLOGIN and have no password.

**Backup and restore**
- `ops/backup/drill.sh` + `drill_seed.py`. The seed script refuses any DB not named `aleekhan_drill_*`.
- Docs: `docs/ops/BACKUP_RESTORE.md` and `ROLLBACK.md`.

**Job monitoring**
- `manage.py outbox_status` (`platform_core/ops/monitoring.py`) and `docs/ops/JOB_MONITORING.md`.

**Perf**
- `test_perf_smoke.py` (marker `perf`). The budget (p95 < 250 ms) is a TECHNICAL DEFAULT.

**Security docs**
- `docs/security/PHASE_00_SECURITY_CHECKLIST.md`. The signature block is **left blank** for the employer/auditor.
- `docs/security/THREAT_MODEL_DELTA_00.6_00.7.md`.

No migrations.

## 3. Data integrity
The drill restores 11 tables with identical row counts and checksums. Triggers, functions and migration state are identical, and the audit append-only trigger is still enforced after restore. The app role cannot delete or alter audit rows, nor disable or drop triggers (roles check: 26 passed, 0 failed).

## 4. Security evidence
- **Secret scan:** 0 findings over the tree and history; 1 allowlisted entry (`logs/ci/secret_scan.json`).
- **Dependencies:** pip-audit (runtime lock) found no known vulnerabilities. `npm audit --omit=dev` found 0 vulnerabilities (`logs/ci/11_security.log`).
- **SBOMs:** `logs/ci/sbom-*.cdx.json`.
- **Logs:** no account name or home path in any evidence log (grep: 0 hits).
- **Static analysis:** ruff now includes the bandit (`S`) rules.

## 5. Test evidence (orchestrator, `tools/ci_local.sh reports/phase-00/step-7/logs/ci` on d6b6de9, exit 0)

| Stage | Result | Evidence |
|---|---|---|
| lint (ruff + format) | PASS | `logs/ci/01_lint.log` |
| type (mypy strict, 86 files) | PASS | `02_type.log` |
| tools (unittest) | 37 OK | `03_tools.log` |
| unit + integration (PG 17.9) | 488 passed, 1 skipped (REV-0014), 1 deselected (perf) | `04_unit.log`, `pytest-unit-integration.xml` |
| migration roundtrip | ROUNDTRIP OK, schema diff EMPTY | `05_migration.log`, `migration/` |
| contract | 18 passed | `06_contract.log` |
| authz | 166 passed | `07_authz.log` |
| frontend (eslint, tsc, vitest, build) | PASS, vitest 23 passed | `08_frontend.log` |
| e2e (msedge, real Django + PG) | 12 + 1 passed | `09_e2e.log` |
| perf smoke | p95: live 0.69, ready 1.33, version 0.79, freshness 3.64 ms | `10_perf.log`, `perf.json` |
| security | PASS | `11_security.log` |
| ops (roles + drill) | roles 26/0; drill PASS | `12_ops.log`, `roles/`, `drill/drill_report.md` |
| artifacts | PASS | `13_artifacts.log`, `frontend-dist.sha256` |

**Verification history:** the first orchestrator run on 5f3f5c3 had two failing stages, and both were fixed in d6b6de9.
- security: the scanner flagged its own test fixture.
- artifacts: the PyPI connection was reset.

**Drill**
- 500 synthetic rows; dump 124 435 bytes; sha256 `e3f0eaa3…c542`, re-verified before restore.
- Dump 589 ms, restore 682 ms, verify 6176 ms, total 16.5 s.
- This proves the procedure on the local portable PG. It is not a production-size RTO measurement.

## 6. Demo (employer)
- After push, GitHub → Actions → "ci" shows the first hosted run.
- The checklist `docs/security/PHASE_00_SECURITY_CHECKLIST.md` waits for the employer/auditor signature.

## 7. Issues / decisions
- **REV-0014 (open):** `backend/.env.example` cannot be read or written by the agents (permission rule). We did not try to get around this. The test stays skipped with that reason. It needs the employer to edit the file, or to allow the agent access to that file.
- **First GitHub run:** not yet observed (no gh CLI). It is checked after push and before the Gate.
- **Action pins:** actions are pinned to major tags. Pinning to full commit SHAs is a follow-up.
- **Deployment-time items:** CSP on the reverse proxy, artifact signing, and backup encryption with WAL archiving (design only).
- **Staging drill:** a drill on the in-company staging server, once it exists (DEC-045).
- **Freshness basis:** still import time (TECHNICAL DEFAULT), pending DEC-016.
- **Persian deny-list:** «حقوق» also matches «شخص حقوقی». The fail-safe direction was chosen; a note for the data steward is in the threat-model delta.
- **REV-0013:** deferred to PHASE_01.
- **pip-audit cache:** a warm local cache can answer pip-audit without the network (documented).

## 8. Rollback
`git revert d6b6de9 5f3f5c3`. No migrations. Roles and drill databases are created only in throw-away scope and dropped by traps.

## 9. Review request
Request PASS.

## 10. Next step (proposal)
00.8 Report & Review:
- Write the phase report.
- Write `GATE_PACKET_FA.md`.
- Tag `phase-00-rc1`.
- STOP for the employer.
