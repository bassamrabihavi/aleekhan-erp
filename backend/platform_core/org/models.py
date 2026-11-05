"""Organisation tree (DEC-043, details DEC-048 APPROVED 2026-11-04) - PHASE_01 / 01.2.

* ``OrgUnitType``  fixed list seeded by migration (COMPANY, DEPARTMENT, SECTION, LINE); the owner/admin may
  add types (provenance SYS). Types do not impose a parent/child order (DEC-048 does not state one).
* ``OrgUnit``      current structure (``parent``) + ``effective_from`` of the current values. Every change is
  copied by trigger into ``OrgUnitHistory`` (effective-dated, append-only except closing ``valid_to``).
  Trigger ``trg_org_unit_tree_guard`` (serialised by an advisory lock): no cycle, depth <= parameter
  ``org_tree_max_depth`` (DEC-048: 6), no ACTIVE child under an INACTIVE parent.
* ``Position``     reports-to between POSITIONS (DEC-048 item 3), acyclic (trigger); at most one ACTIVE unit
  head.
  History in ``PositionHistory``.
* ``PositionAssignment``  one PRIMARY position per person at any instant + ACTING with an end date (DEC-048
  item 2); a position may have up to ``Position.primary_capacity`` PRIMARY holders at once (Q-0106, employer
  answer 2026-11-05; default 1, unit heads 1); no ADDITIONAL kind in PHASE_01. Exclusion constraints and
  per-position locks (migration 0008) are race-safe.
  Holding a position grants NO permission (roles are separate, DEC-049).

The tree holds names only - no contact data (DEC-048 item 6). Real units/people are never seeded (C-45).
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint
from django.db.models.functions import Now

from platform_core.schema_common import (
    DECISION_ID_PATTERN,
    SYNTHETIC_LABEL,
    SYSTEM_KEY_PATTERN,
    UNIT_TYPE_PATTERN,
    Provenance,
    in_values,
    min_length,
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


class OrgStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive (effective-dated end, never deleted)"


class OrgUnitType(models.Model):
    code = models.CharField(max_length=32, primary_key=True)
    name_fa = models.CharField(max_length=100)
    sort_order = models.SmallIntegerField()
    is_active = models.BooleanField(db_default=True)
    decision_id = models.CharField(max_length=7, blank=True, default="")
    provenance = models.CharField(max_length=16, choices=Provenance.choices, db_default=Provenance.SYS)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_org_unit_type"
        constraints = [
            CheckConstraint(condition=Q(code__regex=UNIT_TYPE_PATTERN), name="ck_org_unit_type_code_fmt"),
            CheckConstraint(condition=~Q(name_fa=""), name="ck_org_unit_type_name_nonempty"),
            CheckConstraint(condition=Q(sort_order__gte=0), name="ck_org_unit_type_sort_nonneg"),
            CheckConstraint(
                condition=Q(decision_id="") | Q(decision_id__regex=DECISION_ID_PATTERN),
                name="ck_org_unit_type_decision_fmt",
            ),
            CheckConstraint(
                condition=in_values("provenance", [Provenance.SYS, Provenance.MIGRATION_SEED]),
                name="ck_org_unit_type_provenance",
            ),
            CheckConstraint(
                condition=~Q(provenance=Provenance.MIGRATION_SEED) | ~Q(decision_id=""),
                name="ck_org_unit_type_seed_has_decision",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_org_unit_type_row_version_pos"),
        ]
        indexes = [models.Index(fields=["created_by"], name="ix_org_unit_type_created_by")]

    def __str__(self) -> str:
        return self.code


def _synthetic_label_check(table: str, field: str) -> CheckConstraint:
    return CheckConstraint(
        condition=~Q(provenance=Provenance.SEED_SYNTHETIC) | Q(**{f"{field}__contains": SYNTHETIC_LABEL}),
        name=f"ck_{table}_synthetic_label",
    )


def _provenance_check(table: str) -> CheckConstraint:
    return CheckConstraint(
        condition=in_values("provenance", [Provenance.SYS, Provenance.SEED_SYNTHETIC]),
        name=f"ck_{table}_provenance",
    )


class OrgUnit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64)
    name_fa = models.CharField(max_length=200)
    unit_type = models.ForeignKey(
        OrgUnitType, on_delete=models.PROTECT, related_name="+", db_column="unit_type_code", db_index=False
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children", db_index=False
    )
    status = models.CharField(max_length=8, choices=OrgStatus.choices, db_default=OrgStatus.ACTIVE)
    effective_from = models.DateTimeField(db_default=Now())
    provenance = models.CharField(max_length=16, choices=Provenance.choices, db_default=Provenance.SYS)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk()
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_org_unit"
        constraints = [
            UniqueConstraint(fields=["code"], name="uq_org_unit_code"),
            CheckConstraint(condition=Q(code__regex=SYSTEM_KEY_PATTERN), name="ck_org_unit_code_fmt"),
            CheckConstraint(condition=~Q(name_fa=""), name="ck_org_unit_name_nonempty"),
            CheckConstraint(condition=in_values("status", OrgStatus.values), name="ck_org_unit_status"),
            CheckConstraint(condition=~Q(parent=F("id")), name="ck_org_unit_not_own_parent"),
            _provenance_check("org_unit"),
            _synthetic_label_check("org_unit", "name_fa"),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_org_unit_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["parent"], name="ix_org_unit_parent"),
            models.Index(fields=["unit_type"], name="ix_org_unit_type"),
            models.Index(fields=["created_by"], name="ix_org_unit_created_by"),
            models.Index(fields=["updated_by"], name="ix_org_unit_updated_by"),
        ]

    def __str__(self) -> str:
        return self.code


class OrgUnitHistory(models.Model):
    """Effective-dated snapshot of an org unit, written only by trigger ``trg_org_unit_history``."""

    id = models.BigAutoField(primary_key=True)
    unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="history", db_index=False)
    unit_row_version = models.BigIntegerField()
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField(null=True, blank=True)
    code = models.CharField(max_length=64)
    name_fa = models.CharField(max_length=200)
    unit_type_code = models.CharField(max_length=32)
    parent = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    status = models.CharField(max_length=8, choices=OrgStatus.choices)
    changed_by = _user_fk()
    recorded_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "platform_org_unit_history"
        constraints = [
            UniqueConstraint(fields=["unit", "unit_row_version"], name="uq_org_unit_history_version"),
            CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                name="ck_org_unit_history_validity",
            ),
            CheckConstraint(
                condition=in_values("status", OrgStatus.values), name="ck_org_unit_history_status"
            ),
        ]
        indexes = [
            models.Index(fields=["unit", "valid_from"], name="ix_org_unit_history_unit"),
            models.Index(fields=["parent"], name="ix_org_unit_history_parent"),
            models.Index(fields=["changed_by"], name="ix_org_unit_history_changed_by"),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.unit_row_version}"


class Position(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="positions", db_index=False)
    code = models.CharField(max_length=64)
    title_fa = models.CharField(max_length=200)
    reports_to = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reports", db_index=False
    )
    is_unit_head = models.BooleanField(db_default=False)
    # Q-0106 (employer answer 2026-11-05): how many PRIMARY holders the position may have at any instant;
    # default 1, a unit-head (managerial) position always 1. Enforced under a per-position lock (0008).
    primary_capacity = models.SmallIntegerField(db_default=1)
    status = models.CharField(max_length=8, choices=OrgStatus.choices, db_default=OrgStatus.ACTIVE)
    effective_from = models.DateTimeField(db_default=Now())
    provenance = models.CharField(max_length=16, choices=Provenance.choices, db_default=Provenance.SYS)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk()
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_position"
        constraints = [
            UniqueConstraint(fields=["code"], name="uq_position_code"),
            UniqueConstraint(
                fields=["unit"],
                condition=Q(is_unit_head=True, status=OrgStatus.ACTIVE),
                name="uq_position_one_active_head",
            ),
            CheckConstraint(condition=Q(code__regex=SYSTEM_KEY_PATTERN), name="ck_position_code_fmt"),
            CheckConstraint(condition=~Q(title_fa=""), name="ck_position_title_nonempty"),
            CheckConstraint(condition=in_values("status", OrgStatus.values), name="ck_position_status"),
            CheckConstraint(condition=~Q(reports_to=F("id")), name="ck_position_not_own_manager"),
            CheckConstraint(condition=Q(primary_capacity__gte=1), name="ck_position_capacity_pos"),
            CheckConstraint(
                condition=~Q(is_unit_head=True) | Q(primary_capacity=1), name="ck_position_head_capacity_one"
            ),
            _provenance_check("position"),
            _synthetic_label_check("position", "title_fa"),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_position_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["unit", "status"], name="ix_position_unit"),
            models.Index(fields=["reports_to"], name="ix_position_reports_to"),
            models.Index(fields=["created_by"], name="ix_position_created_by"),
            models.Index(fields=["updated_by"], name="ix_position_updated_by"),
        ]

    def __str__(self) -> str:
        return self.code


class PositionHistory(models.Model):
    """Effective-dated snapshot of a position, written only by trigger ``trg_position_history``."""

    id = models.BigAutoField(primary_key=True)
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name="history", db_index=False)
    position_row_version = models.BigIntegerField()
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField(null=True, blank=True)
    unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="+", db_index=False)
    code = models.CharField(max_length=64)
    title_fa = models.CharField(max_length=200)
    reports_to = models.ForeignKey(
        Position, on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    is_unit_head = models.BooleanField()
    primary_capacity = models.SmallIntegerField()
    status = models.CharField(max_length=8, choices=OrgStatus.choices)
    changed_by = _user_fk()
    recorded_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "platform_position_history"
        constraints = [
            UniqueConstraint(fields=["position", "position_row_version"], name="uq_position_history_version"),
            CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                name="ck_position_history_validity",
            ),
            CheckConstraint(
                condition=in_values("status", OrgStatus.values), name="ck_position_history_status"
            ),
        ]
        indexes = [
            models.Index(fields=["position", "valid_from"], name="ix_position_history_position"),
            models.Index(fields=["unit"], name="ix_position_history_unit"),
            models.Index(fields=["reports_to"], name="ix_position_history_reports_to"),
            models.Index(fields=["changed_by"], name="ix_position_history_changed_by"),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.position_row_version}"


class PositionAssignmentKind(models.TextChoices):
    PRIMARY = "PRIMARY", "Primary position (one per person at any instant, DEC-048)"
    ACTING = "ACTING", "Acting (always with an end date, DEC-048)"


class PositionAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name="holders", db_index=False)
    user = models.ForeignKey(
        "platform_core.User", on_delete=models.PROTECT, related_name="position_assignments", db_index=False
    )
    kind = models.CharField(max_length=8, choices=PositionAssignmentKind.choices)
    valid_from = models.DateTimeField(db_default=Now())
    valid_to = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk()
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_position_assignment"
        constraints = [
            CheckConstraint(
                condition=in_values("kind", PositionAssignmentKind.values), name="ck_position_assignment_kind"
            ),
            CheckConstraint(
                condition=~Q(kind=PositionAssignmentKind.ACTING) | Q(valid_to__isnull=False),
                name="ck_position_assignment_acting_has_end",
            ),
            CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=F("valid_from")),
                name="ck_position_assignment_validity",
            ),
            CheckConstraint(condition=Q(min_length("reason", 3)), name="ck_position_assignment_reason"),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_position_assignment_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["position", "valid_from"], name="ix_position_assignment_pos"),
            models.Index(fields=["user", "valid_from"], name="ix_position_assignment_user"),
            models.Index(fields=["created_by"], name="ix_position_assignment_cby"),
            models.Index(fields=["updated_by"], name="ix_position_assignment_uby"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.kind} {self.position_id}"
