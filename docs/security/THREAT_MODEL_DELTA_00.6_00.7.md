# Threat model delta - steps 00.6 (integration) and 00.7 (security & ops)

Method: STRIDE per new component / data flow, against SECURITY_BASELINE and the risk register
(`docs/discovery/RISKS.md`). Likelihood/impact are qualitative (H/M/L), not measured. Status: DRAFT for the
reviewer and the employer; it does not close any business decision.

## 1. New components and data flows

| Component (step) | Data flow | Trust boundary |
|---|---|---|
| Import batch / staging (00.6) | operator file -> hash + provenance -> staging rows (JSON) | untrusted file content -> platform DB (no parser yet) |
| Freshness (00.6, REV-0601 in 00.7) | validated batch -> `IntegrationSource.last_*` -> `GET /integration/freshness` | internal |
| Conflict queue (00.6) | engine -> conflict items -> authenticated API (PHASE_01 roles) | API (deny-all in PHASE_00) |
| Outbox -> consumers/inbox (00.6) | event rows -> handlers, retries, dead letters, compensation | internal worker |
| CI on GitHub-hosted runners (00.7, DEC-045 A) | repository code + synthetic fixtures -> third-party runner | code leaves the company; the repository is PUBLIC (DEC-046, employer decision 2026-11-04, amends the visibility part of DEC-041); no secrets, no data |
| Public repository (DEC-046, updated in 00.8 for REV-0703) | code, `handoff/` copy (without 09_PRIVATE), docs, reports, status, commit metadata -> anyone on the internet; fork pull requests -> CI | internet -> repository / CI; the DEC-041 data rule stays: no private factory data, passwords, customer or salary data in Git |
| Backup dumps (00.7) | DB -> `pg_dump` file -> backup volume | contains all business data in production |
| DB roles (00.7) | app processes -> PostgreSQL as `app`; deploy -> `owner` | process vs database |
| Monitoring command (00.7) | DB -> `outbox_status` stdout/JSON -> cron/alerting | operational metadata |

## 2. Threats and mitigations

| ID | STRIDE | Threat | L | I | Mitigation (evidence) | Residual / owner |
|---|---|---|---|---|---|---|
| T-60 | Tampering | Older snapshot validated after a newer one makes stale data look current (freshness moves backwards) | M | H | REV-0601: monotonic rule + `SELECT ... FOR UPDATE` on the source; audit `freshness_advanced` (`test_integration_freshness_monotonic.py`, concurrent case) | basis = import time until DEC-016 (UI shows `last_as_of`) - employer |
| T-61 | Info disclosure | Persian salary/password columns staged or written to audit/outbox | M | H | REV-0602 normalised Persian deny-list (`test_redaction_persian.py`) | deny-list is technical; classification DEC-028 / PHASE_01 field matrix |
| T-62 | Info disclosure | Over-blocking: deny-list refuses legitimate columns (e.g. `شخص حقوقی` "legal entity" contains `حقوق`) | M | L | refusal is the safe direction; ambiguous short words matched only exactly (`رمز` vs `قرمز`, `شبا` vs `شبانه`, `کارت` vs `کارتن`) | data steward confirms column names before PHASE_06 imports |
| T-63 | Tampering / Repudiation | Compromised app process deletes or rewrites audit rows, or disables the audit trigger | L | H | app role: no UPDATE/DELETE/TRUNCATE on audit/compensation, not owner (cannot DISABLE/DROP trigger), cannot set `session_replication_role` (`ops/db/roles_check.sh`) + DB triggers | superuser/owner credentials must stay with IT; periodic audit integrity check (later phase) |
| T-64 | Elevation | App role runs DDL (drops tables, adds columns) after an injection bug | L | H | app has no CREATE on schema, not owner (roles check) | - |
| T-65 | Info disclosure | Backup files stolen from the backup volume | M | H | encryption with age/gpg public key, separate volume, sha256 (`docs/ops/BACKUP_RESTORE.md` section 3) | design only until the staging server exists - IT |
| T-66 | Tampering | Corrupted/altered backup restored silently | L | H | sha256 recorded and re-verified before restore; `pg_restore --single-transaction --exit-on-error`; table fingerprints compared (drill) | - |
| T-67 | Info disclosure | Secrets/PII leak via CI logs or artifacts on GitHub. Since DEC-046 the repository is public, so logs and artifacts of runs are readable by anyone | L | H | no repository secrets; trust-auth throw-away DB (no password exists); synthetic fixtures; secret scan of tree + history (whole-value placeholders only, REV-0702); logs pass `tools/redact_paths.py` | GitHub retains artifacts 30 days - acceptable only because evidence is synthetic; anything private must never reach a log - orchestrator/reviewer |
| T-68 | Tampering (supply chain) | Malicious/compromised GitHub Action or dependency | M | H | `permissions: contents: read`, `persist-credentials: false`, exact dependency pins + lock, pip-audit/npm audit, SBOM | actions pinned to full commit SHAs with version comments (REV-0704, 00.8; `reports/phase-00/step-8/logs/rev0704_action_shas.log`) | SHA updates are manual and reviewed - orchestrator |
| T-69 | DoS | Public `/health/ready` used to load the migration graph repeatedly | M | L | REV-0016: 10 s cache; per-IP probe throttle; proxy may restrict to private network | - |
| T-70 | DoS / Spoofing | All clients share one rate-limit bucket behind the proxy, or a client spoofs XFF | M | M | REV-0015: staging/prod refuse TLS-header trust without `NUM_PROXIES>=1`; XFF ignored when `NUM_PROXIES=0` (tests) | proxy must overwrite XFF (DEC-042 config) - IT |
| T-71 | Info disclosure | Monitoring output reveals payloads / error texts | L | M | `outbox_status` prints counts, ages, reason codes only (`test_command_text_json_and_exit_codes`) | no public endpoint for queue state |
| T-72 | Repudiation | Silent job failure (dispatcher down, dead letters unnoticed) | M | M | `outbox_status --fail-on warn` for cron alerting (`docs/ops/JOB_MONITORING.md`) | alert channel to be configured by IT |
| T-73 | Info disclosure | Personal identifiers (home path, account name) in committed logs (REV-0502) | M | L | `tools/redact_paths.py` in `tools/ci_local.sh`; older step-5 log not rewritten (historic evidence) | - |
| T-74 | Spoofing | Browser for E2E differs between machines -> unreproducible evidence (REV-0603) | M | L | `browser-preflight.mjs` logs channel + versions, fails clearly | - |
| T-75 | Info disclosure | Public repository (DEC-046): design, security and ops documents (threat model, DB roles, backup design, this checklist), the `handoff/` contract copy and reports are readable by anyone, which helps an attacker plan against the future internal deployment | H | M | the DEC-041 data rule: no private sources, credentials, hostnames/IPs of the factory network, customer or salary data in Git; secrets only from the environment (checklist 2.2); security relies on controls, not on secrecy of the design; deployment details (DEC-042 proxy config, real hosts) are kept out of the repo | accepted by the employer in DEC-046 - employer |
| T-76 | Info disclosure | Commit metadata (author names, e-mail addresses, machine names in reports) is public and permanent | H | L | `ALEEKHAN_MACHINE` uses neutral names (`work-windows`); reports pass `tools/redact_paths.py` (account name, home path); a GitHub `noreply` commit e-mail can be configured by the employer for future commits | published history cannot be rewritten (same reason as the history allowlist) - employer |
| T-77 | Elevation / Tampering | A fork pull request changes the workflow or tests to run untrusted code in CI with repository privileges or secrets | M | H | trigger is `pull_request` (never `pull_request_target`): fork runs get a read-only `GITHUB_TOKEN` and no secrets; `permissions: contents: read` at workflow level; `persist-credentials: false`; the workflow uses no secrets at all; actions pinned to SHAs (T-68). Recommended repository setting (employer): "Require approval for all outside collaborators" for fork workflow runs | runner minutes can be consumed by fork PRs (DoS of CI only) - employer |
| T-78 | Info disclosure | A future change accidentally commits private data (now immediately public, cannot be recalled from forks/clones) | M | H | three layers: `control/tools/precommit_guard.py` (staged diff), `tools/secret_scan.py` over tree + untracked + full history as a CI gate (stage 11), `.gitignore` for private source types; REV-0702 closed the substring-placeholder bypass | detection is pattern-based (cannot recognise arbitrary customer names). **Accepted residual risk (REV-0803):** a value that declares itself synthetic with the prefix `example-`, `synthetic-` or `not-a-real-` is exempt as a whole, so a real secret written with such a prefix would not be reported; mitigations: reviewer checks every diff touching data/fixtures/config, `control/tools/precommit_guard.py` (independent patterns, no prefix exemption) on staged diffs, history scan in CI on every push - reviewer / orchestrator |

## 3. Re-check of earlier decisions

- **C-17 `/version` public:** unchanged - returns only api/contract version, short commit, environment name; no
  new fields in 00.6/00.7. Keep public (reports must tie screenshots to commits).
- **DATA_TABLE sensitivity classes:** confirmed as technical classes for PHASE_00; business confirmation stays
  with DEC-028 and the PHASE_01 field matrix.
- **DEC-041 / DEC-046 repository visibility:** DEC-041 assumed a private repository; DEC-046 (APPROVED by the
  employer on 2026-11-04) keeps it public. T-67 was re-assessed and T-75..T-78 added in step 00.8 (REV-0703).
- **RISKS R-02 / R-16 / R-05:** secret scan (R-02) and SCA/SBOM (R-16) now exist; R-05 mitigated by DEC-045 A
  (workflow + local CI + local drill) - first GitHub run and staging drill still pending.
