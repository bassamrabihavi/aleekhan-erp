"""Typed, versioned parameters and dynamic-field drafts (PHASE_01 / 01.2; page 42, C-33).

* ``ParameterDefinition``  immutable key + type + classification. TECHNICAL (ops default), OWNER_POLICY
  (owner decision on platform/security policy, e.g. DEC-051 password/session policy) and BUSINESS_RULE
  (business decision)
  definitions must name their decision (CHECK).
* ``ParameterValue``       value revisions (DRAFT -> PENDING_APPROVAL -> PUBLISHED | REJECTED; PUBLISHED ->
  SUPERSEDED). The value effective at instant t = the PUBLISHED/SUPERSEDED revision with the latest
  ``effective_from <= t`` (SQL function ``platform_param_value(key)``). Published values are immutable;
  BUSINESS_RULE publish needs publisher != proposer (DEC-032; trigger). Values are canonical strings validated
  against the datatype and bounds by trigger.
* ``DynamicFieldDefinition``  DRAFT only in PHASE_01 (layout/publish = PHASE_11, C-33); key immutable.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint
from django.db.models.functions import Now

from platform_core.schema_common import (
    DECISION_ID_PATTERN,
    ENTITY_TYPE_PATTERN,
    MODULE_PATTERN,
    SYSTEM_KEY_PATTERN,
    Provenance,
    Sensitivity,
    in_values,
)


def _user_fk() -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        "platform_core.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )


class Datatype(models.TextChoices):
    STRING = "STRING", "String"
    INTEGER = "INTEGER", "Integer"
    DECIMAL = "DECIMAL", "Decimal (canonical string)"
    BOOLEAN = "BOOLEAN", "Boolean (true/false)"
    DATE = "DATE", "Date (YYYY-MM-DD, UTC calendar)"
    DURATION = "DURATION", "Duration (integer + unit)"
    ENUM = "ENUM", "One of allowed_values"


class Classification(models.TextChoices):
    TECHNICAL = "TECHNICAL", "Technical default (ops-confirmable, no business meaning)"
    OWNER_POLICY = "OWNER_POLICY", "Owner-approved platform/security policy (decision required)"
    BUSINESS_RULE = "BUSINESS_RULE", "Business rule (decision required; maker-checker publish, DEC-032)"


class ParameterUnit(models.TextChoices):
    NONE = "", "No unit"
    COUNT = "count", "Count"
    CHARACTERS = "characters", "Characters"
    SECONDS = "seconds", "Seconds"
    MINUTES = "minutes", "Minutes"
    HOURS = "hours", "Hours"
    DAYS = "days", "Days"
    MONTHS = "months", "Months"
    BYTES = "bytes", "Bytes"
    LEVELS = "levels", "Tree levels"


class ParameterDefinition(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    label_fa = models.CharField(max_length=200)
    datatype = models.CharField(max_length=8, choices=Datatype.choices)
    unit = models.CharField(max_length=16, choices=ParameterUnit.choices, blank=True, default="")
    owner_module = models.CharField(max_length=32)
    classification = models.CharField(max_length=16, choices=Classification.choices)
    decision_id = models.CharField(max_length=7, blank=True, default="")
    min_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    allowed_values = models.JSONField(null=True, blank=True)  # ENUM only: JSON array of strings
    description_fa = models.CharField(max_length=500, blank=True, default="")
    provenance = models.CharField(max_length=16, choices=Provenance.choices, db_default=Provenance.SYS)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_parameter_definition"
        constraints = [
            CheckConstraint(
                condition=Q(key__regex=SYSTEM_KEY_PATTERN), name="ck_parameter_definition_key_fmt"
            ),
            CheckConstraint(condition=~Q(label_fa=""), name="ck_parameter_definition_label_nonempty"),
            CheckConstraint(
                condition=in_values("datatype", Datatype.values), name="ck_parameter_definition_datatype"
            ),
            CheckConstraint(
                condition=in_values("unit", ParameterUnit.values), name="ck_parameter_definition_unit"
            ),
            CheckConstraint(
                condition=Q(owner_module__regex=MODULE_PATTERN), name="ck_parameter_definition_module_fmt"
            ),
            CheckConstraint(
                condition=in_values("classification", Classification.values),
                name="ck_parameter_definition_classification",
            ),
            CheckConstraint(
                condition=Q(decision_id="") | Q(decision_id__regex=DECISION_ID_PATTERN),
                name="ck_parameter_definition_decision_fmt",
            ),
            CheckConstraint(
                condition=Q(classification=Classification.TECHNICAL) | ~Q(decision_id=""),
                name="ck_parameter_definition_decision_required",
            ),
            CheckConstraint(
                condition=Q(min_value__isnull=True)
                | Q(max_value__isnull=True)
                | Q(min_value__lte=F("max_value")),
                name="ck_parameter_definition_bounds",
            ),
            CheckConstraint(
                condition=(Q(datatype=Datatype.ENUM) & Q(allowed_values__isnull=False))
                | (~Q(datatype=Datatype.ENUM) & Q(allowed_values__isnull=True)),
                name="ck_parameter_definition_enum_values",
            ),
            CheckConstraint(
                condition=in_values("provenance", [Provenance.SYS, Provenance.MIGRATION_SEED]),
                name="ck_parameter_definition_provenance",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_parameter_definition_row_version_pos"),
        ]
        indexes = [models.Index(fields=["created_by"], name="ix_parameter_definition_cby")]

    def __str__(self) -> str:
        return self.key


class ValueStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
    PUBLISHED = "PUBLISHED", "Published"
    SUPERSEDED = "SUPERSEDED", "Superseded"
    REJECTED = "REJECTED", "Rejected"


VALUE_EFFECTIVE = [ValueStatus.PUBLISHED, ValueStatus.SUPERSEDED]


class ParameterValue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(
        ParameterDefinition,
        on_delete=models.PROTECT,
        related_name="values",
        db_column="parameter_key",
        db_index=False,
    )
    value = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=ValueStatus.choices, db_default=ValueStatus.DRAFT)
    effective_from = models.DateTimeField()
    decision_id = models.CharField(max_length=7, blank=True, default="")
    reason = models.CharField(max_length=500, blank=True, default="")
    provenance = models.CharField(max_length=16, choices=Provenance.choices, db_default=Provenance.SYS)
    proposed_by = _user_fk()
    proposed_at = models.DateTimeField(db_default=Now())
    published_by = _user_fk()
    published_at = models.DateTimeField(null=True, blank=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    approval_request = models.ForeignKey(
        "platform_core.ApprovalRequest",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_parameter_value"
        constraints = [
            UniqueConstraint(
                fields=["definition", "effective_from"],
                condition=Q(status__in=VALUE_EFFECTIVE),
                name="uq_parameter_value_effective",
            ),
            CheckConstraint(
                condition=in_values("status", ValueStatus.values), name="ck_parameter_value_status"
            ),
            CheckConstraint(
                condition=Q(decision_id="") | Q(decision_id__regex=DECISION_ID_PATTERN),
                name="ck_parameter_value_decision_fmt",
            ),
            CheckConstraint(
                condition=in_values("provenance", [Provenance.SYS, Provenance.MIGRATION_SEED]),
                name="ck_parameter_value_provenance",
            ),
            # a human proposes every value except the reviewed migration seed (decision id: trigger)
            CheckConstraint(
                condition=Q(provenance=Provenance.MIGRATION_SEED, proposed_by__isnull=True)
                | Q(provenance=Provenance.SYS, proposed_by__isnull=False),
                name="ck_parameter_value_proposer",
            ),
            CheckConstraint(
                condition=~in_values("status", VALUE_EFFECTIVE)
                | Q(published_at__isnull=False)
                & (Q(provenance=Provenance.MIGRATION_SEED) | Q(published_by__isnull=False)),
                name="ck_parameter_value_published_has_publisher",
            ),
            CheckConstraint(
                condition=~Q(status=ValueStatus.SUPERSEDED) | Q(superseded_at__isnull=False),
                name="ck_parameter_value_superseded_at",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_parameter_value_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["definition", "status", "effective_from"], name="ix_parameter_value_lookup"),
            models.Index(fields=["proposed_by"], name="ix_parameter_value_proposer"),
            models.Index(fields=["published_by"], name="ix_parameter_value_publisher"),
            models.Index(fields=["approval_request"], name="ix_parameter_value_approval"),
        ]

    def __str__(self) -> str:
        return f"{self.definition_id}={self.value} [{self.status}]"


class FieldDatatype(models.TextChoices):
    STRING = "STRING", "String"
    INTEGER = "INTEGER", "Integer"
    DECIMAL = "DECIMAL", "Decimal"
    BOOLEAN = "BOOLEAN", "Boolean"
    DATE = "DATE", "Date"
    ENUM = "ENUM", "Enum"
    REFERENCE = "REFERENCE", "Reference"


class DynamicFieldDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    field_key = models.CharField(max_length=64)
    entity_scope = models.CharField(max_length=64)
    label_fa = models.CharField(max_length=200)
    datatype = models.CharField(max_length=10, choices=FieldDatatype.choices)
    security_class = models.CharField(max_length=2, choices=Sensitivity.choices)
    help_fa = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=8, db_default="DRAFT")
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk()
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_dynamic_field_definition"
        constraints = [
            UniqueConstraint(fields=["field_key"], name="uq_dynamic_field_key"),
            CheckConstraint(
                condition=Q(field_key__regex=SYSTEM_KEY_PATTERN), name="ck_dynamic_field_key_fmt"
            ),
            CheckConstraint(
                condition=Q(entity_scope__regex=ENTITY_TYPE_PATTERN), name="ck_dynamic_field_scope_fmt"
            ),
            CheckConstraint(condition=~Q(label_fa=""), name="ck_dynamic_field_label_nonempty"),
            CheckConstraint(
                condition=in_values("datatype", FieldDatatype.values), name="ck_dynamic_field_datatype"
            ),
            CheckConstraint(
                condition=in_values("security_class", Sensitivity.values),
                name="ck_dynamic_field_security_class",
            ),
            # PHASE_01 stores drafts only (C-33); publishing into forms is PHASE_11
            CheckConstraint(condition=Q(status="DRAFT"), name="ck_dynamic_field_draft_only"),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_dynamic_field_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["entity_scope"], name="ix_dynamic_field_scope"),
            models.Index(fields=["created_by"], name="ix_dynamic_field_created_by"),
            models.Index(fields=["updated_by"], name="ix_dynamic_field_updated_by"),
        ]

    def __str__(self) -> str:
        return self.field_key
