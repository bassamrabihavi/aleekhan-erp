"""PHASE_02 / 02.8 Gate follow-up REV-0290 (DEC-059 amendment 2026-11-17): order change-request limits.

* ``commercial_order_change_request.expires_at`` (nullable): written at submit = ``submitted_at`` +
  ``approval_request_expiry_days`` (the DEC-032 period, 30 days). CHECK ``ck_commercial_cr_open_has_expiry``:
  a SUBMITTED / APPROVED request has it; CHECK ``ck_commercial_cr_expiry_after_submit``: it lies after
  ``submitted_at``. Partial index ``ix_ccr_open_expires_at`` serves the expiry sweep.
* Partial UNIQUE ``uq_commercial_cr_one_open_per_order``: at most one SUBMITTED / APPROVED request per order
  (the DB backstop of the engine refusal ``OPEN_CHANGE_REQUEST_EXISTS``; two concurrent submits -> one wins).
* Housekeeping job type ``change_request_expiry_sweep`` (same job-run lifecycle as ``approval_expiry_sweep``):
  open requests past ``expires_at`` -> EXPIRED (audit + outbox per request).

Existing open rows are backfilled from their ``submitted_at`` with the effective parameter value (SQL function
``platform_param_value_at``, migration 0012). If an order already has more than one open request, the
migration stops with a clear message (count only): a person withdraws / decides the extra ones first - the
migration never closes business records by itself.

Reverse: the job definition (and its runs) are removed, then constraints, index and column are dropped (exact
inverse). Frozen data: this file must not import application code.
"""

from typing import Any

from django.db import migrations, models

ADDED_HOUSEKEEPING_JOBS = {
    "change_request_expiry_sweep": "انقضای درخواست‌های تغییر سفارش (۳۰ روز)",
}

BACKFILL_SQL = """
UPDATE public.commercial_order_change_request
   SET expires_at = submitted_at
       + make_interval(days => public.platform_param_value_at('approval_request_expiry_days', now())::int)
 WHERE status IN ('SUBMITTED', 'APPROVED') AND expires_at IS NULL;
"""


def refuse_duplicate_open(apps: Any, schema_editor: Any) -> None:
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM (SELECT order_id FROM public.commercial_order_change_request"
            " WHERE status IN ('SUBMITTED', 'APPROVED') GROUP BY order_id HAVING count(*) > 1) d"
        )
        row = cur.fetchone()
    n = int(row[0]) if row else 0
    if n:
        raise RuntimeError(
            f"0029: {n} order(s) have more than one SUBMITTED/APPROVED change request; withdraw or decide the "
            "extra requests first (DEC-059 amendment 2026-11-17), then migrate again"
        )


def seed_jobs(apps: Any, schema_editor: Any) -> None:
    job_definition = apps.get_model("platform_core", "JobDefinition")
    for job_type, name_fa in ADDED_HOUSEKEEPING_JOBS.items():
        job_definition.objects.using(schema_editor.connection.alias).get_or_create(
            job_type=job_type, defaults={"name_fa": name_fa, "cancellable": True, "protected": False}
        )


def unseed_jobs(apps: Any, schema_editor: Any) -> None:
    # plain SQL: the historical-model delete collector cannot follow JobRun relations inside a reverse run
    for job_type in ADDED_HOUSEKEEPING_JOBS:
        schema_editor.execute("DELETE FROM platform_job_run WHERE job_type = %s", [job_type])
        schema_editor.execute("DELETE FROM platform_job_definition WHERE job_type = %s", [job_type])


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0028_phase02_golden_summary"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderchangerequest",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="orderchangerequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("SUBMITTED", "Submitted"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("APPLIED", "Applied (new order version)"),
                    ("WITHDRAWN", "Withdrawn by the requester"),
                    ("EXPIRED", "Expired (30 days unanswered, DEC-059 amendment 2026-11-17)"),
                ],
                db_default="DRAFT",
                max_length=12,
            ),
        ),
        migrations.RunPython(refuse_duplicate_open, migrations.RunPython.noop),
        migrations.RunSQL(sql=BACKFILL_SQL, reverse_sql=migrations.RunSQL.noop),
        # the backfill fires the deferred constraint triggers of 0020; run them now, otherwise PostgreSQL refuses
        # the following CREATE INDEX / ADD CONSTRAINT ("pending trigger events")
        migrations.RunSQL(sql="SET CONSTRAINTS ALL IMMEDIATE;", reverse_sql=migrations.RunSQL.noop),
        migrations.AddIndex(
            model_name="orderchangerequest",
            index=models.Index(
                condition=models.Q(("status__in", ["SUBMITTED", "APPROVED"])),
                fields=["expires_at"],
                name="ix_ccr_open_expires_at",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["SUBMITTED", "APPROVED"])),
                fields=("order",),
                name="uq_commercial_cr_one_open_per_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status__in", ["SUBMITTED", "APPROVED"]), _negated=True),
                    ("expires_at__isnull", False),
                    _connector="OR",
                ),
                name="ck_commercial_cr_open_has_expiry",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("expires_at__isnull", True),
                    models.Q(("expires_at__gt", models.F("submitted_at")), ("submitted_at__isnull", False)),
                    _connector="OR",
                ),
                name="ck_commercial_cr_expiry_after_submit",
            ),
        ),
        migrations.RunPython(seed_jobs, unseed_jobs),
    ]
