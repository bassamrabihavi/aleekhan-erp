#!/usr/bin/env bash
# Migration round-trip + schema-diff evidence (PHASE_00 / 00.2).
#
#   up (from empty DB) -> makemigrations --check -> schema dump A
#   -> migrate platform_core zero (rollback) -> schema dump Z (must contain only django_migrations)
#   -> up again -> schema dump B -> diff A B (must be empty)
#
# Connection comes from the environment (PGHOST/PGPORT/PGUSER/PGPASSWORD or a ~/.pgpass); the password is
# never printed. The script creates and finally drops a throw-away database ($ROUNDTRIP_DB).
#
# Usage: backend/scripts/db_roundtrip.sh <output-dir>
# Env:   PYTHON (default: python), PG_BIN (dir with psql/pg_dump, default: PATH),
#        ROUNDTRIP_DB (default: aleekhan_roundtrip), KEEP_DB=1 to keep the database afterwards.
set -euo pipefail

OUT="${1:?usage: db_roundtrip.sh <output-dir>}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python}"
PSQL="${PG_BIN:+$PG_BIN/}psql"
PG_DUMP="${PG_BIN:+$PG_BIN/}pg_dump"
DB="${ROUNDTRIP_DB:-aleekhan_roundtrip}"

case "$DB" in
  *[!a-z0-9_]*|"") echo "ROUNDTRIP_DB must match [a-z0-9_]+" >&2; exit 2 ;;
esac

export ALEEKHAN_ENV="${ALEEKHAN_ENV:-test}"
unset DATABASE_URL || true

dump_schema() {
  # pg_dump >= 17.6 writes a random "\restrict <key>" token; drop it so dumps are comparable.
  "$PG_DUMP" --schema-only --no-owner --no-privileges -d "$DB" | grep -v -E '^\\(un)?restrict ' > "$1"
}

tables() {
  "$PSQL" -d "$DB" -Atc "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1"
}

manage() {
  (cd "$HERE" && PGDATABASE="$DB" "$PYTHON" manage.py "$@")
}

echo "== server: $("$PSQL" -d postgres -Atc 'SHOW server_version')"
echo "== drop/create throw-away database $DB"
"$PSQL" -d postgres -v ON_ERROR_STOP=1 -qc "DROP DATABASE IF EXISTS $DB" >/dev/null
"$PSQL" -d postgres -v ON_ERROR_STOP=1 -qc "CREATE DATABASE $DB ENCODING 'UTF8' TEMPLATE template0" >/dev/null
echo "tables in empty DB: $(tables | wc -l | tr -d ' ')"

echo "== [1] migrate up from empty DB"
manage migrate --noinput
manage showmigrations platform_core
echo "== [2] makemigrations --check --dry-run (model/migration drift)"
manage makemigrations --check --dry-run
dump_schema "$OUT/schema_up_1.sql"
echo "tables after up #1:"; tables
echo "seed rows: $("$PSQL" -d "$DB" -Atc 'SELECT count(*) FROM platform_schema_meta')"

echo "== [3] migrate platform_core zero (full rollback)"
manage migrate platform_core zero --noinput
manage showmigrations platform_core
dump_schema "$OUT/schema_zero.sql"
echo "tables after rollback:"; tables
echo "platform functions left: $("$PSQL" -d "$DB" -Atc "SELECT count(*) FROM pg_proc WHERE proname LIKE 'platform\_%'")"
remaining="$(tables | grep -v -x 'django_migrations' || true)"
if [ -n "$remaining" ]; then echo "FAIL: tables left after rollback: $remaining" >&2; exit 1; fi

echo "== [4] migrate up again"
manage migrate --noinput
dump_schema "$OUT/schema_up_2.sql"

echo "== [5] schema diff (up #1 vs up #2)"
if diff -u "$OUT/schema_up_1.sql" "$OUT/schema_up_2.sql" > "$OUT/schema_diff.txt"; then
  echo "schema diff: EMPTY ($(wc -l < "$OUT/schema_up_1.sql" | tr -d ' ') lines compared)"
else
  echo "FAIL: schema differs after round-trip, see schema_diff.txt" >&2; exit 1
fi

if [ "${KEEP_DB:-0}" != "1" ]; then
  "$PSQL" -d postgres -v ON_ERROR_STOP=1 -qc "DROP DATABASE IF EXISTS $DB" >/dev/null
  echo "== dropped $DB"
fi
echo "ROUNDTRIP OK"
