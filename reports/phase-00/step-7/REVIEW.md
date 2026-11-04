VERDICT: BLOCKED
PHASE/STEP: PHASE_00 / 00.7 (Security & Ops) COMMIT: d6b6de96784d8d4d715e5978a2552c3531798faa (implementation 5f3f5c3, fix d6b6de9; evidence commit 128abdf, status commit b5397b6)
REVIEWER: aleekhan-reviewer (independent, fresh context), machine work-windows, 2026-11-04
NOTE: advisory until DEC-036 is APPROVED; the employer confirms the step.

## Why BLOCKED
The code in this step has no P0/P1 defect that I found. The block comes from REV-0701 (P0): the GitHub remote is **public**, but DEC-041 (APPROVED) says it must be private. Only the employer can fix this. The rule is "Critical/P0 fail => BLOCKED" (SECURITY_BASELINE 5), so this verdict cannot be PASS.

Once `GET https://api.github.com/repos/bassamrabihavi/aleekhan-erp` stops answering anonymously, or returns `"private": true`, this step can be re-reviewed without any code change.

## Re-run by reviewer
`git diff --stat d6b6de9 HEAD -- . ':!reports' ':!control'` is empty, so the HEAD b5397b6 code is identical to the reviewed commit. Output went to the scratchpad only.

**Full local run.** `bash tools/ci_local.sh <scratchpad>/ci` (test PG 17.9 env loaded, password not printed). The system stopped it for low memory during the frontend `tsc` stage. Following the memory instruction, I did not restart it. Stages that completed before the stop:

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
| `tools/secret_scan.py --history` | 517 text files, 49 commits, `env_values_checked=1` (the test DB password value is checked and is absent from the tree and the history), 1 allowlisted entry (5f3f5c3 test fixture, a `${PGPASSWORD}` reference and not a secret, verified in `git show 5f3f5c3`), findings=0 → PASS |
| `ops/db/roles_check.sh` | passed=26 failed=0; throw-away DB and roles dropped |
| `ops/backup/drill.sh` | drill PASS, all 10 checks (11 tables identical, sha256 re-verified, 6 migrations, `migrate --check` clean, audit trigger enforced, 500 synthetic rows); drill DBs dropped (only `aleekhan_dev` remains) |
| `tools/lock_runtime.py --check` | lock matches the venv (9 packages) |
| perf smoke | 1 passed |
| `pip_audit -r backend/requirements.lock --no-deps --disable-pip --strict` | No known vulnerabilities found |

**Not reproduced locally (memory):** frontend build, E2E, npm audit, SBOMs. The independent evidence for these is GitHub Actions run 41790868012 on b5397b6 (code identical): `status=completed`, `conclusion=success`, and every step [1]–[13] has `conclusion=success` (public jobs API, read-only `curl`). The jobs API cannot tell PASS from SKIPPED inside a stage, because `ci_local.sh` exits 0 for SKIPPED. The uploaded `summary.md` artifact settles that, and the orchestrator should attach it before the Gate.

**Privacy checks:**
- grep of reports/phase-00/step-7, docs, ops, tools and .github for the account name, home path, `PGPASSWORD=` and `password=`: only library code in the Playwright bundle and scanner test fixtures.
- I decoded the zip embedded in `logs/ci/playwright-report/index.html`: 0 path or account hits.
- Working tree is clean afterwards, and no server is listening on 8000 or 5173.

## CHECKS
- R01 ✔ Scope matches PHASE_00.md:24: CI, secret scan, dependency scan, privacy/permissions tests, perf, backup/rollback, job monitoring and the security checklist. REV-0601/0602/0603/0015/0016 are carried review fixes (imports.py `_advance_freshness`, redaction.py, settings.py:223-230, views.py `_check_migrations`). There are no business tables or business features.
- R02 ✔ Every threshold is labelled TECHNICAL DEFAULT: the perf budget (test_perf_smoke.py), DUE_BACKLOG_WARN (ops/monitoring.py), statement timeouts (ops/db/roles.sql), backup schedule and retention (docs/ops/BACKUP_RESTORE.md §2), and the freshness basis pending DEC-016. RPO/RTO cite DEC-004. The Persian deny-list is a technical deny-list deferred to DEC-028.
- R03 ✔ No migrations in this step. The roundtrip was reproduced (schema diff EMPTY). Freshness update is under `select_for_update` (imports.py `_advance_freshness`), with a concurrent test (test_integration_freshness_monotonic.py:106).
- R04 ✔ Validate stays one unit of work, and the audit records `freshness_advanced` (imports.py `validate_batch`). The app role keeps audit and compensation as INSERT+SELECT only (ops/db/grants.sql:13-15). Reproduced in the roles check: app DELETE/UPDATE/TRUNCATE/DISABLE/DROP TRIGGER/`session_replication_role` are all denied.
- R05 ✔ The `supersedes_freshness` rule is a pure function, tested parametrically (test_integration_freshness_monotonic.py:59). There is no other engine change.
- R06 ✔ Deny-by-default route parity is generated from the production URLconf (tests/authz_urls.py, test_authz_route_parity.py): anonymous → 401, authenticated without permission → 403, decision endpoint never ALLOW, public probes refuse writes with 405. It fails on any unknown permission profile. The OpenAPI contract is unchanged (18 contract tests pass).
- R07 n/a No UI change in this step: only eslint.config.js, browser-preflight.mjs, e2e.sh and README in frontend/. E2E is green in GitHub run 41790868012 and in the orchestrator log `logs/ci/09_e2e.log`.
- R08 ✘ Code-level controls are evidenced. Bandit `S` rules are in ruff (ruff.toml). Other controls reproduced above: secret scan of tree + history + env values, pip-audit on the runtime lock, Persian redaction (166 authz tests include test_redaction_persian.py), structured-log redaction, and least-privilege roles. **But the repository is public, contrary to DEC-041 (REV-0701, P0).** Minor: REV-0702.
- R09 ✔ Writes stay inside platform_core tables. The monitoring snapshot is read-only (test_ops_monitoring.py:87). The drill seed refuses any DB not named `aleekhan_drill_*` (drill_seed.py docstring; drill.sh checks the prefix).
- R10 ✔ REV-0601: provenance is monotonic. `last_as_of` is returned next to the freshness classification, and the basis is documented as pending DEC-016 (freshness.py docstring).
- R11 ✔ The backup/restore drill was reproduced. RTO is honestly stated as "procedure only, not production-size" (drill_report "targets" note, REPORT §5). `outbox_status` gives exit codes for cron. The readiness cache does not cache failures.
- R12 ✔ The local partial re-run matches the logged counts. The remaining stages are evidenced by an independent hosted CI run that passed end to end. E2E ran against a real backend. No mocked evidence.
- R13 ✔ New docs: docs/ops/{CI,DB_ROLES,BACKUP_RESTORE,ROLLBACK,JOB_MONITORING}.md, docs/security/PHASE_00_SECURITY_CHECKLIST.md, docs/security/THREAT_MODEL_DELTA_00.6_00.7.md, API_RUNTIME.md, the integration README and the frontend README. The threat model must be updated for REV-0701 (see REV-0703).
- R14 n/a Owner acceptance is left to the employer at Gate time. The checklist signature block is correctly left blank (PHASE_00_SECURITY_CHECKLIST.md "Sign-off").

## ISSUES
- REV-0701 [P0] GitHub repository `bassamrabihavi/aleekhan-erp` (settings, not a file)
  - Problem: the repo is publicly readable. This contradicts DEC-041 (APPROVED: "GitHub private repo"). Anyone can read the following anonymously:
    - the whole handoff (factory processes and decisions);
    - control/PROJECT_STATUS.json;
    - the reports and the CI artifacts;
    - commit metadata (author name and company e-mail).
  - Repro: `curl -s https://api.github.com/repos/bassamrabihavi/aleekhan-erp`, which returns `"private": false, "visibility": "public"` (2026-11-04).
  - Mitigating facts:
    - The secret scan over all 49 commits, including the live test DB password value, found 0 findings, so no credential needs rotation based on repo content.
    - 09_PRIVATE and the raw sources are not in the repo.
  - Expected fix: the employer sets visibility to Private (GitHub → Settings → General → Danger Zone → Change visibility).
  - After that:
    - Confirm that anonymous API access returns 404.
    - Check the Forks/Stars count on the repo page, since a fork made while it was public keeps a copy. Report any fork to the employer.
    - Note: for private repos, GitHub Actions minutes come out of the account quota.
  - Regression check: add a pre-Gate check (in 00.8) that queries the repo visibility and fails if the repo is public. Record the evidence in the Gate packet.
- REV-0702 [P2] tools/secret_scan.py:58-62 (`_PLACEHOLDER_RE`, used via `is_placeholder` → `re.search`)
  - Problem: the placeholder words (`example|sample|fake|dummy|synthetic|placeholder|redacted|pass|...`) match anywhere inside the value. A real literal that only contains one of these words is silently not reported. For example, a password assignment whose value contains the word Sample, and an API-key assignment whose value contains Example, [literals elided by the orchestrator so the pre-commit guard passes] both give no finding.
  - Repro: `python -c "import sys; sys.path.insert(0,'tools'); import secret_scan as s; print(s.scan_line(<password assignment with a value containing Sample>))"` prints `[]`.
  - Expected fix: treat a value as a placeholder only when the whole value is a known placeholder form. That means anchored patterns such as `^(<...>|\$\{...\}|change_?me|example|...)$`, or a prefix form like `synthetic-`/`example-`. Keep the template forms as they are.
  - Regression test: positive cases for real-looking literals that contain those words, plus the existing negative placeholder cases.
- REV-0703 [P3] docs/security/THREAT_MODEL_DELTA_00.6_00.7.md (component table, "CI on GitHub-hosted runners" row; T-67)
  - Problem: the trust-boundary analysis assumes a private repo ("already on GitHub per DEC-041"). It does not cover the public exposure, or `pull_request` runs from forks while the repo is public.
  - Expected fix: add a threat row for repository visibility (mitigated by REV-0701 plus the pre-Gate visibility check). Keep `permissions: contents: read` and no secrets as they are. No test needed.
- REV-0704 [P3] .github/workflows/ci.yml:66-68,72,129 (actions pinned to major tags)
  - Problem: this is already disclosed in REPORT §7. Tag pins are mutable, which is a supply-chain risk (T-68).
  - Expected fix: pin each action to a full commit SHA verified from the official repositories before Pilot, and track it in the checklist (3.13). No test needed.
- Carried, not new:
  - REV-0014 (P3): `.env.example` test skipped with reason; the employer must edit the file or grant the agent access.
  - REV-0013: deferred to PHASE_01.

## EMPLOYER ATTENTION
- مخزن GitHub الان «عمومی» است؛ طبق DEC-041 باید «خصوصی» باشد. لطفاً در GitHub مسیر Settings → General → Change visibility → Private را بزنید. بعد از این کار، این گام بدون تغییر کد دوباره بازبینی می‌شود.
- اگر تا الان کسی مخزن را Fork کرده باشد، یک نسخه پیش او می‌ماند. لطفاً شمار Fork را در صفحه مخزن نگاه کنید و نتیجه را اعلام کنید.
- چک‌لیست امنیتی فاز صفر (docs/security/PHASE_00_SECURITY_CHECKLIST.md) منتظر امضای شما و ممیز/IT است.
- فایل backend/.env.example: یا خودتان آن را ویرایش کنید یا اجازه دسترسی بدهید (REV-0014).
