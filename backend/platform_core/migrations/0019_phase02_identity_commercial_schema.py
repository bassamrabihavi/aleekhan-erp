"""PHASE_02 / 02.2: Identity (product registry, serials) and Commercial (orders) tables - generated from
``platform_core/product_identity/models.py`` and ``platform_core/commercial/models.py``.

21 tables, every PK / FK (PROTECT) / UNIQUE / CHECK / index named in the models (DATA_TABLE.md PHASE_02, ERD.md
section 7, decisions DEC-005/006/057/058/059). Triggers, deferred constraint triggers and the FK/index renaming
follow in 0020; the non-sensitive seed in 0021; the permission matrix v2.0 in 0022. Reverse: drops the tables
(empty until the 02.3 engine writes; PROTECT FKs and 0021/0022 reverses refuse a used catalogue first).
"""

import uuid

import django.db.models.deletion
import django.db.models.expressions
import django.db.models.functions.comparison
import django.db.models.functions.datetime
import django.db.models.functions.text
import django.db.models.lookups
from django.db import migrations, models

import platform_core.code14


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0018_outbox_discard_and_orphan_job"),
    ]

    operations = [
        migrations.CreateModel(
            name="CodeRuleRevision",
            fields=[
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("code_namespace", models.CharField(db_default="product_code", max_length=16)),
                ("revision_no", models.IntegerField()),
                ("scope", models.JSONField(default=dict)),
                ("rule_spec", models.JSONField(default=dict)),
                ("source_workbook_sha256", models.CharField(max_length=64)),
                ("golden_case_count", models.IntegerField(db_default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("IN_REVIEW", "In review"),
                            ("APPROVED", "Approved"),
                            ("ACTIVE", "Active (codes are issued under it)"),
                            ("RETIRED", "Retired"),
                            ("REJECTED", "Rejected"),
                        ],
                        db_default="DRAFT",
                        max_length=12,
                    ),
                ),
                ("decision_id", models.CharField(max_length=7)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "approval",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.approvalrequest",
                    ),
                ),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "evidence_document",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.document",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
            ],
            options={
                "db_table": "identity_code_rule_revision",
            },
        ),
        migrations.CreateModel(
            name="CodeRuleGoldenCase",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("product_type_code", models.CharField(max_length=2)),
                ("inputs", models.JSONField(default=dict)),
                ("expected_code", platform_core.code14.Code14Field()),
                ("source_sheet", models.CharField(max_length=100)),
                ("source_cell_ref", models.CharField(max_length=32)),
                ("source_workbook_sha256", models.CharField(max_length=64)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "rule_revision",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.coderulerevision",
                    ),
                ),
            ],
            options={
                "db_table": "identity_code_rule_golden_case",
            },
        ),
        migrations.CreateModel(
            name="Customer",
            fields=[
                (
                    "provenance_kind",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("IMP", "Applied from an import batch"),
                            ("LEG", "Read-only legacy evidence (historical)"),
                            ("EXT", "External reference only"),
                        ],
                        db_default="SYS",
                        max_length=8,
                    ),
                ),
                ("source_sheet", models.CharField(blank=True, db_default="", max_length=100)),
                ("source_cell_ref", models.CharField(blank=True, db_default="", max_length=32)),
                ("source_raw_value", models.TextField(blank=True, null=True)),
                ("source_formula", models.TextField(blank=True, null=True)),
                ("transform_rule_version", models.CharField(blank=True, db_default="", max_length=64)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("customer_no", models.CharField(max_length=32)),
                ("display_name_fa", models.CharField(max_length=200)),
                ("legal_name_fa", models.CharField(blank=True, max_length=300, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive (never deleted)")],
                        db_default="ACTIVE",
                        max_length=8,
                    ),
                ),
                ("default_required_quality_ref", models.CharField(blank=True, max_length=64, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "import_batch",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.importbatch",
                    ),
                ),
                (
                    "staging_row",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.stagingrow",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
            ],
            options={
                "db_table": "identity_customer",
            },
        ),
        migrations.CreateModel(
            name="CustomerBrand",
            fields=[
                (
                    "provenance_kind",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("IMP", "Applied from an import batch"),
                            ("LEG", "Read-only legacy evidence (historical)"),
                            ("EXT", "External reference only"),
                        ],
                        db_default="SYS",
                        max_length=8,
                    ),
                ),
                ("source_sheet", models.CharField(blank=True, db_default="", max_length=100)),
                ("source_cell_ref", models.CharField(blank=True, db_default="", max_length=32)),
                ("source_raw_value", models.TextField(blank=True, null=True)),
                ("source_formula", models.TextField(blank=True, null=True)),
                ("transform_rule_version", models.CharField(blank=True, db_default="", max_length=64)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("brand_name_fa", models.CharField(max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive (never deleted)")],
                        db_default="ACTIVE",
                        max_length=8,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.customer",
                    ),
                ),
                (
                    "import_batch",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.importbatch",
                    ),
                ),
                (
                    "staging_row",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.stagingrow",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
            ],
            options={
                "db_table": "identity_customer_brand",
            },
        ),
        migrations.CreateModel(
            name="CustomerOrder",
            fields=[
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("order_no", models.CharField(max_length=32)),
                ("external_po_number", models.CharField(blank=True, db_default="", max_length=64)),
                ("program_ref", models.CharField(blank=True, max_length=64, null=True)),
                ("order_date", models.DateField()),
                ("requested_due_date", models.DateField(blank=True, null=True)),
                ("required_quality_requirement", models.CharField(blank=True, max_length=64, null=True)),
                ("customer_representative_name", models.CharField(blank=True, max_length=200, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft (edited directly)"),
                            ("VALIDATED", "Validated"),
                            ("CONFIRMED", "Confirmed by planning; serials allocated (DEC-006 L-A / DEC-057)"),
                            ("RELEASED_TO_PLAN", "Released to planning"),
                            ("ON_HOLD", "On hold (single hold state, DEC-059)"),
                            ("CANCELLED", "Cancelled"),
                            ("PARTIAL_FULFILLED", "Partially fulfilled (later phase)"),
                            ("FULFILLED", "Fulfilled (later phase)"),
                            ("CLOSED", "Closed (later phase, DEC-020)"),
                        ],
                        db_default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("status_before_hold", models.CharField(blank=True, max_length=20, null=True)),
                ("hold_reason", models.CharField(blank=True, max_length=500, null=True)),
                ("cancel_reason", models.CharField(blank=True, max_length=500, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("current_version", models.IntegerField(db_default=0)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                (
                    "brand",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.customerbrand",
                    ),
                ),
                (
                    "confirmed_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.customer",
                    ),
                ),
                (
                    "released_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
            ],
            options={
                "db_table": "commercial_customer_order",
            },
        ),
        migrations.CreateModel(
            name="ExternalRefType",
            fields=[
                ("key", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("label_fa", models.CharField(max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive (never deleted)")],
                        db_default="ACTIVE",
                        max_length=8,
                    ),
                ),
                ("decision_id", models.CharField(blank=True, db_default="", max_length=7)),
                (
                    "provenance",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("MIGRATION_SEED", "Seeded by a reviewed migration (non-sensitive catalogue)"),
                            ("SEED_SYNTHETIC", "Synthetic dev/test data (never production)"),
                        ],
                        db_default="SYS",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
            ],
            options={
                "db_table": "identity_external_ref_type",
            },
        ),
        migrations.CreateModel(
            name="ExternalRef",
            fields=[
                (
                    "provenance_kind",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("IMP", "Applied from an import batch"),
                            ("LEG", "Read-only legacy evidence (historical)"),
                            ("EXT", "External reference only"),
                        ],
                        db_default="SYS",
                        max_length=8,
                    ),
                ),
                ("source_sheet", models.CharField(blank=True, db_default="", max_length=100)),
                ("source_cell_ref", models.CharField(blank=True, db_default="", max_length=32)),
                ("source_raw_value", models.TextField(blank=True, null=True)),
                ("source_formula", models.TextField(blank=True, null=True)),
                ("transform_rule_version", models.CharField(blank=True, db_default="", max_length=64)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                (
                    "target_type",
                    models.CharField(
                        choices=[
                            ("customer", "Customer"),
                            ("product", "Product"),
                            ("style", "Style"),
                            ("customer_order", "Customer order"),
                            ("order_line", "Order line"),
                            ("serial", "Serial"),
                        ],
                        max_length=16,
                    ),
                ),
                ("target_id", models.UUIDField()),
                (
                    "system",
                    models.CharField(
                        choices=[
                            ("RAHKARAN", "Rahkaran (read-only Excel import)"),
                            ("CUSTOMER", "The customer's own reference"),
                            ("LEGACY_PLANNING", "Legacy Planning workbook"),
                            ("OTHER", "Other"),
                        ],
                        max_length=16,
                    ),
                ),
                ("value", models.CharField(max_length=64)),
                ("valid_from", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("valid_to", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "import_batch",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.importbatch",
                    ),
                ),
                (
                    "staging_row",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.stagingrow",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "ref_type",
                    models.ForeignKey(
                        db_column="namespace",
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.externalreftype",
                    ),
                ),
            ],
            options={
                "db_table": "identity_external_ref",
            },
        ),
        migrations.CreateModel(
            name="OrderChangeRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("request_no", models.CharField(max_length=32)),
                ("base_order_version", models.IntegerField()),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("QTY_CHANGE", "Quantity (the line keeps its serial, DEC-059)"),
                            ("DUE_DATE_CHANGE", "Due date (needs the planning approval too, DEC-059)"),
                            ("ADD_LINE", "Add a line (gets a new serial)"),
                            ("CANCEL_LINE", "Cancel a line (before release only)"),
                            ("CANCEL_ORDER", "Cancel the order (before release only)"),
                            ("HOLD", "Hold"),
                            ("RESUME", "Resume to the previous state"),
                        ],
                        max_length=16,
                    ),
                ),
                ("items", models.JSONField(default=list)),
                ("reason", models.CharField(max_length=500)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("SUBMITTED", "Submitted"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("APPLIED", "Applied (new order version)"),
                            ("WITHDRAWN", "Withdrawn by the requester"),
                            ("EXPIRED", "Expired (period not decided: OPEN)"),
                        ],
                        db_default="DRAFT",
                        max_length=12,
                    ),
                ),
                ("impact", models.JSONField(blank=True, null=True)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("planning_approved_at", models.DateTimeField(blank=True, null=True)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("applied_version", models.IntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "applied_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "approval",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.approvalrequest",
                    ),
                ),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.customerorder",
                    ),
                ),
                (
                    "planning_approval",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.approvalrequest",
                    ),
                ),
                (
                    "planning_approved_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
            ],
            options={
                "db_table": "commercial_order_change_request",
            },
        ),
        migrations.CreateModel(
            name="CustomerOrderVersion",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("version", models.IntegerField()),
                ("image", models.JSONField()),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("CONFIRMED", "Version 1 written at confirmation"),
                            ("CHANGE_APPLIED", "An applied change request"),
                            ("CANCELLED", "Order cancelled by a change request"),
                        ],
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                (
                    "created_by",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.customerorder",
                    ),
                ),
                (
                    "change_request",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.orderchangerequest",
                    ),
                ),
            ],
            options={
                "db_table": "commercial_customer_order_version",
            },
        ),
        migrations.CreateModel(
            name="OrderType",
            fields=[
                ("code", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("label_fa", models.CharField(max_length=100)),
                ("sort_order", models.SmallIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive (never deleted)")],
                        db_default="ACTIVE",
                        max_length=8,
                    ),
                ),
                ("decision_id", models.CharField(max_length=7)),
                (
                    "provenance",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("MIGRATION_SEED", "Seeded by a reviewed migration (non-sensitive catalogue)"),
                            ("SEED_SYNTHETIC", "Synthetic dev/test data (never production)"),
                        ],
                        db_default="SYS",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
            ],
            options={
                "db_table": "commercial_order_type",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("code__regex", "^[a-z][a-z0-9_]{2,63}$")),
                        name="ck_commercial_order_type_code_fmt",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("label_fa", ""), _negated=True),
                        name="ck_commercial_order_type_label_nonempty",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("sort_order__gte", 0)),
                        name="ck_commercial_order_type_sort_nonneg",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("status__in", ["ACTIVE", "INACTIVE"])),
                        name="ck_commercial_order_type_status",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("decision_id__regex", "^DEC-[0-9]{3}$")),
                        name="ck_commercial_order_type_decision",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("provenance__in", ["SYS", "MIGRATION_SEED"])),
                        name="ck_commercial_order_type_provenance",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="customerorder",
            name="order_type",
            field=models.ForeignKey(
                db_column="order_type_code",
                db_index=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="platform_core.ordertype",
            ),
        ),
        migrations.CreateModel(
            name="ProductClass",
            fields=[
                (
                    "provenance_kind",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("IMP", "Applied from an import batch"),
                            ("LEG", "Read-only legacy evidence (historical)"),
                            ("EXT", "External reference only"),
                        ],
                        db_default="SYS",
                        max_length=8,
                    ),
                ),
                ("source_sheet", models.CharField(blank=True, db_default="", max_length=100)),
                ("source_cell_ref", models.CharField(blank=True, db_default="", max_length=32)),
                ("source_raw_value", models.TextField(blank=True, null=True)),
                ("source_formula", models.TextField(blank=True, null=True)),
                ("transform_rule_version", models.CharField(blank=True, db_default="", max_length=64)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                (
                    "level_key",
                    models.CharField(
                        choices=[
                            (
                                "product_type",
                                "Product type (code segment 2, the golden-test family, DEC-005 Q-C)",
                            ),
                            ("category", "Category within a product type (code segment 3)"),
                        ],
                        max_length=16,
                    ),
                ),
                ("segment_value", models.CharField(max_length=2)),
                ("label_fa", models.CharField(max_length=200)),
                (
                    "product_no_scheme",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("SEQUENTIAL_PER_TYPE", "Largest product number of the type + 1 (DEC-005)"),
                            ("BELT_BUCKLE_WIDTH", "Buckle-type code (2) + belt width (2) (DEC-005, belt)"),
                        ],
                        max_length=24,
                        null=True,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("ACTIVE", "Active"),
                            ("RETIRED", "Retired (never deleted)"),
                        ],
                        db_default="DRAFT",
                        max_length=8,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "import_batch",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.importbatch",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.productclass",
                    ),
                ),
                (
                    "staging_row",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.stagingrow",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
            ],
            options={
                "db_table": "identity_product_class",
            },
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                (
                    "provenance_kind",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("IMP", "Applied from an import batch"),
                            ("LEG", "Read-only legacy evidence (historical)"),
                            ("EXT", "External reference only"),
                        ],
                        db_default="SYS",
                        max_length=8,
                    ),
                ),
                ("source_sheet", models.CharField(blank=True, db_default="", max_length=100)),
                ("source_cell_ref", models.CharField(blank=True, db_default="", max_length=32)),
                ("source_raw_value", models.TextField(blank=True, null=True)),
                ("source_formula", models.TextField(blank=True, null=True)),
                ("transform_rule_version", models.CharField(blank=True, db_default="", max_length=64)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("product_no", models.CharField(max_length=4)),
                ("name_fa", models.CharField(max_length=200)),
                ("buckle_type_code", models.CharField(blank=True, max_length=2, null=True)),
                ("belt_width_code", models.CharField(blank=True, max_length=2, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("ACTIVE", "Active"),
                            ("RETIRED", "Retired (never deleted)"),
                        ],
                        db_default="DRAFT",
                        max_length=8,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "import_batch",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.importbatch",
                    ),
                ),
                (
                    "staging_row",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.stagingrow",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "product_type",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.productclass",
                    ),
                ),
            ],
            options={
                "db_table": "identity_product",
            },
        ),
        migrations.CreateModel(
            name="ProductCode",
            fields=[
                (
                    "provenance_kind",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("IMP", "Applied from an import batch"),
                            ("LEG", "Read-only legacy evidence (historical)"),
                            ("EXT", "External reference only"),
                        ],
                        db_default="SYS",
                        max_length=8,
                    ),
                ),
                ("source_sheet", models.CharField(blank=True, db_default="", max_length=100)),
                ("source_cell_ref", models.CharField(blank=True, db_default="", max_length=32)),
                ("source_raw_value", models.TextField(blank=True, null=True)),
                ("source_formula", models.TextField(blank=True, null=True)),
                ("transform_rule_version", models.CharField(blank=True, db_default="", max_length=64)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("code", platform_core.code14.Code14Field()),
                ("code_namespace", models.CharField(db_default="product_code", max_length=16)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("RESERVED", "Reserved by the system, waiting for Rahkaran (DEC-005 B1)"),
                            ("ACTIVE", "Active (seen in Rahkaran)"),
                            ("RETIRED", "Retired"),
                            ("DISPUTED", "Disputed (conflict; a human decides)"),
                        ],
                        max_length=12,
                    ),
                ),
                (
                    "erp_status",
                    models.CharField(
                        choices=[
                            ("ERP_PENDING", "Not yet seen in the Rahkaran import"),
                            ("ERP_MATCHED", "Seen in the Rahkaran import (exact match)"),
                            ("ERP_MISSING", "Expected in Rahkaran, not found"),
                        ],
                        db_default="ERP_PENDING",
                        max_length=12,
                    ),
                ),
                ("issue_idempotency_key", models.UUIDField(blank=True, null=True)),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "erp_seen_batch",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.importbatch",
                    ),
                ),
                (
                    "import_batch",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.importbatch",
                    ),
                ),
                (
                    "issued_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "rule_revision",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.coderulerevision",
                    ),
                ),
                (
                    "staging_row",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.stagingrow",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
            ],
            options={
                "db_table": "identity_product_code",
            },
        ),
        migrations.CreateModel(
            name="SerialCounter",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("namespace_key", models.CharField(max_length=64)),
                ("start_value", models.BigIntegerField()),
                ("next_value", models.BigIntegerField()),
                ("legacy_max_exclusive", models.BigIntegerField()),
                ("number_pattern", models.CharField(max_length=64)),
                ("decision_id", models.CharField(max_length=7)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
            ],
            options={
                "db_table": "identity_serial_counter",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("namespace_key",), name="uq_identity_serial_counter_namespace"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("namespace_key", "factory_serial")),
                        name="ck_identity_serial_counter_single_ns",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("start_value__gte", 1)),
                        name="ck_identity_serial_counter_start_pos",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("next_value__gte", models.F("start_value"))),
                        name="ck_identity_serial_counter_next_ge_start",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("legacy_max_exclusive__lt", models.F("start_value"))),
                        name="ck_identity_serial_counter_legacy_below_start",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("number_pattern", "^[1-9][0-9]*$")),
                        name="ck_identity_serial_counter_pattern",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("decision_id__regex", "^DEC-[0-9]{3}$")),
                        name="ck_identity_serial_counter_decision",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("row_version__gte", 1)),
                        name="ck_identity_serial_counter_row_version_pos",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Serial",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("serial_number", models.CharField(max_length=32)),
                ("serial_value", models.BigIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ALLOCATED", "Allocated at order confirm (DEC-006 L-A)"),
                            ("CANCELLED", "Cancelled; the number is never re-used (DEC-059)"),
                            ("IN_PRODUCTION", "In production (PHASE_07)"),
                            ("PARTIALLY_DELIVERED", "Partially delivered (PHASE_09)"),
                            ("DELIVERED", "Delivered (PHASE_09)"),
                            ("CLOSED", "Closed (DEC-020)"),
                        ],
                        db_default="ALLOCATED",
                        max_length=20,
                    ),
                ),
                ("allocation_idempotency_key", models.UUIDField()),
                ("allocated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("cancel_reason", models.CharField(blank=True, max_length=500, null=True)),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "allocated_by",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.customer",
                    ),
                ),
                (
                    "product_code",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.productcode",
                    ),
                ),
                (
                    "serial_counter",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.serialcounter",
                    ),
                ),
            ],
            options={
                "db_table": "identity_serial",
            },
        ),
        migrations.CreateModel(
            name="SerialSnapshot",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("version", models.IntegerField()),
                ("snapshot", models.JSONField()),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("ALLOCATED", "Version 1, written in the allocation transaction"),
                            ("CHANGE_APPLIED", "An applied change request (DEC-059)"),
                            ("TECH_PACKAGE_LINKED", "Technical package linked (PHASE_03/04)"),
                        ],
                        max_length=20,
                    ),
                ),
                ("order_version", models.IntegerField()),
                ("change_request_id", models.UUIDField(blank=True, null=True)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                (
                    "created_by",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "serial",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.serial",
                    ),
                ),
            ],
            options={
                "db_table": "identity_serial_snapshot",
            },
        ),
        migrations.CreateModel(
            name="Style",
            fields=[
                (
                    "provenance_kind",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("IMP", "Applied from an import batch"),
                            ("LEG", "Read-only legacy evidence (historical)"),
                            ("EXT", "External reference only"),
                        ],
                        db_default="SYS",
                        max_length=8,
                    ),
                ),
                ("source_sheet", models.CharField(blank=True, db_default="", max_length=100)),
                ("source_cell_ref", models.CharField(blank=True, db_default="", max_length=32)),
                ("source_raw_value", models.TextField(blank=True, null=True)),
                ("source_formula", models.TextField(blank=True, null=True)),
                ("transform_rule_version", models.CharField(blank=True, db_default="", max_length=64)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("style_no", models.CharField(max_length=4)),
                ("name_fa", models.CharField(max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("ACTIVE", "Active"),
                            ("RETIRED", "Retired (never deleted)"),
                        ],
                        db_default="DRAFT",
                        max_length=8,
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.productclass",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "import_batch",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.importbatch",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.product",
                    ),
                ),
                (
                    "staging_row",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.stagingrow",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
            ],
            options={
                "db_table": "identity_style",
            },
        ),
        migrations.AddField(
            model_name="serial",
            name="style",
            field=models.ForeignKey(
                db_index=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="platform_core.style",
            ),
        ),
        migrations.AddField(
            model_name="productcode",
            name="style",
            field=models.ForeignKey(
                blank=True,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="platform_core.style",
            ),
        ),
        migrations.CreateModel(
            name="HistoricalOrderRecord",
            fields=[
                (
                    "provenance_kind",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("IMP", "Applied from an import batch"),
                            ("LEG", "Read-only legacy evidence (historical)"),
                            ("EXT", "External reference only"),
                        ],
                        db_default="SYS",
                        max_length=8,
                    ),
                ),
                ("source_sheet", models.CharField(blank=True, db_default="", max_length=100)),
                ("source_cell_ref", models.CharField(blank=True, db_default="", max_length=32)),
                ("source_raw_value", models.TextField(blank=True, null=True)),
                ("source_formula", models.TextField(blank=True, null=True)),
                ("transform_rule_version", models.CharField(blank=True, db_default="", max_length=64)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("legacy_order_ref", models.CharField(blank=True, db_default="", max_length=64)),
                ("legacy_serial_text", models.CharField(blank=True, max_length=32, null=True)),
                ("legacy_serial_value", models.BigIntegerField(blank=True, null=True)),
                ("legacy_serial_duplicate", models.BooleanField(db_default=False)),
                ("legacy_product_code_raw", models.TextField(blank=True, null=True)),
                ("normalised_product_code", platform_core.code14.Code14Field(blank=True, null=True)),  # type: ignore[misc]
                (
                    "code_flag",
                    models.CharField(
                        choices=[
                            ("OK", "14-digit code present"),
                            (
                                "DISPUTED",
                                "Not a valid 14-digit code; planning decides (DEC-005 Q-D), never auto-fixed",
                            ),
                            ("ABSENT", "No code in the legacy row"),
                        ],
                        max_length=8,
                    ),
                ),
                ("payload", models.JSONField(default=dict)),
                (
                    "match_status",
                    models.CharField(
                        choices=[
                            ("UNMATCHED", "Not matched"),
                            ("SUGGESTED", "Suggested by similarity (never auto-linked)"),
                            ("CONFIRMED", "Confirmed by a person"),
                            ("REJECTED", "Rejected by a person"),
                        ],
                        db_default="UNMATCHED",
                        max_length=12,
                    ),
                ),
                ("matched_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "import_batch",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.importbatch",
                    ),
                ),
                (
                    "matched_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "staging_row",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.stagingrow",
                    ),
                ),
                (
                    "matched_product_code",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.productcode",
                    ),
                ),
                (
                    "matched_style",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.style",
                    ),
                ),
            ],
            options={
                "db_table": "identity_historical_order_record",
            },
        ),
        migrations.CreateModel(
            name="StyleRevision",
            fields=[
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("revision_no", models.IntegerField()),
                ("attributes", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("ACTIVE", "Active (immutable)"),
                            ("SUPERSEDED", "Superseded (immutable)"),
                        ],
                        db_default="DRAFT",
                        max_length=12,
                    ),
                ),
                ("technical_package_revision_id", models.UUIDField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "style",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.style",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
            ],
            options={
                "db_table": "identity_style_revision",
            },
        ),
        migrations.AddField(
            model_name="serial",
            name="style_revision",
            field=models.ForeignKey(
                db_index=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="platform_core.stylerevision",
            ),
        ),
        migrations.CreateModel(
            name="UnitOfMeasure",
            fields=[
                ("code", models.CharField(max_length=8, primary_key=True, serialize=False)),
                ("label_fa", models.CharField(max_length=50)),
                ("decision_id", models.CharField(max_length=7)),
                (
                    "provenance",
                    models.CharField(
                        choices=[
                            ("SYS", "Created in the platform"),
                            ("MIGRATION_SEED", "Seeded by a reviewed migration (non-sensitive catalogue)"),
                            ("SEED_SYNTHETIC", "Synthetic dev/test data (never production)"),
                        ],
                        db_default="SYS",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
            ],
            options={
                "db_table": "identity_unit_of_measure",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("code__regex", "^[A-Z][A-Z_]{1,7}$")),
                        name="ck_identity_uom_code_fmt",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("label_fa", ""), _negated=True),
                        name="ck_identity_uom_label_nonempty",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("decision_id__regex", "^DEC-[0-9]{3}$")),
                        name="ck_identity_uom_decision_fmt",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("provenance__in", ["SYS", "MIGRATION_SEED"])),
                        name="ck_identity_uom_provenance",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="productclass",
            name="uom",
            field=models.ForeignKey(
                blank=True,
                db_column="uom_code",
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="platform_core.unitofmeasure",
            ),
        ),
        migrations.CreateModel(
            name="CustomerOrderLine",
            fields=[
                ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("updated_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
                ("row_version", models.BigIntegerField(db_default=1)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("line_no", models.IntegerField()),
                ("quantity", models.IntegerField()),
                ("requested_due_date", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("OPEN", "Open (draft order)"),
                            ("CONFIRMED", "Confirmed; carries its serial (DEC-006 L-A)"),
                            ("REMOVED", "Removed from a draft (row kept, line_no never re-used)"),
                            ("CANCELLED", "Cancelled by a change request before release (DEC-059 C-A)"),
                        ],
                        db_default="OPEN",
                        max_length=12,
                    ),
                ),
                ("order_version", models.IntegerField(db_default=0)),
                ("cancel_reason", models.CharField(blank=True, max_length=500, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.customerorder",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.user",
                    ),
                ),
                (
                    "product_code",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.productcode",
                    ),
                ),
                (
                    "serial",
                    models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.serial",
                    ),
                ),
                (
                    "style",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.style",
                    ),
                ),
                (
                    "style_revision",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.stylerevision",
                    ),
                ),
                (
                    "uom",
                    models.ForeignKey(
                        db_column="uom_code",
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="platform_core.unitofmeasure",
                    ),
                ),
            ],
            options={
                "db_table": "commercial_customer_order_line",
            },
        ),
        migrations.AddIndex(
            model_name="coderulerevision",
            index=models.Index(fields=["evidence_document"], name="ix_icrr_evidence"),
        ),
        migrations.AddIndex(
            model_name="coderulerevision",
            index=models.Index(fields=["approval"], name="ix_icrr_approval"),
        ),
        migrations.AddIndex(
            model_name="coderulerevision",
            index=models.Index(fields=["approved_by"], name="ix_icrr_approved_by"),
        ),
        migrations.AddIndex(
            model_name="coderulerevision",
            index=models.Index(fields=["created_by"], name="ix_icrr_created_by"),
        ),
        migrations.AddIndex(
            model_name="coderulerevision",
            index=models.Index(fields=["updated_by"], name="ix_icrr_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.UniqueConstraint(
                fields=("code_namespace", "revision_no"), name="uq_identity_code_rule_revision_no"
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "ACTIVE")),
                fields=("code_namespace",),
                name="uq_identity_code_rule_one_active",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(("code_namespace", "product_code")), name="ck_identity_code_rule_namespace"
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(("revision_no__gte", 1)), name="ck_identity_code_rule_revision_pos"
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=django.db.models.lookups.Exact(
                    models.Func(models.F("scope"), function="jsonb_typeof", output_field=models.CharField()),
                    models.Value("object"),
                ),
                name="ck_identity_code_rule_scope_object",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=django.db.models.lookups.Exact(
                    models.Func(
                        models.F("rule_spec"), function="jsonb_typeof", output_field=models.CharField()
                    ),
                    models.Value("object"),
                ),
                name="ck_identity_code_rule_spec_object",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(("source_workbook_sha256__regex", "^[0-9a-f]{64}$")),
                name="ck_identity_code_rule_sha256_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(("golden_case_count__gte", 0)), name="ck_identity_code_rule_golden_nonneg"
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("status__in", ["DRAFT", "IN_REVIEW", "APPROVED", "ACTIVE", "RETIRED", "REJECTED"])
                ),
                name="ck_identity_code_rule_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(("decision_id__regex", "^DEC-[0-9]{3}$")),
                name="ck_identity_code_rule_decision_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status__in", ["APPROVED", "ACTIVE", "RETIRED"]), _negated=True),
                    models.Q(
                        ("approved_at__isnull", False),
                        ("approved_by__isnull", False),
                        ("created_by__isnull", False),
                        models.Q(("approved_by", models.F("created_by")), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="ck_identity_code_rule_approved_by_other",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_code_rule_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="coderulegoldencase",
            index=models.Index(fields=["rule_revision", "product_type_code"], name="ix_igld_family"),
        ),
        migrations.AddIndex(
            model_name="coderulegoldencase",
            index=models.Index(fields=["verified_by"], name="ix_igld_verified_by"),
        ),
        migrations.AddIndex(
            model_name="coderulegoldencase",
            index=models.Index(fields=["created_by"], name="ix_igld_created_by"),
        ),
        migrations.AddConstraint(
            model_name="coderulegoldencase",
            constraint=models.UniqueConstraint(
                fields=("rule_revision", "source_sheet", "source_cell_ref"),
                name="uq_identity_golden_case_source",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulegoldencase",
            constraint=models.CheckConstraint(
                condition=models.Q(("expected_code__regex", "^[0-9]{14}$")),
                name="ck_identity_golden_case_code_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulegoldencase",
            constraint=models.CheckConstraint(
                condition=models.Q(("product_type_code__regex", "^[0-9]{2}$")),
                name="ck_identity_golden_case_family_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulegoldencase",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("product_type_code", django.db.models.functions.text.Substr("expected_code", 3, 2))
                ),
                name="ck_identity_golden_case_family_segment",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulegoldencase",
            constraint=models.CheckConstraint(
                condition=django.db.models.lookups.Exact(
                    models.Func(models.F("inputs"), function="jsonb_typeof", output_field=models.CharField()),
                    models.Value("object"),
                ),
                name="ck_identity_golden_case_inputs_object",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulegoldencase",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("source_sheet", ""), _negated=True),
                    models.Q(("source_cell_ref", ""), _negated=True),
                ),
                name="ck_identity_golden_case_source",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulegoldencase",
            constraint=models.CheckConstraint(
                condition=models.Q(("source_workbook_sha256__regex", "^[0-9a-f]{64}$")),
                name="ck_identity_golden_case_sha256_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="coderulegoldencase",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("verified_at__isnull", True), ("verified_by__isnull", True)),
                    models.Q(("verified_at__isnull", False), ("verified_by__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_golden_case_verified_pair",
            ),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(
                django.db.models.functions.text.Lower("display_name_fa"), name="ix_icus_name_lower"
            ),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["import_batch"], name="ix_icus_prov_batch"),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["staging_row"], name="ix_icus_prov_row"),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["created_by"], name="ix_icus_created_by"),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["updated_by"], name="ix_icus_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(fields=("customer_no",), name="uq_identity_customer_no"),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("customer_no", ""), _negated=True),
                    ("customer_no", django.db.models.functions.text.Trim("customer_no")),
                ),
                name="ck_identity_customer_no_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.CheckConstraint(
                condition=models.Q(("display_name_fa", ""), _negated=True),
                name="ck_identity_customer_name_nonempty",
            ),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["ACTIVE", "INACTIVE"])), name="ck_identity_customer_status"
            ),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.CheckConstraint(
                condition=models.Q(("provenance_kind__in", ["SYS", "IMP", "LEG", "EXT"])),
                name="ck_identity_customer_prov_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind__in", ["IMP", "LEG"]), _negated=True),
                    models.Q(("import_batch__isnull", False), ("staging_row__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_customer_prov_imp_has_row",
            ),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind", "SYS"), _negated=True),
                    models.Q(("import_batch__isnull", True), ("staging_row__isnull", True)),
                    _connector="OR",
                ),
                name="ck_identity_customer_prov_sys_no_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("source_raw_value__isnull", True),
                    django.db.models.lookups.LessThanOrEqual(
                        django.db.models.functions.text.Length("source_raw_value"), 4000
                    ),
                    _connector="OR",
                ),
                name="ck_identity_customer_prov_raw_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_customer_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="customerbrand",
            index=models.Index(fields=["customer"], name="ix_ibrd_customer"),
        ),
        migrations.AddIndex(
            model_name="customerbrand",
            index=models.Index(fields=["import_batch"], name="ix_ibrd_prov_batch"),
        ),
        migrations.AddIndex(
            model_name="customerbrand",
            index=models.Index(fields=["staging_row"], name="ix_ibrd_prov_row"),
        ),
        migrations.AddIndex(
            model_name="customerbrand",
            index=models.Index(fields=["created_by"], name="ix_ibrd_created_by"),
        ),
        migrations.AddIndex(
            model_name="customerbrand",
            index=models.Index(fields=["updated_by"], name="ix_ibrd_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="customerbrand",
            constraint=models.UniqueConstraint(
                models.F("customer"),
                django.db.models.functions.text.Lower("brand_name_fa"),
                name="uq_identity_brand_customer_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerbrand",
            constraint=models.CheckConstraint(
                condition=models.Q(("brand_name_fa", ""), _negated=True),
                name="ck_identity_brand_name_nonempty",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerbrand",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["ACTIVE", "INACTIVE"])), name="ck_identity_brand_status"
            ),
        ),
        migrations.AddConstraint(
            model_name="customerbrand",
            constraint=models.CheckConstraint(
                condition=models.Q(("provenance_kind__in", ["SYS", "IMP", "LEG", "EXT"])),
                name="ck_identity_brand_prov_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerbrand",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind__in", ["IMP", "LEG"]), _negated=True),
                    models.Q(("import_batch__isnull", False), ("staging_row__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_brand_prov_imp_has_row",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerbrand",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind", "SYS"), _negated=True),
                    models.Q(("import_batch__isnull", True), ("staging_row__isnull", True)),
                    _connector="OR",
                ),
                name="ck_identity_brand_prov_sys_no_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerbrand",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("source_raw_value__isnull", True),
                    django.db.models.lookups.LessThanOrEqual(
                        django.db.models.functions.text.Length("source_raw_value"), 4000
                    ),
                    _connector="OR",
                ),
                name="ck_identity_brand_prov_raw_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerbrand",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_brand_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="externalreftype",
            index=models.Index(fields=["created_by"], name="ix_iert_created_by"),
        ),
        migrations.AddIndex(
            model_name="externalreftype",
            index=models.Index(fields=["updated_by"], name="ix_iert_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="externalreftype",
            constraint=models.CheckConstraint(
                condition=models.Q(("key__regex", "^[a-z][a-z0-9_]{2,63}$")),
                name="ck_identity_ext_ref_type_key_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalreftype",
            constraint=models.CheckConstraint(
                condition=models.Q(("label_fa", ""), _negated=True),
                name="ck_identity_ext_ref_type_label_nonempty",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalreftype",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["ACTIVE", "INACTIVE"])),
                name="ck_identity_ext_ref_type_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalreftype",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("decision_id", ""), ("decision_id__regex", "^DEC-[0-9]{3}$"), _connector="OR"
                ),
                name="ck_identity_ext_ref_type_decision_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalreftype",
            constraint=models.CheckConstraint(
                condition=models.Q(("provenance__in", ["SYS", "MIGRATION_SEED"])),
                name="ck_identity_ext_ref_type_provenance",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalreftype",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance", "MIGRATION_SEED"), _negated=True),
                    models.Q(("decision_id", ""), _negated=True),
                    _connector="OR",
                ),
                name="ck_identity_ext_ref_type_seed_has_decision",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalreftype",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_ext_ref_type_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="externalref",
            index=models.Index(fields=["system", "ref_type", "value"], name="ix_iext_lookup"),
        ),
        migrations.AddIndex(
            model_name="externalref",
            index=models.Index(fields=["target_type", "target_id"], name="ix_iext_target"),
        ),
        migrations.AddIndex(
            model_name="externalref",
            index=models.Index(fields=["ref_type"], name="ix_iext_type"),
        ),
        migrations.AddIndex(
            model_name="externalref",
            index=models.Index(fields=["import_batch"], name="ix_iext_prov_batch"),
        ),
        migrations.AddIndex(
            model_name="externalref",
            index=models.Index(fields=["staging_row"], name="ix_iext_prov_row"),
        ),
        migrations.AddIndex(
            model_name="externalref",
            index=models.Index(fields=["created_by"], name="ix_iext_created_by"),
        ),
        migrations.AddIndex(
            model_name="externalref",
            index=models.Index(fields=["updated_by"], name="ix_iext_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="externalref",
            constraint=models.UniqueConstraint(
                fields=("system", "ref_type", "value", "target_type", "target_id"),
                name="uq_identity_ext_ref_target_value",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalref",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "target_type__in",
                        ["customer", "product", "style", "customer_order", "order_line", "serial"],
                    )
                ),
                name="ck_identity_ext_ref_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalref",
            constraint=models.CheckConstraint(
                condition=models.Q(("system__in", ["RAHKARAN", "CUSTOMER", "LEGACY_PLANNING", "OTHER"])),
                name="ck_identity_ext_ref_system",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalref",
            constraint=models.CheckConstraint(
                condition=models.Q(("value", ""), _negated=True), name="ck_identity_ext_ref_value_nonempty"
            ),
        ),
        migrations.AddConstraint(
            model_name="externalref",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("valid_to__isnull", True), ("valid_to__gt", models.F("valid_from")), _connector="OR"
                ),
                name="ck_identity_ext_ref_validity",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalref",
            constraint=models.CheckConstraint(
                condition=models.Q(("provenance_kind__in", ["SYS", "IMP", "LEG", "EXT"])),
                name="ck_identity_ext_ref_prov_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalref",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind__in", ["IMP", "LEG"]), _negated=True),
                    models.Q(("import_batch__isnull", False), ("staging_row__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_ext_ref_prov_imp_has_row",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalref",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind", "SYS"), _negated=True),
                    models.Q(("import_batch__isnull", True), ("staging_row__isnull", True)),
                    _connector="OR",
                ),
                name="ck_identity_ext_ref_prov_sys_no_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalref",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("source_raw_value__isnull", True),
                    django.db.models.lookups.LessThanOrEqual(
                        django.db.models.functions.text.Length("source_raw_value"), 4000
                    ),
                    _connector="OR",
                ),
                name="ck_identity_ext_ref_prov_raw_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="externalref",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_ext_ref_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="orderchangerequest",
            index=models.Index(fields=["order", "status"], name="ix_ccr_order_status"),
        ),
        migrations.AddIndex(
            model_name="orderchangerequest",
            index=models.Index(fields=["approval"], name="ix_ccr_approval"),
        ),
        migrations.AddIndex(
            model_name="orderchangerequest",
            index=models.Index(fields=["planning_approval"], name="ix_ccr_planning_approval"),
        ),
        migrations.AddIndex(
            model_name="orderchangerequest",
            index=models.Index(fields=["requested_by"], name="ix_ccr_requested_by"),
        ),
        migrations.AddIndex(
            model_name="orderchangerequest",
            index=models.Index(fields=["decided_by"], name="ix_ccr_decided_by"),
        ),
        migrations.AddIndex(
            model_name="orderchangerequest",
            index=models.Index(fields=["planning_approved_by"], name="ix_ccr_planning_by"),
        ),
        migrations.AddIndex(
            model_name="orderchangerequest",
            index=models.Index(fields=["applied_by"], name="ix_ccr_applied_by"),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.UniqueConstraint(fields=("request_no",), name="uq_commercial_cr_request_no"),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("request_no", ""), _negated=True),
                    ("request_no", django.db.models.functions.text.Trim("request_no")),
                ),
                name="ck_commercial_cr_request_no_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(("base_order_version__gte", 1)), name="ck_commercial_cr_base_version_pos"
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "kind__in",
                        [
                            "QTY_CHANGE",
                            "DUE_DATE_CHANGE",
                            "ADD_LINE",
                            "CANCEL_LINE",
                            "CANCEL_ORDER",
                            "HOLD",
                            "RESUME",
                        ],
                    )
                ),
                name="ck_commercial_cr_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        ["DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "APPLIED", "WITHDRAWN", "EXPIRED"],
                    )
                ),
                name="ck_commercial_cr_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=django.db.models.lookups.Exact(
                    models.Func(models.F("items"), function="jsonb_typeof", output_field=models.CharField()),
                    models.Value("array"),
                ),
                name="ck_commercial_cr_items_array",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    django.db.models.lookups.GreaterThanOrEqual(
                        django.db.models.functions.text.Length("reason"), 3
                    )
                ),
                name="ck_commercial_cr_reason_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("impact__isnull", True),
                    django.db.models.lookups.Exact(
                        models.Func(
                            models.F("impact"), function="jsonb_typeof", output_field=models.CharField()
                        ),
                        models.Value("object"),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_cr_impact_object",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("decided_by__isnull", True),
                    models.Q(("decided_by", models.F("requested_by")), _negated=True),
                    _connector="OR",
                ),
                name="ck_commercial_cr_decider_not_requester",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("planning_approved_by__isnull", True),
                    models.Q(("planning_approved_by", models.F("requested_by")), _negated=True),
                    _connector="OR",
                ),
                name="ck_commercial_cr_planner_not_requester",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("decided_at__isnull", True), ("decided_by__isnull", True)),
                    models.Q(("decided_at__isnull", False), ("decided_by__isnull", False)),
                    _connector="OR",
                ),
                name="ck_commercial_cr_decided_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("planning_approved_at__isnull", True), ("planning_approved_by__isnull", True)),
                    models.Q(
                        ("planning_approved_at__isnull", False), ("planning_approved_by__isnull", False)
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_cr_planning_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("planning_approval__isnull", True), ("planning_approved_by__isnull", True)),
                    ("kind", "DUE_DATE_CHANGE"),
                    _connector="OR",
                ),
                name="ck_commercial_cr_planning_only_due_date",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status__in", ["SUBMITTED", "APPROVED", "APPLIED"]), _negated=True),
                    ("submitted_at__isnull", False),
                    _connector="OR",
                ),
                name="ck_commercial_cr_submitted_has_ts",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status__in", ["APPROVED", "REJECTED", "APPLIED"]), _negated=True),
                    ("decided_by__isnull", False),
                    _connector="OR",
                ),
                name="ck_commercial_cr_decided_has_decider",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "APPLIED"), _negated=True),
                    models.Q(
                        ("applied_at__isnull", False),
                        ("applied_by__isnull", False),
                        (
                            "applied_version",
                            django.db.models.expressions.CombinedExpression(
                                models.F("base_order_version"), "+", models.Value(1)
                            ),
                        ),
                        ("applied_version__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_cr_applied_next_version",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("status", "APPLIED"),
                    models.Q(
                        ("applied_at__isnull", True),
                        ("applied_by__isnull", True),
                        ("applied_version__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_cr_unapplied_empty",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderchangerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("kind", "DUE_DATE_CHANGE"), ("status", "APPLIED"), _negated=True),
                    ("planning_approved_by__isnull", False),
                    _connector="OR",
                ),
                name="ck_commercial_cr_due_date_planning_approved",
            ),
        ),
        migrations.AddIndex(
            model_name="customerorderversion",
            index=models.Index(fields=["change_request"], name="ix_cver_cr"),
        ),
        migrations.AddIndex(
            model_name="customerorderversion",
            index=models.Index(fields=["created_by"], name="ix_cver_by"),
        ),
        migrations.AddConstraint(
            model_name="customerorderversion",
            constraint=models.UniqueConstraint(
                fields=("order", "version"), name="uq_commercial_order_version_no"
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorderversion",
            constraint=models.CheckConstraint(
                condition=models.Q(("version__gte", 1)), name="ck_commercial_order_version_pos"
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorderversion",
            constraint=models.CheckConstraint(
                condition=django.db.models.lookups.Exact(
                    models.Func(models.F("image"), function="jsonb_typeof", output_field=models.CharField()),
                    models.Value("object"),
                ),
                name="ck_commercial_order_version_image",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorderversion",
            constraint=models.CheckConstraint(
                condition=models.Q(("reason__in", ["CONFIRMED", "CHANGE_APPLIED", "CANCELLED"])),
                name="ck_commercial_order_version_reason",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorderversion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("change_request__isnull", True), ("reason", "CONFIRMED"), ("version", 1)),
                    models.Q(
                        ("change_request__isnull", False),
                        ("version__gt", 1),
                        models.Q(("reason", "CONFIRMED"), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_order_version_reason_by_no",
            ),
        ),
        migrations.AddIndex(
            model_name="customerorder",
            index=models.Index(fields=["customer", "external_po_number"], name="ix_cord_customer_po"),
        ),
        migrations.AddIndex(
            model_name="customerorder",
            index=models.Index(fields=["brand"], name="ix_cord_brand"),
        ),
        migrations.AddIndex(
            model_name="customerorder",
            index=models.Index(fields=["order_type"], name="ix_cord_type"),
        ),
        migrations.AddIndex(
            model_name="customerorder",
            index=models.Index(fields=["status", "order_date"], name="ix_cord_status"),
        ),
        migrations.AddIndex(
            model_name="customerorder",
            index=models.Index(fields=["confirmed_by"], name="ix_cord_confirmed_by"),
        ),
        migrations.AddIndex(
            model_name="customerorder",
            index=models.Index(fields=["released_by"], name="ix_cord_released_by"),
        ),
        migrations.AddIndex(
            model_name="customerorder",
            index=models.Index(fields=["created_by"], name="ix_cord_created_by"),
        ),
        migrations.AddIndex(
            model_name="customerorder",
            index=models.Index(fields=["updated_by"], name="ix_cord_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.UniqueConstraint(fields=("order_no",), name="uq_commercial_order_no"),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("order_no", ""), _negated=True),
                    ("order_no", django.db.models.functions.text.Trim("order_no")),
                ),
                name="ck_commercial_order_no_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        [
                            "DRAFT",
                            "VALIDATED",
                            "CONFIRMED",
                            "RELEASED_TO_PLAN",
                            "ON_HOLD",
                            "CANCELLED",
                            "PARTIAL_FULFILLED",
                            "FULFILLED",
                            "CLOSED",
                        ],
                    )
                ),
                name="ck_commercial_order_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("requested_due_date__isnull", True),
                    ("requested_due_date__gte", models.F("order_date")),
                    _connector="OR",
                ),
                name="ck_commercial_order_due_after_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("hold_reason__isnull", False),
                        ("status", "ON_HOLD"),
                        ("status_before_hold__in", ("CONFIRMED", "RELEASED_TO_PLAN")),
                        ("status_before_hold__isnull", False),
                        django.db.models.lookups.GreaterThanOrEqual(
                            django.db.models.functions.text.Length("hold_reason"), 3
                        ),
                    ),
                    models.Q(
                        models.Q(("status", "ON_HOLD"), _negated=True),
                        ("hold_reason__isnull", True),
                        ("status_before_hold__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_order_hold_consistent",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "CANCELLED"), _negated=True),
                    models.Q(
                        ("cancel_reason__isnull", False),
                        ("cancelled_at__isnull", False),
                        django.db.models.lookups.GreaterThanOrEqual(
                            django.db.models.functions.text.Length("cancel_reason"), 3
                        ),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_order_cancel_has_reason",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(("current_version__gte", 0)), name="ck_commercial_order_version_nonneg"
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status__in", ("DRAFT", "VALIDATED")), _negated=True),
                    models.Q(("confirmed_by__isnull", True), ("current_version", 0)),
                    _connector="OR",
                ),
                name="ck_commercial_order_draft_unversioned",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("status__in", ["DRAFT", "VALIDATED", "CANCELLED"]),
                    models.Q(
                        ("confirmed_at__isnull", False),
                        ("confirmed_by__isnull", False),
                        ("current_version__gte", 1),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_order_confirmed_versioned",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("current_version__gte", 1), ("status", "CANCELLED"), _negated=True),
                    ("confirmed_by__isnull", False),
                    _connector="OR",
                ),
                name="ck_commercial_order_cancel_after_confirm",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("confirmed_by__isnull", True),
                    models.Q(
                        ("created_by__isnull", False),
                        models.Q(("confirmed_by", models.F("created_by")), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_order_confirmer_not_creator",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        models.Q(("status", "RELEASED_TO_PLAN"), _negated=True),
                        models.Q(("status_before_hold", "RELEASED_TO_PLAN"), _negated=True),
                    ),
                    models.Q(("released_at__isnull", False), ("released_by__isnull", False)),
                    _connector="OR",
                ),
                name="ck_commercial_order_released_has_actor",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("customer_representative_name__isnull", True),
                    models.Q(("customer_representative_name", ""), _negated=True),
                    _connector="OR",
                ),
                name="ck_commercial_order_rep_name_nonempty",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorder",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_commercial_order_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(django.db.models.functions.text.Lower("name_fa"), name="ix_iprd_name_lower"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["import_batch"], name="ix_iprd_prov_batch"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["staging_row"], name="ix_iprd_prov_row"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["created_by"], name="ix_iprd_created_by"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["updated_by"], name="ix_iprd_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(
                fields=("product_type", "product_no"), name="uq_identity_product_type_no"
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("product_no__regex", "^[0-9]{4}$")), name="ck_identity_product_no_fmt"
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("name_fa", ""), _negated=True), name="ck_identity_product_name_nonempty"
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("belt_width_code__isnull", True), ("buckle_type_code__isnull", True)),
                    models.Q(
                        ("belt_width_code__isnull", False),
                        ("belt_width_code__regex", "^[0-9]{2}$"),
                        ("buckle_type_code__isnull", False),
                        ("buckle_type_code__regex", "^[0-9]{2}$"),
                        (
                            "product_no",
                            django.db.models.functions.text.Concat(
                                models.F("buckle_type_code"), models.F("belt_width_code")
                            ),
                        ),
                    ),
                    _connector="OR",
                ),
                name="ck_identity_product_belt_no",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["DRAFT", "ACTIVE", "RETIRED"])),
                name="ck_identity_product_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("provenance_kind__in", ["SYS", "IMP", "LEG", "EXT"])),
                name="ck_identity_product_prov_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind__in", ["IMP", "LEG"]), _negated=True),
                    models.Q(("import_batch__isnull", False), ("staging_row__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_product_prov_imp_has_row",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind", "SYS"), _negated=True),
                    models.Q(("import_batch__isnull", True), ("staging_row__isnull", True)),
                    _connector="OR",
                ),
                name="ck_identity_product_prov_sys_no_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("source_raw_value__isnull", True),
                    django.db.models.lookups.LessThanOrEqual(
                        django.db.models.functions.text.Length("source_raw_value"), 4000
                    ),
                    _connector="OR",
                ),
                name="ck_identity_product_prov_raw_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_product_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="serialsnapshot",
            index=models.Index(fields=["change_request_id"], name="ix_isnp_cr"),
        ),
        migrations.AddIndex(
            model_name="serialsnapshot",
            index=models.Index(fields=["created_by"], name="ix_isnp_created_by"),
        ),
        migrations.AddConstraint(
            model_name="serialsnapshot",
            constraint=models.UniqueConstraint(
                fields=("serial", "version"), name="uq_identity_serial_snapshot_version"
            ),
        ),
        migrations.AddConstraint(
            model_name="serialsnapshot",
            constraint=models.CheckConstraint(
                condition=models.Q(("version__gte", 1)), name="ck_identity_serial_snapshot_version_pos"
            ),
        ),
        migrations.AddConstraint(
            model_name="serialsnapshot",
            constraint=models.CheckConstraint(
                condition=models.Q(("order_version__gte", 1)),
                name="ck_identity_serial_snapshot_order_version",
            ),
        ),
        migrations.AddConstraint(
            model_name="serialsnapshot",
            constraint=models.CheckConstraint(
                condition=django.db.models.lookups.Exact(
                    models.Func(
                        models.F("snapshot"), function="jsonb_typeof", output_field=models.CharField()
                    ),
                    models.Value("object"),
                ),
                name="ck_identity_serial_snapshot_image_object",
            ),
        ),
        migrations.AddConstraint(
            model_name="serialsnapshot",
            constraint=models.CheckConstraint(
                condition=models.Q(("reason__in", ["ALLOCATED", "CHANGE_APPLIED", "TECH_PACKAGE_LINKED"])),
                name="ck_identity_serial_snapshot_reason",
            ),
        ),
        migrations.AddConstraint(
            model_name="serialsnapshot",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("reason", "ALLOCATED"), ("version", 1)),
                    models.Q(("version__gt", 1), models.Q(("reason", "ALLOCATED"), _negated=True)),
                    _connector="OR",
                ),
                name="ck_identity_serial_snapshot_v1_allocated",
            ),
        ),
        migrations.AddConstraint(
            model_name="serialsnapshot",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("reason", "CHANGE_APPLIED"), _negated=True),
                    ("change_request_id__isnull", False),
                    _connector="OR",
                ),
                name="ck_identity_serial_snapshot_change_has_cr",
            ),
        ),
        migrations.AddIndex(
            model_name="style",
            index=models.Index(fields=["category"], name="ix_isty_category"),
        ),
        migrations.AddIndex(
            model_name="style",
            index=models.Index(django.db.models.functions.text.Lower("name_fa"), name="ix_isty_name_lower"),
        ),
        migrations.AddIndex(
            model_name="style",
            index=models.Index(fields=["import_batch"], name="ix_isty_prov_batch"),
        ),
        migrations.AddIndex(
            model_name="style",
            index=models.Index(fields=["staging_row"], name="ix_isty_prov_row"),
        ),
        migrations.AddIndex(
            model_name="style",
            index=models.Index(fields=["created_by"], name="ix_isty_created_by"),
        ),
        migrations.AddIndex(
            model_name="style",
            index=models.Index(fields=["updated_by"], name="ix_isty_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="style",
            constraint=models.UniqueConstraint(
                fields=("product", "category", "style_no"), name="uq_identity_style_product_category_no"
            ),
        ),
        migrations.AddConstraint(
            model_name="style",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("style_no__regex", "^[0-9]{4}$"), models.Q(("style_no", "0000"), _negated=True)
                ),
                name="ck_identity_style_no_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="style",
            constraint=models.CheckConstraint(
                condition=models.Q(("name_fa", ""), _negated=True), name="ck_identity_style_name_nonempty"
            ),
        ),
        migrations.AddConstraint(
            model_name="style",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["DRAFT", "ACTIVE", "RETIRED"])),
                name="ck_identity_style_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="style",
            constraint=models.CheckConstraint(
                condition=models.Q(("provenance_kind__in", ["SYS", "IMP", "LEG", "EXT"])),
                name="ck_identity_style_prov_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="style",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind__in", ["IMP", "LEG"]), _negated=True),
                    models.Q(("import_batch__isnull", False), ("staging_row__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_style_prov_imp_has_row",
            ),
        ),
        migrations.AddConstraint(
            model_name="style",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind", "SYS"), _negated=True),
                    models.Q(("import_batch__isnull", True), ("staging_row__isnull", True)),
                    _connector="OR",
                ),
                name="ck_identity_style_prov_sys_no_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="style",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("source_raw_value__isnull", True),
                    django.db.models.lookups.LessThanOrEqual(
                        django.db.models.functions.text.Length("source_raw_value"), 4000
                    ),
                    _connector="OR",
                ),
                name="ck_identity_style_prov_raw_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="style",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_style_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="productcode",
            index=models.Index(fields=["style"], name="ix_ipcd_style"),
        ),
        migrations.AddIndex(
            model_name="productcode",
            index=models.Index(fields=["rule_revision"], name="ix_ipcd_rule"),
        ),
        migrations.AddIndex(
            model_name="productcode",
            index=models.Index(fields=["erp_seen_batch"], name="ix_ipcd_erp_batch"),
        ),
        migrations.AddIndex(
            model_name="productcode",
            index=models.Index(fields=["issued_by"], name="ix_ipcd_issued_by"),
        ),
        migrations.AddIndex(
            model_name="productcode",
            index=models.Index(fields=["status", "erp_status"], name="ix_ipcd_status"),
        ),
        migrations.AddIndex(
            model_name="productcode",
            index=models.Index(fields=["import_batch"], name="ix_ipcd_prov_batch"),
        ),
        migrations.AddIndex(
            model_name="productcode",
            index=models.Index(fields=["staging_row"], name="ix_ipcd_prov_row"),
        ),
        migrations.AddIndex(
            model_name="productcode",
            index=models.Index(fields=["created_by"], name="ix_ipcd_created_by"),
        ),
        migrations.AddIndex(
            model_name="productcode",
            index=models.Index(fields=["updated_by"], name="ix_ipcd_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.UniqueConstraint(
                fields=("code_namespace", "code"), name="uq_identity_product_code_ns_code"
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.UniqueConstraint(
                fields=("issue_idempotency_key",), name="uq_identity_product_code_issue_key"
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(("code__regex", "^[0-9]{14}$")), name="ck_identity_product_code_fmt"
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(("code_namespace", "product_code")),
                name="ck_identity_product_code_namespace",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["RESERVED", "ACTIVE", "RETIRED", "DISPUTED"])),
                name="ck_identity_product_code_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(("erp_status__in", ["ERP_PENDING", "ERP_MATCHED", "ERP_MISSING"])),
                name="ck_identity_product_code_erp_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "ACTIVE"), _negated=True),
                    ("erp_status", "ERP_MATCHED"),
                    _connector="OR",
                ),
                name="ck_identity_product_code_active_matched",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "RESERVED"), _negated=True),
                    ("erp_status", "ERP_PENDING"),
                    _connector="OR",
                ),
                name="ck_identity_product_code_reserved_pending",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("erp_status", "ERP_MATCHED"), _negated=True),
                    ("erp_seen_batch__isnull", False),
                    _connector="OR",
                ),
                name="ck_identity_product_code_matched_has_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind", "SYS"), _negated=True),
                    models.Q(
                        ("code__startswith", "02"),
                        ("issue_idempotency_key__isnull", False),
                        ("issued_at__isnull", False),
                        ("issued_by__isnull", False),
                        ("rule_revision__isnull", False),
                        ("style__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="ck_identity_product_code_sys_issued",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(("provenance_kind__in", ["SYS", "IMP", "LEG", "EXT"])),
                name="ck_identity_product_code_prov_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind__in", ["IMP", "LEG"]), _negated=True),
                    models.Q(("import_batch__isnull", False), ("staging_row__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_product_code_prov_imp_has_row",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind", "SYS"), _negated=True),
                    models.Q(("import_batch__isnull", True), ("staging_row__isnull", True)),
                    _connector="OR",
                ),
                name="ck_identity_product_code_prov_sys_no_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("source_raw_value__isnull", True),
                    django.db.models.lookups.LessThanOrEqual(
                        django.db.models.functions.text.Length("source_raw_value"), 4000
                    ),
                    _connector="OR",
                ),
                name="ck_identity_product_code_prov_raw_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="productcode",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_product_code_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="historicalorderrecord",
            index=models.Index(fields=["legacy_serial_text"], name="ix_ihst_serial"),
        ),
        migrations.AddIndex(
            model_name="historicalorderrecord",
            index=models.Index(fields=["normalised_product_code"], name="ix_ihst_code"),
        ),
        migrations.AddIndex(
            model_name="historicalorderrecord",
            index=models.Index(fields=["matched_style"], name="ix_ihst_style"),
        ),
        migrations.AddIndex(
            model_name="historicalorderrecord",
            index=models.Index(fields=["matched_product_code"], name="ix_ihst_pcode"),
        ),
        migrations.AddIndex(
            model_name="historicalorderrecord",
            index=models.Index(fields=["matched_by"], name="ix_ihst_matched_by"),
        ),
        migrations.AddIndex(
            model_name="historicalorderrecord",
            index=models.Index(fields=["import_batch"], name="ix_ihst_batch"),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.UniqueConstraint(
                fields=("staging_row",), name="uq_identity_historical_staging_row"
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("provenance_kind", "LEG")), name="ck_identity_historical_is_legacy"
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("normalised_product_code__regex", "^[0-9]{14}$")),
                name="ck_identity_historical_code_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("code_flag__in", ["OK", "DISPUTED", "ABSENT"])),
                name="ck_identity_historical_code_flag",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("code_flag", "OK"), _negated=True),
                    ("normalised_product_code__isnull", False),
                    _connector="OR",
                ),
                name="ck_identity_historical_ok_has_code",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("code_flag", "ABSENT"), _negated=True),
                    models.Q(
                        ("legacy_product_code_raw__isnull", True), ("normalised_product_code__isnull", True)
                    ),
                    _connector="OR",
                ),
                name="ck_identity_historical_absent_has_none",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("code_flag", "DISPUTED"), _negated=True),
                    ("legacy_product_code_raw__isnull", False),
                    _connector="OR",
                ),
                name="ck_identity_historical_disputed_has_raw",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("legacy_serial_value__isnull", True),
                    models.Q(
                        (
                            "legacy_serial_text",
                            django.db.models.functions.comparison.Cast(
                                models.F("legacy_serial_value"), output_field=models.CharField()
                            ),
                        ),
                        ("legacy_serial_text__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="ck_identity_historical_serial_value_is_text",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("legacy_serial_text__isnull", True),
                    models.Q(("legacy_serial_text__regex", "^[1-9][0-9]{0,17}$"), _negated=True),
                    ("legacy_serial_value__isnull", False),
                    _connector="OR",
                ),
                name="ck_identity_historical_plain_serial_has_value",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=django.db.models.lookups.Exact(
                    models.Func(
                        models.F("payload"), function="jsonb_typeof", output_field=models.CharField()
                    ),
                    models.Value("object"),
                ),
                name="ck_identity_historical_payload_object",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("match_status__in", ["UNMATCHED", "SUGGESTED", "CONFIRMED", "REJECTED"])),
                name="ck_identity_historical_match_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("match_status__in", ["CONFIRMED", "REJECTED"]), _negated=True),
                    models.Q(("matched_at__isnull", False), ("matched_by__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_historical_decided_has_actor",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("match_status", "CONFIRMED"), _negated=True),
                    ("matched_style__isnull", False),
                    _connector="OR",
                ),
                name="ck_identity_historical_confirmed_has_style",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("provenance_kind__in", ["SYS", "IMP", "LEG", "EXT"])),
                name="ck_identity_historical_prov_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind__in", ["IMP", "LEG"]), _negated=True),
                    models.Q(("import_batch__isnull", False), ("staging_row__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_historical_prov_imp_has_row",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind", "SYS"), _negated=True),
                    models.Q(("import_batch__isnull", True), ("staging_row__isnull", True)),
                    _connector="OR",
                ),
                name="ck_identity_historical_prov_sys_no_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("source_raw_value__isnull", True),
                    django.db.models.lookups.LessThanOrEqual(
                        django.db.models.functions.text.Length("source_raw_value"), 4000
                    ),
                    _connector="OR",
                ),
                name="ck_identity_historical_prov_raw_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicalorderrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_historical_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="stylerevision",
            index=models.Index(fields=["created_by"], name="ix_isrv_created_by"),
        ),
        migrations.AddIndex(
            model_name="stylerevision",
            index=models.Index(fields=["updated_by"], name="ix_isrv_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="stylerevision",
            constraint=models.UniqueConstraint(
                fields=("style", "revision_no"), name="uq_identity_style_revision_no"
            ),
        ),
        migrations.AddConstraint(
            model_name="stylerevision",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "ACTIVE")),
                fields=("style",),
                name="uq_identity_style_revision_one_active",
            ),
        ),
        migrations.AddConstraint(
            model_name="stylerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(("revision_no__gte", 1)), name="ck_identity_style_revision_no_pos"
            ),
        ),
        migrations.AddConstraint(
            model_name="stylerevision",
            constraint=models.CheckConstraint(
                condition=django.db.models.lookups.Exact(
                    models.Func(
                        models.F("attributes"), function="jsonb_typeof", output_field=models.CharField()
                    ),
                    models.Value("object"),
                ),
                name="ck_identity_style_revision_attrs_object",
            ),
        ),
        migrations.AddConstraint(
            model_name="stylerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["DRAFT", "ACTIVE", "SUPERSEDED"])),
                name="ck_identity_style_revision_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="stylerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_style_revision_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="serial",
            index=models.Index(fields=["customer"], name="ix_iser_customer"),
        ),
        migrations.AddIndex(
            model_name="serial",
            index=models.Index(fields=["style"], name="ix_iser_style"),
        ),
        migrations.AddIndex(
            model_name="serial",
            index=models.Index(fields=["style_revision"], name="ix_iser_style_revision"),
        ),
        migrations.AddIndex(
            model_name="serial",
            index=models.Index(fields=["product_code"], name="ix_iser_product_code"),
        ),
        migrations.AddIndex(
            model_name="serial",
            index=models.Index(fields=["allocated_by"], name="ix_iser_allocated_by"),
        ),
        migrations.AddIndex(
            model_name="serial",
            index=models.Index(fields=["allocated_at"], name="ix_iser_allocated_at"),
        ),
        migrations.AddConstraint(
            model_name="serial",
            constraint=models.UniqueConstraint(
                fields=("serial_counter", "serial_number"), name="uq_identity_serial_number"
            ),
        ),
        migrations.AddConstraint(
            model_name="serial",
            constraint=models.UniqueConstraint(
                fields=("serial_counter", "serial_value"), name="uq_identity_serial_value"
            ),
        ),
        migrations.AddConstraint(
            model_name="serial",
            constraint=models.UniqueConstraint(
                fields=("allocation_idempotency_key",), name="uq_identity_serial_allocation_key"
            ),
        ),
        migrations.AddConstraint(
            model_name="serial",
            constraint=models.CheckConstraint(
                condition=models.Q(("serial_number__regex", "^[1-9][0-9]*$")),
                name="ck_identity_serial_number_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="serial",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "serial_number",
                        django.db.models.functions.comparison.Cast(
                            models.F("serial_value"), output_field=models.CharField()
                        ),
                    )
                ),
                name="ck_identity_serial_number_is_value",
            ),
        ),
        migrations.AddConstraint(
            model_name="serial",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        [
                            "ALLOCATED",
                            "CANCELLED",
                            "IN_PRODUCTION",
                            "PARTIALLY_DELIVERED",
                            "DELIVERED",
                            "CLOSED",
                        ],
                    )
                ),
                name="ck_identity_serial_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="serial",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "CANCELLED"), _negated=True),
                    models.Q(
                        ("cancel_reason__isnull", False),
                        ("cancelled_at__isnull", False),
                        django.db.models.lookups.GreaterThanOrEqual(
                            django.db.models.functions.text.Length("cancel_reason"), 3
                        ),
                    ),
                    _connector="OR",
                ),
                name="ck_identity_serial_cancel_has_reason",
            ),
        ),
        migrations.AddConstraint(
            model_name="serial",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_serial_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="productclass",
            index=models.Index(fields=["parent"], name="ix_icls_parent"),
        ),
        migrations.AddIndex(
            model_name="productclass",
            index=models.Index(fields=["uom"], name="ix_icls_uom"),
        ),
        migrations.AddIndex(
            model_name="productclass",
            index=models.Index(fields=["import_batch"], name="ix_icls_prov_batch"),
        ),
        migrations.AddIndex(
            model_name="productclass",
            index=models.Index(fields=["staging_row"], name="ix_icls_prov_row"),
        ),
        migrations.AddIndex(
            model_name="productclass",
            index=models.Index(fields=["created_by"], name="ix_icls_created_by"),
        ),
        migrations.AddIndex(
            model_name="productclass",
            index=models.Index(fields=["updated_by"], name="ix_icls_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.UniqueConstraint(
                condition=models.Q(("level_key", "product_type")),
                fields=("segment_value",),
                name="uq_identity_class_type_segment",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.UniqueConstraint(
                condition=models.Q(("level_key", "category")),
                fields=("parent", "segment_value"),
                name="uq_identity_class_category_segment",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(("level_key__in", ["product_type", "category"])),
                name="ck_identity_class_level",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("level_key", "product_type"), ("parent__isnull", True)),
                    models.Q(("level_key", "category"), ("parent__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_class_parent_by_level",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("level_key", "product_type"),
                        ("product_no_scheme__isnull", False),
                        ("uom__isnull", False),
                    ),
                    models.Q(
                        ("level_key", "category"), ("product_no_scheme__isnull", True), ("uom__isnull", True)
                    ),
                    _connector="OR",
                ),
                name="ck_identity_class_type_attributes",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("product_no_scheme__isnull", True),
                    ("product_no_scheme__in", ["SEQUENTIAL_PER_TYPE", "BELT_BUCKLE_WIDTH"]),
                    _connector="OR",
                ),
                name="ck_identity_class_scheme",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(("segment_value__regex", "^[0-9]{2}$")),
                name="ck_identity_class_segment_fmt",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(("label_fa", ""), _negated=True), name="ck_identity_class_label_nonempty"
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(("parent", models.F("id")), _negated=True),
                name="ck_identity_class_not_own_parent",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["DRAFT", "ACTIVE", "RETIRED"])),
                name="ck_identity_class_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(("provenance_kind__in", ["SYS", "IMP", "LEG", "EXT"])),
                name="ck_identity_class_prov_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind__in", ["IMP", "LEG"]), _negated=True),
                    models.Q(("import_batch__isnull", False), ("staging_row__isnull", False)),
                    _connector="OR",
                ),
                name="ck_identity_class_prov_imp_has_row",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("provenance_kind", "SYS"), _negated=True),
                    models.Q(("import_batch__isnull", True), ("staging_row__isnull", True)),
                    _connector="OR",
                ),
                name="ck_identity_class_prov_sys_no_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("source_raw_value__isnull", True),
                    django.db.models.lookups.LessThanOrEqual(
                        django.db.models.functions.text.Length("source_raw_value"), 4000
                    ),
                    _connector="OR",
                ),
                name="ck_identity_class_prov_raw_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="productclass",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_identity_class_row_version_pos"
            ),
        ),
        migrations.AddIndex(
            model_name="customerorderline",
            index=models.Index(fields=["style"], name="ix_clin_style"),
        ),
        migrations.AddIndex(
            model_name="customerorderline",
            index=models.Index(fields=["style_revision"], name="ix_clin_style_revision"),
        ),
        migrations.AddIndex(
            model_name="customerorderline",
            index=models.Index(fields=["product_code"], name="ix_clin_product_code"),
        ),
        migrations.AddIndex(
            model_name="customerorderline",
            index=models.Index(fields=["uom"], name="ix_clin_uom"),
        ),
        migrations.AddIndex(
            model_name="customerorderline",
            index=models.Index(fields=["created_by"], name="ix_clin_created_by"),
        ),
        migrations.AddIndex(
            model_name="customerorderline",
            index=models.Index(fields=["updated_by"], name="ix_clin_updated_by"),
        ),
        migrations.AddConstraint(
            model_name="customerorderline",
            constraint=models.UniqueConstraint(
                fields=("order", "line_no"), name="uq_commercial_line_order_no"
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorderline",
            constraint=models.UniqueConstraint(fields=("serial",), name="uq_commercial_line_serial"),
        ),
        migrations.AddConstraint(
            model_name="customerorderline",
            constraint=models.CheckConstraint(
                condition=models.Q(("line_no__gte", 1)), name="ck_commercial_line_no_pos"
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorderline",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity__gt", 0)), name="ck_commercial_line_quantity_pos"
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorderline",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["OPEN", "CONFIRMED", "REMOVED", "CANCELLED"])),
                name="ck_commercial_line_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorderline",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("order_version", 0), ("serial__isnull", True), ("status__in", ["OPEN", "REMOVED"])
                    ),
                    models.Q(("order_version__gte", 1), ("serial__isnull", False), ("status", "CONFIRMED")),
                    models.Q(("order_version__gte", 1), ("serial__isnull", False), ("status", "CANCELLED")),
                    _connector="OR",
                ),
                name="ck_commercial_line_serial_by_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorderline",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "CANCELLED"), _negated=True),
                    models.Q(
                        ("cancel_reason__isnull", False),
                        django.db.models.lookups.GreaterThanOrEqual(
                            django.db.models.functions.text.Length("cancel_reason"), 3
                        ),
                    ),
                    _connector="OR",
                ),
                name="ck_commercial_line_cancel_has_reason",
            ),
        ),
        migrations.AddConstraint(
            model_name="customerorderline",
            constraint=models.CheckConstraint(
                condition=models.Q(("row_version__gte", 1)), name="ck_commercial_line_row_version_pos"
            ),
        ),
    ]
