# CI (PHASE_00 / 00.7)

DEC-045 option A: GitHub-hosted Actions with synthetic fixtures only, no repository secrets; the same stages run
locally with `tools/ci_local.sh` so evidence exists on both machines (Windows work PC, Ubuntu home) and before the
first GitHub run.

## Stages (REPOSITORY_AND_RELEASE_CONTRACT_FA order)

| # | Stage | What runs |
|---|---|---|
| 1 | `lint` | `ruff check .` (incl. `S` = bandit security rules) + `ruff format --check .` |
| 2 | `type` | `mypy .` strict (backend) |
| 3 | `tools` | `unittest` for `tools/` (handoff verifier, secret scanner, path redaction, lock tool, logo sampler) |
| 4 | `unit` | pytest unit + integration on PostgreSQL 17 (junit `pytest-unit-integration.xml`) |
| 5 | `migration` | `backend/scripts/db_roundtrip.sh` (up -> zero -> up, schema diff) + `makemigrations --check` |
| 6 | `contract` | OpenAPI 3.1 contract tests (`test_api_contract.py`) |
| 7 | `authz` | deny-by-default route parity, log redaction, Persian redaction tests |
| 8 | `frontend` | `npm ci`, eslint, tsc, vitest, `vite build` |
| 9 | `e2e` | `frontend/scripts/e2e.sh` (real Django + PostgreSQL + Vite, Playwright; screenshots in `<out>/screenshots`) |
| 10 | `perf` | `pytest -m perf` latency smoke (`perf.json`, TECHNICAL DEFAULT budget) |
| 11 | `security` | secret scan (tree + history), lock check, `pip-audit` (runtime lock = gate; whole venv = informational), `npm audit --omit=dev` |
| 12 | `ops` | `ops/db/roles_check.sh` (least privilege) + `ops/backup/drill.sh` (backup/restore drill) |
| 13 | `artifacts` | commit id, CycloneDX SBOMs (python runtime, frontend prod), sha256 of `frontend/dist` |

Secret scan: the working tree includes untracked, non-ignored files (caught before `git add`); history findings in
commits that cannot be rewritten are suppressed only by exact `<sha40> <path> <rule> <reason>` entries in
`tools/secret_scan_allowlist.txt` (counted and listed as `ALLOWLISTED` in the log).

Network (flaky PyPI/registry): `pip-audit` calls retry on network errors only (`PIP_AUDIT_ATTEMPTS`, default 3;
`PIP_AUDIT_TIMEOUT`, default 60 s; `PIP_AUDIT_CACHE_DIR`). Security stage: runtime-lock audit and `npm audit` are
gates - unreachable service after retries = FAIL with "dependency scan NOT performed". Whole-venv audit: one
attempt, informational. Artifacts stage: if the pip-audit SBOM cannot be produced for network reasons, an offline
inventory SBOM is written from the lock (`tools/offline_sbom.py`, `sbom-python-runtime.offline.cdx.json`, labelled
`sbom-source=offline-lock`) and the log says FALLBACK.

Each stage writes `<out>/NN_<stage>.log` (through `tools/redact_paths.py`: no home paths / account names) and a
line in `<out>/summary.tsv` / `summary.md` with PASS / FAIL / SKIPPED and, for SKIPPED, the printed reason.
`CI_SKIP="e2e" CI_SKIP_REASON="..."` skips stages explicitly (the reason is recorded).

## Local run

```bash
set -a; . <test DB env file outside the repo>; set +a     # PGHOST/PGPORT/PGUSER/PGPASSWORD - never printed
export PG_BIN=<postgres 17 bin dir> ALEEKHAN_MACHINE=<machine name>
# Windows work machine: Playwright CDN blocked -> installed Edge
export E2E_BROWSER_CHANNEL=msedge PLAYWRIGHT_BROWSERS_PATH=<dir outside repo>
bash tools/ci_local.sh reports/phase-00/step-7/logs/ci            # all stages
bash tools/ci_local.sh /tmp/ci lint type unit                      # selected stages
```

The machine has little memory: stages run strictly one after another; the E2E stage starts and stops its own
servers.

Evidence format (REV-0134, step 01.8): every `NN_<stage>.log` starts with a `# command` block (the exact stage
function that ran) and ends with `# exit code: N`; `summary.md` has an exit-code column, the worktree state at
the end of the run (modified tracked / untracked counts) and the git tree id of every code directory as tested
(`backend`, `frontend`, `tools`, `ops`, `docs`, `.github`). Evidence produced before the commit is matched to it
with `git rev-parse <commit>:<dir>` (must equal the recorded id). E2E artefact folders can be redirected with
`CI_E2E_SCREENSHOT_DIR`, `CI_E2E_HTML_REPORT`, `CI_E2E_OUTPUT_DIR`.

## GitHub Actions (`.github/workflows/ci.yml`)

push / pull_request to `main` (+ manual). ubuntu-latest, PostgreSQL 17 service container (trust auth on the
runner-local port: there is no password at all), Python 3.12, Node 24, PostgreSQL 17 client from the PGDG apt
repository (pg_dump must match the server major), Playwright bundled Chromium. One workflow step per stage, each
calling `tools/ci_local.sh` with `CI_APPEND=1`; the evidence folder is uploaded as artifact
`ci-evidence-<sha>` (30 days) even when a stage fails. `permissions: contents: read`, checkout without
persisted credentials.

Action pins (REV-0704, step 00.8): every `uses:` is a full commit SHA with a `# vX.Y.Z` comment, resolved from
the official repositories through the public GitHub API; each pinned SHA equalled the moving major tag that the
green 00.7 run used (`reports/phase-00/step-8/logs/rev0704_action_shas.log`). Updating an action = resolve the
new release tag to its commit SHA the same way and change SHA + comment together.

Public repository (DEC-046): `pull_request` runs from forks receive a read-only `GITHUB_TOKEN` and no repository
secrets; the workflow defines no secrets and never uses `pull_request_target`. Hosted evidence: GitHub Actions run
41790868012 on b5397b6, all steps `success` (`reports/phase-00/step-7/REVIEW.md`).

## Dependency policy

- Exact pins: `backend/requirements.txt` (direct runtime), `backend/requirements.lock` (runtime incl. transitive,
  generated by `tools/lock_runtime.py`, checked in CI), `backend/requirements-dev.txt`, `frontend/package-lock.json`.
- Repository rule for new versions: released >= 14 days before the pin date - except security fixes reported by
  `pip-audit` / `npm audit`, which are applied as soon as the full CI passes (documented per upgrade).
- 00.7 check of Django: `pip index versions Django` lists 5.2.19 (PyPI upload 2026-11-03, one day before this
  step); `pip-audit` (PyPI and OSV services) reports **no known vulnerabilities** for the pinned 5.2.18. So there
  is no security reason to break the 14-day rule: Django stays 5.2.18 and 5.2.19 is re-evaluated at the next pin
  date (or immediately if an advisory appears).
- Vulnerability in a runtime dependency = security stage FAIL (pip-audit `--strict` on the lock; `npm audit
  --omit=dev --audit-level=low`).
