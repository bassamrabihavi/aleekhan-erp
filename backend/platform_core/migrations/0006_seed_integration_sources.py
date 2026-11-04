"""Non-sensitive seed: metadata of the three known READ-ONLY source systems (no file, no data, no password).

Names come from handoff/02_DOMAIN_CONTRACTS/SOURCE_MAPPING_AND_IMPORT.md. ``staleness_threshold`` values are
TECHNICAL DEFAULTS (threshold_basis = TECHNICAL_DEFAULT) until the owner decides the snapshot validity /
re-import policy (DEC-016 for Rahkaran; DEC-025 for the legacy workbooks). ``policy_decision_id`` is the decision
that must be APPROVED before any batch of that source may be applied or superseded (RULE_NOT_APPROVED until then).
"""

from datetime import timedelta
from typing import Any

from django.db import migrations

SEEDED = (
    {
        "code": "rahkaran_excel",
        "name_fa": "راهکاران — خروجی اکسل (فقط‌خواندنی)",
        "kind": "EXCEL_FILE",
        "policy_decision_id": "DEC-016",
        "staleness_threshold": timedelta(hours=24),
    },
    {
        "code": "legacy_planning_xlsm",
        "name_fa": "فایل قدیمی برنامه‌ریزی (XLSM، فقط داده)",
        "kind": "XLSM_FILE",
        "policy_decision_id": "DEC-025",
        "staleness_threshold": timedelta(days=7),
    },
    {
        "code": "legacy_wh_xlsm",
        "name_fa": "فایل قدیمی انبار (XLSM، فقط داده)",
        "kind": "XLSM_FILE",
        "policy_decision_id": "DEC-025",
        "staleness_threshold": timedelta(days=7),
    },
)


def seed(apps: Any, schema_editor: Any) -> None:
    source = apps.get_model("platform_core", "IntegrationSource")
    db = schema_editor.connection.alias
    for row in SEEDED:
        source.objects.using(db).get_or_create(
            code=row["code"],
            defaults={
                **{k: v for k, v in row.items() if k != "code"},
                "direction": "READ_ONLY",
                "threshold_basis": "TECHNICAL_DEFAULT",
                "is_enabled": True,
            },
        )


def unseed(apps: Any, schema_editor: Any) -> None:
    source = apps.get_model("platform_core", "IntegrationSource")
    source.objects.using(schema_editor.connection.alias).filter(
        code__in=[r["code"] for r in SEEDED], batches__isnull=True, conflicts__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0005_integration_triggers"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
