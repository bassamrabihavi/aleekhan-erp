"""Identity module tables (PHASE_02 / 02.2): customers, product classes, products, styles, 14-digit product
codes, the factory serial counter, serials and their snapshots, external references, legacy history.

Design: docs/discovery/DATA_TABLE.md (PHASE_02 section), STATE_TRANSITIONS.md section 5, docs/db/ERD.md
section 7. Decisions built in (control/decisions/DECISION_LOG.md, all APPROVED 2026-11-12):

* DEC-005: Code14 = ``"02"`` + product-type code (2) + category code (2) + product number (4) + style
  number (4).
  The segments are columns: ``ProductClass.segment_value`` (type / category, 2 digits), ``Product.product_no``
  and ``Style.style_no`` (4 digits). A belt product number is buckle-type code (2) + width (2). A code row in
  the registry is RESERVED / ERP_PENDING until the Rahkaran import shows it (B1: nothing is written to
  Rahkaran). Legacy codes that are not 14 digits stay as history text (``HistoricalOrderRecord``, DISPUTED),
  never auto-fixed. **No type, category or code value is seeded**: they come from the private source through
  the server import, never from Git.
* DEC-006: one factory-wide counter (``SerialCounter``, S-A), first serial 63001 (seed), gapless (G-B): the
  number is drawn under ``SELECT ... FOR UPDATE`` of the counter row inside the confirm transaction, never a
  DB sequence, never ``MAX()+1``; a rolled back confirm consumes nothing. New serials are plain integer text
  (``^[1-9][0-9]*$``); legacy shapes are history text only.
* DEC-058: brands under the customer (1:N); typed external references (system + type), types extensible.
* REV-0201 (ownership): Identity owns ``identity_serial`` and ``identity_serial_snapshot``. The Commercial
  order
  line points to its serial with a UNIQUE FK (``commercial_customer_order_line.serial_id``); Identity has no
  mirror column. Each module writes only its own tables inside one unit of work; the DB checks the pairing at
  commit (deferred constraint triggers, migration 0020).

Triggers, deferred constraint triggers and FK/index renaming: migration 0020 (``0020_phase02_db_guards``).
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint
from django.db.models.functions import Cast, Concat, Lower, Now, Substr

from platform_core.code14 import Code14Field, code14_check_constraint
from platform_core.models import _json_is_object
from platform_core.schema_common import (
    DECISION_ID_PATTERN,
    SHA256_PATTERN,
    SYSTEM_KEY_PATTERN,
    Provenance,
    ProvenanceKind,
    SourceProvenance,
    in_values,
    min_length,
    provenance_constraints,
    provenance_indexes,
    trimmed_nonempty,
)

TWO_DIGITS = r"^[0-9]{2}$"
FOUR_DIGITS = r"^[0-9]{4}$"
# DEC-006: a serial issued by the system is a plain integer as text (no prefix, no leading zero, no check
# digit)
SERIAL_NUMBER_PATTERN = r"^[1-9][0-9]*$"
FACTORY_SERIAL_NAMESPACE = "factory_serial"  # DEC-006 S-A: the single factory-wide namespace
PRODUCT_CODE_NAMESPACE = "product_code"


def _user_fk(*, null: bool = True) -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        "platform_core.User",
        on_delete=models.PROTECT,
        null=null,
        blank=null,
        related_name="+",
        db_index=False,
    )


def _fk(to: str, *, null: bool = False, db_column: str | None = None) -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        to,
        on_delete=models.PROTECT,
        null=null,
        blank=null,
        related_name="+",
        db_index=False,
        db_column=db_column,
    )


class AuditColumns(models.Model):
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk()
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        abstract = True


def _row_version(table: str) -> CheckConstraint:
    return CheckConstraint(condition=Q(row_version__gte=1), name=f"ck_{table}_row_version_pos")


def _audit_indexes(table: str) -> list[models.Index]:
    return [
        models.Index(fields=["created_by"], name=f"ix_{table}_created_by"),
        models.Index(fields=["updated_by"], name=f"ix_{table}_updated_by"),
    ]


# ------------------------------------------------------------------------------------------- catalogues
class UnitOfMeasure(models.Model):
    """Order units (DEC-058: shoe = pair, every other type = piece; a set counts as one piece). Seeded
    (0021)."""

    code = models.CharField(max_length=8, primary_key=True)
    label_fa = models.CharField(max_length=50)
    decision_id = models.CharField(max_length=7)
    provenance = models.CharField(max_length=16, choices=Provenance.choices, db_default=Provenance.SYS)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "identity_unit_of_measure"
        constraints = [
            CheckConstraint(condition=Q(code__regex=r"^[A-Z][A-Z_]{1,7}$"), name="ck_identity_uom_code_fmt"),
            CheckConstraint(condition=~Q(label_fa=""), name="ck_identity_uom_label_nonempty"),
            CheckConstraint(
                condition=Q(decision_id__regex=DECISION_ID_PATTERN), name="ck_identity_uom_decision_fmt"
            ),
            CheckConstraint(
                condition=in_values("provenance", [Provenance.SYS, Provenance.MIGRATION_SEED]),
                name="ck_identity_uom_provenance",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class MasterStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    RETIRED = "RETIRED", "Retired (never deleted)"


class PartyStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive (never deleted)"


# ------------------------------------------------------------------------------------------- customers
class Customer(SourceProvenance, AuditColumns):
    """Customer master (S2). No contact columns (DEC-028); the representative name lives on the order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_no = models.CharField(max_length=32)  # internal, system-generated technical number
    display_name_fa = models.CharField(max_length=200)
    legal_name_fa = models.CharField(max_length=300, null=True, blank=True)
    status = models.CharField(max_length=8, choices=PartyStatus.choices, db_default=PartyStatus.ACTIVE)
    default_required_quality_ref = models.CharField(max_length=64, null=True, blank=True)  # text (DEC-058)

    class Meta:
        db_table = "identity_customer"
        constraints = [
            UniqueConstraint(fields=["customer_no"], name="uq_identity_customer_no"),
            CheckConstraint(condition=trimmed_nonempty("customer_no"), name="ck_identity_customer_no_fmt"),
            CheckConstraint(condition=~Q(display_name_fa=""), name="ck_identity_customer_name_nonempty"),
            CheckConstraint(
                condition=in_values("status", PartyStatus.values), name="ck_identity_customer_status"
            ),
            *provenance_constraints("identity_customer"),
            _row_version("identity_customer"),
        ]
        indexes = [
            # duplicate WARNING only (engine check, acknowledged by the user); never a unique merge key
            models.Index(Lower("display_name_fa"), name="ix_icus_name_lower"),
            *provenance_indexes("icus"),
            *_audit_indexes("icus"),
        ]

    def __str__(self) -> str:
        return self.customer_no


class CustomerBrand(SourceProvenance, AuditColumns):
    """DEC-058 B-A: one customer, many brands; the brand on an order is optional."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = _fk("platform_core.Customer")
    brand_name_fa = models.CharField(max_length=200)
    status = models.CharField(max_length=8, choices=PartyStatus.choices, db_default=PartyStatus.ACTIVE)

    class Meta:
        db_table = "identity_customer_brand"
        constraints = [
            UniqueConstraint(F("customer"), Lower("brand_name_fa"), name="uq_identity_brand_customer_name"),
            CheckConstraint(condition=~Q(brand_name_fa=""), name="ck_identity_brand_name_nonempty"),
            CheckConstraint(
                condition=in_values("status", PartyStatus.values), name="ck_identity_brand_status"
            ),
            *provenance_constraints("identity_brand"),
            _row_version("identity_brand"),
        ]
        indexes = [
            models.Index(fields=["customer"], name="ix_ibrd_customer"),
            *provenance_indexes("ibrd"),
            *_audit_indexes("ibrd"),
        ]

    def __str__(self) -> str:
        return str(self.id)


# ------------------------------------------------------------------------------- product classification
class ClassLevel(models.TextChoices):
    PRODUCT_TYPE = "product_type", "Product type (code segment 2, the golden-test family, DEC-005 Q-C)"
    CATEGORY = "category", "Category within a product type (code segment 3)"


class ProductNoScheme(models.TextChoices):
    SEQUENTIAL_PER_TYPE = "SEQUENTIAL_PER_TYPE", "Largest product number of the type + 1 (DEC-005)"
    BELT_BUCKLE_WIDTH = "BELT_BUCKLE_WIDTH", "Buckle-type code (2) + belt width (2) (DEC-005, belt)"


class ProductClass(SourceProvenance, AuditColumns):
    """Product types (parent NULL) and their categories (parent = type), with their 2-digit code segments.

    Nothing is seeded: the list comes from the Planning ``Sorce`` sheet through the server import (DEC-005).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    level_key = models.CharField(max_length=16, choices=ClassLevel.choices)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    segment_value = models.CharField(max_length=2)
    label_fa = models.CharField(max_length=200)
    # product types only (DEC-058 units; DEC-005 product-number scheme)
    uom = _fk("platform_core.UnitOfMeasure", null=True, db_column="uom_code")
    product_no_scheme = models.CharField(
        max_length=24, choices=ProductNoScheme.choices, null=True, blank=True
    )
    status = models.CharField(max_length=8, choices=MasterStatus.choices, db_default=MasterStatus.DRAFT)

    class Meta:
        db_table = "identity_product_class"
        constraints = [
            UniqueConstraint(
                fields=["segment_value"],
                condition=Q(level_key=ClassLevel.PRODUCT_TYPE),
                name="uq_identity_class_type_segment",
            ),
            UniqueConstraint(
                fields=["parent", "segment_value"],
                condition=Q(level_key=ClassLevel.CATEGORY),
                name="uq_identity_class_category_segment",
            ),
            CheckConstraint(
                condition=in_values("level_key", ClassLevel.values), name="ck_identity_class_level"
            ),
            CheckConstraint(
                condition=Q(level_key=ClassLevel.PRODUCT_TYPE, parent__isnull=True)
                | Q(level_key=ClassLevel.CATEGORY, parent__isnull=False),
                name="ck_identity_class_parent_by_level",
            ),
            CheckConstraint(
                condition=Q(
                    level_key=ClassLevel.PRODUCT_TYPE, uom__isnull=False, product_no_scheme__isnull=False
                )
                | Q(level_key=ClassLevel.CATEGORY, uom__isnull=True, product_no_scheme__isnull=True),
                name="ck_identity_class_type_attributes",
            ),
            CheckConstraint(
                condition=Q(product_no_scheme__isnull=True)
                | in_values("product_no_scheme", ProductNoScheme.values),
                name="ck_identity_class_scheme",
            ),
            CheckConstraint(
                condition=Q(segment_value__regex=TWO_DIGITS), name="ck_identity_class_segment_fmt"
            ),
            CheckConstraint(condition=~Q(label_fa=""), name="ck_identity_class_label_nonempty"),
            CheckConstraint(condition=~Q(parent=F("id")), name="ck_identity_class_not_own_parent"),
            CheckConstraint(
                condition=in_values("status", MasterStatus.values), name="ck_identity_class_status"
            ),
            *provenance_constraints("identity_class"),
            _row_version("identity_class"),
        ]
        indexes = [
            models.Index(fields=["parent"], name="ix_icls_parent"),
            models.Index(fields=["uom"], name="ix_icls_uom"),
            *provenance_indexes("icls"),
            *_audit_indexes("icls"),
        ]

    def __str__(self) -> str:
        return f"{self.level_key}:{self.segment_value}"


class Product(SourceProvenance, AuditColumns):
    """A product of one product type; ``product_no`` = code segment 4 (DEC-005: max of the type + 1)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_type = _fk("platform_core.ProductClass")
    product_no = models.CharField(max_length=4)
    name_fa = models.CharField(max_length=200)
    # belt types only (scheme BELT_BUCKLE_WIDTH): product_no = buckle_type_code || belt_width_code
    buckle_type_code = models.CharField(max_length=2, null=True, blank=True)
    belt_width_code = models.CharField(max_length=2, null=True, blank=True)
    status = models.CharField(max_length=8, choices=MasterStatus.choices, db_default=MasterStatus.DRAFT)

    class Meta:
        db_table = "identity_product"
        constraints = [
            UniqueConstraint(fields=["product_type", "product_no"], name="uq_identity_product_type_no"),
            CheckConstraint(condition=Q(product_no__regex=FOUR_DIGITS), name="ck_identity_product_no_fmt"),
            CheckConstraint(condition=~Q(name_fa=""), name="ck_identity_product_name_nonempty"),
            CheckConstraint(
                condition=Q(buckle_type_code__isnull=True, belt_width_code__isnull=True)
                | Q(
                    buckle_type_code__isnull=False,
                    belt_width_code__isnull=False,
                    buckle_type_code__regex=TWO_DIGITS,
                    belt_width_code__regex=TWO_DIGITS,
                    product_no=Concat(F("buckle_type_code"), F("belt_width_code")),
                ),
                name="ck_identity_product_belt_no",
            ),
            CheckConstraint(
                condition=in_values("status", MasterStatus.values), name="ck_identity_product_status"
            ),
            *provenance_constraints("identity_product"),
            _row_version("identity_product"),
        ]
        indexes = [
            models.Index(Lower("name_fa"), name="ix_iprd_name_lower"),
            *provenance_indexes("iprd"),
            *_audit_indexes("iprd"),
        ]

    def __str__(self) -> str:
        return self.product_no


class Style(SourceProvenance, AuditColumns):
    """A style of a product within a category; ``style_no`` = code segment 5, from 0001 per (product,
    category)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = _fk("platform_core.Product")
    category = _fk("platform_core.ProductClass")
    style_no = models.CharField(max_length=4)
    name_fa = models.CharField(max_length=200)
    status = models.CharField(max_length=8, choices=MasterStatus.choices, db_default=MasterStatus.DRAFT)

    class Meta:
        db_table = "identity_style"
        constraints = [
            UniqueConstraint(
                fields=["product", "category", "style_no"], name="uq_identity_style_product_category_no"
            ),
            CheckConstraint(
                condition=Q(style_no__regex=FOUR_DIGITS) & ~Q(style_no="0000"),
                name="ck_identity_style_no_fmt",
            ),
            CheckConstraint(condition=~Q(name_fa=""), name="ck_identity_style_name_nonempty"),
            CheckConstraint(
                condition=in_values("status", MasterStatus.values), name="ck_identity_style_status"
            ),
            *provenance_constraints("identity_style"),
            _row_version("identity_style"),
        ]
        indexes = [
            models.Index(fields=["category"], name="ix_isty_category"),
            models.Index(Lower("name_fa"), name="ix_isty_name_lower"),
            *provenance_indexes("isty"),
            *_audit_indexes("isty"),
        ]

    def __str__(self) -> str:
        return self.style_no


class StyleRevisionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active (immutable)"
    SUPERSEDED = "SUPERSEDED", "Superseded (immutable)"


class StyleRevision(AuditColumns):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    style = _fk("platform_core.Style")
    revision_no = models.IntegerField()
    # colour, main material, hardware colour, notes - text references only (master lists: PHASE_04/06)
    attributes = models.JSONField(default=dict)
    status = models.CharField(
        max_length=12, choices=StyleRevisionStatus.choices, db_default=StyleRevisionStatus.DRAFT
    )
    technical_package_revision_id = models.UUIDField(null=True, blank=True)  # PHASE_03/04 (C-59), no FK yet

    class Meta:
        db_table = "identity_style_revision"
        constraints = [
            UniqueConstraint(fields=["style", "revision_no"], name="uq_identity_style_revision_no"),
            UniqueConstraint(
                fields=["style"],
                condition=Q(status=StyleRevisionStatus.ACTIVE),
                name="uq_identity_style_revision_one_active",
            ),
            CheckConstraint(condition=Q(revision_no__gte=1), name="ck_identity_style_revision_no_pos"),
            CheckConstraint(
                condition=_json_is_object("attributes"), name="ck_identity_style_revision_attrs_object"
            ),
            CheckConstraint(
                condition=in_values("status", StyleRevisionStatus.values),
                name="ck_identity_style_revision_status",
            ),
            _row_version("identity_style_revision"),
        ]
        indexes = _audit_indexes("isrv")

    def __str__(self) -> str:
        return f"{self.style_id} r{self.revision_no}"


# --------------------------------------------------------------------------------------- 14-digit codes
class CodeRuleStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    IN_REVIEW = "IN_REVIEW", "In review"
    APPROVED = "APPROVED", "Approved"
    ACTIVE = "ACTIVE", "Active (codes are issued under it)"
    RETIRED = "RETIRED", "Retired"
    REJECTED = "REJECTED", "Rejected"


class CodeRuleRevision(AuditColumns):
    """Versioned rule of the ``product_code`` namespace (DEC-005). Approver != maker (DEC-005 Q-A /
    DEC-057)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code_namespace = models.CharField(max_length=16, db_default=PRODUCT_CODE_NAMESPACE)
    revision_no = models.IntegerField()
    scope = models.JSONField(default=dict)  # which product types the revision covers
    rule_spec = models.JSONField(default=dict)  # JSON schema written by the 02.3 engine
    source_workbook_sha256 = models.CharField(max_length=64)  # DEC-037 baseline hash
    evidence_document = _fk("platform_core.Document", null=True)
    golden_case_count = models.IntegerField(db_default=0)
    status = models.CharField(max_length=12, choices=CodeRuleStatus.choices, db_default=CodeRuleStatus.DRAFT)
    decision_id = models.CharField(max_length=7)
    approval = _fk("platform_core.ApprovalRequest", null=True)
    approved_by = _user_fk()
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_code_rule_revision"
        constraints = [
            UniqueConstraint(
                fields=["code_namespace", "revision_no"], name="uq_identity_code_rule_revision_no"
            ),
            UniqueConstraint(
                fields=["code_namespace"],
                condition=Q(status=CodeRuleStatus.ACTIVE),
                name="uq_identity_code_rule_one_active",
            ),
            CheckConstraint(
                condition=Q(code_namespace=PRODUCT_CODE_NAMESPACE), name="ck_identity_code_rule_namespace"
            ),
            CheckConstraint(condition=Q(revision_no__gte=1), name="ck_identity_code_rule_revision_pos"),
            CheckConstraint(condition=_json_is_object("scope"), name="ck_identity_code_rule_scope_object"),
            CheckConstraint(condition=_json_is_object("rule_spec"), name="ck_identity_code_rule_spec_object"),
            CheckConstraint(
                condition=Q(source_workbook_sha256__regex=SHA256_PATTERN),
                name="ck_identity_code_rule_sha256_fmt",
            ),
            CheckConstraint(
                condition=Q(golden_case_count__gte=0), name="ck_identity_code_rule_golden_nonneg"
            ),
            CheckConstraint(
                condition=in_values("status", CodeRuleStatus.values), name="ck_identity_code_rule_status"
            ),
            CheckConstraint(
                condition=Q(decision_id__regex=DECISION_ID_PATTERN), name="ck_identity_code_rule_decision_fmt"
            ),
            # maker-checker: an approved rule names its approver, who is not its maker (no self-approval)
            CheckConstraint(
                condition=~Q(
                    status__in=[CodeRuleStatus.APPROVED, CodeRuleStatus.ACTIVE, CodeRuleStatus.RETIRED]
                )
                | (
                    Q(approved_by__isnull=False, approved_at__isnull=False, created_by__isnull=False)
                    & ~Q(approved_by=F("created_by"))
                ),
                name="ck_identity_code_rule_approved_by_other",
            ),
            _row_version("identity_code_rule"),
        ]
        indexes = [
            models.Index(fields=["evidence_document"], name="ix_icrr_evidence"),
            models.Index(fields=["approval"], name="ix_icrr_approval"),
            models.Index(fields=["approved_by"], name="ix_icrr_approved_by"),
            *_audit_indexes("icrr"),
        ]

    def __str__(self) -> str:
        return f"{self.code_namespace} r{self.revision_no} [{self.status}]"


class CodeRuleGoldenCase(models.Model):
    """A golden case of a rule revision. Real cases exist ONLY in the server DB (DEC-028/046, R-38): never in
    Git, fixtures or logs. Repository tests use synthetic cases."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule_revision = _fk("platform_core.CodeRuleRevision")
    product_type_code = models.CharField(max_length=2)  # the family (DEC-005 Q-C: family = product type)
    inputs = models.JSONField(default=dict)
    expected_code = Code14Field()
    source_sheet = models.CharField(max_length=100)
    source_cell_ref = models.CharField(max_length=32)
    source_workbook_sha256 = models.CharField(max_length=64)
    verified_by = _user_fk()
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk()

    class Meta:
        db_table = "identity_code_rule_golden_case"
        constraints = [
            UniqueConstraint(
                fields=["rule_revision", "source_sheet", "source_cell_ref"],
                name="uq_identity_golden_case_source",
            ),
            code14_check_constraint("expected_code", "ck_identity_golden_case_code_fmt"),
            CheckConstraint(
                condition=Q(product_type_code__regex=TWO_DIGITS), name="ck_identity_golden_case_family_fmt"
            ),
            # the family of a case is the type segment of its expected code (characters 3-4, DEC-005)
            CheckConstraint(
                condition=Q(product_type_code=Substr("expected_code", 3, 2)),
                name="ck_identity_golden_case_family_segment",
            ),
            CheckConstraint(
                condition=_json_is_object("inputs"), name="ck_identity_golden_case_inputs_object"
            ),
            CheckConstraint(
                condition=~Q(source_sheet="") & ~Q(source_cell_ref=""), name="ck_identity_golden_case_source"
            ),
            CheckConstraint(
                condition=Q(source_workbook_sha256__regex=SHA256_PATTERN),
                name="ck_identity_golden_case_sha256_fmt",
            ),
            CheckConstraint(
                condition=Q(verified_by__isnull=True, verified_at__isnull=True)
                | Q(verified_by__isnull=False, verified_at__isnull=False),
                name="ck_identity_golden_case_verified_pair",
            ),
        ]
        indexes = [
            models.Index(fields=["rule_revision", "product_type_code"], name="ix_igld_family"),
            models.Index(fields=["verified_by"], name="ix_igld_verified_by"),
            models.Index(fields=["created_by"], name="ix_igld_created_by"),
        ]

    def __str__(self) -> str:
        return f"golden {self.rule_revision_id} {self.source_sheet}!{self.source_cell_ref}"


class ProductCodeStatus(models.TextChoices):
    RESERVED = "RESERVED", "Reserved by the system, waiting for Rahkaran (DEC-005 B1)"
    ACTIVE = "ACTIVE", "Active (seen in Rahkaran)"
    RETIRED = "RETIRED", "Retired"
    DISPUTED = "DISPUTED", "Disputed (conflict; a human decides)"


class ErpStatus(models.TextChoices):
    ERP_PENDING = "ERP_PENDING", "Not yet seen in the Rahkaran import"
    ERP_MATCHED = "ERP_MATCHED", "Seen in the Rahkaran import (exact match)"
    ERP_MISSING = "ERP_MISSING", "Expected in Rahkaran, not found"


class ProductCode(SourceProvenance, AuditColumns):
    """Registry of 14-digit codes of the ``product_code`` namespace (ID-01: text, leading zeros kept)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = Code14Field()
    code_namespace = models.CharField(max_length=16, db_default=PRODUCT_CODE_NAMESPACE)
    style = _fk("platform_core.Style", null=True)
    rule_revision = _fk("platform_core.CodeRuleRevision", null=True)
    status = models.CharField(max_length=12, choices=ProductCodeStatus.choices)
    erp_status = models.CharField(max_length=12, choices=ErpStatus.choices, db_default=ErpStatus.ERP_PENDING)
    erp_seen_batch = _fk("platform_core.ImportBatch", null=True)
    issue_idempotency_key = models.UUIDField(null=True, blank=True)
    issued_by = _user_fk()
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_product_code"
        constraints = [
            UniqueConstraint(fields=["code_namespace", "code"], name="uq_identity_product_code_ns_code"),
            UniqueConstraint(fields=["issue_idempotency_key"], name="uq_identity_product_code_issue_key"),
            code14_check_constraint("code", "ck_identity_product_code_fmt"),
            CheckConstraint(
                condition=Q(code_namespace=PRODUCT_CODE_NAMESPACE), name="ck_identity_product_code_namespace"
            ),
            CheckConstraint(
                condition=in_values("status", ProductCodeStatus.values),
                name="ck_identity_product_code_status",
            ),
            CheckConstraint(
                condition=in_values("erp_status", ErpStatus.values),
                name="ck_identity_product_code_erp_status",
            ),
            CheckConstraint(
                condition=~Q(status=ProductCodeStatus.ACTIVE) | Q(erp_status=ErpStatus.ERP_MATCHED),
                name="ck_identity_product_code_active_matched",
            ),
            CheckConstraint(
                condition=~Q(status=ProductCodeStatus.RESERVED) | Q(erp_status=ErpStatus.ERP_PENDING),
                name="ck_identity_product_code_reserved_pending",
            ),
            CheckConstraint(
                condition=~Q(erp_status=ErpStatus.ERP_MATCHED) | Q(erp_seen_batch__isnull=False),
                name="ck_identity_product_code_matched_has_batch",
            ),
            # a code issued by the system: under a rule revision, for a style, by a person, prefix "02"
            # (DEC-005)
            CheckConstraint(
                condition=~Q(provenance_kind=ProvenanceKind.SYS)
                | Q(
                    rule_revision__isnull=False,
                    style__isnull=False,
                    issued_by__isnull=False,
                    issued_at__isnull=False,
                    issue_idempotency_key__isnull=False,
                    code__startswith="02",
                ),
                name="ck_identity_product_code_sys_issued",
            ),
            *provenance_constraints("identity_product_code"),
            _row_version("identity_product_code"),
        ]
        indexes = [
            models.Index(fields=["style"], name="ix_ipcd_style"),
            models.Index(fields=["rule_revision"], name="ix_ipcd_rule"),
            models.Index(fields=["erp_seen_batch"], name="ix_ipcd_erp_batch"),
            models.Index(fields=["issued_by"], name="ix_ipcd_issued_by"),
            models.Index(fields=["status", "erp_status"], name="ix_ipcd_status"),
            *provenance_indexes("ipcd"),
            *_audit_indexes("ipcd"),
        ]

    def __str__(self) -> str:
        return self.code


# ---------------------------------------------------------------------------------------------- serials
class SerialCounter(models.Model):
    """DEC-006: the single factory-wide gapless counter (row-locked by the allocation, never a sequence)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    namespace_key = models.CharField(max_length=64)
    start_value = models.BigIntegerField()  # 63001 (DEC-006 P-A), seed 0021
    next_value = models.BigIntegerField()  # the number the next allocation takes
    # DEC-006: every legacy serial (Planning, paper, Rahkaran) must be below this value; checked on import
    legacy_max_exclusive = models.BigIntegerField()
    number_pattern = models.CharField(max_length=64)
    decision_id = models.CharField(max_length=7)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "identity_serial_counter"
        constraints = [
            UniqueConstraint(fields=["namespace_key"], name="uq_identity_serial_counter_namespace"),
            CheckConstraint(
                condition=Q(namespace_key=FACTORY_SERIAL_NAMESPACE),
                name="ck_identity_serial_counter_single_ns",
            ),
            CheckConstraint(condition=Q(start_value__gte=1), name="ck_identity_serial_counter_start_pos"),
            CheckConstraint(
                condition=Q(next_value__gte=F("start_value")), name="ck_identity_serial_counter_next_ge_start"
            ),
            CheckConstraint(
                condition=Q(legacy_max_exclusive__lt=F("start_value")),
                name="ck_identity_serial_counter_legacy_below_start",
            ),
            CheckConstraint(
                condition=Q(number_pattern=SERIAL_NUMBER_PATTERN), name="ck_identity_serial_counter_pattern"
            ),
            CheckConstraint(
                condition=Q(decision_id__regex=DECISION_ID_PATTERN),
                name="ck_identity_serial_counter_decision",
            ),
            _row_version("identity_serial_counter"),
        ]

    def __str__(self) -> str:
        return f"{self.namespace_key} next={self.next_value}"


class SerialStatus(models.TextChoices):
    ALLOCATED = "ALLOCATED", "Allocated at order confirm (DEC-006 L-A)"
    CANCELLED = "CANCELLED", "Cancelled; the number is never re-used (DEC-059)"
    # reserved for later phases (contract enum); not written in PHASE_02
    IN_PRODUCTION = "IN_PRODUCTION", "In production (PHASE_07)"
    PARTIALLY_DELIVERED = "PARTIALLY_DELIVERED", "Partially delivered (PHASE_09)"
    DELIVERED = "DELIVERED", "Delivered (PHASE_09)"
    CLOSED = "CLOSED", "Closed (DEC-020)"


class Serial(models.Model):
    """One serial per committed order line (ID-02/03). Never deleted, never re-numbered, never re-used."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    serial_counter = _fk("platform_core.SerialCounter")
    serial_number = models.CharField(max_length=32)  # varchar(32): text, as DEC-006 requires
    serial_value = models.BigIntegerField()  # the same number as integer (range checks, gapless proof)
    customer = _fk("platform_core.Customer")
    style = _fk("platform_core.Style")
    style_revision = _fk("platform_core.StyleRevision")
    product_code = _fk("platform_core.ProductCode", null=True)
    status = models.CharField(max_length=20, choices=SerialStatus.choices, db_default=SerialStatus.ALLOCATED)
    allocation_idempotency_key = models.UUIDField()
    allocated_by = _user_fk(null=False)
    allocated_at = models.DateTimeField(db_default=Now())
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=500, null=True, blank=True)
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "identity_serial"
        constraints = [
            UniqueConstraint(fields=["serial_counter", "serial_number"], name="uq_identity_serial_number"),
            UniqueConstraint(fields=["serial_counter", "serial_value"], name="uq_identity_serial_value"),
            UniqueConstraint(fields=["allocation_idempotency_key"], name="uq_identity_serial_allocation_key"),
            CheckConstraint(
                condition=Q(serial_number__regex=SERIAL_NUMBER_PATTERN), name="ck_identity_serial_number_fmt"
            ),
            CheckConstraint(
                condition=Q(serial_number=Cast(F("serial_value"), output_field=models.CharField())),
                name="ck_identity_serial_number_is_value",
            ),
            CheckConstraint(
                condition=in_values("status", SerialStatus.values), name="ck_identity_serial_status"
            ),
            CheckConstraint(
                condition=~Q(status=SerialStatus.CANCELLED)
                | (
                    Q(cancelled_at__isnull=False, cancel_reason__isnull=False)
                    & Q(min_length("cancel_reason", 3))
                ),
                name="ck_identity_serial_cancel_has_reason",
            ),
            _row_version("identity_serial"),
        ]
        indexes = [
            models.Index(fields=["customer"], name="ix_iser_customer"),
            models.Index(fields=["style"], name="ix_iser_style"),
            models.Index(fields=["style_revision"], name="ix_iser_style_revision"),
            models.Index(fields=["product_code"], name="ix_iser_product_code"),
            models.Index(fields=["allocated_by"], name="ix_iser_allocated_by"),
            models.Index(fields=["allocated_at"], name="ix_iser_allocated_at"),
        ]

    def __str__(self) -> str:
        return self.serial_number


class SnapshotReason(models.TextChoices):
    ALLOCATED = "ALLOCATED", "Version 1, written in the allocation transaction"
    CHANGE_APPLIED = "CHANGE_APPLIED", "An applied change request (DEC-059)"
    TECH_PACKAGE_LINKED = "TECH_PACKAGE_LINKED", "Technical package linked (PHASE_03/04)"


class SerialSnapshot(models.Model):
    """Append-only history of what a serial stands for (customer, PO, line, code, style, qty, dates)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    serial = _fk("platform_core.Serial")
    version = models.IntegerField()
    snapshot = models.JSONField()
    reason = models.CharField(max_length=20, choices=SnapshotReason.choices)
    order_version = models.IntegerField()  # Commercial order version the image reflects
    change_request_id = models.UUIDField(
        null=True, blank=True
    )  # Commercial id (reference, no cross-module FK)
    created_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk(null=False)

    class Meta:
        db_table = "identity_serial_snapshot"
        constraints = [
            UniqueConstraint(fields=["serial", "version"], name="uq_identity_serial_snapshot_version"),
            CheckConstraint(condition=Q(version__gte=1), name="ck_identity_serial_snapshot_version_pos"),
            CheckConstraint(
                condition=Q(order_version__gte=1), name="ck_identity_serial_snapshot_order_version"
            ),
            CheckConstraint(
                condition=_json_is_object("snapshot"), name="ck_identity_serial_snapshot_image_object"
            ),
            CheckConstraint(
                condition=in_values("reason", SnapshotReason.values),
                name="ck_identity_serial_snapshot_reason",
            ),
            CheckConstraint(
                condition=Q(version=1, reason=SnapshotReason.ALLOCATED)
                | (Q(version__gt=1) & ~Q(reason=SnapshotReason.ALLOCATED)),
                name="ck_identity_serial_snapshot_v1_allocated",
            ),
            CheckConstraint(
                condition=~Q(reason=SnapshotReason.CHANGE_APPLIED) | Q(change_request_id__isnull=False),
                name="ck_identity_serial_snapshot_change_has_cr",
            ),
        ]
        indexes = [
            models.Index(fields=["change_request_id"], name="ix_isnp_cr"),
            models.Index(fields=["created_by"], name="ix_isnp_created_by"),
        ]

    def __str__(self) -> str:
        return f"{self.serial_id} v{self.version}"


# ------------------------------------------------------------------------------------ external references
class ExternalSystem(models.TextChoices):
    RAHKARAN = "RAHKARAN", "Rahkaran (read-only Excel import)"
    CUSTOMER = "CUSTOMER", "The customer's own reference"
    LEGACY_PLANNING = "LEGACY_PLANNING", "Legacy Planning workbook"
    OTHER = "OTHER", "Other"


class ExternalRefType(models.Model):
    """Typed external reference kinds (DEC-058). Seeded generic types; ``product_data_steward`` may add
    more."""

    key = models.CharField(max_length=64, primary_key=True)
    label_fa = models.CharField(max_length=200)
    status = models.CharField(max_length=8, choices=PartyStatus.choices, db_default=PartyStatus.ACTIVE)
    decision_id = models.CharField(max_length=7, blank=True, db_default="")
    provenance = models.CharField(max_length=16, choices=Provenance.choices, db_default=Provenance.SYS)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk()
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "identity_external_ref_type"
        constraints = [
            CheckConstraint(
                condition=Q(key__regex=SYSTEM_KEY_PATTERN), name="ck_identity_ext_ref_type_key_fmt"
            ),
            CheckConstraint(condition=~Q(label_fa=""), name="ck_identity_ext_ref_type_label_nonempty"),
            CheckConstraint(
                condition=in_values("status", PartyStatus.values), name="ck_identity_ext_ref_type_status"
            ),
            CheckConstraint(
                condition=Q(decision_id="") | Q(decision_id__regex=DECISION_ID_PATTERN),
                name="ck_identity_ext_ref_type_decision_fmt",
            ),
            CheckConstraint(
                condition=in_values("provenance", [Provenance.SYS, Provenance.MIGRATION_SEED]),
                name="ck_identity_ext_ref_type_provenance",
            ),
            CheckConstraint(
                condition=~Q(provenance=Provenance.MIGRATION_SEED) | ~Q(decision_id=""),
                name="ck_identity_ext_ref_type_seed_has_decision",
            ),
            _row_version("identity_ext_ref_type"),
        ]
        indexes = _audit_indexes("iert")

    def __str__(self) -> str:
        return self.key


class ExternalTargetType(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    PRODUCT = "product", "Product"
    STYLE = "style", "Style"
    CUSTOMER_ORDER = "customer_order", "Customer order"
    ORDER_LINE = "order_line", "Order line"
    SERIAL = "serial", "Serial"


class ExternalRef(SourceProvenance, AuditColumns):
    """A raw external identifier (kept exactly as text, never parsed into a number, never our serial)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target_type = models.CharField(max_length=16, choices=ExternalTargetType.choices)
    target_id = models.UUIDField()  # polymorphic reference (customer / product / ... / serial)
    system = models.CharField(max_length=16, choices=ExternalSystem.choices)
    ref_type = _fk("platform_core.ExternalRefType", db_column="namespace")
    value = models.CharField(max_length=64)
    valid_from = models.DateTimeField(db_default=Now())
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_external_ref"
        constraints = [
            # no global uniqueness of ``value`` (C-56): only per system + type + target
            UniqueConstraint(
                fields=["system", "ref_type", "value", "target_type", "target_id"],
                name="uq_identity_ext_ref_target_value",
            ),
            CheckConstraint(
                condition=in_values("target_type", ExternalTargetType.values),
                name="ck_identity_ext_ref_target",
            ),
            CheckConstraint(
                condition=in_values("system", ExternalSystem.values), name="ck_identity_ext_ref_system"
            ),
            CheckConstraint(condition=~Q(value=""), name="ck_identity_ext_ref_value_nonempty"),
            CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=F("valid_from")),
                name="ck_identity_ext_ref_validity",
            ),
            *provenance_constraints("identity_ext_ref"),
            _row_version("identity_ext_ref"),
        ]
        indexes = [
            models.Index(fields=["system", "ref_type", "value"], name="ix_iext_lookup"),
            models.Index(fields=["target_type", "target_id"], name="ix_iext_target"),
            models.Index(fields=["ref_type"], name="ix_iext_type"),
            *provenance_indexes("iext"),
            *_audit_indexes("iext"),
        ]

    def __str__(self) -> str:
        return f"{self.system}:{self.ref_type_id}"


# ------------------------------------------------------------------------------------------ legacy history
class LegacyCodeFlag(models.TextChoices):
    OK = "OK", "14-digit code present"
    DISPUTED = "DISPUTED", "Not a valid 14-digit code; planning decides (DEC-005 Q-D), never auto-fixed"
    ABSENT = "ABSENT", "No code in the legacy row"


class MatchStatus(models.TextChoices):
    UNMATCHED = "UNMATCHED", "Not matched"
    SUGGESTED = "SUGGESTED", "Suggested by similarity (never auto-linked)"
    CONFIRMED = "CONFIRMED", "Confirmed by a person"
    REJECTED = "REJECTED", "Rejected by a person"


class HistoricalOrderRecord(SourceProvenance):
    """Read-only legacy order row (LEG). Never an official order; legacy serials stay text (DEC-006)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    legacy_order_ref = models.CharField(max_length=64, blank=True, db_default="")
    # legacy serial exactly as written (S-prefix, -digit / -P / -N suffix, BG prefix ... kept as text)
    legacy_serial_text = models.CharField(max_length=32, null=True, blank=True)
    legacy_serial_value = models.BigIntegerField(null=True, blank=True)  # plain-integer legacy serials only
    legacy_serial_duplicate = models.BooleanField(db_default=False)  # flagged at import, never merged
    legacy_product_code_raw = models.TextField(null=True, blank=True)  # NOT Code14-checked
    normalised_product_code = Code14Field(null=True, blank=True)  # type: ignore[misc]  # str-typed field
    code_flag = models.CharField(max_length=8, choices=LegacyCodeFlag.choices)
    payload = models.JSONField(default=dict)  # mapped legacy columns, raw (no contact data, DEC-028)
    match_status = models.CharField(
        max_length=12, choices=MatchStatus.choices, db_default=MatchStatus.UNMATCHED
    )
    matched_style = _fk("platform_core.Style", null=True)
    matched_product_code = _fk("platform_core.ProductCode", null=True)
    matched_by = _user_fk()
    matched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "identity_historical_order_record"
        constraints = [
            UniqueConstraint(fields=["staging_row"], name="uq_identity_historical_staging_row"),
            CheckConstraint(
                condition=Q(provenance_kind=ProvenanceKind.LEG), name="ck_identity_historical_is_legacy"
            ),
            code14_check_constraint("normalised_product_code", "ck_identity_historical_code_fmt"),
            CheckConstraint(
                condition=in_values("code_flag", LegacyCodeFlag.values),
                name="ck_identity_historical_code_flag",
            ),
            CheckConstraint(
                condition=~Q(code_flag=LegacyCodeFlag.OK) | Q(normalised_product_code__isnull=False),
                name="ck_identity_historical_ok_has_code",
            ),
            CheckConstraint(
                condition=~Q(code_flag=LegacyCodeFlag.ABSENT)
                | Q(legacy_product_code_raw__isnull=True, normalised_product_code__isnull=True),
                name="ck_identity_historical_absent_has_none",
            ),
            CheckConstraint(
                condition=~Q(code_flag=LegacyCodeFlag.DISPUTED) | Q(legacy_product_code_raw__isnull=False),
                name="ck_identity_historical_disputed_has_raw",
            ),
            CheckConstraint(
                condition=Q(legacy_serial_value__isnull=True)
                | Q(
                    legacy_serial_text__isnull=False,
                    legacy_serial_text=Cast(F("legacy_serial_value"), output_field=models.CharField()),
                ),
                name="ck_identity_historical_serial_value_is_text",
            ),
            # a plain-integer legacy serial always carries its value (so the DEC-006 range check can see it)
            CheckConstraint(
                condition=Q(legacy_serial_text__isnull=True)
                | ~Q(legacy_serial_text__regex=r"^[1-9][0-9]{0,17}$")
                | Q(legacy_serial_value__isnull=False),
                name="ck_identity_historical_plain_serial_has_value",
            ),
            CheckConstraint(
                condition=_json_is_object("payload"), name="ck_identity_historical_payload_object"
            ),
            CheckConstraint(
                condition=in_values("match_status", MatchStatus.values),
                name="ck_identity_historical_match_status",
            ),
            CheckConstraint(
                condition=~Q(match_status__in=[MatchStatus.CONFIRMED, MatchStatus.REJECTED])
                | Q(matched_by__isnull=False, matched_at__isnull=False),
                name="ck_identity_historical_decided_has_actor",
            ),
            CheckConstraint(
                condition=~Q(match_status=MatchStatus.CONFIRMED) | Q(matched_style__isnull=False),
                name="ck_identity_historical_confirmed_has_style",
            ),
            *provenance_constraints("identity_historical"),
            _row_version("identity_historical"),
        ]
        indexes = [
            models.Index(fields=["legacy_serial_text"], name="ix_ihst_serial"),
            models.Index(fields=["normalised_product_code"], name="ix_ihst_code"),
            models.Index(fields=["matched_style"], name="ix_ihst_style"),
            models.Index(fields=["matched_product_code"], name="ix_ihst_pcode"),
            models.Index(fields=["matched_by"], name="ix_ihst_matched_by"),
            models.Index(fields=["import_batch"], name="ix_ihst_batch"),
        ]

    def __str__(self) -> str:
        return f"legacy {self.id}"
