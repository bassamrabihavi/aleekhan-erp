#!/usr/bin/env bash
# Least-privilege role check (PHASE_00 / 00.7, docs/ops/DB_ROLES.md).
#
#   1. create a throw-away database + three throw-away roles (unique random suffix, NOLOGIN, no password)
#   2. ops/db/roles.sql, then `manage.py migrate` AS THE OWNER ROLE (PGOPTIONS="-c role=..."), then
#      ops/db/grants.sql
#   3. as the APP role: the platform write path works (unit of work: audit + outbox), and every attempt to
#      bypass the append-only audit (DELETE/UPDATE/TRUNCATE, DISABLE TRIGGER, DROP TRIGGER,
#      session_replication_role=replica) or to run DDL is refused
#   4. as the READONLY role: SELECT works, writes are refused
#   5. always drop the database and the roles (trap)
#
# The connection is the existing admin/test login from the libpq environment (PGHOST/PGPORT/PGUSER/
# PGPASSWORD or ~/.pgpass) - it is not changed and its password is never printed. The checked roles never
# log in: the admin session switches to them with the `role` setting, so no password is generated, stored
# or logged. Privilege checks use the current role exactly as for a login of that role.
#
# Usage: ops/db/roles_check.sh <output-dir>      (writes roles_check.json; human log on stdout)
# Env:   PG_BIN, PYTHON (default: repo .venv python), ROLES_DB (default aleekhan_roles_check)
set -uo pipefail

OUT="${1:?usage: roles_check.sh <output-dir>}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PSQL="${PG_BIN:+$PG_BIN/}psql"
DB="${ROLES_DB:-aleekhan_roles_check}"
case "$DB" in *[!a-z0-9_]*|"") echo "ROLES_DB must match [a-z0-9_]+" >&2; exit 2 ;; esac
if [ -z "${PYTHON:-}" ]; then
  if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then PYTHON="$ROOT/.venv/Scripts/python.exe"; else PYTHON="$ROOT/.venv/bin/python"; fi
fi
for v in PGHOST PGPORT PGUSER; do
  if [ -z "${!v:-}" ]; then echo "missing libpq env $v (load the test DB env first)" >&2; exit 2; fi
done

SUFFIX="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
OWNER="aleekhan_rc_owner_$SUFFIX"
APP="aleekhan_rc_app_$SUFFIX"
RO="aleekhan_rc_ro_$SUFFIX"
PASS=0
FAIL=0
RESULTS=()

# psql on Windows writes CRLF; strip CR so values compare equal (pipefail keeps psql's exit status)
admin() { "$PSQL" -X -v ON_ERROR_STOP=1 -qAt "$@" | tr -d '\015'; }

cleanup() {
  echo "== cleanup: drop $DB and roles *_$SUFFIX"
  admin -d postgres -c "DROP DATABASE IF EXISTS $DB WITH (FORCE)" >/dev/null 2>&1 || echo "WARN: drop database failed" >&2
  for r in "$APP" "$RO" "$OWNER"; do
    admin -d postgres -c "DROP ROLE IF EXISTS $r" >/dev/null 2>&1 || echo "WARN: drop role failed" >&2
  done
}
trap cleanup EXIT

record() {  # name outcome detail
  if [ "$2" = PASS ]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); fi
  printf '%-4s %s%s\n' "$2" "$1" "${3:+  ($3)}"
  RESULTS+=("{\"check\": \"$1\", \"result\": \"$2\"}")
}

as_role() {  # role sql -> rc, stderr in $ERR
  local role="$1" sql="$2" errf
  errf="$(mktemp)"
  PGOPTIONS="-c role=$role" "$PSQL" -X -v ON_ERROR_STOP=1 -qAt -d "$DB" -c "$sql" >/dev/null 2>"$errf"
  local rc=$?
  ERR="$(head -n1 "$errf" | sed -E 's/^psql:[^E]*//')"
  rm -f "$errf"
  return $rc
}

expect_ok() {  # name role sql
  if as_role "$2" "$3"; then record "$1" PASS; else record "$1" FAIL "unexpected error: $ERR"; fi
}

expect_denied() {  # name role sql
  if as_role "$2" "$3"; then
    record "$1" FAIL "statement was ALLOWED"
  elif printf '%s' "$ERR" | grep -q -E 'permission denied|must be owner|read-only transaction|must be superuser'; then
    record "$1" PASS "$ERR"
  else
    record "$1" FAIL "failed for another reason: $ERR"
  fi
}

echo "== server: $(admin -d postgres -c 'SHOW server_version')"
echo "== throw-away database $DB, roles owner/app/ro with suffix $SUFFIX (NOLOGIN, no password)"
admin -d postgres -c "DROP DATABASE IF EXISTS $DB WITH (FORCE)" >/dev/null || exit 1
admin -d postgres -c "CREATE DATABASE $DB ENCODING 'UTF8' TEMPLATE template0" >/dev/null || exit 1
admin -d postgres -v db="$DB" -v owner="$OWNER" -v app="$APP" -v ro="$RO" -f "$ROOT/ops/db/roles.sql" >/dev/null || exit 1

echo "== migrate as the owner role"
(
  cd "$ROOT/backend" && PGDATABASE="$DB" PGOPTIONS="-c role=$OWNER" ALEEKHAN_ENV=test \
    "$PYTHON" manage.py migrate --noinput >/dev/null
) || { echo "FAIL: migrate as owner role" >&2; exit 1; }
admin -d "$DB" -v app="$APP" -v ro="$RO" -c "SET ROLE $OWNER" -f "$ROOT/ops/db/grants.sql" >/dev/null || exit 1
tables_not_owned="$(admin -d "$DB" -c "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner <> '$OWNER'")"
if [ "$tables_not_owned" = "0" ]; then record "all tables owned by the owner role" PASS; else record "all tables owned by the owner role" FAIL "$tables_not_owned not owned"; fi

AUDIT_INSERT="INSERT INTO platform_audit_event (id, occurred_at, actor_type, action, outcome, resource_type, resource_id, scope, reason) VALUES (gen_random_uuid(), now(), 'SYSTEM', 'platform.ops.roles_check', 'SUCCESS', 'platform.synthetic', 'roles-check', '{}', '')"

echo "== app role: allowed runtime path"
expect_ok "app: INSERT audit row" "$APP" "$AUDIT_INSERT"
expect_ok "app: SELECT audit" "$APP" "SELECT count(*) FROM platform_audit_event"
expect_ok "app: UPDATE integration source (DML)" "$APP" "UPDATE platform_integration_source SET name_fa = name_fa WHERE false"
if (
  cd "$ROOT/backend" && PGDATABASE="$DB" PGOPTIONS="-c role=$APP" ALEEKHAN_ENV=test "$PYTHON" manage.py shell -c "
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.uow import unit_of_work
with unit_of_work(RequestContext(Actor.system())) as uow:
    uow.audit(action='platform.ops.roles_check', resource_type='platform.synthetic', resource_id='roles-check')
    uow.emit(event_type='platform.ops.roles_checked', aggregate_type='platform.synthetic',
             aggregate_id='roles-check', aggregate_version=1, payload={'note': 'synthetic'})
" >/dev/null 2>&1
); then record "app: unit of work (audit + outbox) via Django" PASS; else record "app: unit of work (audit + outbox) via Django" FAIL; fi
if (cd "$ROOT/backend" && PGDATABASE="$DB" PGOPTIONS="-c role=$APP" ALEEKHAN_ENV=test "$PYTHON" manage.py outbox_status --json >/dev/null 2>&1); then
  record "app: manage.py outbox_status" PASS
else
  record "app: manage.py outbox_status" FAIL
fi

echo "== app role: audit bypass and DDL must be refused"
expect_denied "app: DELETE audit rows" "$APP" "DELETE FROM platform_audit_event"
expect_denied "app: UPDATE audit rows" "$APP" "UPDATE platform_audit_event SET reason = 'x'"
expect_denied "app: TRUNCATE audit" "$APP" "TRUNCATE platform_audit_event"
expect_denied "app: DISABLE audit trigger" "$APP" "ALTER TABLE platform_audit_event DISABLE TRIGGER trg_audit_event_append_only"
expect_denied "app: DISABLE TRIGGER ALL" "$APP" "ALTER TABLE platform_audit_event DISABLE TRIGGER ALL"
expect_denied "app: DROP audit trigger" "$APP" "DROP TRIGGER trg_audit_event_append_only ON platform_audit_event"
expect_denied "app: session_replication_role=replica (skips triggers)" "$APP" "SET session_replication_role = replica"
expect_denied "app: DELETE compensation rows" "$APP" "DELETE FROM platform_compensation_record"
expect_denied "app: write django_migrations" "$APP" "INSERT INTO django_migrations (app, name, applied) VALUES ('x', 'y', now())"
expect_denied "app: CREATE TABLE" "$APP" "CREATE TABLE rc_probe (id int)"
expect_denied "app: CREATE FUNCTION" "$APP" "CREATE FUNCTION rc_probe() RETURNS int LANGUAGE sql AS 'SELECT 1'"
expect_denied "app: DROP TABLE" "$APP" "DROP TABLE platform_outbox_event"
expect_denied "app: ALTER TABLE ADD COLUMN" "$APP" "ALTER TABLE platform_outbox_event ADD COLUMN rc_probe int"

echo "== readonly role"
expect_ok "ro: SELECT audit" "$RO" "SELECT count(*) FROM platform_audit_event"
expect_ok "ro: SELECT outbox" "$RO" "SELECT count(*) FROM platform_outbox_event"
expect_denied "ro: INSERT audit" "$RO" "$AUDIT_INSERT"
expect_denied "ro: UPDATE integration source" "$RO" "UPDATE platform_integration_source SET name_fa = name_fa"
expect_denied "ro: DELETE outbox" "$RO" "DELETE FROM platform_outbox_event"

echo "== audit trigger still enabled and rows intact"
state="$(admin -d "$DB" -c "SELECT string_agg(tgname || '=' || tgenabled::text, ',' ORDER BY tgname) FROM pg_trigger WHERE tgrelid = 'platform_audit_event'::regclass AND NOT tgisinternal")"
if [ "$state" = "trg_audit_event_append_only=O,trg_audit_event_no_truncate=O" ]; then record "audit triggers enabled" PASS "$state"; else record "audit triggers enabled" FAIL "$state"; fi
rows="$(admin -d "$DB" -c "SELECT count(*) FROM platform_audit_event WHERE action = 'platform.ops.roles_check'")"
if [ "$rows" = "2" ]; then record "audit rows written by app are intact (2)" PASS; else record "audit rows written by app are intact (2)" FAIL "found $rows"; fi

{
  printf '{\n  "server_version": "%s",\n  "passed": %d,\n  "failed": %d,\n  "checks": [\n' \
    "$(admin -d postgres -c 'SHOW server_version')" "$PASS" "$FAIL"
  for i in "${!RESULTS[@]}"; do
    sep=","; [ "$i" -eq $((${#RESULTS[@]} - 1)) ] && sep=""
    printf '    %s%s\n' "${RESULTS[$i]}" "$sep"
  done
  printf '  ]\n}\n'
} > "$OUT/roles_check.json"

echo "== roles check: passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
