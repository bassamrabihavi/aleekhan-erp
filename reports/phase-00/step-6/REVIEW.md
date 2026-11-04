VERDICT: PASS
PHASE/STEP: PHASE_00 / 00.6 (Integration) COMMIT: d7b444a8f2e907b8bb6c730faf15a5b455dc5e9e (evidence commit 033dcea, status commit f186209)
REVIEWER: aleekhan-reviewer (independent, fresh context), machine work-windows, 2026-11-04
NOTE: advisory until DEC-036 is APPROVED; the employer confirms the step.

## Re-run by reviewer (Python 3.12 venv, Node 24.20.0, PostgreSQL 17.9 test instance)
`git diff --stat d7b444a HEAD -- . ':!reports' ':!control'` is empty, so the HEAD f186209 code is identical to the reviewed commit.

| Command | Result |
|---|---|
| `ruff check .` and `ruff format --check .` (repo) | All checks passed; 117 files already formatted |
| `mypy .` (backend, strict) | Success: no issues found in 74 source files |
| `manage.py makemigrations --check --dry-run` | No changes detected |
| `pytest` (real PG, ALEEKHAN_ENV=test) | 384 passed in 19.58s (matches logs/pytest.log) |
| `backend/scripts/db_roundtrip.sh <scratchpad>` (up, zero, up) | 0001–0006 applied; rollback leaves only django_migrations and 0 platform functions; schema diff EMPTY (953 lines); ROUNDTRIP OK |
| `npm run lint` / `npm run typecheck` | exit 0 / exit 0 |
| `npx vitest run` | 3 files, 23/23 passed |
| `npm audit --omit=dev` | found 0 vulnerabilities |
| `frontend/scripts/e2e.sh` (own DB `aleekhan_e2e_rev6`, `E2E_BROWSER_CHANNEL=msedge`, screenshots and artefacts written to the scratchpad) | real backend: 12 passed (24.6s); backend-down: 1 passed (5.7s); DB dropped; ports 8000 and 5173 free afterwards; working tree clean. The first attempt without the Edge channel failed only because the bundled headless shell is not installed on this machine, which is an environment problem and not a code defect. |
| grep for the account name, temp-path user ID, `PGPASSWORD=` and `password=` in reports/phase-00/step-6 | 0 hits |
| `sha256sum` of docs/ui/brand/aleekhan-logo.png and frontend/src/assets/brand/aleekhan-logo.png | both `ef3fa9d1…4b33`, identical to the brand README |

## CHECKS
- R01 ✔ The diff (`git show --stat d7b444a`, 47 files) stays inside platform_core/integration, engine (outbox/consumers/errors), the 4 integration endpoints, migrations 0004–0006, and docs/tests. No business tables or business writes. Logo and palette are an employer request recorded in commit 8309034 and in docs/ui/brand/README.md, so they are not an unauthorised extra. REV-0501/0503/0504 are carried UI fixes.
- R02 ✔ No business rule was invented. The APPLIED, SUPERSEDED and COMPENSATED edges call `require_approved_rule(source.policy_decision_id)` (integration/imports.py:`_gated`), which gives RULE_NOT_APPROVED. Thresholds, the retry policy and the size limits are labelled TECHNICAL_DEFAULT (migrations/0006 docstring, engine/outbox.py INTEGRATION_POLICY). Seeded sources are metadata only. The DEC-025/DEC-035 mapping question is disclosed in REPORT §7.
- R03 ✔ Every table has named PK/FK/unique/check constraints (migrations/0004_integration.py: uq_import_batch_source_sha256, ck_integration_source_read_only, partial uq_conflict_item_open_key, and others). Immutability triggers are in 0005 (provenance, staged payload, append-only compensation, no-update inbox). The up/zero/up roundtrip was reproduced. Race tests use real PG threads: test_integration_imports.py:449, test_integration_freshness_conflicts.py:266, test_integration_consumers.py:370 and :395.
- R04 ✔ Each transition is one unit_of_work (state + audit + outbox): imports.py stage/validate/reject and conflicts.py `_resolve`. The inbox uses `INSERT … ON CONFLICT DO NOTHING` in the same transaction as the handler (consumers.py `process_once`). Compensation is unique per (consumer, event) and is taken under a lock on the outbox row (consumers.py `record_compensation`). Duplicate import returns the same batch with no second event.
- R05 ✔ Deterministic backoff with injectable jitter and clock (engine/outbox.py `backoff_delay`, `sha256_jitter`). Golden files exist (tests/golden/integration_backoff.golden.json, import_batch_machine.golden.json). Unapproved rules block apply/supersede/compensate.
- R06 ✔ OpenAPI is 0.4.0-draft, and the contract test keeps CONTRACT_VERSION equal (api/views.py). Each view has its own `required_action` (integration_views.py: READ_FRESHNESS, READ_CONFLICTS, RESOLVE_CONFLICT). Resolve requires If-Match, Idempotency-Key and an identified USER. A scoped queryset returns 404 out of scope (BOLA). Production is deny-by-default and answers 401.
- R07 ✔ Screenshots at 1440/1180/768/390, simulated-stale and backend-down show build d7b444a8f2e9, RTL layout, the logo and the green primary. In the stale screenshot the chips are neutral (REV-0503 fixed). The 768 layout spans the last panel (REV-0504 fixed). E2E passed again, including the axe and overflow checks. Role-sensitivity is n/a until PHASE_01 login.
- R08 ✔ READ_ONLY is enforced in both the DB CHECK and the service (`sources.require_writable`). Filenames are basename-only with bidi/control characters stripped (imports.py `safe_basename`). Stored errors are safe codes only. Prod dependencies have 0 vulnerabilities. No secrets or PII in reports (grep). Quarantine/scan is deferred to SEC-03 and disclosed. See REV-0602: the sensitive-field refusal does not cover Persian column names.
- R09 ✔ There are no writes outside the platform_core tables. Resolving a conflict changes only the conflict item (conflicts.py docstring and `_resolve`). Business consequences are left to owning modules in later phases.
- R10 ✔ for the PHASE_00 framework scope: hash, size and provenance are immutable; staging is separate from official data; batch state machine, row validation, reject, dedup/idempotency, audit and a compensation mechanism are present; freshness carries a stale flag; there is a conflict queue. The binary original is not stored, and there is no ExcelSourceRecord (cell/formula/cached value) or parser yet. Both are explicitly deferred in docs/integration/README.md:162-164 and REPORT §7 and must exist before any real import (PHASE_06/12). See REV-0601 for freshness provenance.
- R11 n/a Ops (worker, scheduling, monitoring, restore drill) is 00.7. A crashed dispatcher is repaired by `recover_stale` and `sweep_dead_letters` (tested).
- R12 ✔ All logged evidence was reproduced independently (table above). E2E ran against real Django + PG. Simulated states are labelled SIMULATED. CI is still absent (00.7, DEC-045 A).
- R13 ✔ Updated: docs/integration/README.md (new), ERROR_CODES.md, engine/README.md, API_RUNTIME.md, openapi-draft.yaml, STATE_TRANSITIONS.md, DESIGN_TOKENS.md §5, brand README, frontend README.
- R14 n/a Owner acceptance is left to the employer at Gate time.

## ISSUES
- REV-0601 [P2] backend/platform_core/integration/imports.py (`validate_batch`, the `IntegrationSource…update(last_success_at=now, last_success_batch=batch, last_as_of=batch.source_as_of)` call)
  - Problem: freshness provenance can move backwards.
    - The update is unconditional. If an older snapshot (earlier `source_as_of`) or a batch without `source_as_of` is validated after a newer one, `last_as_of` goes back in time or is reset to NULL, and `last_success_batch` points to the older batch.
    - `freshness` is computed from import time (`last_success_at`), not data time. So a month-old snapshot imported today is reported as `fresh`. This touches SOURCE_MAPPING §7: "do not advertise stale stock as real-time".
  - Repro:
    1. Receive, stage and validate batch A with `source_as_of=T`.
    2. Do the same for batch B with `source_as_of=T-30d` (or None).
    3. `GET integration/freshness` shows `last_as_of=T-30d` (or null) and `freshness=fresh`.
  - Expected fix: never regress `last_as_of` or `last_success_batch`. Take the max under a row lock on the source (`select_for_update`), or keep the newest by `source_as_of`. Also document, or decide under DEC-016, whether staleness is measured from `source_as_of` when it is present. Until then, the UI/API must show `last_as_of` next to `fresh`.
  - Regression test: validate a newer batch and then an older or undated batch, and assert that `last_as_of` and `last_success_batch` are unchanged. Run it under concurrency as well.
  - Not blocking: there is no import entry point or business consumer in PHASE_00. Must be fixed before the first real import (PHASE_06 WH-01 or earlier).
- REV-0602 [P2] backend/platform_core/engine/redaction.py:21-37, used by imports.py `_check_rows`
  - Problem: the sensitive-field deny-list is English only. The factory workbooks have Persian headers, and keys such as `حقوق`, `دستمزد`, `رمز عبور`, `گذرواژه` and `کلمه عبور` all return `is_sensitive_key(...) == False` (reviewer one-liner). So the claim in REPORT §2/§4 that "password and salary fields are refused at staging" does not hold for real source files.
  - Repro: `stage_rows(ctx, batch_id, [StagingInput(1, {"حقوق": 1})])`. The row is staged instead of returning SENSITIVE_FIELD.
  - Expected fix: add Persian fragments, normalised for Arabic/Persian yeh and kaf, ZWNJ and spacing (at least حقوق, دستمزد, فیش حقوقی, رمز, گذرواژه, کلمه عبور, پسورد). Keep it a technical deny-list; the full classification still belongs to the privacy decision (DEC-028) and the PHASE_01 field matrix. Correct the REPORT wording to "English key names only" if the fix is deferred.
  - Regression test: parametrised tests for redact, outbox reject and staging refusal with Persian keys (including ZWNJ and the Arabic yeh/kaf variants). Assert that values are never echoed.
  - Not blocking: no parser or upload endpoint exists yet. Must be fixed before any parser or import endpoint.
- REV-0603 [P3] frontend/scripts/e2e.sh and frontend/README.md:20-21
  - Problem: on this work machine the default Playwright browser is not installed, so a plain `scripts/e2e.sh` fails all 13 tests with "Executable doesn't exist". It only passes with `E2E_BROWSER_CHANNEL=msedge`. REPORT §5 mentions msedge, but the exact command and environment are not recorded in logs/e2e.log.
  - Expected fix: print the browser channel and version at the top of the e2e log, and record the full reproduction environment (PG_BIN, channel) in the REPORT. No test needed.

No P0/P1 issues. Previously open items remain tracked: REV-0013 to REV-0016 (00.7/PHASE_01) and REV-0502 (an old step-5 log; step-6 logs are clean).

## EMPLOYER ATTENTION
- لوگو و رنگ سبز اصلی روی صفحه «وضعیت سامانه» اعمال شده است. لطفاً صفحه را ببینید و ظاهر را تأیید کنید (اگر فایل SVG لوگو دارید، بدهید).
- تصمیم DEC-016 (راهکاران) هنوز باز است:
  - مدت اعتبار Snapshot راهکاران (فعلاً ۲۴ ساعت، پیش‌فرض فنی).
  - اگر همان فایل دوباره آپلود شود چه بشود (الان همان دسته قبلی برمی‌گردد، حتی اگر قبلاً رد شده باشد).
  - «تازگی داده» از زمان آپلود حساب شود یا از تاریخ خود Snapshot؟
- نگاشت فایل‌های قدیمی Planning/WH به DEC-025 یا DEC-035 را تأیید کنید.
