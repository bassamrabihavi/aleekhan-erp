VERDICT: PASS
PHASE/STEP: PHASE_00 / 00.7 (Security & Ops) COMMIT: d6b6de96784d8d4d715e5978a2552c3531798faa (implementation 5f3f5c3, fix d6b6de9; evidence commit 128abdf, status commit b5397b6)
REVIEWER: aleekhan-reviewer (independent, fresh context), machine work-windows, 2026-11-04
NOTE: advisory until DEC-036 is APPROVED; the employer confirms the step.

## Review history
- **Round 1, BLOCKED** (commit b312dc8). The only blocker was REV-0701 (P0): the GitHub repo was public, contrary to DEC-041.
- **Round 2, PASS** (this file, re-review on HEAD 513153b).
  - The employer approved DEC-046 on 2026-11-04 (commit 513153b): the repo stays public. DEC-046 changes only the visibility part of DEC-041; the DEC-041 data rule stays.
  - Evidence: `control/decisions/DECISION_LOG.md:7`, `control/decisions/DECISION_LOG.csv:16`, and `control/PROJECT_STATUS.json` (DEC-046 `status: APPROVED`, `decided_by: کارفرما`).
  - The ADDENDUM row shows the status the decision was raised with (`OPEN`), as it does for DEC-041 and DEC-045.
  - `git diff --stat d6b6de9 HEAD -- . ':!reports' ':!control'` is empty, so no code changed. As requested, I did not re-run the heavy checks; the round-1 evidence below still applies.

## Re-run by reviewer (round 1, on code identical to d6b6de9)
Output went to the scratchpad only.

**Full local run.** `bash tools/ci_local.sh <scratchpad>/ci` (test PG 17.9 env loaded, password not printed). The system stopped it for low memory during the frontend `tsc` stage, and I did not restart it. Stages that completed before the stop:

| Stage | Result |
|---|---|
| lint | ruff: All checks passed |
| type | mypy strict: PASS |
| tools unittest | PASS |
| unit + integration | 488 passed, 1 skipped (REV-0014), 1 deselected (perf). Matches `logs/ci/04_unit.log`. |
| migration | up/zero/up: schema diff EMPTY (953 lines), ROUNDTRIP OK |
| contract | 18 passed |
| authz | 166 passed |
| vitest | 23/23 passed |

**Separate light runs:**

| Check | Result |
|---|---|
| `tools/secret_scan.py --history` | 517 text files, 49 commits, `env_values_checked=1` (the test DB password value is absent from the tree and the history), 1 allowlisted entry (5f3f5c3 test fixture, a `${PGPASSWORD}` reference and not a secret, verified in `git show 5f3f5c3`), findings=0 → PASS |
| `ops/db/roles_check.sh` | passed=26 failed=0; throw-away DB and roles dropped |
| `ops/backup/drill.sh` | drill PASS, all 10 checks (11 tables identical, sha256 re-verified, 6 migrations, `migrate --check` clean, audit trigger enforced, 500 synthetic rows); drill DBs dropped |
| `tools/lock_runtime.py --check` | lock matches the venv (9 packages) |
| perf smoke | 1 passed |
| `pip_audit -r backend/requirements.lock --no-deps --disable-pip --strict` | No known vulnerabilities found |

**Not reproduced locally (memory).** These stages are frontend build, E2E, npm audit and SBOMs.
- Independent evidence: GitHub Actions run 41790868012 on b5397b6 (code identical). It shows `status=completed` and `conclusion=success`, and every step [1]–[13] has `conclusion=success` (public jobs API, read-only `curl`).
- The jobs API cannot tell PASS from SKIPPED inside a stage, because `ci_local.sh` exits 0 for SKIPPED. The orchestrator should attach the uploaded `summary.md` artifact to the Gate packet (00.8).

**Privacy checks:**
- grep of reports/phase-00/step-7, docs, ops, tools and .github for the account name, home path, `PGPASSWORD=` and `password=`: only library code in the Playwright bundle and scanner test fixtures.
- I decoded the zip embedded in `logs/ci/playwright-report/index.html`: 0 path or account hits.
- Working tree was clean afterwards, and no server was listening on 8000 or 5173.

## CHECKS
- R01 ✔ Scope matches PHASE_00.md:24: CI, secret scan, dependency scan, privacy/permissions tests, perf, backup/rollback, job monitoring and the security checklist.
  - REV-0601/0602/0603/0015/0016 are carried review fixes (imports.py `_advance_freshness`, redaction.py, settings.py:223-230, views.py `_check_migrations`).
  - There are no business tables or business features.
- R02 ✔ Every threshold is labelled TECHNICAL DEFAULT:
  - perf budget (test_perf_smoke.py);
  - DUE_BACKLOG_WARN (ops/monitoring.py);
  - statement timeouts (ops/db/roles.sql);
  - backup schedule and retention (docs/ops/BACKUP_RESTORE.md §2);
  - freshness basis, pending DEC-016.

  RPO/RTO cite DEC-004. The Persian deny-list is a technical deny-list deferred to DEC-028. Repository visibility is now an employer decision (DEC-046), not an agent assumption.
- R03 ✔ No migrations in this step, and the roundtrip was reproduced (schema diff EMPTY). The freshness update runs under `select_for_update` (imports.py `_advance_freshness`), with a concurrent test (test_integration_freshness_monotonic.py:106).
- R04 ✔ Validate stays one unit of work, and the audit records `freshness_advanced` (imports.py `validate_batch`).
  - The app role keeps audit and compensation as INSERT+SELECT only (ops/db/grants.sql:13-15).
  - Reproduced in the roles check: for the app role, DELETE/UPDATE/TRUNCATE, DISABLE/DROP TRIGGER and `session_replication_role` are all denied.
- R05 ✔ The `supersedes_freshness` rule is a pure function with parametrised tests (test_integration_freshness_monotonic.py:59). There is no other engine change.
- R06 ✔ Deny-by-default route parity is generated from the production URLconf (tests/authz_urls.py, test_authz_route_parity.py):
  - anonymous → 401;
  - authenticated without permission → 403;
  - the decision endpoint never returns ALLOW;
  - public probes refuse writes with 405.

  The test fails on any unknown permission profile. The OpenAPI contract is unchanged (18 contract tests pass).
- R07 n/a No UI change in this step: only eslint.config.js, browser-preflight.mjs, e2e.sh and the README in frontend/. E2E is green in GitHub run 41790868012 and in the orchestrator log `logs/ci/09_e2e.log`.
- R08 ✔ Code-level controls are evidenced:
  - Bandit `S` rules are enabled in ruff (ruff.toml);
  - secret scan of tree, history and env values (0 findings);
  - pip-audit on the runtime lock (clean);
  - Persian redaction (test_redaction_persian.py is part of the 166 authz tests);
  - structured-log redaction;
  - least-privilege roles (26/0).

  Repository visibility is settled by DEC-046 (REV-0701 resolved). Because the repo is public, the secret scan is now the main barrier. That makes REV-0702 a must-fix before the Gate (see below), but it is not a P0/P1: there are 0 findings in the current tree and history.
- R09 ✔ Writes stay inside platform_core tables. The monitoring snapshot is read-only (test_ops_monitoring.py:87). The drill seed refuses any DB not named `aleekhan_drill_*` (drill_seed.py docstring; drill.sh checks the prefix).
- R10 ✔ REV-0601: provenance is monotonic. `last_as_of` is returned next to the freshness classification, and the basis is documented as pending DEC-016 (freshness.py docstring).
- R11 ✔ The backup/restore drill was reproduced. RTO is honestly stated as "procedure only, not production-size" (drill_report "targets" note, REPORT §5). `outbox_status` gives exit codes for cron. The readiness cache does not cache failures.
- R12 ✔ The partial local re-run matches the logged counts. The remaining stages are evidenced by an independent hosted CI run that passed end to end. E2E ran against a real backend. No mocked evidence.
- R13 ✔ New docs:
  - docs/ops/{CI,DB_ROLES,BACKUP_RESTORE,ROLLBACK,JOB_MONITORING}.md;
  - docs/security/PHASE_00_SECURITY_CHECKLIST.md;
  - docs/security/THREAT_MODEL_DELTA_00.6_00.7.md;
  - API_RUNTIME.md, the integration README and the frontend README.

  The threat model still describes the repo as private, so it must be updated for DEC-046 in 00.8 (REV-0703, P3).
- R14 n/a Owner acceptance is left to the employer at Gate time. The checklist signature block is correctly left blank (PHASE_00_SECURITY_CHECKLIST.md "Sign-off").

## ISSUES
- REV-0701 [P0 → RESOLVED by employer decision DEC-046] GitHub repository `bassamrabihavi/aleekhan-erp` (settings, not a file)
  - Original finding: the repo is public (`"private": false, "visibility": "public"`), contrary to DEC-041.
  - Resolution: the employer accepted public visibility and its consequences in DEC-046 (commit 513153b). Code, handoff, reports, status and commit e-mails are readable by anyone.
  - The rule that stays in force: no private factory data, passwords or customer data in the repo, with the secret scan as a CI gate.
    - Round-1 evidence: 0 findings over 49 commits, including a check for the live test DB password value.
    - 09_PRIVATE and the raw sources are not in the repo.
  - The round-1 suggestion of a "fail if public" pre-Gate check is withdrawn.
  - Remaining follow-ups: REV-0702 (strengthen the gate) and REV-0703 (threat model).
- REV-0702 [P2, open → fix in 00.8 before Gate-0] tools/secret_scan.py:58-62 (`_PLACEHOLDER_RE`, used via `is_placeholder` → `re.search`)
  - Problem: the placeholder words (`example|sample|fake|dummy|synthetic|placeholder|redacted|...`) match anywhere inside the value. So a real-looking literal is not reported just because it contains one of those words somewhere.
  - Why it matters now: with the repo public (DEC-046), this scanner is the main control.
  - Repro (no literal needed):
    - `python -c "import sys; sys.path.insert(0,'tools'); import secret_scan as s; print(s.is_placeholder('Q7' + 'Sample' + '2026'))"` prints `True`.
    - So any `password-literal` value built like that is skipped by `scan_line`. The same value without the word is flagged.
    - Verified in round 1 with a synthetic value; the value is not reproduced here.
  - Expected fix: treat a value as a placeholder only when the whole value is a known placeholder form. Use anchored patterns such as `^(<...>|\$\{...\}|change_?me|example)$`, or an explicit prefix form like `synthetic-`/`example-`. Keep the template forms (`${...}`, `<...>`, `%(...)s`, `{{...}}`).
  - Regression test: positive cases for real-looking values that contain those words, plus the existing negative placeholder cases. Build the fixtures from split string fragments, as in tools/tests/test_secret_scan.py, so that the scanner and the pre-commit guard do not flag the test file itself.
- REV-0703 [P3, open → 00.8] docs/security/THREAT_MODEL_DELTA_00.6_00.7.md (component table, "CI on GitHub-hosted runners" row; T-67)
  - Problem: the trust-boundary analysis assumes a private repo ("already on GitHub per DEC-041"). It does not cover the public exposure accepted in DEC-046, or `pull_request` runs from forks.
  - Expected fix: add a threat row for public visibility.
    - Mitigations: DEC-046 data rule, secret-scan gate (with REV-0702), `permissions: contents: read`, `persist-credentials: false`, no repository secrets.
    - Fork PRs get a read-only token and no secrets.
    - Also update checklist item 2.1. No test needed.
- REV-0704 [P3, open → before Pilot] .github/workflows/ci.yml:66-68,72,129 (actions pinned to major tags)
  - Problem: already disclosed in REPORT §7. Tag pins are mutable, which is a supply-chain risk (T-68).
  - Expected fix: pin each action to a full commit SHA verified from the official repositories, and track it in checklist item 3.13. No test needed.
- Carried, not new:
  - REV-0014 (P3): the `.env.example` test is skipped with a reason. The employer must edit the file or grant the agent access.
  - REV-0013: deferred to PHASE_01.
- Gate packet (00.8): attach the `summary.md` artifact of GitHub run 41790868012, so PASS and SKIPPED can be told apart per stage.

## EMPLOYER ATTENTION
- با تصمیم DEC-046 (عمومی ماندن مخزن)، مانع REV-0701 برطرف شد. از این به بعد هر چیزی که commit شود برای همه قابل خواندن است، پس هیچ فایل خصوصی کارخانه، رمز یا داده مشتری نباید وارد مخزن شود.
- REV-0702: اسکنر راز در بعضی حالت‌ها رمز واقعی را نمی‌بیند. اصلاح آن در گام 00.8 و پیش از Gate لازم است.
- چک‌لیست امنیتی فاز صفر (docs/security/PHASE_00_SECURITY_CHECKLIST.md) منتظر امضای شما و ممیز/IT است.
- فایل backend/.env.example: یا خودتان آن را ویرایش کنید یا اجازه دسترسی بدهید (REV-0014).
