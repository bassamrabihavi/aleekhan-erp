"""Non-sensitive PHASE_02 seed (generic catalogue only - no customer, type, category, code or serial values).

* Units PIECE / PAIR (DEC-058: shoe = pair; bag, belt, pocket item, accessory and set = piece).
* The four Planning order types (DEC-058 item 6).
* Generic external reference types (DEC-058 item 4); ``product_data_steward`` may add more at runtime.
* The single factory serial counter (DEC-006): namespace ``factory_serial``, first serial **63001**, legacy
  serials must stay below 63000 (``legacy_max_exclusive``), number pattern ``^[1-9][0-9]*$``.

NOT seeded on purpose (DEC-005 / DEC-028 / DEC-046, rule R-38): product types, categories, products, styles,
codes, customers and serials. They come from the private Planning source through the server import only.
The legacy-maximum check of DEC-006 (no Planning, paper or Rahkaran serial >= 63000) is enforced on every legacy
row by trigger ``trg_identity_historical_order_record_guard`` (0020); the import must verify it before go-live.

Reverse: deletes exactly these rows (PROTECT FKs refuse once real rows reference them - the intended guard). The
counter row is never deleted at runtime (trigger); the reverse runs as the schema owner and lifts that trigger
for one statement inside the migration transaction, only while no serial exists (FK PROTECT otherwise).
Frozen data: this file must not import application code.
"""

from typing import Any

from django.db import migrations

SEED = "MIGRATION_SEED"

UNITS = (
    ("PIECE", "عدد"),
    ("PAIR", "جفت"),
)

ORDER_TYPES = (
    ("pre_production", "پیش تولید", 10),
    ("series_production", "سری تولید", 20),
    ("sampling", "نمونه‌سازی", 30),
    ("trial_production", "تولید آزمایشی", 40),
)

EXTERNAL_REF_TYPES = (
    ("rahkaran_project_code", "کد پروژه راهکاران"),
    ("contract_no", "شماره قرارداد"),
    ("customer_style_code", "کد استایل مشتری"),
    ("customer_serial", "سریال مشتری (هرگز سریال ما نیست)"),
)

SERIAL_COUNTER = {
    "namespace_key": "factory_serial",
    "start_value": 63001,
    "next_value": 63001,
    "legacy_max_exclusive": 63000,
    "number_pattern": r"^[1-9][0-9]*$",
    "decision_id": "DEC-006",
}


def seed(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    unit = apps.get_model("platform_core", "UnitOfMeasure")
    order_type = apps.get_model("platform_core", "OrderType")
    ref_type = apps.get_model("platform_core", "ExternalRefType")
    counter = apps.get_model("platform_core", "SerialCounter")
    for code, label in UNITS:
        unit.objects.using(db).create(code=code, label_fa=label, decision_id="DEC-058", provenance=SEED)
    for code, label, order in ORDER_TYPES:
        order_type.objects.using(db).create(
            code=code, label_fa=label, sort_order=order, decision_id="DEC-058", provenance=SEED
        )
    for key, label in EXTERNAL_REF_TYPES:
        ref_type.objects.using(db).create(key=key, label_fa=label, decision_id="DEC-058", provenance=SEED)
    counter.objects.using(db).create(**SERIAL_COUNTER)


def unseed(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    get = apps.get_model
    schema_editor.execute(
        "ALTER TABLE identity_serial_counter DISABLE TRIGGER trg_identity_serial_counter_no_delete"
    )
    get("platform_core", "SerialCounter").objects.using(db).filter(
        namespace_key=SERIAL_COUNTER["namespace_key"]
    ).delete()
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # flush deferred FK checks before ALTER
    schema_editor.execute(
        "ALTER TABLE identity_serial_counter ENABLE TRIGGER trg_identity_serial_counter_no_delete"
    )
    schema_editor.execute(
        "ALTER TABLE identity_external_ref_type DISABLE TRIGGER trg_identity_external_ref_type_no_delete"
    )
    get("platform_core", "ExternalRefType").objects.using(db).filter(
        provenance=SEED, key__in=[k for k, _ in EXTERNAL_REF_TYPES]
    ).delete()
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    schema_editor.execute(
        "ALTER TABLE identity_external_ref_type ENABLE TRIGGER trg_identity_external_ref_type_no_delete"
    )
    get("platform_core", "OrderType").objects.using(db).filter(
        provenance=SEED, code__in=[c for c, _l, _o in ORDER_TYPES]
    ).delete()
    get("platform_core", "UnitOfMeasure").objects.using(db).filter(
        provenance=SEED, code__in=[c for c, _ in UNITS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0020_phase02_db_guards"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
