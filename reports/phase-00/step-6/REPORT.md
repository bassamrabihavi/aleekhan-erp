# REPORT — PHASE_00 / 00.6 Integration

```
PROJECT: Aleekhan
PHASE: PHASE_00
STEP: 00.6
COMMIT SHA: d7b444a8f2e907b8bb6c730faf15a5b455dc5e9e
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-04
IMPLEMENTER: Claude Code (aleekhan-implementer), verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0
```

## 1. Purpose & acceptance IDs
Step text: "00.6 — Integration: فقط Source/Events مربوط؛ staging, retries, backoff, compensation, freshness and conflict queue؛ بدون تغییر مستقیم ماژول دیگر."
This step builds a generic, platform-level integration framework only. There are no business entities and no business writes. External sources stay READ_ONLY.

Related acceptance case: **WH-01** ("snapshot imports twice → single accounted snapshot", minimum phase 6). This step adds the framework support only (a duplicate sha256 for the same source returns the existing batch). WH-01 itself is tested in PHASE_06.

Carried-in employer request (2026-11-04):
- Official logo (`docs/ui/brand/`).
- The logo's green becomes the primary colour.

Carried UI review items: REV-0501, REV-0503, REV-0504.

## 2. Actual changes (commit d7b444a)

**Migrations**
- `platform_core.0004_integration`. Six tables:
  - `platform_integration_source`: CHECK `direction='READ_ONLY'`.
  - `platform_import_batch`: unique per (source, sha256).
  - `platform_import_staging_row`.
  - `platform_conflict_item`: one OPEN item per (source, kind, key).
  - `platform_inbox_event`.
  - `platform_compensation_record`.
- `0005_integration_triggers`:
  - row_version triggers.
  - Immutable batch provenance and staged payloads.
  - Append-only compensation records; inbox rows cannot be updated.
- `0006_seed_integration_sources`: metadata only for `rahkaran_excel` (DEC-016) and `legacy_planning_xlsm` / `legacy_wh_xlsm` (DEC-025). Staleness thresholds are marked TECHNICAL_DEFAULT.

**Engine** (`engine/outbox.py`, new `engine/consumers.py`)
- Handler registry.
- Consumer inbox (event_id dedupe).
- Compensation records on permanent failure.
- Retry policy: 8 attempts, 5 s × 2ⁿ capped at 30 min, 25 % jitter, 5 min lease, batch 50. These are TECHNICAL DEFAULTS.
- Injectable clock and jitter make the tests deterministic.

**Integration package** (`platform_core/integration/`): `sources`, `imports`, `freshness`, `conflicts`.
- Batch states: RECEIVED→STAGED→VALIDATED, and REJECTED.
- APPLIED, SUPERSEDED and COMPENSATED are blocked with `RULE_NOT_APPROVED` plus the source's decision id.
- Rows with password- or salary-type fields are refused before they are stored, and the error does not echo the values.

**Error codes:** `SOURCE_READ_ONLY` and `SOURCE_DISABLED` (409, with Persian messages).

**API** (`/api/v1`, OpenAPI 0.4.0-draft)
- `GET integration/freshness`
- `GET integration/conflicts`
- `GET integration/conflicts/{id}`
- `POST integration/conflicts/{id}/resolve` (requires If-Match and Idempotency-Key)

All four are deny-by-default and return 401 in the real runtime until PHASE_01 login.

**UI**
- Logo: byte-identical copy in `frontend/src/assets/brand/` with alt «لوگوی سراجی سنتی عالیخان».
- Primary colour `#01392d`, sampled from the logo by `tools/sample_logo_colors.py`.
- The success colour moved to hue 135° and success chips now carry a check-mark shape (D4).
- REV-0501: E2E screenshots default to an untracked directory.
- REV-0503: chips turn neutral while data is stale.
- REV-0504: the last panel spans the row at 2 columns.

**Docs**
- `docs/integration/README.md`
- `ERROR_CODES.md`, `engine/README.md`, `API_RUNTIME.md`
- `STATE_TRANSITIONS.md` §1.6
- `DESIGN_TOKENS.md` §5 (contrast table)
- `docs/ui/brand/README.md`

## 3. Data integrity
- **Constraints:** every new table has named PK, FK, unique, check and index constraints. Status-changing writes go through the unit of work (write + audit + outbox in one transaction).
- **Race tests on the real PostgreSQL 17:**
  - 6 concurrent imports of the same file give 1 batch.
  - 6 concurrent raises of the same conflict give 1 OPEN item.
  - 4 dispatchers × 40 events × 2 consumers: each handler runs exactly once per event.
- **No business writes:** nothing is applied to any business table.

## 4. Security evidence
- **External sources:** the READ_ONLY direction is enforced in the DB (CHECK) and in the service (`SOURCE_READ_ONLY`).
- **Sensitive fields:** password and salary fields are refused at staging, and filenames are stored as basename only.
- **Endpoints:** deny-by-default. The three new integration permissions are not yet assigned (PHASE_01 permission matrix, DEC-032).
- **Production dependencies:** `npm audit --omit=dev` found 0 vulnerabilities (`logs/npm_audit_prod.log`).
- **Logs:** all logs were scanned for credentials (0 hits). User home paths are replaced with `<home>`.
- **Test fixtures:** synthetic, built inside the tests. No private sources were read.

## 5. Test evidence (orchestrator re-run on work-windows)

| Command | Outcome | Log |
|---|---|---|
| `ruff check` + `ruff format --check` | PASS | `logs/ruff.log` |
| `mypy .` (strict) | PASS, no issues in 74 files | `logs/mypy.log` |
| `makemigrations --check --dry-run` | PASS, no changes | `logs/makemigrations_check.log` |
| `pytest` (real PostgreSQL) | **384 passed** | `logs/pytest.log`, `logs/pytest.xml` |
| `db_roundtrip.sh` (up → zero → up) | ROUNDTRIP OK, schema diff EMPTY (953 lines) | `logs/db_roundtrip.log`, `logs/migrations/` |
| `unittest tools/tests` | 16 OK | `logs/tools_tests.log` |
| `verify_handoff.py` | OK=300, KNOWN_DEFECT=1 (DEC-044), failures=0 | `logs/verify_handoff.log` |
| `npm run lint` / `typecheck` | PASS / PASS | `logs/eslint.log`, `logs/tsc.log` |
| vitest | 23 passed | `logs/vitest.log` |
| `npm run build` | PASS | `logs/vite_build.log` |
| `scripts/e2e.sh` (msedge, real Django + PG) | 12 passed + 1 passed (backend-down) | `logs/e2e.log` |

Screenshots were taken from the committed build d7b444a at 1440, 1180, 768 and 390 px, plus the simulated error, simulated stale and real backend-down states. They are in `screenshots/`.

## 6. Demo (employer)
Visible change: the system status page now shows the official logo and the green palette. The page must be started on request because of the memory limits on work-windows. The integration endpoints cannot be demonstrated until PHASE_01 login.

## 7. Issues / decisions
- **DEC-016 (OPEN):** sets the Rahkaran freshness threshold and the re-import/supersede rule. The current values are technical defaults.
- **Decision mapping:** the legacy workbooks are mapped to DEC-025. DEC-035 may be the better fit; to be confirmed.
- **No worker process:** there is no Celery/Redis yet, so dispatch and sweep are library calls only. Scheduling and monitoring belong to 00.7 / PHASE_01.
- **Not yet built:** file storage, the XLSX parser and quarantine/virus scan (SEC-03, PHASE_01).
- **Logo quality:** the logo is a 300 px raster. An SVG master is requested from the employer.
- **Still open:** REV-0013 to REV-0016 (00.7/PHASE_01) and REV-0502 (vite_build.log path — home paths are now redacted in step-6 logs).

## 8. Rollback
- Code: `git revert d7b444a`.
- DB: `manage.py migrate platform_core 0003` (tested in the roundtrip; no business data involved).

## 9. Review request
Request PASS.

## 10. Next step (proposal)
00.7 Security & Ops:
- CI on GitHub Actions (DEC-045 A).
- Secret and dependency scans.
- Restore drill.
- DB roles.
- `.env.example`.
- REV-0013 to REV-0016.
