"""PHASE_02 / 02.6: non-sensitive seed of ONE read-only source - the Planning workbook as the source of the
product-type / category catalogue and the legacy 14-digit code registry (metadata only: no file, no value, no
hash, no password).

* ``policy_decision_id`` = DEC-005 (APPROVED 2026-11-12): the apply of this source is registered in code
  (``integration.imports.SOURCE_APPLY_POLICIES``, reviewed commit), and only for the catalogue / code registry.
  The legacy order / serial migration of the same workbook stays on ``legacy_planning_xlsm`` (DEC-025, OPEN,
  PHASE_12) and remains RULE_NOT_APPROVED.
* ``staleness_threshold`` 30 days is a TECHNICAL DEFAULT (``threshold_basis = TECHNICAL_DEFAULT``): the
  catalogue changes rarely; the re-import policy is not a business rule yet.
* The DEC-037 baseline hash is NOT stored: the operator passes it to the import command (``--expected-sha256``).

Reverse: deletes the row only while no batch or conflict references it (PROTECT FKs otherwise - intended).
Frozen data: this file must not import application code.
"""

from datetime import timedelta
from typing import Any

from django.db import migrations

SOURCE = {
    "code": "planning_catalogue_xlsm",
    "name_fa": "فایل برنامه‌ریزی — فهرست پایه نوع، دسته و کد (XLSM، فقط داده)",
    "kind": "XLSM_FILE",
    "policy_decision_id": "DEC-005",
    "staleness_threshold": timedelta(days=30),
}


def seed(apps: Any, schema_editor: Any) -> None:
    source = apps.get_model("platform_core", "IntegrationSource")
    source.objects.using(schema_editor.connection.alias).get_or_create(
        code=SOURCE["code"],
        defaults={
            **{k: v for k, v in SOURCE.items() if k != "code"},
            "direction": "READ_ONLY",
            "threshold_basis": "TECHNICAL_DEFAULT",
            "is_enabled": True,
        },
    )


def unseed(apps: Any, schema_editor: Any) -> None:
    source = apps.get_model("platform_core", "IntegrationSource")
    source.objects.using(schema_editor.connection.alias).filter(
        code=SOURCE["code"], batches__isnull=True, conflicts__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0025_phase02_api_numbers"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
