"""Integration framework tables (PHASE_00 / 00.6). Platform level, generic, NO business entities.

* ``IntegrationSource``  registry of external source systems (metadata only). ``direction`` is READ_ONLY and a
  CHECK constraint enforces it (Rahkaran: Excel import / read-only, ADR-001; a write direction needs an ADR).
* ``ImportBatch``        one received file per (source, sha256) with provenance; immutable provenance columns
  (trigger ``trg_import_batch_provenance``). Raw file bytes are never stored in the DB or the repo.
* ``StagingRow``         staged rows of a batch (payload JSON + validation status + row error codes). Staged
  data is never applied to business tables in PHASE_00 (applying is blocked: RULE_NOT_APPROVED).
* ``ConflictItem``       conflict queue: items that need a human decision. Resolving never writes business
  data.

Design and state machines: ``docs/integration/README.md``.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import models
from django.db.models import CheckConstraint, F, Func, Q, UniqueConstraint, Value
from django.db.models.functions import Now
from django.db.models.lookups import Exact

from platform_core.models import ACTOR_CONSISTENT, ActorType, _json_is_object

SOURCE_CODE_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"
DECISION_ID_PATTERN = r"^DEC-[0-9]{3}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
KIND_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"


def _jsonb_typeof_is(field: str, kind: str) -> Exact:
    """Boolean expression ``jsonb_typeof(<field>) = <kind>`` for named CHECK constraints."""
    return Exact(Func(F(field), function="jsonb_typeof", output_field=models.CharField()), Value(kind))


class SourceKind(models.TextChoices):
    EXCEL_FILE = "EXCEL_FILE", "Excel workbook export (.xlsx)"
    XLSM_FILE = "XLSM_FILE", "Legacy macro workbook (.xlsm, read as data only, never executed)"


class SourceDirection(models.TextChoices):
    READ_ONLY = "READ_ONLY", "Read only (import)"


class ThresholdBasis(models.TextChoices):
    TECHNICAL_DEFAULT = "TECHNICAL_DEFAULT", "Technical default (to be confirmed by the owner)"
    OWNER_APPROVED = "OWNER_APPROVED", "Approved by the owner (decision recorded)"


class IntegrationSource(models.Model):
    id = models.SmallAutoField(primary_key=True)
    code = models.CharField(max_length=64)
    name_fa = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=SourceKind.choices)
    direction = models.CharField(
        max_length=16, choices=SourceDirection.choices, db_default=SourceDirection.READ_ONLY
    )
    # The owner decision that governs applying / re-import policy of this source's data (blocked until
    # APPROVED).
    policy_decision_id = models.CharField(max_length=7)
    staleness_threshold = models.DurationField()
    threshold_basis = models.CharField(
        max_length=20, choices=ThresholdBasis.choices, db_default=ThresholdBasis.TECHNICAL_DEFAULT
    )
    is_enabled = models.BooleanField(db_default=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_success_batch = models.ForeignKey(
        "platform_core.ImportBatch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_constraint=True,
    )
    last_as_of = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_integration_source"
        constraints = [
            UniqueConstraint(fields=["code"], name="uq_integration_source_code"),
            CheckConstraint(
                condition=Q(code__regex=SOURCE_CODE_PATTERN), name="ck_integration_source_code_fmt"
            ),
            CheckConstraint(condition=~Q(name_fa=""), name="ck_integration_source_name_nonempty"),
            CheckConstraint(condition=Q(kind__in=SourceKind.values), name="ck_integration_source_kind"),
            # ADR-001: Rahkaran (and every PHASE_00 source) is read-only. Relaxing this needs an ADR +
            # migration.
            CheckConstraint(
                condition=Q(direction=SourceDirection.READ_ONLY), name="ck_integration_source_read_only"
            ),
            CheckConstraint(
                condition=Q(policy_decision_id__regex=DECISION_ID_PATTERN),
                name="ck_integration_source_decision_fmt",
            ),
            CheckConstraint(
                condition=Q(staleness_threshold__gt=timedelta(0)),
                name="ck_integration_source_threshold_pos",
            ),
            CheckConstraint(
                condition=Q(threshold_basis__in=ThresholdBasis.values),
                name="ck_integration_source_threshold_basis",
            ),
            CheckConstraint(
                condition=Q(last_success_at__isnull=True, last_success_batch__isnull=True)
                | Q(last_success_at__isnull=False, last_success_batch__isnull=False),
                name="ck_integration_source_last_success_pair",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_integration_source_row_version_pos"),
        ]

    def __str__(self) -> str:
        return self.code


class BatchStatus(models.TextChoices):
    RECEIVED = "RECEIVED", "Received (provenance recorded)"
    STAGED = "STAGED", "Rows staged"
    VALIDATED = "VALIDATED", "Validated (awaiting review)"
    REJECTED = "REJECTED", "Rejected"
    SUPERSEDED = "SUPERSEDED", "Superseded by a newer batch"
    APPLIED = "APPLIED", "Applied to official data"
    COMPENSATED = "COMPENSATED", "Applied, then compensated"


class ImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(IntegrationSource, on_delete=models.PROTECT, related_name="batches")
    file_sha256 = models.CharField(max_length=64)
    byte_size = models.BigIntegerField()
    # basename only, control characters removed (never a client path); see integration.imports.safe_basename
    original_name = models.CharField(max_length=255)
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_id = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    correlation_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=BatchStatus.choices, db_default=BatchStatus.RECEIVED)
    # "as of" claimed by the importer for the snapshot (unverified evidence, SOURCE_MAPPING section 7).
    source_as_of = models.DateTimeField(null=True, blank=True)
    row_count = models.IntegerField(db_default=0)
    error_row_count = models.IntegerField(db_default=0)
    received_at = models.DateTimeField(db_default=Now())
    staged_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_import_batch"
        constraints = [
            # WH-01 framework: the same file for the same source is ONE batch (idempotent import).
            UniqueConstraint(fields=["source", "file_sha256"], name="uq_import_batch_source_sha256"),
            CheckConstraint(
                condition=Q(file_sha256__regex=SHA256_PATTERN), name="ck_import_batch_sha256_fmt"
            ),
            CheckConstraint(condition=Q(byte_size__gt=0), name="ck_import_batch_byte_size_pos"),
            CheckConstraint(condition=~Q(original_name=""), name="ck_import_batch_name_nonempty"),
            CheckConstraint(condition=Q(actor_type__in=ActorType.values), name="ck_import_batch_actor_type"),
            CheckConstraint(condition=ACTOR_CONSISTENT, name="ck_import_batch_actor_id_for_user"),
            CheckConstraint(condition=Q(status__in=BatchStatus.values), name="ck_import_batch_status"),
            CheckConstraint(condition=Q(row_count__gte=0), name="ck_import_batch_row_count_nonneg"),
            CheckConstraint(
                condition=Q(error_row_count__gte=0, error_row_count__lte=F("row_count")),
                name="ck_import_batch_error_rows_range",
            ),
            CheckConstraint(
                condition=Q(status=BatchStatus.RECEIVED)
                | Q(status=BatchStatus.REJECTED)
                | Q(staged_at__isnull=False),
                name="ck_import_batch_staged_has_ts",
            ),
            CheckConstraint(
                condition=~Q(
                    status__in=[
                        BatchStatus.VALIDATED,
                        BatchStatus.SUPERSEDED,
                        BatchStatus.APPLIED,
                        BatchStatus.COMPENSATED,
                    ]
                )
                | Q(validated_at__isnull=False),
                name="ck_import_batch_validated_has_ts",
            ),
            CheckConstraint(
                condition=~Q(status__in=[BatchStatus.REJECTED, BatchStatus.SUPERSEDED])
                | (Q(closed_at__isnull=False) & ~Q(close_reason="")),
                name="ck_import_batch_closed_has_reason",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_import_batch_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["source", "received_at"], name="ix_import_batch_source_recv"),
            models.Index(fields=["status", "received_at"], name="ix_import_batch_status"),
        ]

    def __str__(self) -> str:
        return f"batch {self.id} [{self.status}]"


class RowStatus(models.TextChoices):
    NEW = "NEW", "Staged, not validated yet"
    PENDING_REVIEW = "PENDING_REVIEW", "Structurally valid, awaiting review"
    ERROR = "ERROR", "Validation error (see error_codes)"
    MATCHED = "MATCHED", "Matched to an official record (business rule; not reachable in PHASE_00)"
    REJECTED = "REJECTED", "Rejected"
    APPROVED = "APPROVED", "Approved (business rule; not reachable in PHASE_00)"


class StagingRow(models.Model):
    id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    sheet_name = models.CharField(max_length=100, blank=True, default="")
    row_number = models.IntegerField()
    payload = models.JSONField()
    payload_sha256 = models.CharField(max_length=64)
    validation_status = models.CharField(max_length=16, choices=RowStatus.choices, db_default=RowStatus.NEW)
    error_codes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_import_staging_row"
        constraints = [
            UniqueConstraint(fields=["batch", "sheet_name", "row_number"], name="uq_staging_row_position"),
            CheckConstraint(condition=Q(row_number__gte=1), name="ck_staging_row_number_pos"),
            CheckConstraint(condition=_json_is_object("payload"), name="ck_staging_row_payload_object"),
            CheckConstraint(
                condition=Q(payload_sha256__regex=SHA256_PATTERN), name="ck_staging_row_payload_sha256_fmt"
            ),
            CheckConstraint(
                condition=Q(validation_status__in=RowStatus.values), name="ck_staging_row_status"
            ),
            CheckConstraint(
                condition=_jsonb_typeof_is("error_codes", "array"), name="ck_staging_row_error_codes_array"
            ),
            CheckConstraint(
                condition=~Q(validation_status=RowStatus.ERROR) | ~Q(error_codes=[]),
                name="ck_staging_row_error_has_codes",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_staging_row_row_version_pos"),
        ]
        indexes = [models.Index(fields=["batch", "validation_status"], name="ix_staging_row_batch_status")]

    def __str__(self) -> str:
        return f"row {self.sheet_name}#{self.row_number} [{self.validation_status}]"


class ConflictStatus(models.TextChoices):
    OPEN = "OPEN", "Open (needs a human decision)"
    RESOLVED = "RESOLVED", "Resolved"
    DISMISSED = "DISMISSED", "Dismissed"


class ConflictItem(models.Model):
    # Internal surrogate (cursor order); ``conflict_id`` is the public identity.
    id = models.BigAutoField(primary_key=True)
    conflict_id = models.UUIDField(default=uuid.uuid4, editable=False)
    source = models.ForeignKey(IntegrationSource, on_delete=models.PROTECT, related_name="conflicts")
    batch = models.ForeignKey(
        ImportBatch, on_delete=models.PROTECT, null=True, blank=True, related_name="conflicts"
    )
    conflict_key = models.CharField(max_length=200)
    kind = models.CharField(max_length=64)
    details = models.JSONField(default=dict, blank=True)  # redacted by the service; identifiers only
    status = models.CharField(max_length=16, choices=ConflictStatus.choices, db_default=ConflictStatus.OPEN)
    raised_by_type = models.CharField(max_length=16, choices=ActorType.choices)
    raised_by_id = models.UUIDField(null=True, blank=True)
    raised_at = models.DateTimeField(db_default=Now())
    resolved_by = models.UUIDField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_conflict_item"
        constraints = [
            UniqueConstraint(fields=["conflict_id"], name="uq_conflict_item_conflict_id"),
            # at most one OPEN item per (source, kind, key): raising again returns the open one
            UniqueConstraint(
                fields=["source", "kind", "conflict_key"],
                condition=Q(status=ConflictStatus.OPEN),
                name="uq_conflict_item_open_key",
            ),
            CheckConstraint(condition=~Q(conflict_key=""), name="ck_conflict_item_key_nonempty"),
            CheckConstraint(condition=Q(kind__regex=KIND_PATTERN), name="ck_conflict_item_kind_fmt"),
            CheckConstraint(condition=_json_is_object("details"), name="ck_conflict_item_details_object"),
            CheckConstraint(condition=Q(status__in=ConflictStatus.values), name="ck_conflict_item_status"),
            CheckConstraint(
                condition=Q(raised_by_type__in=ActorType.values), name="ck_conflict_item_raised_by_type"
            ),
            CheckConstraint(
                condition=~Q(raised_by_type=ActorType.USER) | Q(raised_by_id__isnull=False),
                name="ck_conflict_item_raised_by_id_for_user",
            ),
            CheckConstraint(
                condition=(
                    Q(status=ConflictStatus.OPEN)
                    & Q(resolved_by__isnull=True, resolved_at__isnull=True, resolution_note="")
                )
                | (
                    ~Q(status=ConflictStatus.OPEN)
                    & Q(resolved_by__isnull=False, resolved_at__isnull=False)
                    & ~Q(resolution_note="")
                ),
                name="ck_conflict_item_resolution_consistent",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_conflict_item_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["status", "id"], name="ix_conflict_item_status"),
            models.Index(fields=["batch"], name="ix_conflict_item_batch"),
        ]

    def __str__(self) -> str:
        return f"conflict {self.kind}:{self.conflict_key} [{self.status}]"
