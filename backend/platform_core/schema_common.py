"""Shared schema vocabulary for the PHASE_01 platform tables (step 01.2).

Patterns mirror ``docs/api/openapi-draft.yaml`` (0.5.x) so the database refuses what the contract refuses.
Only structure lives here; behaviour (state machines, policies) is the domain engine of step 01.3.
"""

from __future__ import annotations

from collections.abc import Sequence

from django.db import models
from django.db.models import Q
from django.db.models.functions import Length
from django.db.models.lookups import GreaterThanOrEqual

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


def min_length(field: str, n: int) -> GreaterThanOrEqual:
    """``length(<field>) >= n`` for named CHECK constraints (e.g. mandatory reasons)."""
    return GreaterThanOrEqual(Length(field), n)


def in_values(field: str, values: Sequence[str]) -> Q:
    return Q(**{f"{field}__in": list(values)})
