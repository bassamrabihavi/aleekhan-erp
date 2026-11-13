"""PHASE_02 / 02.3 domain engine: DB guards for the 2026-11-12 amendments + technical number sequences
(reversible).

1. DEC-059 amendment 2026-11-12 (REV-0222): an order that is ON_HOLD may be cancelled directly when its stored
   previous state is before release (``status_before_hold = 'CONFIRMED'``), with the version bump of the applied
   CANCEL_ORDER change request. After release cancel stays blocked (C-A). ``commercial_order_guard()`` is
   replaced by the 0020 body with exactly one more allowed transition; the reverse restores the 0020 body
   byte-identically (taken from the frozen 0020 text, so a round trip leaves an empty schema diff).
2. DEC-059 amendment 2026-11-12: the planning approver of a due-date change is not the deciding manager
   (``ck_commercial_cr_planner_not_decider``; "not the requester" is ``ck_commercial_cr_planner_not_requester``
   of 0019).
3. Technical numbers of customers, orders and change requests (PROPOSED format ``CU-``/``SO-``/``CR-`` + at
   least 6 digits, docs/discovery/DATA_TABLE.md "02.3 numbers"): one sequence each. Race-safe and unique (the
   tables keep their UNIQUE constraints); gaps are allowed (a rolled back write consumes a number) - these are
   NOT the gapless factory serial (DEC-006), which never uses a sequence.

4. DEC-005 amendment 2026-11-13: style segment ``0000`` is legacy only. ``ck_identity_style_no_fmt`` accepts
   ``0000`` for imported / legacy styles (provenance IMP / LEG) only - so a legacy code with style 0000 can be
   registered and matched to its style - and the new ``ck_identity_product_code_sys_no_style_0000`` keeps
   "never issued by the system" in the database (a SYS code never ends with style 0000; a SYS style never
   is 0000). Reverse: the 0019 CHECK (refuses 0000 always) - only while no legacy 0000 style exists.

Frozen data: only the frozen SQL text of migration 0020 is imported (no application code).
"""

from importlib import import_module

from django.db import migrations, models

_g = import_module("platform_core.migrations.0020_phase02_db_guards")


def _function(sql: str, name: str) -> str:
    start = sql.index(f"CREATE FUNCTION {name}()")
    end = sql.index("$fn$;", sql.index("$fn$", sql.index("AS $fn$", start) + 7)) + len("$fn$;")
    return sql[start:end]


ORDER_GUARD_0020 = _function(_g.GUARDS_SQL, "commercial_order_guard")
OLD_CLAUSE = (
    "            OR (OLD.status = 'CONFIRMED' AND NEW.status = 'CANCELLED' AND step = 1), false) THEN"
)
NEW_CLAUSE = (
    "            OR (OLD.status = 'CONFIRMED' AND NEW.status = 'CANCELLED' AND step = 1)\n"
    "            -- DEC-059 amendment 2026-11-12: a held order whose stored state is before release\n"
    "            OR (OLD.status = 'ON_HOLD' AND OLD.status_before_hold = 'CONFIRMED' AND NEW.status = 'CANCELLED'\n"
    "                AND step = 1), false) THEN"
)
assert ORDER_GUARD_0020.count(OLD_CLAUSE) == 1
ORDER_GUARD_FORWARD = ORDER_GUARD_0020.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1).replace(
    OLD_CLAUSE, NEW_CLAUSE
)
ORDER_GUARD_REVERSE = ORDER_GUARD_0020.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)

SEQUENCES = ("identity_customer_no_seq", "commercial_order_no_seq", "commercial_change_request_no_seq")
SEQUENCES_FORWARD = "\n".join(
    f"CREATE SEQUENCE public.{s} AS bigint START WITH 1 INCREMENT BY 1 NO CYCLE;" for s in SEQUENCES
)
SEQUENCES_REVERSE = "\n".join(f"DROP SEQUENCE IF EXISTS public.{s};" for s in reversed(SEQUENCES))


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0022_dec057_matrix_v20"),
    ]

    operations = [
        migrations.RunSQL(sql=ORDER_GUARD_FORWARD, reverse_sql=ORDER_GUARD_REVERSE),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("planning_approved_by__isnull", True),
                    ("decided_by__isnull", True),
                    models.Q(("planning_approved_by", models.F("decided_by")), _negated=True),
                    _connector="OR",
                ),
                name="ck_commercial_cr_planner_not_decider",
            ),
        ),
        migrations.RunSQL(sql=SEQUENCES_FORWARD, reverse_sql=SEQUENCES_REVERSE),
        # 4. DEC-005 amendment 2026-11-13: style 0000 is legacy only (import / history), never system-issued
        migrations.RemoveConstraint(
            model_name="style",
            name="ck_identity_style_no_fmt",
        ),
        migrations.AddConstraint(
            model_name="style",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("style_no__regex", "^[0-9]{4}$"),
                    models.Q(
                        models.Q(("style_no", "0000"), _negated=True),
                        ("provenance_kind__in", ["IMP", "LEG"]),
                        _connector="OR",
                    ),
                ),
                name="ck_identity_style_no_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind", "SYS"), _negated=True),
                    models.Q(("code__endswith", "0000"), _negated=True),
                    _connector="OR",
                ),
                name="ck_identity_product_code_sys_no_style_0000",
            ),
        ),
    ]
