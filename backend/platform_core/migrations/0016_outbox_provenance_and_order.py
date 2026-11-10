"""PHASE_01 / 01.6 Integration: outbox provenance + per-aggregate ordering index (reversible, additive).

* ``producer`` / ``build_commit`` / ``schema_migration`` on ``platform_outbox_event`` (phase rule: new data carries
  source provenance and commit/migration). Written by ``UnitOfWork.emit`` from the event catalogue
  (``engine/events.py``); ``''`` = row written before this migration (backward compatible: existing rows and
  readers keep working, no backfill - provenance of older rows is honestly unknown). Format CHECKs only.
* ``ix_outbox_event_agg_open`` (aggregate_type, aggregate_id, id) WHERE delivery_status <> 'ACKED': the
  dispatcher claims an event only if no earlier undelivered event of the same aggregate exists.

Reverse: drops the index, the three CHECKs and the three columns (provenance values are lost; delivery state is
untouched).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0015_dec056_matrix_v12"),
    ]

    operations = [
        migrations.AddField(
            model_name="outboxevent",
            name="build_commit",
            field=models.CharField(blank=True, db_default="", max_length=12),
        ),
        migrations.AddField(
            model_name="outboxevent",
            name="producer",
            field=models.CharField(blank=True, db_default="", max_length=100),
        ),
        migrations.AddField(
            model_name="outboxevent",
            name="schema_migration",
            field=models.CharField(blank=True, db_default="", max_length=100),
        ),
        migrations.AddIndex(
            model_name="outboxevent",
            index=models.Index(
                condition=models.Q(("delivery_status", "ACKED"), _negated=True),
                fields=["aggregate_type", "aggregate_id", "id"],
                name="ix_outbox_event_agg_open",
            ),
        ),
        migrations.AddConstraint(
            model_name="outboxevent",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("producer", ""),
                    ("producer__regex", "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$"),
                    _connector="OR",
                ),
                name="ck_outbox_event_producer_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="outboxevent",
            constraint=models.CheckConstraint(
                condition=models.Q(("build_commit__regex", "^([0-9a-f]{7,12})?$")),
                name="ck_outbox_event_build_commit_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="outboxevent",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("schema_migration", ""),
                    ("schema_migration__regex", "^[a-z][a-z0-9_]*\\.[0-9]{4}_[a-z0-9_]+$"),
                    _connector="OR",
                ),
                name="ck_outbox_event_schema_migration_fmt",
            ),
        ),
    ]
