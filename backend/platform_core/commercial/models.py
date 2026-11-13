"""Commercial module tables (PHASE_02 / 02.2): customer orders (PO header + independent lines), immutable
order
versions and change requests.

Design: docs/discovery/DATA_TABLE.md (PHASE_02 section 3), STATE_TRANSITIONS.md 5.1/5.2/5.5, docs/db/ERD.md
section 7. Decisions built in (all APPROVED 2026-11-12):

* DEC-006 L-A: every line gets its serial when the order is confirmed, in the same transaction. A CONFIRMED
  line
  always has a serial (CHECK); a line never has two serials and a serial belongs to one line (UNIQUE FK).
* DEC-057: the confirmer is not the order's creator (``ck_commercial_order_confirmer_not_creator``); the
  decider
  of a change request is not its requester.
* DEC-058: brand optional and of the same customer (trigger); PO number not unique (warning only); order types
  seeded (0021); the customer representative **name** only (PII: masked for viewers, audited reads/changes by
  the engine; never in exports, logs or fixtures); required grade = free text.
* DEC-059: a confirmed order is never edited in place: header/line data change only together with a version
  bump (+1) made by an applied change request, which also writes the new ``CustomerOrderVersion``. After
  release to planning only the due date and hold/resume may change; cancel only before release. One ON_HOLD
  state that resumes to the stored previous state. A due-date change also needs the planning approval.

Not decided, so NOT enforced here (REV-0203): "one open change request per order", a change request expiry
period. Decided 2026-11-12 (DEC-059 amendment, 02.3 migration 0023): the planning approver of a due-date
change is neither the requester nor the deciding manager; a held order whose stored state is CONFIRMED may be
cancelled directly.

Triggers and deferred constraint triggers: migration 0020 (``0020_phase02_db_guards``).
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint
from django.db.models.functions import Now

from platform_core.integration.models import _jsonb_typeof_is
from platform_core.models import _json_is_object
from platform_core.product_identity.models import AuditColumns, PartyStatus
from platform_core.schema_common import (
    DECISION_ID_PATTERN,
    SYSTEM_KEY_PATTERN,
    Provenance,
    in_values,
    min_length,
    trimmed_nonempty,
)


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


def _row_version(table: str) -> CheckConstraint:
    return CheckConstraint(condition=Q(row_version__gte=1), name=f"ck_{table}_row_version_pos")


class OrderType(models.Model):
    """DEC-058: the four Planning order types (seed 0021); generic, no customer data."""

    code = models.CharField(max_length=64, primary_key=True)
    label_fa = models.CharField(max_length=100)
    sort_order = models.SmallIntegerField()
    status = models.CharField(max_length=8, choices=PartyStatus.choices, db_default=PartyStatus.ACTIVE)
    decision_id = models.CharField(max_length=7)
    provenance = models.CharField(max_length=16, choices=Provenance.choices, db_default=Provenance.SYS)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "commercial_order_type"
        constraints = [
            CheckConstraint(
                condition=Q(code__regex=SYSTEM_KEY_PATTERN), name="ck_commercial_order_type_code_fmt"
            ),
            CheckConstraint(condition=~Q(label_fa=""), name="ck_commercial_order_type_label_nonempty"),
            CheckConstraint(condition=Q(sort_order__gte=0), name="ck_commercial_order_type_sort_nonneg"),
            CheckConstraint(
                condition=in_values("status", PartyStatus.values), name="ck_commercial_order_type_status"
            ),
            CheckConstraint(
                condition=Q(decision_id__regex=DECISION_ID_PATTERN), name="ck_commercial_order_type_decision"
            ),
            CheckConstraint(
                condition=in_values("provenance", [Provenance.SYS, Provenance.MIGRATION_SEED]),
                name="ck_commercial_order_type_provenance",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class OrderStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft (edited directly)"
    VALIDATED = "VALIDATED", "Validated"
    CONFIRMED = "CONFIRMED", "Confirmed by planning; serials allocated (DEC-006 L-A / DEC-057)"
    RELEASED_TO_PLAN = "RELEASED_TO_PLAN", "Released to planning"
    ON_HOLD = "ON_HOLD", "On hold (single hold state, DEC-059)"
    CANCELLED = "CANCELLED", "Cancelled"
    # written only by later phases (PHASE_07/09); FULFILLED -> CLOSED is DEC-020
    PARTIAL_FULFILLED = "PARTIAL_FULFILLED", "Partially fulfilled (later phase)"
    FULFILLED = "FULFILLED", "Fulfilled (later phase)"
    CLOSED = "CLOSED", "Closed (later phase, DEC-020)"


HOLDABLE = (OrderStatus.CONFIRMED, OrderStatus.RELEASED_TO_PLAN)
NOT_CONFIRMED = (OrderStatus.DRAFT, OrderStatus.VALIDATED)


class CustomerOrder(AuditColumns):
    """PO header. Several independent lines per order (ID-03); each line gets its own serial."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_no = models.CharField(max_length=32)  # internal, system-generated (not the serial)
    customer = _fk("platform_core.Customer")
    brand = _fk("platform_core.CustomerBrand", null=True)
    external_po_number = models.CharField(
        max_length=64, blank=True, db_default=""
    )  # raw, NOT unique (DEC-058)
    order_type = _fk("platform_core.OrderType", db_column="order_type_code")
    program_ref = models.CharField(max_length=64, null=True, blank=True)  # PHASE_05 owns programs
    order_date = models.DateField()
    requested_due_date = models.DateField(null=True, blank=True)
    required_quality_requirement = models.CharField(
        max_length=64, null=True, blank=True
    )  # free text (DEC-058)
    # DEC-058: PII (name only, never contact data); masked for management_viewer; reads/changes audited
    customer_representative_name = models.CharField(max_length=200, null=True, blank=True)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, db_default=OrderStatus.DRAFT)
    status_before_hold = models.CharField(max_length=20, null=True, blank=True)
    hold_reason = models.CharField(max_length=500, null=True, blank=True)
    cancel_reason = models.CharField(max_length=500, null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    current_version = models.IntegerField(db_default=0)  # 0 = never confirmed
    confirmed_by = _user_fk()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    released_by = _user_fk()
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "commercial_customer_order"
        constraints = [
            UniqueConstraint(fields=["order_no"], name="uq_commercial_order_no"),
            CheckConstraint(condition=trimmed_nonempty("order_no"), name="ck_commercial_order_no_fmt"),
            CheckConstraint(
                condition=in_values("status", OrderStatus.values), name="ck_commercial_order_status"
            ),
            CheckConstraint(
                condition=Q(requested_due_date__isnull=True) | Q(requested_due_date__gte=F("order_date")),
                name="ck_commercial_order_due_after_order",
            ),
            CheckConstraint(
                condition=Q(
                    status=OrderStatus.ON_HOLD,
                    status_before_hold__isnull=False,
                    status_before_hold__in=HOLDABLE,
                    hold_reason__isnull=False,
                )
                & Q(min_length("hold_reason", 3))
                | (
                    ~Q(status=OrderStatus.ON_HOLD)
                    & Q(status_before_hold__isnull=True, hold_reason__isnull=True)
                ),
                name="ck_commercial_order_hold_consistent",
            ),
            CheckConstraint(
                condition=~Q(status=OrderStatus.CANCELLED)
                | (
                    Q(cancelled_at__isnull=False, cancel_reason__isnull=False)
                    & Q(min_length("cancel_reason", 3))
                ),
                name="ck_commercial_order_cancel_has_reason",
            ),
            CheckConstraint(condition=Q(current_version__gte=0), name="ck_commercial_order_version_nonneg"),
            CheckConstraint(
                condition=~Q(status__in=NOT_CONFIRMED) | Q(current_version=0, confirmed_by__isnull=True),
                name="ck_commercial_order_draft_unversioned",
            ),
            CheckConstraint(
                condition=Q(status__in=[*NOT_CONFIRMED, OrderStatus.CANCELLED])
                | Q(current_version__gte=1, confirmed_by__isnull=False, confirmed_at__isnull=False),
                name="ck_commercial_order_confirmed_versioned",
            ),
            CheckConstraint(
                condition=~Q(status=OrderStatus.CANCELLED, current_version__gte=1)
                | Q(confirmed_by__isnull=False),
                name="ck_commercial_order_cancel_after_confirm",
            ),
            # DEC-057 / DEC-032: nobody confirms his own order (the owner neither)
            CheckConstraint(
                condition=Q(confirmed_by__isnull=True)
                | (Q(created_by__isnull=False) & ~Q(confirmed_by=F("created_by"))),
                name="ck_commercial_order_confirmer_not_creator",
            ),
            CheckConstraint(
                condition=~Q(status=OrderStatus.RELEASED_TO_PLAN)
                & ~Q(status_before_hold=OrderStatus.RELEASED_TO_PLAN)
                | Q(released_by__isnull=False, released_at__isnull=False),
                name="ck_commercial_order_released_has_actor",
            ),
            CheckConstraint(
                condition=Q(customer_representative_name__isnull=True) | ~Q(customer_representative_name=""),
                name="ck_commercial_order_rep_name_nonempty",
            ),
            _row_version("commercial_order"),
        ]
        indexes = [
            models.Index(fields=["customer", "external_po_number"], name="ix_cord_customer_po"),
            models.Index(fields=["brand"], name="ix_cord_brand"),
            models.Index(fields=["order_type"], name="ix_cord_type"),
            models.Index(fields=["status", "order_date"], name="ix_cord_status"),
            models.Index(fields=["confirmed_by"], name="ix_cord_confirmed_by"),
            models.Index(fields=["released_by"], name="ix_cord_released_by"),
            models.Index(fields=["created_by"], name="ix_cord_created_by"),
            models.Index(fields=["updated_by"], name="ix_cord_updated_by"),
        ]

    def __str__(self) -> str:
        return self.order_no


class LineStatus(models.TextChoices):
    OPEN = "OPEN", "Open (draft order)"
    CONFIRMED = "CONFIRMED", "Confirmed; carries its serial (DEC-006 L-A)"
    REMOVED = "REMOVED", "Removed from a draft (row kept, line_no never re-used)"
    CANCELLED = "CANCELLED", "Cancelled by a change request before release (DEC-059 C-A)"


class CustomerOrderLine(AuditColumns):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = _fk("platform_core.CustomerOrder")
    line_no = models.IntegerField()
    style = _fk("platform_core.Style")
    style_revision = _fk("platform_core.StyleRevision")
    product_code = _fk("platform_core.ProductCode", null=True)
    quantity = models.IntegerField()
    uom = _fk("platform_core.UnitOfMeasure", db_column="uom_code")
    requested_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=LineStatus.choices, db_default=LineStatus.OPEN)
    # REV-0201: the Commercial side holds the pairing; Identity owns the serial row (no mirror column there)
    serial = _fk("platform_core.Serial", null=True)
    order_version = models.IntegerField(db_default=0)  # order version that last changed this line (0 = draft)
    cancel_reason = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        db_table = "commercial_customer_order_line"
        constraints = [
            UniqueConstraint(fields=["order", "line_no"], name="uq_commercial_line_order_no"),
            UniqueConstraint(fields=["serial"], name="uq_commercial_line_serial"),
            CheckConstraint(condition=Q(line_no__gte=1), name="ck_commercial_line_no_pos"),
            CheckConstraint(condition=Q(quantity__gt=0), name="ck_commercial_line_quantity_pos"),
            CheckConstraint(
                condition=in_values("status", LineStatus.values), name="ck_commercial_line_status"
            ),
            CheckConstraint(
                condition=Q(
                    status__in=[LineStatus.OPEN, LineStatus.REMOVED], serial__isnull=True, order_version=0
                )
                | Q(status=LineStatus.CONFIRMED, serial__isnull=False, order_version__gte=1)
                | Q(status=LineStatus.CANCELLED, serial__isnull=False, order_version__gte=1),
                name="ck_commercial_line_serial_by_status",
            ),
            CheckConstraint(
                condition=~Q(status=LineStatus.CANCELLED)
                | (Q(cancel_reason__isnull=False) & Q(min_length("cancel_reason", 3))),
                name="ck_commercial_line_cancel_has_reason",
            ),
            _row_version("commercial_line"),
        ]
        indexes = [
            models.Index(fields=["style"], name="ix_clin_style"),
            models.Index(fields=["style_revision"], name="ix_clin_style_revision"),
            models.Index(fields=["product_code"], name="ix_clin_product_code"),
            models.Index(fields=["uom"], name="ix_clin_uom"),
            models.Index(fields=["created_by"], name="ix_clin_created_by"),
            models.Index(fields=["updated_by"], name="ix_clin_updated_by"),
        ]

    def __str__(self) -> str:
        return f"{self.order_id}#{self.line_no}"


class VersionReason(models.TextChoices):
    CONFIRMED = "CONFIRMED", "Version 1 written at confirmation"
    CHANGE_APPLIED = "CHANGE_APPLIED", "An applied change request"
    CANCELLED = "CANCELLED", "Order cancelled by a change request"


class CustomerOrderVersion(models.Model):
    """Append-only image of the order (header + all lines) per version. Old versions are never modified."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = _fk("platform_core.CustomerOrder")
    version = models.IntegerField()
    image = models.JSONField()
    reason = models.CharField(max_length=16, choices=VersionReason.choices)
    change_request = _fk("platform_core.OrderChangeRequest", null=True)
    created_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk(null=False)

    class Meta:
        db_table = "commercial_customer_order_version"
        constraints = [
            UniqueConstraint(fields=["order", "version"], name="uq_commercial_order_version_no"),
            CheckConstraint(condition=Q(version__gte=1), name="ck_commercial_order_version_pos"),
            CheckConstraint(condition=_json_is_object("image"), name="ck_commercial_order_version_image"),
            CheckConstraint(
                condition=in_values("reason", VersionReason.values), name="ck_commercial_order_version_reason"
            ),
            CheckConstraint(
                condition=Q(version=1, reason=VersionReason.CONFIRMED, change_request__isnull=True)
                | (Q(version__gt=1, change_request__isnull=False) & ~Q(reason=VersionReason.CONFIRMED)),
                name="ck_commercial_order_version_reason_by_no",
            ),
        ]
        indexes = [
            models.Index(fields=["change_request"], name="ix_cver_cr"),
            models.Index(fields=["created_by"], name="ix_cver_by"),
        ]

    def __str__(self) -> str:
        return f"{self.order_id} v{self.version}"


class ChangeKind(models.TextChoices):
    QTY_CHANGE = "QTY_CHANGE", "Quantity (the line keeps its serial, DEC-059)"
    DUE_DATE_CHANGE = "DUE_DATE_CHANGE", "Due date (needs the planning approval too, DEC-059)"
    ADD_LINE = "ADD_LINE", "Add a line (gets a new serial)"
    CANCEL_LINE = "CANCEL_LINE", "Cancel a line (before release only)"
    CANCEL_ORDER = "CANCEL_ORDER", "Cancel the order (before release only)"
    HOLD = "HOLD", "Hold"
    RESUME = "RESUME", "Resume to the previous state"


# DEC-059: after release to planning only these kinds are allowed
AFTER_RELEASE_KINDS = (ChangeKind.DUE_DATE_CHANGE, ChangeKind.HOLD, ChangeKind.RESUME)


class ChangeStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    APPLIED = "APPLIED", "Applied (new order version)"
    WITHDRAWN = "WITHDRAWN", "Withdrawn by the requester"
    EXPIRED = "EXPIRED", "Expired (period not decided: OPEN)"


class OrderChangeRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_no = models.CharField(max_length=32)
    order = _fk("platform_core.CustomerOrder")
    base_order_version = models.IntegerField()
    kind = models.CharField(max_length=16, choices=ChangeKind.choices)
    items = models.JSONField(default=list)
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=12, choices=ChangeStatus.choices, db_default=ChangeStatus.DRAFT)
    impact = models.JSONField(null=True, blank=True)
    approval = _fk("platform_core.ApprovalRequest", null=True)  # commercial_manager decision
    planning_approval = _fk("platform_core.ApprovalRequest", null=True)  # due-date second approval
    requested_by = _user_fk(null=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by = _user_fk()
    decided_at = models.DateTimeField(null=True, blank=True)
    planning_approved_by = _user_fk()
    planning_approved_at = models.DateTimeField(null=True, blank=True)
    applied_by = _user_fk()
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_version = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "commercial_order_change_request"
        constraints = [
            UniqueConstraint(fields=["request_no"], name="uq_commercial_cr_request_no"),
            CheckConstraint(condition=trimmed_nonempty("request_no"), name="ck_commercial_cr_request_no_fmt"),
            CheckConstraint(condition=Q(base_order_version__gte=1), name="ck_commercial_cr_base_version_pos"),
            CheckConstraint(condition=in_values("kind", ChangeKind.values), name="ck_commercial_cr_kind"),
            CheckConstraint(
                condition=in_values("status", ChangeStatus.values), name="ck_commercial_cr_status"
            ),
            CheckConstraint(
                condition=_jsonb_typeof_is("items", "array"), name="ck_commercial_cr_items_array"
            ),
            CheckConstraint(condition=Q(min_length("reason", 3)), name="ck_commercial_cr_reason_len"),
            CheckConstraint(
                condition=Q(impact__isnull=True) | Q(_json_is_object("impact")),
                name="ck_commercial_cr_impact_object",
            ),
            # maker != checker (DEC-057 / DEC-032): the requester never decides or approves his own request
            CheckConstraint(
                condition=Q(decided_by__isnull=True) | ~Q(decided_by=F("requested_by")),
                name="ck_commercial_cr_decider_not_requester",
            ),
            CheckConstraint(
                condition=Q(planning_approved_by__isnull=True) | ~Q(planning_approved_by=F("requested_by")),
                name="ck_commercial_cr_planner_not_requester",
            ),
            # DEC-059 amendment 2026-11-12: the planning approver is not the deciding manager (02.3, 0023)
            CheckConstraint(
                condition=Q(planning_approved_by__isnull=True)
                | Q(decided_by__isnull=True)
                | ~Q(planning_approved_by=F("decided_by")),
                name="ck_commercial_cr_planner_not_decider",
            ),
            CheckConstraint(
                condition=Q(decided_by__isnull=True, decided_at__isnull=True)
                | Q(decided_by__isnull=False, decided_at__isnull=False),
                name="ck_commercial_cr_decided_pair",
            ),
            CheckConstraint(
                condition=Q(planning_approved_by__isnull=True, planning_approved_at__isnull=True)
                | Q(planning_approved_by__isnull=False, planning_approved_at__isnull=False),
                name="ck_commercial_cr_planning_pair",
            ),
            CheckConstraint(
                condition=Q(planning_approved_by__isnull=True, planning_approval__isnull=True)
                | Q(kind=ChangeKind.DUE_DATE_CHANGE),
                name="ck_commercial_cr_planning_only_due_date",
            ),
            CheckConstraint(
                condition=~Q(status__in=[ChangeStatus.SUBMITTED, ChangeStatus.APPROVED, ChangeStatus.APPLIED])
                | Q(submitted_at__isnull=False),
                name="ck_commercial_cr_submitted_has_ts",
            ),
            CheckConstraint(
                condition=~Q(status__in=[ChangeStatus.APPROVED, ChangeStatus.REJECTED, ChangeStatus.APPLIED])
                | Q(decided_by__isnull=False),
                name="ck_commercial_cr_decided_has_decider",
            ),
            CheckConstraint(
                condition=~Q(status=ChangeStatus.APPLIED)
                | Q(
                    applied_by__isnull=False,
                    applied_at__isnull=False,
                    applied_version__isnull=False,
                    applied_version=F("base_order_version") + 1,
                ),
                name="ck_commercial_cr_applied_next_version",
            ),
            CheckConstraint(
                condition=Q(status=ChangeStatus.APPLIED)
                | Q(applied_by__isnull=True, applied_at__isnull=True, applied_version__isnull=True),
                name="ck_commercial_cr_unapplied_empty",
            ),
            # DEC-059: a due-date change is applied only with the planning approval as well
            CheckConstraint(
                condition=~Q(status=ChangeStatus.APPLIED, kind=ChangeKind.DUE_DATE_CHANGE)
                | Q(planning_approved_by__isnull=False),
                name="ck_commercial_cr_due_date_planning_approved",
            ),
        ]
        indexes = [
            models.Index(fields=["order", "status"], name="ix_ccr_order_status"),
            models.Index(fields=["approval"], name="ix_ccr_approval"),
            models.Index(fields=["planning_approval"], name="ix_ccr_planning_approval"),
            models.Index(fields=["requested_by"], name="ix_ccr_requested_by"),
            models.Index(fields=["decided_by"], name="ix_ccr_decided_by"),
            models.Index(fields=["planning_approved_by"], name="ix_ccr_planning_by"),
            models.Index(fields=["applied_by"], name="ix_ccr_applied_by"),
        ]

    def __str__(self) -> str:
        return self.request_no
