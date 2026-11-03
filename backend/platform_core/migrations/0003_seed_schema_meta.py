"""Non-sensitive seed: the single platform_schema_meta row. No business data (PHASE_00 rule)."""

from typing import Any

from django.db import migrations

SCHEMA_CONTRACT = "PHASE_00.2"
SEEDED_BY = "platform_core.0003_seed_schema_meta"


def seed(apps: Any, schema_editor: Any) -> None:
    schema_meta = apps.get_model("platform_core", "SchemaMeta")
    schema_meta.objects.using(schema_editor.connection.alias).get_or_create(
        id=1, defaults={"schema_contract": SCHEMA_CONTRACT, "seeded_by_migration": SEEDED_BY}
    )


def unseed(apps: Any, schema_editor: Any) -> None:
    schema_meta = apps.get_model("platform_core", "SchemaMeta")
    schema_meta.objects.using(schema_editor.connection.alias).filter(
        id=1, seeded_by_migration=SEEDED_BY
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0002_db_triggers"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
