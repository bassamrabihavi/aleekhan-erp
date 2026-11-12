"""Shared schema vocabulary for the PHASE_01 platform tables (step 01.2).

Patterns mirror ``docs/api/openapi-draft.yaml`` (0.5.x) so the database refuses what the contract refuses.
Only structure lives here; behaviour (state machines, policies) is the domain engine of step 01.3.
"""

from __future__ import annotations

from collections.abc import Sequence

from django.db import models
from django.db.models import Q
from django.db.models.functions import Length, Trim
from django.db.models.lookups import GreaterThanOrEqual, LessThanOrEqual

# --------------------------------------------------------------------------------------------- patterns
SYSTEM_KEY_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"  # OpenAPI SystemKey
ENTITY_TYPE_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"  # OpenAPI EntityRef.entity_type
MODULE_PATTERN = r"^[a-z][a-z0-9_]{1,31}$"  # OpenAPI Parameter.owner_module
PERMISSION_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$"  # OpenAPI x-aleekhan-permission
UNIT_TYPE_PATTERN = r"^[A-Z][A-Z_]{1,31}$"  # OpenAPI OrgUnitCreateRequest.unit_type
USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{2,63}$"  # OpenAPI User.username (lower-case only -> no case clash)
DECISION_ID_PATTERN = r"^DEC-[0-9]{3}$"
MATRIX_VERSION_PATTERN = r"^[0-9]+\.[0-9]+$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
# Django password-hasher encoding "<algorithm>$..." (hash never leaves the DB, never in audit/outbox/logs)
PASSWORD_HASH_PATTERN = r"^[a-z0-9_]{3,32}\$.+$"  # noqa: S105 - a regex, not a secret
STORAGE_KEY_PATTERN = r"^[A-Za-z0-9_-]{32,64}$"  # random key, never a client path
ERROR_CODE_PATTERN = r"^[A-Z][A-Z0-9_]{2,63}$"

# Mandatory label of every synthetic dev/test row (DEC-046 public repo; PHASE_01 "no unlabelled fake data").
SYNTHETIC_LABEL = "محیط آزمایشی — داده ساختگی"


class Provenance(models.TextChoices):
    SYS = "SYS", "Created in the platform"
    MIGRATION_SEED = "MIGRATION_SEED", "Seeded by a reviewed migration (non-sensitive catalogue)"
    SEED_SYNTHETIC = "SEED_SYNTHETIC", "Synthetic dev/test data (never production)"


class Sensitivity(models.TextChoices):
    S0 = "S0", "Public-internal"
    S1 = "S1", "Internal operational"
    S2 = "S2", "Confidential business"
    S3 = "S3", "Restricted personal/financial"


class NetworkZone(models.TextChoices):
    INTERNAL = "INTERNAL", "Factory network (explicit CIDR list in server config, DEC-052)"
    EXTERNAL = "EXTERNAL", "Outside (incl. VPN, DEC-052)"
    UNKNOWN = "UNKNOWN", "Unknown (treated as outside, DEC-052)"


class ProvenanceKind(models.TextChoices):
    """PHASE_02 source provenance (docs/discovery/DATA_TABLE.md PHASE_02 section 1.1; OpenAPI
    ``Provenance``)."""

    SYS = "SYS", "Created in the platform"
    IMP = "IMP", "Applied from an import batch"
    LEG = "LEG", "Read-only legacy evidence (historical)"
    EXT = "EXT", "External reference only"


class SourceProvenance(models.Model):
    """Provenance block of every PHASE_02 table that can hold imported or legacy-derived data.

    The workbook hash is reached through ``import_batch.file_sha256`` (one hash, one truth). An IMP/LEG row
    always points to its raw staging row; a SYS row never carries a batch (no fake provenance). Use
    :func:`provenance_constraints` / :func:`provenance_indexes` in the concrete model's ``Meta``.
    """

    provenance_kind = models.CharField(
        max_length=8, choices=ProvenanceKind.choices, db_default=ProvenanceKind.SYS
    )
    import_batch = models.ForeignKey(
        "platform_core.ImportBatch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    staging_row = models.ForeignKey(
        "platform_core.StagingRow",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    source_sheet = models.CharField(max_length=100, blank=True, db_default="")
    source_cell_ref = models.CharField(max_length=32, blank=True, db_default="")
    source_raw_value = models.TextField(null=True, blank=True)  # exactly as read, never trimmed
    source_formula = models.TextField(null=True, blank=True)  # formula text != evaluated truth
    transform_rule_version = models.CharField(max_length=64, blank=True, db_default="")

    class Meta:
        abstract = True


def provenance_constraints(table: str) -> list[models.CheckConstraint]:
    """Named CHECKs of the provenance block (``table`` = constraint name stem, e.g. ``identity_customer``)."""
    return [
        models.CheckConstraint(
            condition=in_values("provenance_kind", ProvenanceKind.values), name=f"ck_{table}_prov_kind"
        ),
        models.CheckConstraint(
            condition=~Q(provenance_kind__in=[ProvenanceKind.IMP, ProvenanceKind.LEG])
            | Q(import_batch__isnull=False, staging_row__isnull=False),
            name=f"ck_{table}_prov_imp_has_row",
        ),
        models.CheckConstraint(
            condition=~Q(provenance_kind=ProvenanceKind.SYS)
            | Q(import_batch__isnull=True, staging_row__isnull=True),
            name=f"ck_{table}_prov_sys_no_batch",
        ),
        models.CheckConstraint(
            condition=Q(source_raw_value__isnull=True) | Q(LessThanOrEqual(Length("source_raw_value"), 4000)),
            name=f"ck_{table}_prov_raw_len",
        ),
    ]


def provenance_indexes(table: str) -> list[models.Index]:
    return [
        models.Index(fields=["import_batch"], name=f"ix_{table}_prov_batch"),
        models.Index(fields=["staging_row"], name=f"ix_{table}_prov_row"),
    ]


def trimmed_nonempty(field: str) -> Q:
    """``<field> <> '' AND <field> = btrim(<field>)`` (technical identifiers, raw external values)."""
    return ~Q(**{field: ""}) & Q(**{field: Trim(field)})


def min_length(field: str, n: int) -> GreaterThanOrEqual:
    """``length(<field>) >= n`` for named CHECK constraints (e.g. mandatory reasons)."""
    return GreaterThanOrEqual(Length(field), n)


def in_values(field: str, values: Sequence[str]) -> Q:
    return Q(**{f"{field}__in": list(values)})
