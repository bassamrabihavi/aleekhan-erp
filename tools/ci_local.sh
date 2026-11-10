#!/usr/bin/env bash
# Local / CI pipeline runner (PHASE_00 / 00.7). The SAME stages run on this machine (Windows Git Bash or
# Linux) and in GitHub Actions (.github/workflows/ci.yml calls this script one stage at a time).
#
# Order (REPOSITORY_AND_RELEASE_CONTRACT_FA): lint -> type -> unit/integration -> migration -> API contracts
# -> authorization -> frontend (lint/type/unit/build) -> E2E -> perf smoke -> security scan -> ops (roles,
# backup drill) -> build/artifacts.
#
# Every stage writes <out>/NN_<stage>.log; all output passes tools/redact_paths.py (REV-0502: no home paths
# or account names in evidence; REV-0103: junit xml files are redacted in place, incl. the host name). A stage
# that cannot run prints "SKIPPED: <reason>" and is listed with that reason in <out>/summary.md - never silently.
# REV-0134 (01.8): every log starts with the exact commands of the stage ("# command" block = the stage
# function) and ends with "# exit code: N", so a short tool output is still verifiable evidence. The summary
# also records the worktree state and, per code directory, the git tree id of the tested files (so evidence
# produced before the commit can be matched to it: `git rev-parse <sha>:backend` == the recorded id).
# Passwords are never printed (libpq env only).
#
# Usage: tools/ci_local.sh <out-dir> [stage ...]          (default: all stages, keep going after a failure)
# Stages: lint type tools unit migration contract authz frontend e2e perf security ops artifacts
# Env:    PYTHON (default repo .venv), PG_BIN, NPM (default npm), E2E_BROWSER_CHANNEL, CI_SKIP="e2e ops",
#         CI_SKIP_REASON="..." (printed for skipped stages), PLAYWRIGHT_BROWSERS_PATH, CI_APPEND=1,
#         CI_E2E_SCREENSHOT_DIR / CI_E2E_HTML_REPORT / CI_E2E_OUTPUT_DIR (e2e artefact folders)
set -uo pipefail

OUT="${1:?usage: ci_local.sh <out-dir> [stage ...]}"
shift
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALL_STAGES=(lint type tools unit migration contract authz frontend e2e perf security ops artifacts)
if [ "$#" -gt 0 ]; then STAGES=("$@"); else STAGES=("${ALL_STAGES[@]}"); fi

if [ -z "${PYTHON:-}" ]; then
  if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then PYTHON="$ROOT/.venv/Scripts/python.exe"
  elif [ -x "$ROOT/.venv/bin/python" ]; then PYTHON="$ROOT/.venv/bin/python"
  else PYTHON="python3"; fi
fi
export PYTHON
NPM="${NPM:-npm}"
export ALEEKHAN_ENV=test
export PYTHONIOENCODING=utf-8
unset DATABASE_URL || true

have_pg() { [ -n "${PGHOST:-}" ] && [ -n "${PGPORT:-}" ] && [ -n "${PGUSER:-}" ]; }
have_node() { command -v node >/dev/null 2>&1 && command -v "$NPM" >/dev/null 2>&1; }
skip() { echo "SKIPPED: $*"; return 77; }
need_pg() { have_pg || skip "no PostgreSQL libpq env (PGHOST/PGPORT/PGUSER) - load the test DB env first"; }
need_node() { have_node || skip "node/npm not on PATH (Node 24 LTS required)"; }

# pip-audit with retries for NETWORK errors only (PyPI / OSV). Return codes:
#   0 = completed, no vulnerabilities; 1 = completed with findings (or a non-network error);
#   75 = network unavailable after all attempts (caller decides: gate -> FAIL, SBOM -> offline fallback).
# Env: PIP_AUDIT_ATTEMPTS (default 3), PIP_AUDIT_TIMEOUT (seconds per request, default 60), PIP_AUDIT_CACHE_DIR.
NET_ERR_RE='ConnectionError|ConnectTimeout|ReadTimeout|RemoteDisconnected|Max retries exceeded|Read timed out|Temporary failure in name resolution|NewConnectionError|SSLError'
pip_audit_retry() {
  local attempts="${PIP_AUDIT_ATTEMPTS:-3}" i rc errf
  errf="$(mktemp)"
  for ((i = 1; i <= attempts; i++)); do
    "$PYTHON" -m pip_audit --progress-spinner off --timeout "${PIP_AUDIT_TIMEOUT:-60}" \
      ${PIP_AUDIT_CACHE_DIR:+--cache-dir "$PIP_AUDIT_CACHE_DIR"} "$@" 2>"$errf"
    rc=$?
    if [ "$rc" -eq 0 ]; then grep -v -E '^WARNING:pip_audit' "$errf" >&2; rm -f "$errf"; return 0; fi
    if ! grep -q -E "$NET_ERR_RE" "$errf"; then cat "$errf" >&2; rm -f "$errf"; return 1; fi
    echo "pip-audit: network error on attempt $i/$attempts: $(grep -o -E "$NET_ERR_RE" "$errf" | head -n1)" >&2
    [ "$i" -lt "$attempts" ] && sleep $((i * 10))
  done
  rm -f "$errf"
  return 75
}

# ------------------------------------------------------------------------------------------------ stages
stage_lint() {
  "$PYTHON" -m ruff --version && "$PYTHON" -m ruff check . && "$PYTHON" -m ruff format --check .
}
stage_type() {
  (cd backend && "$PYTHON" -m mypy --version && "$PYTHON" -m mypy .)
}
stage_tools() {
  "$PYTHON" -m unittest discover -s tools/tests -p "test_*.py" -v
}
stage_unit() {
  need_pg || return $?
  # contract + authorization tests run in their own stages below (same pytest, separate evidence)
  (cd backend && "$PYTHON" -m pytest -q --junitxml="$OUT/pytest-unit-integration.xml" \
    --ignore=platform_core/tests/test_api_contract.py --ignore=platform_core/tests/test_authz_route_parity.py)
}
stage_migration() {
  need_pg || return $?
  bash backend/scripts/db_roundtrip.sh "$OUT/migration" && \
    (cd backend && DJANGO_SETTINGS_MODULE=aleekhan.settings_test "$PYTHON" manage.py makemigrations --check --dry-run)
}
stage_contract() {
  need_pg || return $?
  # 01.8: the draft contract itself is validated as OpenAPI (openapi-spec-validator, requirements-dev.txt)
  "$PYTHON" -c 'import sys, yaml; from openapi_spec_validator import validate
spec = yaml.safe_load(open("docs/api/openapi-draft.yaml", encoding="utf-8")); validate(spec)
ops = sum(1 for p in spec["paths"].values() for m in p if m in ("get","put","post","delete","patch"))
print("OpenAPI valid", spec["openapi"], spec["info"]["version"], len(spec["paths"]), "paths", ops, "operations")' \
    && (cd backend && "$PYTHON" -m pytest -q --junitxml="$OUT/pytest-contract.xml" platform_core/tests/test_api_contract.py)
}
stage_authz() {
  need_pg || return $?
  (cd backend && "$PYTHON" -m pytest -q --junitxml="$OUT/pytest-authz.xml" \
    platform_core/tests/test_authz_route_parity.py platform_core/tests/test_log_redaction.py \
    platform_core/tests/test_redaction_persian.py)
}
stage_frontend() {
  need_node || return $?
  (cd frontend && node --version && "$NPM" --version && "$NPM" ci --no-audit && "$NPM" run lint && "$NPM" run typecheck \
    && "$NPM" test && "$NPM" run build && ls -1 dist/assets)
}
stage_e2e() {
  need_pg || return $?
  need_node || return $?
  [ -d frontend/node_modules ] || skip "frontend/node_modules missing (run the frontend stage first)" || return $?
  # CI_E2E_SCREENSHOT_DIR / CI_E2E_HTML_REPORT / CI_E2E_OUTPUT_DIR override the defaults below (01.8: the
  # screenshots go to the step report folder, the bulky Playwright report/output stay outside the repo)
  (cd frontend && E2E_SCREENSHOT_DIR="${CI_E2E_SCREENSHOT_DIR:-$OUT/screenshots}" \
    E2E_HTML_REPORT="${CI_E2E_HTML_REPORT:-$OUT/playwright-report}" \
    E2E_OUTPUT_DIR="${CI_E2E_OUTPUT_DIR:-$OUT/playwright-output}" bash scripts/e2e.sh)
}
stage_perf() {
  need_pg || return $?
  # PHASE_00 smoke + PHASE_01 perf (01.7), each with its own numbers file
  (cd backend && ALEEKHAN_PERF_OUT="$OUT/perf.json" "$PYTHON" -m pytest -q -m perf platform_core/tests/test_perf_smoke.py \
    && cat "$OUT/perf.json" \
    && ALEEKHAN_PERF_OUT="$OUT/perf_phase01.json" "$PYTHON" -m pytest -q -m perf platform_core/tests/test_perf_phase01.py \
    && cat "$OUT/perf_phase01.json")
}
stage_security() {
  local rc=0
  echo "== secret scan (tracked files + git history)"
  "$PYTHON" tools/secret_scan.py --history --json "$OUT/secret_scan.json" || rc=1
  echo "== runtime lock matches the venv"
  "$PYTHON" tools/lock_runtime.py --check || rc=1
  echo "== pip-audit: runtime lock (backend/requirements.lock)"
  if "$PYTHON" -m pip_audit --version >/dev/null 2>&1; then
    "$PYTHON" -m pip_audit --version
    # GATE: a vulnerability or an unreachable vulnerability service is a FAIL (never a silent pass)
    pip_audit_retry -r backend/requirements.lock --no-deps --disable-pip --strict -f json -o "$OUT/pip_audit_runtime.json"
    case $? in
      0) echo "pip-audit runtime lock: PASS (no known vulnerabilities)" ;;
      75) echo "FAIL: pip-audit runtime lock could not reach the vulnerability service after ${PIP_AUDIT_ATTEMPTS:-3} attempts - dependency scan NOT performed"; rc=1 ;;
      *) echo "FAIL: pip-audit runtime lock reported vulnerabilities or an error (see above)"; rc=1 ;;
    esac
    echo "== pip-audit: whole dev/QA venv (INFORMATIONAL: tooling is not shipped; findings are listed but do"
    echo "   not fail this stage - the runtime lock above is the gate)"
    PIP_AUDIT_ATTEMPTS=1 pip_audit_retry --skip-editable  # informational: a single attempt
    case $? in
      0) echo "INFO: dev/QA venv: no known vulnerabilities" ;;
      75) echo "INFO: dev/QA venv audit NOT performed: network unavailable after retries (not a gate)" ;;
      *) echo "INFO: dev/QA venv audit reported findings or an error (see above); not a gate" ;;
    esac
  else
    echo "SKIPPED (sub-check): pip-audit not installed in $PYTHON (pip install -r backend/requirements-dev.txt)"
    rc=1
  fi
  echo "== npm audit (production dependencies)"
  if have_node; then
    (cd frontend && "$NPM" audit --omit=dev --audit-level=low) \
      || { echo "FAIL: npm audit reported vulnerabilities or could not reach the registry (see above)"; rc=1; }
  else
    echo "SKIPPED (sub-check): node/npm not on PATH"
    rc=1
  fi
  return $rc
}
stage_ops() {
  need_pg || return $?
  local rc=0
  echo "== least-privilege DB roles"
  bash ops/db/roles_check.sh "$OUT/roles" || rc=1
  echo "== backup / restore drill"
  bash ops/backup/drill.sh "$OUT/drill" || rc=1
  echo "== rollback rehearsal (01.7: down to the PHASE_01 baseline 0010 with data, forward to head)"
  bash ops/backup/rollback_rehearsal.sh "$OUT/rollback" || rc=1
  echo "== outbox monitoring command (on a throw-away migrated DB is covered by the drill; here: help)"
  (cd backend && "$PYTHON" manage.py outbox_status --help >/dev/null && echo "outbox_status: available") || rc=1
  return $rc
}
stage_artifacts() {
  local rc=0
  git rev-parse HEAD > "$OUT/commit.txt"
  git status --porcelain --untracked-files=no | wc -l | tr -d ' ' > "$OUT/worktree_modified_files.txt"
  echo "commit $(cat "$OUT/commit.txt"), modified tracked files: $(cat "$OUT/worktree_modified_files.txt")"
  # SBOM: pip-audit CycloneDX (needs PyPI); if the network is unavailable after retries, an offline inventory
  # SBOM from the lock (tools/offline_sbom.py, labelled sbom-source=offline-lock) - the vulnerability gate is
  # the security stage, not this one.
  local sbom_rc=75
  if "$PYTHON" -m pip_audit --version >/dev/null 2>&1; then
    pip_audit_retry -r backend/requirements.lock --no-deps --disable-pip -f cyclonedx-json -o "$OUT/sbom-python-runtime.cdx.json"
    sbom_rc=$?
  else
    echo "pip-audit not installed in $PYTHON"
  fi
  case "$sbom_rc" in
    0) echo "SBOM python: sbom-python-runtime.cdx.json (pip-audit CycloneDX)" ;;
    75)
      echo "FALLBACK (sub-check): pip-audit SBOM unavailable (network or pip-audit missing) -> offline inventory SBOM from backend/requirements.lock"
      "$PYTHON" tools/offline_sbom.py "$OUT/sbom-python-runtime.offline.cdx.json" \
        && echo "SBOM python: sbom-python-runtime.offline.cdx.json (offline, no vulnerability data)" || rc=1 ;;
    *) echo "FAIL: pip-audit SBOM generation failed (non-network error, see above)"; rc=1 ;;
  esac
  if have_node && [ -d frontend/node_modules ]; then
    (cd frontend && "$NPM" sbom --sbom-format cyclonedx --omit dev > "$OUT/sbom-frontend.cdx.json") \
      && echo "SBOM frontend: sbom-frontend.cdx.json" || rc=1
    if [ -d frontend/dist ]; then
      (cd frontend/dist && find . -type f | LC_ALL=C sort | xargs sha256sum) > "$OUT/frontend-dist.sha256" \
        && echo "frontend dist files hashed: $(wc -l < "$OUT/frontend-dist.sha256" | tr -d ' ')"
    else
      echo "SKIPPED (sub-check): frontend/dist missing (frontend stage not run)"
    fi
  else
    echo "SKIPPED (sub-check): frontend SBOM needs node + node_modules"
  fi
  return $rc
}

# Git tree id of every code directory as it is in the worktree (tracked + untracked, .gitignore honoured), via a
# throw-away index: the real index and the worktree are not touched.
CODE_DIRS=(backend frontend tools ops docs .github)
code_trees() {
  local idx tree d
  idx="$(mktemp)"
  rm -f "$idx"
  GIT_INDEX_FILE="$idx" git read-tree HEAD \
    && GIT_INDEX_FILE="$idx" git add -A -- "${CODE_DIRS[@]}" 2>/dev/null \
    && tree="$(GIT_INDEX_FILE="$idx" git write-tree)" \
    && for d in "${CODE_DIRS[@]}"; do echo "$d $(git rev-parse "$tree:$d")"; done
  rm -f "$idx"
}

# ------------------------------------------------------------------------------------------------ runner
cd "$ROOT" || exit 2
# CI_APPEND=1 (GitHub workflow: one stage per step) keeps the summary of earlier steps.
[ "${CI_APPEND:-0}" = "1" ] || : > "$OUT/summary.tsv"
touch "$OUT/summary.tsv"
FAILED=0
for s in "${STAGES[@]}"; do
  if ! declare -F "stage_$s" >/dev/null; then echo "unknown stage: $s" >&2; exit 2; fi
  IDX=0
  for i in "${!ALL_STAGES[@]}"; do [ "${ALL_STAGES[$i]}" = "$s" ] && IDX=$((i + 1)); done
  log="$OUT/$(printf '%02d' "$IDX")_$s.log"
  echo "================================================================ [$IDX] $s"
  start="$(date +%s)"
  if [[ " ${CI_SKIP:-} " == *" $s "* ]]; then
    { echo "SKIPPED: ${CI_SKIP_REASON:-listed in CI_SKIP (no reason given)}"; } | tee "$log"
    rc=77
  else
    {
      echo "# stage $s | $(date -u +%Y-%m-%dT%H:%M:%SZ) | machine ${ALEEKHAN_MACHINE:-unnamed} | $(uname -s)"
      echo "# command (bash tools/ci_local.sh <out> $s runs this function):"
      declare -f "stage_$s" | sed 's/^/#   /'
      echo "# ---- output"
      "stage_$s"
    } 2>&1 | "$PYTHON" tools/redact_paths.py | tee "$log"
    rc="${PIPESTATUS[0]}"
  fi
  echo "# exit code: $rc" | tee -a "$log"
  # REV-0103: junit xml is written by pytest directly (not through the log filter): redact host/account names
  "$PYTHON" tools/redact_paths.py --in-place "$OUT"/*.xml >/dev/null 2>&1 || true
  secs=$(( $(date +%s) - start ))
  case "$rc" in
    0) result=PASS ;;
    77) result=SKIPPED ;;
    *) result=FAIL; FAILED=$((FAILED + 1)) ;;
  esac
  reason=""
  [ "$result" = SKIPPED ] && reason="$(grep -m1 '^SKIPPED:' "$log" | sed 's/^SKIPPED: //')"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$s" "$result" "$rc" "$secs" "$(basename "$log")" "$reason" >> "$OUT/summary.tsv"
  echo "---------------------------------------------------------------- [$IDX] $s: $result (${secs}s)"
done

{
  echo "# CI summary"
  echo
  echo "Commit \`$(git rev-parse HEAD)\` | machine ${ALEEKHAN_MACHINE:-unnamed} | $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "Worktree at the end of the run: $(git status --porcelain --untracked-files=no | wc -l | tr -d ' ') modified" \
    "tracked file(s), $(git status --porcelain --untracked-files=normal | grep -c '^??') untracked path(s)" \
    "(0/0 = exactly the commit above)."
  echo
  echo "Tested code (git tree id of the worktree per directory; compare with \`git rev-parse <commit>:<dir>\`):"
  echo
  code_trees | while read -r d t; do echo "- \`$d\` $t"; done
  echo
  echo "| Stage | Result | Exit code | Seconds | Log | Skip reason |"
  echo "|---|---|---|---|---|---|"
  while IFS=$'\t' read -r s r code secs l why; do echo "| $s | $r | $code | $secs | $l | ${why:-} |"; done < "$OUT/summary.tsv"
} > "$OUT/summary.md"
cat "$OUT/summary.md"
[ "$FAILED" -eq 0 ]
