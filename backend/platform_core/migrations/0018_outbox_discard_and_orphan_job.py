"""PHASE_01 / 01.7 Security & Ops (reversible).

* REV-0129: outbox delivery state ``DISCARDED`` (terminal; DEAD_LETTER -> DISCARDED by the owner from the
  server console, audited, reason required - ``platform_core.ops.dead_letters``) with ``discarded_at`` and
  CHECK ``ck_outbox_event_discarded_has_ts``. The per-aggregate ordering index ``ix_outbox_event_agg_open``
  now leaves out settled rows (ACKED and DISCARDED), matching ``engine.outbox.SETTLED``.
* Housekeeping job type ``document_orphan_cleanup`` (01.4 report section 7): stored bytes without a
  ``platform_stored_object`` row, older than the grace period, are removed (audited, idempotent).

Reverse: the job definition is removed (its runs first - job runs are operational records, the audit of each
purge stays); DISCARDED rows go back to DEAD_LETTER (the safe state the old code knows: the aggregate is held
again and the owner's discard stays in the audit trail), then the column, CHECK and index return to 0016.
Frozen data: this file must not import application code.
"""

from typing import Any

from django.db import migrations, models

ADDED_HOUSEKEEPING_JOBS = {
    "document_orphan_cleanup": "حذف بایت‌های بی‌صاحب فایل (بدون ردیف ثبت)",
}


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


def undiscard(apps: Any, schema_editor: Any) -> None:
    apps.get_model("platform_core", "OutboxEvent").objects.using(schema_editor.connection.alias).filter(
        delivery_status="DISCARDED"
    ).update(delivery_status="DEAD_LETTER")


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0017_dec056_matrix_v13"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="outboxevent",
            name="ck_outbox_event_delivery_status",
        ),
        migrations.RemoveIndex(
            model_name="outboxevent",
            name="ix_outbox_event_agg_open",
        ),
        migrations.AddField(
            model_name="outboxevent",
            name="discarded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="outboxevent",
            name="delivery_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("DISPATCHED", "Dispatched"),
                    ("ACKED", "Acknowledged"),
                    ("FAILED", "Failed (will retry)"),
                    ("DEAD_LETTER", "Dead letter"),
                    ("DISCARDED", "Discarded by the owner"),
                ],
                db_default="PENDING",
                max_length=16,
            ),
        ),
        # reverse runs this first (operations are undone bottom-up after the constraints below are dropped)
        migrations.RunPython(migrations.RunPython.noop, undiscard),
        migrations.AddIndex(
            model_name="outboxevent",
            index=models.Index(
                condition=models.Q(("delivery_status__in", ["ACKED", "DISCARDED"]), _negated=True),
                fields=["aggregate_type", "aggregate_id", "id"],
                name="ix_outbox_event_agg_open",
            ),
        ),
        migrations.AddConstraint(
            model_name="outboxevent",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "delivery_status__in",
                        ["PENDING", "DISPATCHED", "ACKED", "FAILED", "DEAD_LETTER", "DISCARDED"],
                    )
                ),
                name="ck_outbox_event_delivery_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="outboxevent",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("delivery_status", "DISCARDED"), _negated=True),
                    ("discarded_at__isnull", False),
                    _connector="OR",
                ),
                name="ck_outbox_event_discarded_has_ts",
            ),
        ),
        migrations.RunPython(seed_jobs, unseed_jobs),
    ]
