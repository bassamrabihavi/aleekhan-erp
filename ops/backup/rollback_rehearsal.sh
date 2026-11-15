#!/usr/bin/env bash
# Rollback rehearsal (PHASE_01 / 01.7): migrate throw-away databases WITH synthetic data down to the PHASE_01
# DB baseline (platform_core 0010 = 01.2 schema + seed) and forward again. See docs/ops/ROLLBACK.md section 4.
#
# Reference schemas: fresh `migrate platform_core 0010`, fresh `0011`, fresh head.
#
# Scenario A - data, no housekeeping job runs yet (ops/backup/drill_seed.py with DRILL_SKIP_JOB_RUNS=1):
#   migrate platform_core 0010 must succeed; schema == fresh 0010; business rows kept; DISCARDED events back to
#   DEAD_LETTER (0018 reverse); owner_admin back to matrix 1.0; then forward to head: migrate --check clean,
#   schema == fresh head, owner grants restored, the application reads the DB.
# Scenario B - data AND housekeeping job runs (the normal state of a running system):
#   the reverse of 0011 refuses BY DESIGN (PROTECT FK: job runs reference the housekeeping job types; audit
#   integrity runs are append-only evidence) - the rollback stops at 0011 with a clear error, the DB is left
#   at a consistent migration state (schema == fresh 0011) and forward to head works again.
# PHASE_02 / 02.7 - rollback from head (0028) through 0027 to the PHASE_01 baseline 0018 and forward again:
# Scenario C - PHASE_01 data, PHASE_02 schema and seed but no PHASE_02 business rows (DRILL_SKIP_PHASE02=1):
#   migrate platform_core 0018 must succeed; schema == fresh 0018; PHASE_01 rows kept; no identity_* /
#   commercial_* table or PHASE_02 function left; forward to head: migrate --check clean, schema == fresh head.
# Scenario D - PHASE_02 data (orders, serials, snapshots, versions, numbers, Planning import, failed apply):
#   the reverse of 0022 refuses BY DESIGN (PROTECT: the PHASE_02 roles are assigned - rolling back a used
#   matrix needs a compensation plan, docs/ops/ROLLBACK.md); 0023-0028 are reversed first and the DB stops at
#   a consistent state (0022 applied); rows kept; forward to head is clean and ops/backup/drill_verify_phase02.py
#   passes (gapless serials, versions, snapshots, number counters re-positioned by 0025, import batches).
# Scenarios A and B seed without PHASE_02 rows (DRILL_SKIP_PHASE02=1): they rehearse the PHASE_01 path.
#
# Database names must start with test_ (throw-away only; the seed additionally refuses anything that is not
# test_aleekhan_drill_*). Connection: libpq env; the password is never printed. All databases are dropped at
# the end (trap); the report is written to <output-dir>/rehearsal_report.json.
#
# Usage: ops/backup/rollback_rehearsal.sh <output-dir>
# Env:   PG_BIN, PYTHON (default repo .venv python), REHEARSAL_PREFIX (default test_aleekhan_drill_rb),
#        REHEARSAL_ROWS (default 50), ALEEKHAN_MACHINE (label in the report)
set -uo pipefail

OUT="${1:?usage: rollback_rehearsal.sh <output-dir>}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PSQL="${PG_BIN:+$PG_BIN/}psql"
PG_DUMP="${PG_BIN:+$PG_BIN/}pg_dump"
PREFIX="${REHEARSAL_PREFIX:-test_aleekhan_drill_rb}"
ROWS="${REHEARSAL_ROWS:-50}"
T10="0010_seed_phase01_catalogue"
T11="0011_phase01_engine"
T18="0018_outbox_discard_and_orphan_job"
T22="0022_dec057_matrix_v20"
case "$PREFIX" in test_aleekhan_drill*) ;; *) echo "REHEARSAL_PREFIX must start with test_aleekhan_drill" >&2; exit 2 ;; esac
case "$PREFIX$ROWS" in *[!a-z0-9_]*) echo "REHEARSAL_PREFIX/REHEARSAL_ROWS: [a-z0-9_] only" >&2; exit 2 ;; esac
DBS=("${PREFIX}_ref10" "${PREFIX}_ref11" "${PREFIX}_ref18" "${PREFIX}_ref22" "${PREFIX}_head"
     "${PREFIX}_a" "${PREFIX}_b" "${PREFIX}_c" "${PREFIX}_d")
if [ -z "${PYTHON:-}" ]; then
  if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then PYTHON="$ROOT/.venv/Scripts/python.exe"; else PYTHON="$ROOT/.venv/bin/python"; fi
fi
for v in PGHOST PGPORT PGUSER; do
  if [ -z "${!v:-}" ]; then echo "missing libpq env $v (load the test DB env first)" >&2; exit 2; fi
done
export ALEEKHAN_ENV=test
unset DATABASE_URL || true

STATUS="FAIL"
CHECKS=()
FAILS=0
admin() { "$PSQL" -X -v ON_ERROR_STOP=1 -qAt "$@" | tr -d '\015'; }
check() {
  [ "$2" = PASS ] || FAILS=$((FAILS + 1))
  printf '%-4s %s%s\n' "$2" "$1" "${3:+  ($3)}"
  CHECKS+=("{\"check\": \"$1\", \"result\": \"$2\"}")
}
cleanup() {
  echo "== cleanup: drop ${DBS[*]}"
  for d in "${DBS[@]}"; do
    admin -d postgres -c "DROP DATABASE IF EXISTS $d WITH (FORCE)" >/dev/null 2>&1 || echo "WARN: drop $d failed" >&2
  done
}
trap cleanup EXIT
manage() { (cd "$ROOT/backend" && PGDATABASE="$1" "$PYTHON" manage.py "${@:2}"); }
dump_schema() {  # db file ; drop pg_dump's random \restrict token so dumps compare
  "$PG_DUMP" --schema-only --no-owner --no-privileges -d "$1" | grep -v -E '^\\(un)?restrict ' > "$2"
}
fresh() {
  admin -d postgres -c "DROP DATABASE IF EXISTS $1 WITH (FORCE)" >/dev/null 2>&1
  admin -d postgres -c "CREATE DATABASE $1 ENCODING 'UTF8' TEMPLATE template0" >/dev/null
}
counts() {
  admin -d "$1" -c "SELECT 'users=' || (SELECT count(*) FROM platform_user) || ' units=' || (SELECT count(*) FROM platform_org_unit) || ' tasks=' || (SELECT count(*) FROM platform_work_task) || ' approvals=' || (SELECT count(*) FROM platform_approval_request) || ' revisions=' || (SELECT count(*) FROM platform_document_revision) || ' audit=' || (SELECT count(*) FROM platform_audit_event) || ' outbox=' || (SELECT count(*) FROM platform_outbox_event)"
}
owner_state() {
  admin -d "$1" -c "SELECT matrix_version || '/' || (SELECT count(*) FROM platform_role_permission rp WHERE rp.role_id = r.id) FROM platform_role r WHERE code = 'owner_admin'"
}
seed() {  # db skip_job_runs(0|1) [skip_phase02(0|1), default 1 = the PHASE_01 scenarios A/B]
  manage "$1" migrate --noinput >/dev/null || return 1
  (cd "$ROOT" && PGDATABASE="$1" DRILL_SKIP_JOB_RUNS="$2" DRILL_SKIP_PHASE02="${3:-1}" "$PYTHON" ops/backup/drill_seed.py "$ROWS")
}
counts02() {
  admin -d "$1" -c "SELECT 'customers=' || (SELECT count(*) FROM identity_customer) || ' orders=' || (SELECT count(*) FROM commercial_customer_order) || ' lines=' || (SELECT count(*) FROM commercial_customer_order_line) || ' serials=' || (SELECT count(*) FROM identity_serial) || ' snapshots=' || (SELECT count(*) FROM identity_serial_snapshot) || ' versions=' || (SELECT count(*) FROM commercial_customer_order_version) || ' codes=' || (SELECT count(*) FROM identity_product_code) || ' batches=' || (SELECT count(*) FROM platform_import_batch) || ' conflicts=' || (SELECT count(*) FROM platform_conflict_item) || ' serial_next=' || (SELECT string_agg(next_value::text, ',') FROM identity_serial_counter)"
}
forward_checks() {  # db label
  if manage "$1" migrate --noinput > "$OUT/forward_$2.log" 2>&1 && manage "$1" migrate --check --noinput >/dev/null 2>&1; then
    check "$2: migrate forward to head again, migrate --check clean" PASS
  else
    check "$2: migrate forward to head again, migrate --check clean" FAIL "see forward_$2.log"
  fi
  dump_schema "$1" "$OUT/schema_head_$2.sql"
  if diff -u "$OUT/schema_head_fresh.sql" "$OUT/schema_head_$2.sql" > "$OUT/schema_diff_head_$2.txt"; then
    check "$2: schema after forward == fresh head schema" PASS
  else
    check "$2: schema after forward == fresh head schema" FAIL "see schema_diff_head_$2.txt"
  fi
  if manage "$1" outbox_status --json >/dev/null 2>&1 && manage "$1" job_status --json >/dev/null 2>&1; then
    check "$2: application reads the rolled-forward DB (outbox_status, job_status)" PASS
  else
    check "$2: application reads the rolled-forward DB" FAIL
  fi
}

STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SERVER="$(admin -d postgres -c 'SHOW server_version')"
echo "== server $SERVER | machine ${ALEEKHAN_MACHINE:-unnamed} | rows $ROWS"

echo "== [0] reference schemas: fresh 0010, fresh 0011, fresh head"
fresh "${PREFIX}_ref10" && manage "${PREFIX}_ref10" migrate platform_core "$T10" --noinput >/dev/null || { echo "FAIL: ref 0010" >&2; exit 1; }
dump_schema "${PREFIX}_ref10" "$OUT/schema_ref_0010.sql"
fresh "${PREFIX}_ref11" && manage "${PREFIX}_ref11" migrate platform_core "$T11" --noinput >/dev/null || { echo "FAIL: ref 0011" >&2; exit 1; }
dump_schema "${PREFIX}_ref11" "$OUT/schema_ref_0011.sql"
fresh "${PREFIX}_ref18" && manage "${PREFIX}_ref18" migrate platform_core "$T18" --noinput >/dev/null || { echo "FAIL: ref 0018" >&2; exit 1; }
dump_schema "${PREFIX}_ref18" "$OUT/schema_ref_0018.sql"
fresh "${PREFIX}_ref22" && manage "${PREFIX}_ref22" migrate platform_core "$T22" --noinput >/dev/null || { echo "FAIL: ref 0022" >&2; exit 1; }
dump_schema "${PREFIX}_ref22" "$OUT/schema_ref_0022.sql"
fresh "${PREFIX}_head" && manage "${PREFIX}_head" migrate --noinput >/dev/null || { echo "FAIL: ref head" >&2; exit 1; }
dump_schema "${PREFIX}_head" "$OUT/schema_head_fresh.sql"

# ------------------------------------------------------------------------------------------- scenario A
A="${PREFIX}_a"
echo "== [A] data without housekeeping job runs: migrate to head, seed, roll back to 0010, forward"
fresh "$A" && seed "$A" 1 || { echo "FAIL: scenario A seed" >&2; exit 1; }
A_BEFORE="$(counts "$A")"; A_OWNER="$(owner_state "$A")"
A_DISC="$(admin -d "$A" -c "SELECT count(*) FROM platform_outbox_event WHERE delivery_status = 'DISCARDED'")"
echo "A before: $A_BEFORE | owner $A_OWNER | discarded $A_DISC"
if manage "$A" migrate platform_core "$T10" --noinput > "$OUT/rollback_A.log" 2>&1; then
  check "A: migrate down 0018 -> 0010 with synthetic data" PASS
else
  check "A: migrate down 0018 -> 0010 with synthetic data" FAIL "see rollback_A.log"
fi
dump_schema "$A" "$OUT/schema_A_0010.sql"
if diff -u "$OUT/schema_ref_0010.sql" "$OUT/schema_A_0010.sql" > "$OUT/schema_diff_A_0010.txt"; then
  check "A: schema after rollback == fresh 0010 schema" PASS "$(wc -l < "$OUT/schema_ref_0010.sql" | tr -d ' ') lines"
else
  check "A: schema after rollback == fresh 0010 schema" FAIL "see schema_diff_A_0010.txt"
fi
A_AFTER="$(counts "$A")"
if [ "$A_AFTER" = "$A_BEFORE" ]; then check "A: business rows kept by the rollback ($A_AFTER)" PASS; else check "A: business rows kept" FAIL "$A_BEFORE -> $A_AFTER"; fi
dl="$(admin -d "$A" -c "SELECT count(*) FROM platform_outbox_event WHERE payload->>'label' = 'synthetic_drill_discarded' AND delivery_status = 'DEAD_LETTER'")"
if [ "$A_DISC" -ge 1 ] && [ "$dl" = "$A_DISC" ]; then check "A: DISCARDED events are DEAD_LETTER again (0018 reverse)" PASS; else check "A: DISCARDED events are DEAD_LETTER again" FAIL "found $dl"; fi
ov="$(admin -d "$A" -c "SELECT matrix_version FROM platform_role WHERE code = 'owner_admin'")"
if [ "$ov" = "1.0" ]; then check "A: owner_admin back to matrix 1.0 (0017/0015/0014 reversed)" PASS; else check "A: owner_admin back to matrix 1.0" FAIL "found $ov"; fi
left="$(admin -d "$A" -c "SELECT count(*) FROM django_migrations WHERE app = 'platform_core' AND name ~ '^001[1-8]_'")"
if [ "$left" = "0" ]; then check "A: migrations 0011-0018 unrecorded" PASS; else check "A: migrations 0011-0018 unrecorded" FAIL "$left left"; fi
forward_checks "$A" A
A_OWNER_FWD="$(owner_state "$A")"
if [ "$A_OWNER_FWD" = "$A_OWNER" ]; then check "A: owner_admin matrix/grants restored by forward ($A_OWNER_FWD)" PASS; else check "A: owner grants restored" FAIL "$A_OWNER -> $A_OWNER_FWD"; fi

# ------------------------------------------------------------------------------------------- scenario B
B="${PREFIX}_b"
echo "== [B] data with housekeeping job runs: the 0011 reverse must refuse (PROTECT), DB stays consistent"
fresh "$B" && seed "$B" 0 || { echo "FAIL: scenario B seed" >&2; exit 1; }
B_BEFORE="$(counts "$B")"
if manage "$B" migrate platform_core "$T10" --noinput > "$OUT/rollback_B.log" 2>&1; then
  check "B: rollback below 0011 is refused while job runs exist" FAIL "it was not refused"
elif grep -q "ProtectedError" "$OUT/rollback_B.log"; then
  check "B: rollback below 0011 is refused while job runs exist (PROTECT, by design)" PASS
else
  check "B: rollback below 0011 is refused while job runs exist" FAIL "unexpected error, see rollback_B.log"
fi
state="$(admin -d "$B" -c "SELECT string_agg(name, ',' ORDER BY name) FROM django_migrations WHERE app = 'platform_core' AND name ~ '^001[1-8]_'")"
if [ "$state" = "$T11" ]; then check "B: stopped at a consistent state (0011 applied, 0012-0018 reversed)" PASS; else check "B: stopped at a consistent state" FAIL "applied: $state"; fi
dump_schema "$B" "$OUT/schema_B_0011.sql"
if diff -u "$OUT/schema_ref_0011.sql" "$OUT/schema_B_0011.sql" > "$OUT/schema_diff_B_0011.txt"; then
  check "B: schema == fresh 0011 schema" PASS
else
  check "B: schema == fresh 0011 schema" FAIL "see schema_diff_B_0011.txt"
fi
B_AFTER="$(counts "$B")"
if [ "$B_AFTER" = "$B_BEFORE" ]; then check "B: business rows kept ($B_AFTER)" PASS; else check "B: business rows kept" FAIL "$B_BEFORE -> $B_AFTER"; fi
forward_checks "$B" B

# ------------------------------------------------------------------------------------------- scenario C
C="${PREFIX}_c"
echo "== [C] PHASE_01 data, no PHASE_02 business rows: roll back head -> 0027 -> 0018, forward"
fresh "$C" && seed "$C" 1 1 || { echo "FAIL: scenario C seed" >&2; exit 1; }
C_BEFORE="$(counts "$C")"
if manage "$C" migrate platform_core 0027_dec057_matrix_v22 --noinput > "$OUT/rollback_C_0027.log" 2>&1 \
   && manage "$C" migrate platform_core "$T18" --noinput > "$OUT/rollback_C.log" 2>&1; then
  check "C: migrate down 0028 -> 0027 -> 0018 (PHASE_02 schema without business rows)" PASS
else
  check "C: migrate down 0028 -> 0027 -> 0018" FAIL "see rollback_C*.log"
fi
dump_schema "$C" "$OUT/schema_C_0018.sql"
if diff -u "$OUT/schema_ref_0018.sql" "$OUT/schema_C_0018.sql" > "$OUT/schema_diff_C_0018.txt"; then
  check "C: schema after rollback == fresh 0018 schema" PASS "$(wc -l < "$OUT/schema_ref_0018.sql" | tr -d ' ') lines"
else
  check "C: schema after rollback == fresh 0018 schema" FAIL "see schema_diff_C_0018.txt"
fi
C_AFTER="$(counts "$C")"
if [ "$C_AFTER" = "$C_BEFORE" ]; then check "C: PHASE_01 rows kept by the rollback ($C_AFTER)" PASS; else check "C: PHASE_01 rows kept" FAIL "$C_BEFORE -> $C_AFTER"; fi
left02="$(admin -d "$C" -c "SELECT (SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename ~ '^(identity|commercial)_') + (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public' AND p.proname ~ '^(identity|commercial|phase02)_')")"
if [ "$left02" = "0" ]; then check "C: no PHASE_02 table or function left at 0018" PASS; else check "C: no PHASE_02 table or function left" FAIL "$left02 left"; fi
forward_checks "$C" C

# ------------------------------------------------------------------------------------------- scenario D
D="${PREFIX}_d"
echo "== [D] PHASE_02 data: the 0022 reverse must refuse (PROTECT), DB stays consistent, forward + invariants"
fresh "$D" && seed "$D" 0 0 || { echo "FAIL: scenario D seed" >&2; exit 1; }
D_BEFORE="$(counts02 "$D")"
echo "D before: $D_BEFORE"
if manage "$D" migrate platform_core "$T18" --noinput > "$OUT/rollback_D.log" 2>&1; then
  check "D: rollback below 0022 is refused while PHASE_02 roles are assigned" FAIL "it was not refused"
elif grep -q -E "IntegrityError|ProtectedError" "$OUT/rollback_D.log" && grep -q "platform_role" "$OUT/rollback_D.log"; then
  check "D: rollback below 0022 is refused while PHASE_02 roles are assigned (PROTECT, by design)" PASS
else
  check "D: rollback below 0022 is refused" FAIL "unexpected error, see rollback_D.log"
fi
state="$(admin -d "$D" -c "SELECT string_agg(name, ',' ORDER BY name) FROM django_migrations WHERE app = 'platform_core' AND name ~ '^00(19|2[0-8])_'")"
if [ "$state" = "0019_phase02_identity_commercial_schema,0020_phase02_db_guards,0021_phase02_seed_catalogue,$T22" ]; then
  check "D: stopped at a consistent state (0022 applied, 0023-0028 reversed)" PASS
else
  check "D: stopped at a consistent state" FAIL "applied: $state"
fi
dump_schema "$D" "$OUT/schema_D_0022.sql"
if diff -u "$OUT/schema_ref_0022.sql" "$OUT/schema_D_0022.sql" > "$OUT/schema_diff_D_0022.txt"; then
  check "D: schema == fresh 0022 schema" PASS
else
  check "D: schema == fresh 0022 schema" FAIL "see schema_diff_D_0022.txt"
fi
D_AFTER="$(counts02 "$D")"
if [ "$D_AFTER" = "$D_BEFORE" ]; then check "D: PHASE_02 rows and serial counter kept ($D_AFTER)" PASS; else check "D: PHASE_02 rows kept" FAIL "$D_BEFORE -> $D_AFTER"; fi
forward_checks "$D" D
if (cd "$ROOT" && PGDATABASE="$D" "$PYTHON" ops/backup/drill_verify_phase02.py) > "$OUT/phase02_D_forward.json" 2>&1; then
  check "D: PHASE_02 invariants after forward (gapless serials, versions, snapshots, number counters, imports)" PASS
else
  check "D: PHASE_02 invariants after forward" FAIL "see phase02_D_forward.json"
fi

[ "$FAILS" -eq 0 ] && STATUS="PASS"
FINISHED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
{
  printf '{\n  "rehearsal": "rollback-to-0010 (PHASE_01), 0028-0027-0018 (PHASE_02)",\n  "status": "%s",\n  "started_at": "%s",\n  "finished_at": "%s",\n' "$STATUS" "$STARTED" "$FINISHED"
  printf '  "machine": "%s",\n  "commit": "%s",\n  "server_version": "%s",\n  "synthetic_rows": %s,\n' "${ALEEKHAN_MACHINE:-unnamed}" "$COMMIT" "$SERVER" "$ROWS"
  printf '  "scenario_a_counts": "%s",\n  "scenario_b_counts": "%s",\n' "$A_BEFORE" "$B_BEFORE"
  printf '  "scenario_c_counts": "%s",\n  "scenario_d_counts": "%s",\n' "$C_BEFORE" "$D_BEFORE"
  printf '  "checks": [\n'
  for i in "${!CHECKS[@]}"; do sep=","; [ "$i" -eq $((${#CHECKS[@]} - 1)) ] && sep=""; printf '    %s%s\n' "${CHECKS[$i]}" "$sep"; done
  printf '  ]\n}\n'
} > "$OUT/rehearsal_report.json"
echo "== rehearsal $STATUS (failures: $FAILS)"
[ "$STATUS" = PASS ]
