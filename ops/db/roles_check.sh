#!/usr/bin/env bash
# Least-privilege role check (PHASE_00 / 00.7, docs/ops/DB_ROLES.md).
#
#   1. create a throw-away database + three throw-away roles (unique random suffix, NOLOGIN, no password)
#   2. ops/db/roles.sql, then `manage.py migrate` AS THE OWNER ROLE (PGOPTIONS="-c role=..."), then
#      ops/db/grants.sql
#   3. as the APP role: the platform write path works (unit of work: audit + outbox; PHASE_01: org insert with
#      tree trigger + history), every attempt to
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

expect_refused() {  # name role sql rule - refused by a DB guard naming <rule> (not by a missing privilege)
  if as_role "$2" "$3"; then
    record "$1" FAIL "statement was ALLOWED"
  elif printf '%s' "$ERR" | grep -q -e "$4"; then
    record "$1" PASS "$4"
  else
    record "$1" FAIL "failed for another reason: $ERR"
  fi
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
    # 01.6: the event catalogue refuses unknown types; ALEEKHAN_ENV test/dev accept only the synthetic namespace
    uow.emit(event_type='platform.synthetic.roles_checked', aggregate_type='platform.synthetic',
             aggregate_id='roles-check', aggregate_version=1, payload={'note': 'synthetic'})
" >/dev/null 2>&1
); then record "app: unit of work (audit + outbox) via Django" PASS; else record "app: unit of work (audit + outbox) via Django" FAIL; fi
if (cd "$ROOT/backend" && PGDATABASE="$DB" PGOPTIONS="-c role=$APP" ALEEKHAN_ENV=test "$PYTHON" manage.py outbox_status --json >/dev/null 2>&1); then
  record "app: manage.py outbox_status" PASS
else
  record "app: manage.py outbox_status" FAIL
fi

# PHASE_01 / 01.3: the app role can verify the audit hash chain and record the integrity run
if (
  cd "$ROOT/backend" && PGDATABASE="$DB" PGOPTIONS="-c role=$APP" ALEEKHAN_ENV=test "$PYTHON" manage.py shell -c "
import sys
from platform_core.engine.audit_chain import verify_chain
sys.exit(0 if verify_chain().status == 'OK' else 1)
" >/dev/null 2>&1
); then record "app: audit hash chain verified + integrity run recorded (01.3)" PASS; else record "app: audit hash chain verified + integrity run recorded (01.3)" FAIL; fi

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

echo "== app role: PHASE_01 tables (01.2)"
SYN_NAME="convert_from(decode('d988d8a7d8add8af20d8b3d8a7d8aed8aadaafdb8c2028d985d8addb8cd8b720d8a2d8b2d985d8a7db8cd8b4db8c20e2809420d8afd8a7d8afd98720d8b3d8a7d8aed8aadaafdb8c29', 'hex'), 'UTF8')"
expect_ok "app: INSERT synthetic org unit (tree trigger reads parameter; history via SECURITY DEFINER)" "$APP"   "INSERT INTO platform_org_unit (id, code, name_fa, unit_type_code, provenance) VALUES (gen_random_uuid(), 'rc_unit', $SYN_NAME, 'COMPANY', 'SEED_SYNTHETIC')"
expect_ok "app: SELECT permission catalogue" "$APP" "SELECT count(*) FROM platform_permission"
expect_denied "app: INSERT permission (catalogue is migration-only)" "$APP" "INSERT INTO platform_permission (action, module, description_fa, mfa_step_up, business_approval, maker_checker, matrix_version, decision_id) VALUES ('platform.rc.probe', 'rc', 'x', false, false, false, '1.0', 'DEC-049')"
expect_denied "app: UPDATE permission flags" "$APP" "UPDATE platform_permission SET business_approval = false"
expect_denied "app: INSERT upload type" "$APP" "INSERT INTO platform_upload_type (extension, media_type, label_fa, content_check, decision_id) VALUES ('rcx', 'application/x-rc', 'x', 'PDF', 'DEC-053')"
expect_denied "app: UPDATE protected job type" "$APP" "UPDATE platform_job_definition SET protected = false"
expect_denied "app: DELETE user" "$APP" "DELETE FROM platform_user"
expect_denied "app: DELETE role assignment" "$APP" "DELETE FROM platform_role_assignment"
expect_denied "app: DELETE org unit" "$APP" "DELETE FROM platform_org_unit"
expect_denied "app: DELETE document revision" "$APP" "DELETE FROM platform_document_revision"
expect_denied "app: UPDATE password history" "$APP" "UPDATE platform_password_history SET password_hash = password_hash"
expect_denied "app: DELETE password history" "$APP" "DELETE FROM platform_password_history"
expect_denied "app: UPDATE login attempt" "$APP" "UPDATE platform_login_attempt SET outcome = 'OK'"
expect_denied "app: INSERT org unit history directly" "$APP" "INSERT INTO platform_org_unit_history (unit_id, unit_row_version, valid_from, code, name_fa, unit_type_code, status) SELECT id, 99, now(), code, name_fa, unit_type_code, status FROM platform_org_unit"
expect_denied "app: UPDATE org unit history" "$APP" "UPDATE platform_org_unit_history SET valid_to = now()"
expect_denied "app: DISABLE TECHNICAL/BA guard trigger" "$APP" "ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard"
expect_denied "app: DISABLE org tree trigger" "$APP" "ALTER TABLE platform_org_unit DISABLE TRIGGER trg_org_unit_tree_guard"
expect_denied "app: DROP exclusion constraint" "$APP" "ALTER TABLE platform_position_assignment DROP CONSTRAINT ex_position_assignment_one_primary"
expect_denied "app: TRUNCATE login attempts" "$APP" "TRUNCATE platform_login_attempt"
hist="$(admin -d "$DB" -c "SELECT count(*) FROM platform_org_unit_history h JOIN platform_org_unit u ON u.id = h.unit_id WHERE u.code = 'rc_unit'")"
if [ "$hist" = "1" ]; then record "history row written by trigger for the app role's insert" PASS; else record "history row written by trigger for the app role's insert" FAIL "found $hist"; fi

echo "== app role: PHASE_02 tables (02.2)"
expect_ok "app: SELECT serial counter" "$APP" "SELECT next_value FROM identity_serial_counter"
expect_ok "app: UPDATE serial counter (allocation step)" "$APP" "UPDATE identity_serial_counter SET next_value = next_value WHERE false"
expect_ok "app: INSERT external reference type (steward-extensible, DEC-058)" "$APP" "INSERT INTO identity_external_ref_type (key, label_fa, status, decision_id, provenance) SELECT 'rc_probe_type', 'x', 'ACTIVE', '', 'SYS' WHERE false"
expect_denied "app: INSERT serial counter (seed is migration-only)" "$APP" "INSERT INTO identity_serial_counter (id, namespace_key, start_value, next_value, legacy_max_exclusive, number_pattern, decision_id) SELECT gen_random_uuid(), 'factory_serial', 1, 1, 0, '^[1-9][0-9]*\$', 'DEC-006' WHERE false"
expect_denied "app: DELETE serial counter" "$APP" "DELETE FROM identity_serial_counter"
expect_denied "app: DELETE serial" "$APP" "DELETE FROM identity_serial"
expect_denied "app: UPDATE serial snapshot" "$APP" "UPDATE identity_serial_snapshot SET snapshot = snapshot"
expect_denied "app: DELETE serial snapshot" "$APP" "DELETE FROM identity_serial_snapshot"
expect_denied "app: UPDATE order version" "$APP" "UPDATE commercial_customer_order_version SET image = image"
expect_denied "app: DELETE order line" "$APP" "DELETE FROM commercial_customer_order_line"
expect_denied "app: DELETE product code" "$APP" "DELETE FROM identity_product_code"
expect_denied "app: INSERT unit of measure (catalogue)" "$APP" "INSERT INTO identity_unit_of_measure (code, label_fa, decision_id, provenance) SELECT 'RC', 'x', 'DEC-058', 'SYS' WHERE false"
expect_denied "app: INSERT order type (catalogue)" "$APP" "INSERT INTO commercial_order_type (code, label_fa, sort_order, status, decision_id, provenance) SELECT 'rc_probe', 'x', 1, 'ACTIVE', 'DEC-058', 'SYS' WHERE false"
expect_denied "app: DISABLE gapless counter trigger" "$APP" "ALTER TABLE identity_serial_counter DISABLE TRIGGER trg_identity_serial_counter_gapless"
expect_denied "app: DISABLE serial guard trigger" "$APP" "ALTER TABLE identity_serial DISABLE TRIGGER trg_identity_serial_guard"
# PHASE_02 / 02.4 (migration 0025): technical numbers CU-/SO-/CR-<jalali year>-<n> - the app draws numbers
# (upsert +1), never resets, rewinds, deletes or truncates a counter (guard trigger + grants.sql)
NUMBER_UPSERT="INSERT INTO platform_number_counter AS c (kind, jalali_year, last_value) VALUES ('order', 1999, 1) ON CONFLICT (kind, jalali_year) DO UPDATE SET last_value = c.last_value + 1"
expect_ok "app: draw a technical number (insert year row)" "$APP" "$NUMBER_UPSERT"
expect_ok "app: draw the next technical number (+1)" "$APP" "$NUMBER_UPSERT"
expect_refused "app: reset a number counter" "$APP" "UPDATE platform_number_counter SET last_value = 1" ck_number_counter_forward_only
expect_refused "app: move a number counter by more than one" "$APP" "UPDATE platform_number_counter SET last_value = last_value + 5" ck_number_counter_forward_only
expect_refused "app: insert a counter row above 1" "$APP" "INSERT INTO platform_number_counter (kind, jalali_year, last_value) VALUES ('customer', 1998, 500)" ck_number_counter_starts_at_one
expect_denied "app: DELETE number counter" "$APP" "DELETE FROM platform_number_counter"
expect_denied "app: TRUNCATE number counter" "$APP" "TRUNCATE platform_number_counter"
expect_denied "app: DISABLE number counter guard" "$APP" "ALTER TABLE platform_number_counter DISABLE TRIGGER trg_platform_number_counter_guard"
for seq in identity_customer_no_seq commercial_order_no_seq commercial_change_request_no_seq; do
  gone="$(admin -d "$DB" -c "SELECT count(*) FROM pg_class WHERE relkind = 'S' AND relname = '$seq'")"
  if [ "$gone" = "0" ]; then record "0023 sequence $seq replaced by the counter (0025)" PASS; else record "0023 sequence $seq replaced by the counter (0025)" FAIL "still present"; fi
done
expect_denied "app: DISABLE order guard trigger" "$APP" "ALTER TABLE commercial_customer_order DISABLE TRIGGER trg_commercial_customer_order_guard"
seeded="$(admin -d "$DB" -c "SELECT start_value || '/' || next_value FROM identity_serial_counter WHERE namespace_key = 'factory_serial'")"
if [ "$seeded" = "63001/63001" ]; then record "serial counter seeded at 63001 (DEC-006)" PASS; else record "serial counter seeded at 63001 (DEC-006)" FAIL "found $seeded"; fi

echo "== readonly role"
expect_ok "ro: SELECT audit" "$RO" "SELECT count(*) FROM platform_audit_event"
expect_ok "ro: SELECT outbox" "$RO" "SELECT count(*) FROM platform_outbox_event"
expect_denied "ro: INSERT audit" "$RO" "$AUDIT_INSERT"
expect_denied "ro: UPDATE integration source" "$RO" "UPDATE platform_integration_source SET name_fa = name_fa"
expect_denied "ro: DELETE outbox" "$RO" "DELETE FROM platform_outbox_event"
expect_ok "ro: SELECT role grants" "$RO" "SELECT count(*) FROM platform_role_permission"
expect_denied "ro: UPDATE user" "$RO" "UPDATE platform_user SET display_name = display_name"

echo "== audit trigger still enabled and rows intact"
disabled="$(admin -d "$DB" -c "SELECT count(*) FROM pg_trigger g JOIN pg_class c ON c.oid = g.tgrelid WHERE NOT g.tgisinternal AND (c.relname LIKE 'platform\_%' OR c.relname LIKE 'identity\_%' OR c.relname LIKE 'commercial\_%') AND g.tgenabled <> 'O'")"
if [ "$disabled" = "0" ]; then record "all platform triggers enabled" PASS; else record "all platform triggers enabled" FAIL "$disabled disabled"; fi
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
