#!/usr/bin/env bash
# Backup / restore drill (PHASE_00 / 00.7; DEC-004 RPO 1 h / RTO 4 h; DEC-045 A: first drill in a local test
# environment). See docs/ops/BACKUP_RESTORE.md.
#
#   1. create throw-away source DB, migrate, seed SYNTHETIC labelled rows (ops/backup/drill_seed.py)
#   2. fingerprint: row count + md5 of every public table, applied migrations, trigger states
#   3. pg_dump -Fc  -> sha256 + size of the dump
#   4. drop the source DB (simulated loss)
#   5. verify the dump sha256 again, pg_restore --single-transaction --exit-on-error into a NEW database
#   6. verify: fingerprint identical, `migrate --check` clean, audit append-only trigger still enforced
#   7. drop everything (trap), write drill_report.json + drill_report.md into <output-dir>
#
# Connection: libpq env (PGHOST/PGPORT/PGUSER/PGPASSWORD or ~/.pgpass); the password is never printed. The
# dump holds only synthetic rows and is written to a temporary work dir that is deleted at the end (it is
# never placed in the repository); only its sha256 and size are reported.
#
# Usage: ops/backup/drill.sh <output-dir>
# Env:   PG_BIN, PYTHON (default repo .venv python), DRILL_ROWS (default 500), DRILL_PREFIX (default
#        aleekhan_drill), ALEEKHAN_MACHINE (label in the report)
set -uo pipefail

OUT="${1:?usage: drill.sh <output-dir>}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PSQL="${PG_BIN:+$PG_BIN/}psql"
PG_DUMP="${PG_BIN:+$PG_BIN/}pg_dump"
PG_RESTORE="${PG_BIN:+$PG_BIN/}pg_restore"
PREFIX="${DRILL_PREFIX:-aleekhan_drill}"
ROWS="${DRILL_ROWS:-500}"
case "$PREFIX" in aleekhan_drill*|test_aleekhan_drill*) ;; *) echo "DRILL_PREFIX must start with aleekhan_drill or test_aleekhan_drill" >&2; exit 2 ;; esac
case "$PREFIX$ROWS" in *[!a-z0-9_]*) echo "DRILL_PREFIX/DRILL_ROWS: [a-z0-9_] only" >&2; exit 2 ;; esac
SRC="${PREFIX}_src"
DST="${PREFIX}_restored"
if [ -z "${PYTHON:-}" ]; then
  if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then PYTHON="$ROOT/.venv/Scripts/python.exe"; else PYTHON="$ROOT/.venv/bin/python"; fi
fi
for v in PGHOST PGPORT PGUSER; do
  if [ -z "${!v:-}" ]; then echo "missing libpq env $v (load the test DB env first)" >&2; exit 2; fi
done
export ALEEKHAN_ENV=test
unset DATABASE_URL || true

WORK="$(mktemp -d)"
DUMP="$WORK/drill.dump"
STATUS="FAIL"
CHECKS=()
FAILS=0

# psql on Windows writes CRLF; strip CR so values compare equal (pipefail keeps psql's exit status)
admin() { "$PSQL" -X -v ON_ERROR_STOP=1 -qAt "$@" | tr -d '\015'; }
ms() { date +%s%3N; }
check() {  # name PASS|FAIL detail
  [ "$2" = PASS ] || FAILS=$((FAILS + 1))
  printf '%-4s %s%s\n' "$2" "$1" "${3:+  ($3)}"
  CHECKS+=("{\"check\": \"$1\", \"result\": \"$2\"}")
}
cleanup() {
  echo "== cleanup: drop $SRC, $DST; delete work dir"
  for d in "$SRC" "$DST"; do
    admin -d postgres -c "DROP DATABASE IF EXISTS $d WITH (FORCE)" >/dev/null 2>&1 || echo "WARN: drop $d failed" >&2
  done
  rm -rf "$WORK"
}
trap cleanup EXIT

fingerprint() {  # db -> stdout lines "table rows md5"; returns non-zero on any query error
  local db="$1" t tables
  tables="$(admin -d "$db" -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")" || return 1
  [ -n "$tables" ] || return 1
  for t in $tables; do
    admin -d "$db" -c "SELECT '$t', count(*), md5(coalesce(string_agg(x::text, E'\n' ORDER BY x::text), '')) FROM public.\"$t\" x" | tr '|' ' '
    [ "${PIPESTATUS[0]}" -eq 0 ] || return 1
  done
  echo "triggers $(admin -d "$db" -c "SELECT string_agg(c.relname || '.' || t.tgname || '=' || t.tgenabled::text, ',' ORDER BY c.relname, t.tgname) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid WHERE NOT t.tgisinternal")"
  echo "functions $(admin -d "$db" -c "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public'")"
}
manage() { (cd "$ROOT/backend" && PGDATABASE="$1" "$PYTHON" manage.py "${@:2}"); }

T0="$(ms)"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SERVER="$(admin -d postgres -c 'SHOW server_version')"
DUMP_VERSION="$("$PG_DUMP" --version)"
echo "== server $SERVER | $DUMP_VERSION | machine ${ALEEKHAN_MACHINE:-unnamed} | rows $ROWS"

echo "== [1] create + migrate + seed $SRC"
admin -d postgres -c "DROP DATABASE IF EXISTS $SRC WITH (FORCE)" >/dev/null 2>&1
admin -d postgres -c "DROP DATABASE IF EXISTS $DST WITH (FORCE)" >/dev/null 2>&1
admin -d postgres -c "CREATE DATABASE $SRC ENCODING 'UTF8' TEMPLATE template0" >/dev/null || exit 1
manage "$SRC" migrate --noinput >/dev/null || { echo "FAIL: migrate" >&2; exit 1; }
(cd "$ROOT" && PGDATABASE="$SRC" "$PYTHON" ops/backup/drill_seed.py "$ROWS") || { echo "FAIL: seed" >&2; exit 1; }

echo "== [2] fingerprint before"
fingerprint "$SRC" > "$OUT/fingerprint_before.txt" || { echo "FAIL: fingerprint of $SRC" >&2; exit 1; }
cat "$OUT/fingerprint_before.txt"
TABLES="$(grep -c -v -E '^(triggers|functions) ' "$OUT/fingerprint_before.txt" | tr -d ' ')"
SRC_SIZE="$(admin -d postgres -c "SELECT pg_database_size('$SRC')")"
MIGRATIONS_BEFORE="$(admin -d "$SRC" -c "SELECT count(*) FROM django_migrations")"

echo "== [3] pg_dump -Fc"
T1="$(ms)"
"$PG_DUMP" -Fc -Z 6 -d "$SRC" -f "$DUMP" || { echo "FAIL: pg_dump" >&2; exit 1; }
T2="$(ms)"
SHA_DUMP="$(sha256sum "$DUMP" | cut -d' ' -f1)"
DUMP_BYTES="$(wc -c < "$DUMP" | tr -d ' ')"
echo "dump sha256=$SHA_DUMP bytes=$DUMP_BYTES"
"$PG_RESTORE" --list "$DUMP" > "$WORK/toc.txt" || { echo "FAIL: dump TOC unreadable" >&2; exit 1; }
TOC_ENTRIES="$(grep -c -v '^;' "$WORK/toc.txt" | tr -d ' ')"

echo "== [4] drop source database (simulated loss)"
admin -d postgres -c "DROP DATABASE $SRC WITH (FORCE)" >/dev/null || exit 1
gone="$(admin -d postgres -c "SELECT count(*) FROM pg_database WHERE datname = '$SRC'")"
if [ "$gone" = "0" ]; then check "source database dropped before restore" PASS; else check "source database dropped before restore" FAIL; fi

echo "== [5] verify dump checksum, restore into $DST"
SHA_AGAIN="$(sha256sum "$DUMP" | cut -d' ' -f1)"
if [ "$SHA_AGAIN" = "$SHA_DUMP" ]; then check "dump sha256 unchanged before restore" PASS; else check "dump sha256 unchanged before restore" FAIL; fi
T3="$(ms)"
admin -d postgres -c "CREATE DATABASE $DST ENCODING 'UTF8' TEMPLATE template0" >/dev/null || exit 1
if "$PG_RESTORE" --single-transaction --exit-on-error -d "$DST" "$DUMP"; then check "pg_restore --single-transaction --exit-on-error" PASS; else check "pg_restore --single-transaction --exit-on-error" FAIL; fi
T4="$(ms)"

echo "== [6] verify restored database"
if fingerprint "$DST" > "$OUT/fingerprint_after.txt"; then
  check "fingerprint of restored database readable" PASS
else
  check "fingerprint of restored database readable" FAIL
fi
# 11 = public tables after migrations 0001-0006 (django_migrations + 10 platform tables)
if [ "$TABLES" -ge 11 ]; then check "fingerprint covers all public tables ($TABLES)" PASS; else check "fingerprint covers all public tables" FAIL "only $TABLES"; fi
if diff -u "$OUT/fingerprint_before.txt" "$OUT/fingerprint_after.txt" > "$OUT/fingerprint_diff.txt"; then
  check "row counts + table checksums + triggers + functions identical" PASS "$TABLES tables"
else
  check "row counts + table checksums + triggers + functions identical" FAIL "see fingerprint_diff.txt"
fi
MIGRATIONS_AFTER="$(admin -d "$DST" -c "SELECT count(*) FROM django_migrations")"
if [ "$MIGRATIONS_AFTER" = "$MIGRATIONS_BEFORE" ] && manage "$DST" migrate --check --noinput >/dev/null 2>&1; then
  check "migrations state: $MIGRATIONS_AFTER applied, migrate --check clean" PASS
else
  check "migrations state: migrate --check clean" FAIL "before=$MIGRATIONS_BEFORE after=$MIGRATIONS_AFTER"
fi
err="$(admin -d "$DST" -c "DELETE FROM platform_audit_event" 2>&1 >/dev/null || true)"
if printf '%s' "$err" | grep -q "append-only"; then check "audit append-only trigger enforced after restore" PASS; else check "audit append-only trigger enforced after restore" FAIL; fi
labelled="$(admin -d "$DST" -c "SELECT count(*) FROM platform_outbox_event WHERE payload->>'label' = 'synthetic_drill'")"
if [ "$labelled" = "$ROWS" ]; then check "synthetic labelled outbox rows restored ($labelled)" PASS; else check "synthetic labelled outbox rows restored" FAIL "found $labelled"; fi
if manage "$DST" outbox_status --json > "$WORK/outbox.json" 2>/dev/null; then check "application reads restored DB (outbox_status)" PASS; else check "application reads restored DB (outbox_status)" FAIL; fi
# PHASE_01 / 01.7: the PHASE_01 tables, migrations 0011-0018 and the audit hash chain survive dump + restore
p01="$(admin -d "$DST" -c "SELECT (SELECT count(*) FROM platform_user WHERE username LIKE 'syn.drill.%') * (SELECT count(*) FROM platform_org_unit WHERE code LIKE 'syn_drill_%') * (SELECT count(*) FROM platform_role_assignment WHERE reason = 'synthetic_drill') * (SELECT count(*) FROM platform_work_task) * (SELECT count(*) FROM platform_approval_request) * (SELECT count(*) FROM platform_document_revision) * (SELECT count(*) FROM platform_job_run WHERE state = 'SUCCEEDED') * (SELECT count(*) FROM platform_outbox_event WHERE delivery_status = 'DISCARDED')")"
if [ -n "$p01" ] && [ "$p01" -gt 0 ]; then check "PHASE_01 rows restored (user, org unit, role assignment, task, approval, document revision, job runs, DISCARDED event)" PASS; else check "PHASE_01 rows restored" FAIL "product=$p01"; fi
m01="$(admin -d "$DST" -c "SELECT count(*) FROM django_migrations WHERE app = 'platform_core' AND name ~ '^001[1-8]_'")"
if [ "$m01" = "8" ]; then check "migrations 0011-0018 recorded in the restored DB" PASS; else check "migrations 0011-0018 recorded in the restored DB" FAIL "found $m01"; fi
if manage "$DST" shell -c "import sys; from platform_core.engine import audit_chain as ac; r = ac.check_chain(); sys.exit(0 if r.first_broken is None and r.checked > 0 else 1)" >/dev/null 2>&1; then check "audit hash chain verifies after restore" PASS; else check "audit hash chain verifies after restore" FAIL; fi
if manage "$DST" job_status --json > "$WORK/jobs.json" 2>/dev/null; then check "application reads restored DB (job_status)" PASS; else check "application reads restored DB (job_status)" FAIL; fi
T5="$(ms)"

[ "$FAILS" -eq 0 ] && STATUS="PASS"
DUMP_MS=$((T2 - T1)); RESTORE_MS=$((T4 - T3)); VERIFY_MS=$((T5 - T4)); TOTAL_MS=$((T5 - T0))
RECOVERY_MS=$((T5 - T3))
FINISHED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
DIRTY="$(git -C "$ROOT" status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')"

{
  printf '{\n'
  printf '  "drill": "backup-restore",\n  "status": "%s",\n  "started_at": "%s",\n  "finished_at": "%s",\n' "$STATUS" "$STARTED" "$FINISHED"
  printf '  "machine": "%s",\n  "commit": "%s",\n  "worktree_modified_files": %s,\n' "${ALEEKHAN_MACHINE:-unnamed}" "$COMMIT" "$DIRTY"
  printf '  "server_version": "%s",\n  "pg_dump": "%s",\n  "synthetic_rows": %s,\n' "$SERVER" "$DUMP_VERSION" "$ROWS"
  printf '  "source_db_bytes": %s,\n  "dump_format": "custom (-Fc -Z 6)",\n  "dump_bytes": %s,\n  "dump_toc_entries": %s,\n' "$SRC_SIZE" "$DUMP_BYTES" "$TOC_ENTRIES"
  printf '  "dump_sha256": "%s",\n  "dump_sha256_verified_before_restore": %s,\n' "$SHA_DUMP" "$([ "$SHA_AGAIN" = "$SHA_DUMP" ] && echo true || echo false)"
  printf '  "timings_ms": {"dump": %s, "restore": %s, "verify": %s, "recovery_restore_plus_verify": %s, "total": %s},\n' "$DUMP_MS" "$RESTORE_MS" "$VERIFY_MS" "$RECOVERY_MS" "$TOTAL_MS"
  printf '  "targets": {"rpo": "1h (DEC-004)", "rto": "4h (DEC-004)", "note": "tiny synthetic dataset; RTO for production size must be re-measured on staging; RPO needs scheduled backups/WAL archiving (docs/ops/BACKUP_RESTORE.md)"},\n'
  printf '  "checks": [\n'
  for i in "${!CHECKS[@]}"; do sep=","; [ "$i" -eq $((${#CHECKS[@]} - 1)) ] && sep=""; printf '    %s%s\n' "${CHECKS[$i]}" "$sep"; done
  printf '  ]\n}\n'
} > "$OUT/drill_report.json"

{
  echo "# Backup / restore drill - $STATUS"
  echo
  echo "Synthetic data only (label \`synthetic_drill\`). Generated by \`ops/backup/drill.sh\`; see docs/ops/BACKUP_RESTORE.md."
  echo
  echo "| Item | Value |"
  echo "|---|---|"
  echo "| Started / finished (UTC) | $STARTED / $FINISHED |"
  echo "| Machine / commit | ${ALEEKHAN_MACHINE:-unnamed} / \`$COMMIT\` (modified tracked files: $DIRTY) |"
  echo "| Server / pg_dump | $SERVER / $DUMP_VERSION |"
  echo "| Synthetic rows (audit+outbox pairs, staging rows) | $ROWS |"
  echo "| Source DB size | $SRC_SIZE bytes |"
  echo "| Dump (custom format, -Z 6) | $DUMP_BYTES bytes, $TOC_ENTRIES TOC entries |"
  echo "| Dump sha256 | \`$SHA_DUMP\` (re-verified before restore: $([ "$SHA_AGAIN" = "$SHA_DUMP" ] && echo yes || echo NO)) |"
  echo "| Dump / restore / verify | ${DUMP_MS} ms / ${RESTORE_MS} ms / ${VERIFY_MS} ms |"
  echo "| Recovery (restore + verify) / total drill | ${RECOVERY_MS} ms / ${TOTAL_MS} ms |"
  echo "| Targets (DEC-004) | RPO 1 h, RTO 4 h - this tiny synthetic run proves the procedure, not production-size timing |"
  echo
  echo "## Checks"
  echo
  for c in "${CHECKS[@]}"; do
    name="$(printf '%s' "$c" | sed -E 's/.*"check": "([^"]*)".*/\1/')"; res="$(printf '%s' "$c" | sed -E 's/.*"result": "([^"]*)".*/\1/')"
    echo "- $res - $name"
  done
  echo
  echo "Fingerprints: \`fingerprint_before.txt\`, \`fingerprint_after.txt\` (table rows md5), diff: \`fingerprint_diff.txt\`."
} > "$OUT/drill_report.md"

echo "== drill $STATUS: dump ${DUMP_MS} ms, restore ${RESTORE_MS} ms, verify ${VERIFY_MS} ms, total ${TOTAL_MS} ms, dump ${DUMP_BYTES} bytes sha256 $SHA_DUMP"
[ "$STATUS" = PASS ]
