"""PHASE_02 / 02.4: employer amendments of 2026-11-14 in the database (reversible).

1. Technical numbers with the Jalali year (DEC-058 amendment 2026-11-14): ``CU-`` / ``SO-`` / ``CR-`` +
   Jalali year of creation (Asia/Tehran) + ``-`` + at least 6 digits, numbering restarts at 1 every year.
   The three plain sequences of 0023 are replaced by ``platform_number_counter``: one row per (kind, Jalali
   year), moved by an atomic ``INSERT ... ON CONFLICT DO UPDATE`` under its row lock (race-safe; gaps are
   allowed; uniqueness stays the UNIQUE constraint of each table). The guard trigger lets a row start at 1
   and only move forward by exactly 1, never change its key, never be deleted or truncated - the runtime role
   cannot reset a counter (``ops/db/roles_check.sh``; ``grants.sql`` also revokes DELETE).
   Reverse: drops the table and re-creates the 0023 sequences, positioned after the largest plain-format
   number already used (``CU-000123`` style), so the 02.3 code never re-issues one.
2. Planning reject (DEC-059 amendment 2026-11-14): planning may approve OR reject a due-date change; a
   rejection closes the request REJECTED (the old due date stays). New columns ``planning_rejected_by`` /
   ``planning_rejected_at``; ``ck_commercial_cr_decided_has_decider`` accepts a REJECTED request decided by
   the manager OR rejected by planning; ``ck_commercial_cr_planning_rejected_*`` keep the rejection paired,
   due-date only, final and independent of the requester and of the deciding manager. The change request
   guard of 0020 gets exactly one more lifecycle edge: APPROVED -> REJECTED by a planning rejection (planning
   may decide after the manager). Reverse: the 0020 body byte-identically and the 0019 CHECK - refused while
   a planning-rejected request exists (the intended guard).

Frozen data: only the frozen SQL text of migration 0020 is imported (no application code).
"""

from importlib import import_module
from typing import Any

import django.db.models.deletion
from django.db import migrations, models

_g = import_module("platform_core.migrations.0020_phase02_db_guards")


def _function(sql: str, name: str) -> str:
    start = sql.index(f"CREATE FUNCTION {name}()")
    end = sql.index("$fn$;", sql.index("$fn$", sql.index("AS $fn$", start) + 7)) + len("$fn$;")
    return sql[start:end]


CR_GUARD_0020 = _function(_g.GUARDS_SQL, "commercial_change_request_guard")
OLD_EDGE = "        OR (OLD.status = 'APPROVED' AND NEW.status IN ('APPLIED', 'EXPIRED'))) THEN"
NEW_EDGE = (
    "        OR (OLD.status = 'APPROVED' AND NEW.status IN ('APPLIED', 'EXPIRED'))\n"
    "        -- DEC-059 amendment 2026-11-14: planning rejects a due-date change after the manager approved it\n"
    "        OR (OLD.status = 'APPROVED' AND NEW.status = 'REJECTED' AND NEW.planning_rejected_by_id IS NOT NULL)) THEN"
)
assert CR_GUARD_0020.count(OLD_EDGE) == 1
CR_GUARD_FORWARD = CR_GUARD_0020.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1).replace(
    OLD_EDGE, NEW_EDGE
)
CR_GUARD_REVERSE = CR_GUARD_0020.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)

# kind -> (0023 sequence, number column, table, plain prefix)
SEQUENCES = (
    ("identity_customer_no_seq", "customer_no", "identity_customer", "CU"),
    ("commercial_order_no_seq", "order_no", "commercial_customer_order", "SO"),
    ("commercial_change_request_no_seq", "request_no", "commercial_order_change_request", "CR"),
)

COUNTER_FORWARD = """
DROP SEQUENCE IF EXISTS public.commercial_change_request_no_seq;
DROP SEQUENCE IF EXISTS public.commercial_order_no_seq;
DROP SEQUENCE IF EXISTS public.identity_customer_no_seq;
CREATE TABLE public.platform_number_counter (
    kind varchar(16) NOT NULL,
    jalali_year integer NOT NULL,
    last_value bigint NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT platform_number_counter_pkey PRIMARY KEY (kind, jalali_year),
    CONSTRAINT ck_number_counter_kind CHECK (kind IN ('customer', 'order', 'change_request')),
    CONSTRAINT ck_number_counter_year CHECK (jalali_year BETWEEN 1300 AND 1999),
    CONSTRAINT ck_number_counter_value CHECK (last_value >= 1)
);
COMMENT ON TABLE public.platform_number_counter IS
    'PHASE_02 technical numbers CU-/SO-/CR-<jalali year>-<n> (DEC-058 amendment 2026-11-14); forward only';
CREATE FUNCTION platform_number_counter_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.last_value <> 1 THEN
            RAISE EXCEPTION 'ck_number_counter_starts_at_one: a counter row starts at 1'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'ck_number_counter_no_delete: a number counter is never deleted'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.kind IS DISTINCT FROM OLD.kind OR NEW.jalali_year IS DISTINCT FROM OLD.jalali_year
       OR NEW.last_value <> OLD.last_value + 1 THEN
        RAISE EXCEPTION 'ck_number_counter_forward_only: a number counter only moves forward by one'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$;
CREATE TRIGGER trg_platform_number_counter_guard BEFORE INSERT OR UPDATE OR DELETE
    ON public.platform_number_counter FOR EACH ROW EXECUTE FUNCTION platform_number_counter_guard();
CREATE FUNCTION platform_number_counter_no_truncate() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    RAISE EXCEPTION 'ck_number_counter_no_truncate: number counters are never truncated'
        USING ERRCODE = 'restrict_violation';
END;
$fn$;
CREATE TRIGGER trg_platform_number_counter_no_truncate BEFORE TRUNCATE
    ON public.platform_number_counter FOR EACH STATEMENT EXECUTE FUNCTION platform_number_counter_no_truncate();
"""


def _sequence_reverse() -> str:
    parts = [
        "DROP TRIGGER IF EXISTS trg_platform_number_counter_no_truncate ON public.platform_number_counter;",
        "DROP TRIGGER IF EXISTS trg_platform_number_counter_guard ON public.platform_number_counter;",
        "DROP TABLE IF EXISTS public.platform_number_counter;",
        "DROP FUNCTION IF EXISTS platform_number_counter_no_truncate();",
        "DROP FUNCTION IF EXISTS platform_number_counter_guard();",
    ]
    for seq, column, table, prefix in SEQUENCES:
        parts.append(f"CREATE SEQUENCE public.{seq} AS bigint START WITH 1 INCREMENT BY 1 NO CYCLE;")
        parts.append(
            f"SELECT setval('public.{seq}', m, true) FROM (SELECT max(substring({column} FROM "  # noqa: S608
            f"'^{prefix}-([0-9]{{6,}})$')::bigint) AS m FROM public.{table}) x WHERE m IS NOT NULL;"
        )
    return "\n".join(parts)


COUNTER_REVERSE = _sequence_reverse()


def _rename_fk_forward(apps: Any, schema_editor: Any) -> None:
    """0020 naming convention (``fk_<table>__<column>``) for the new FK."""
    rename = _g.rename_forward
    rename(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0024_dec057_dec059_matrix_v21"),
    ]

    operations = [
        # 1. numbers with the Jalali year
        migrations.RunSQL(sql=COUNTER_FORWARD, reverse_sql=COUNTER_REVERSE),
        # 2. planning reject
        migrations.RemoveConstraint(
            model_name="orderchangerequest",
            name="ck_commercial_cr_decided_has_decider",
        ),
        migrations.AddField(
            model_name="orderchangerequest",
            name="planning_rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="orderchangerequest",
            name="planning_rejected_by",
            field=models.ForeignKey(
                blank=True,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="platform_core.user",
            ),
        ),
        migrations.AddIndex(
            model_name="orderchangerequest",
            index=models.Index(fields=["planning_rejected_by"], name="ix_ccr_planning_rejected_by"),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        models.Q(("status__in", ["APPROVED", "APPLIED"]), _negated=True),
                        ("decided_by__isnull", False),
                        _connector="OR",
                    ),
                    models.Q(
                        models.Q(("status", "REJECTED"), _negated=True),
                        ("decided_by__isnull", False),
                        ("planning_rejected_by__isnull", False),
                        _connector="OR",
                    ),
                ),
                name="ck_commercial_cr_decided_has_decider",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("planning_rejected_at__isnull", True), ("planning_rejected_by__isnull", True)),
                    models.Q(
                        ("planning_rejected_at__isnull", False), ("planning_rejected_by__isnull", False)
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_cr_planning_rejected_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("planning_rejected_by__isnull", True),
                    models.Q(
                        ("kind", "DUE_DATE_CHANGE"),
                        ("planning_approved_by__isnull", True),
                        ("status", "REJECTED"),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_cr_planning_rejected_closes",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("planning_rejected_by__isnull", True),
                    models.Q(
                        models.Q(("planning_rejected_by", models.F("requested_by")), _negated=True),
                        models.Q(
                            ("decided_by__isnull", True),
                            models.Q(("planning_rejected_by", models.F("decided_by")), _negated=True),
                            _connector="OR",
                        ),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_cr_planning_rejecter_independent",
            ),
        ),
        migrations.RunSQL(sql=CR_GUARD_FORWARD, reverse_sql=CR_GUARD_REVERSE),
        # reverse: RemoveField drops the FK whatever its name
        migrations.RunPython(_rename_fk_forward, migrations.RunPython.noop),
    ]
