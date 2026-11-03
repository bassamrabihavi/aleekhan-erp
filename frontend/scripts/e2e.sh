#!/usr/bin/env bash
# E2E runner (PHASE_00 / 00.5): real Django + PostgreSQL + Vite, then Playwright.
#
#   1. create a throw-away PostgreSQL database ($E2E_DB) and migrate it (ALEEKHAN_ENV=dev)
#   2. run Playwright: it starts `manage.py runserver --noreload` and Vite, runs the real-backend tests
#   3. run Playwright again in E2E_MODE=backend-down (Vite only, Django stopped): real "server down" test
#   4. always drop the database again
#
# Connection: libpq env (PGHOST/PGPORT/PGUSER/PGPASSWORD or ~/.pgpass). The password is never printed.
# Env: PG_BIN (dir with psql), E2E_DB (default aleekhan_e2e), E2E_PYTHON (default ../.venv python),
#      PLAYWRIGHT_BROWSERS_PATH (browsers outside the repo), E2E_HTML_REPORT / E2E_OUTPUT_DIR (artefacts).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PSQL="${PG_BIN:+$PG_BIN/}psql"
DB="${E2E_DB:-aleekhan_e2e}"

case "$DB" in
  *[!a-z0-9_]*|"") echo "E2E_DB must match [a-z0-9_]+" >&2; exit 2 ;;
esac
for v in PGHOST PGPORT PGUSER; do
  if [ -z "${!v:-}" ]; then echo "missing libpq env $v (load the test DB env first)" >&2; exit 2; fi
done

if [ -z "${E2E_PYTHON:-}" ]; then
  if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then E2E_PYTHON="$ROOT/.venv/Scripts/python.exe"; else E2E_PYTHON="$ROOT/.venv/bin/python"; fi
fi
export E2E_PYTHON

port_busy() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3>&- 3<&-; return 0; }
  return 1
}
for p in 8000 5173; do
  if port_busy "$p"; then echo "port $p is already in use - stop that server first" >&2; exit 2; fi
done

cleanup() {
  echo "== drop throw-away database $DB"
  "$PSQL" -d postgres -v ON_ERROR_STOP=1 -qc "DROP DATABASE IF EXISTS $DB WITH (FORCE)" >/dev/null || echo "WARN: drop failed" >&2
}
trap cleanup EXIT

echo "== server: $("$PSQL" -d postgres -Atc 'SHOW server_version')"
echo "== create throw-away database $DB"
"$PSQL" -d postgres -v ON_ERROR_STOP=1 -qc "DROP DATABASE IF EXISTS $DB WITH (FORCE)" >/dev/null || exit 1
"$PSQL" -d postgres -v ON_ERROR_STOP=1 -qc "CREATE DATABASE $DB ENCODING 'UTF8' TEMPLATE template0" >/dev/null || exit 1

# Backend env for runserver (dev). The build commit is the real HEAD so the UI can be tied to a commit.
export PGDATABASE="$DB"
export ALEEKHAN_ENV=dev
unset DATABASE_URL || true
ALEEKHAN_BUILD_COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
export ALEEKHAN_BUILD_COMMIT
export E2E_EXPECT_COMMIT="${ALEEKHAN_BUILD_COMMIT:0:12}"
# The suite loads the page ~20 times within a minute from one IP; raise the dev limits for this run only.
export ALEEKHAN_RATE_HEALTH="${ALEEKHAN_RATE_HEALTH:-2000/min}"
export ALEEKHAN_RATE_ANON="${ALEEKHAN_RATE_ANON:-2000/min}"

echo "== migrate (ALEEKHAN_ENV=dev, db=$DB)"
(cd "$ROOT/backend" && "$E2E_PYTHON" manage.py migrate --noinput) || exit 1

cd "$HERE" || exit 1
echo "== playwright: real backend (build commit $E2E_EXPECT_COMMIT)"
npx playwright test
rc1=$?

echo "== playwright: backend stopped (E2E_MODE=backend-down)"
for p in 8000; do
  if port_busy "$p"; then echo "port $p still in use after the first run" >&2; exit 3; fi
done
E2E_MODE=backend-down npx playwright test
rc2=$?

echo "== results: real-backend rc=$rc1, backend-down rc=$rc2"
[ "$rc1" -eq 0 ] && [ "$rc2" -eq 0 ]
