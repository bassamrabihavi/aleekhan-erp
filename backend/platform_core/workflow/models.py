"""Tasks, maker-checker approvals and workflow definitions/instances (PHASE_01 / 01.2).

State machines: docs/discovery/STATE_TRANSITIONS.md section 4.3 (WorkTask), 4.4 (ApprovalRequest), 4.5
(WorkflowInstance). The DB holds the allowed state values, the per-state field invariants and the
"terminal rows are immutable" triggers; transition rules are the engine of step 01.3.

* DEC-032 (APPROVED): decider != requester (CHECK ``ck_approval_request_maker_checker``); every request has an
  expiry (``expires_at`` NOT NULL - 30 days, parameter ``approval_request_expiry_days``); one-time decision.
* DEC-048 (APPROVED): PHASE_01 routing = role + unit scope only (``route_kind`` CHECK = ROLE_UNIT_SCOPE).
* WorkTask: DONE != CLOSED; the verifier differs from the completer (CHECK ``ck_work_task_verifier``).
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import CheckConstraint, F, Func, Q, UniqueConstraint, Value
from django.db.models.functions import Now
from django.db.models.lookups import Exact

from platform_core.models import _json_is_object
from platform_core.schema_common import (
    DECISION_ID_PATTERN,
    ENTITY_TYPE_PATTERN,
    ERROR_CODE_PATTERN,
    SYSTEM_KEY_PATTERN,
    Provenance,
    in_values,
    min_length,
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


# --------------------------------------------------------------------------------------- workflow defs
class DefinitionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    RETIRED = "RETIRED", "Retired"


class WorkflowDefinition(models.Model):
    """Versioned definition shipped in reviewed migrations; steps are immutable once not DRAFT (trigger)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64)
    version = models.IntegerField()
    name_fa = models.CharField(max_length=200)
    status = models.CharField(
        max_length=8, choices=DefinitionStatus.choices, db_default=DefinitionStatus.DRAFT
    )
    steps = models.JSONField(default=list)
    decision_id = models.CharField(max_length=7, blank=True, default="")
    provenance = models.CharField(
        max_length=16, choices=Provenance.choices, db_default=Provenance.MIGRATION_SEED
    )
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_workflow_definition"
        constraints = [
            UniqueConstraint(fields=["key", "version"], name="uq_workflow_definition_key_version"),
            UniqueConstraint(
                fields=["key"],
                condition=Q(status=DefinitionStatus.ACTIVE),
                name="uq_workflow_definition_active",
            ),
            CheckConstraint(
                condition=Q(key__regex=SYSTEM_KEY_PATTERN), name="ck_workflow_definition_key_fmt"
            ),
            CheckConstraint(condition=Q(version__gte=1), name="ck_workflow_definition_version_pos"),
            CheckConstraint(
                condition=Exact(
                    Func(F("steps"), function="jsonb_typeof", output_field=models.CharField()), Value("array")
                ),
                name="ck_workflow_definition_steps_array",
            ),
            CheckConstraint(condition=~Q(name_fa=""), name="ck_workflow_definition_name_nonempty"),
            CheckConstraint(
                condition=in_values("status", DefinitionStatus.values), name="ck_workflow_definition_status"
            ),
            CheckConstraint(
                condition=Q(decision_id="") | Q(decision_id__regex=DECISION_ID_PATTERN),
                name="ck_workflow_definition_decision_fmt",
            ),
            CheckConstraint(
                condition=in_values("provenance", Provenance.values), name="ck_workflow_definition_provenance"
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_workflow_definition_row_version_pos"),
        ]

    def __str__(self) -> str:
        return f"{self.key} v{self.version} [{self.status}]"


class InstanceStatus(models.TextChoices):
    RUNNING = "RUNNING", "Running"
    WAITING = "WAITING", "Waiting for a task/approval"
    CANCEL_REQUESTED = "CANCEL_REQUESTED", "Cancel requested"
    COMPENSATING = "COMPENSATING", "Compensating"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    FAILED = "FAILED", "Failed"


INSTANCE_TERMINAL = [InstanceStatus.COMPLETED, InstanceStatus.CANCELLED, InstanceStatus.FAILED]


class WorkflowInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.PROTECT, related_name="instances", db_index=False
    )
    subject_type = models.CharField(max_length=64)
    subject_id = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20, choices=InstanceStatus.choices, db_default=InstanceStatus.RUNNING
    )
    current_step = models.CharField(max_length=64, blank=True, default="")
    started_at = models.DateTimeField(db_default=Now())
    started_by = _user_fk()
    ended_at = models.DateTimeField(null=True, blank=True)
    cancel_requested_by = _user_fk()
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=500, blank=True, default="")
    failure_code = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_workflow_instance"
        constraints = [
            CheckConstraint(
                condition=in_values("status", InstanceStatus.values), name="ck_workflow_instance_status"
            ),
            CheckConstraint(
                condition=Q(subject_type__regex=ENTITY_TYPE_PATTERN), name="ck_workflow_instance_subject_fmt"
            ),
            CheckConstraint(condition=~Q(subject_id=""), name="ck_workflow_instance_subject_id_nonempty"),
            CheckConstraint(
                condition=~in_values("status", INSTANCE_TERMINAL) | Q(ended_at__isnull=False),
                name="ck_workflow_instance_terminal_ended",
            ),
            CheckConstraint(
                condition=in_values("status", INSTANCE_TERMINAL) | Q(ended_at__isnull=True),
                name="ck_workflow_instance_live_not_ended",
            ),
            CheckConstraint(
                condition=~in_values(
                    "status",
                    [InstanceStatus.CANCEL_REQUESTED, InstanceStatus.COMPENSATING, InstanceStatus.CANCELLED],
                )
                | (Q(cancel_requested_at__isnull=False) & Q(min_length("cancel_reason", 3))),
                name="ck_workflow_instance_cancel_reason",
            ),
            CheckConstraint(
                condition=~Q(status=InstanceStatus.FAILED) | Q(failure_code__regex=ERROR_CODE_PATTERN),
                name="ck_workflow_instance_failure_code",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_workflow_instance_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["definition"], name="ix_workflow_instance_def"),
            models.Index(fields=["subject_type", "subject_id"], name="ix_workflow_instance_subject"),
            models.Index(fields=["status", "started_at"], name="ix_workflow_instance_status"),
            models.Index(fields=["started_by"], name="ix_workflow_instance_starter"),
            models.Index(fields=["cancel_requested_by"], name="ix_workflow_instance_cancel_by"),
        ]

    def __str__(self) -> str:
        return f"{self.definition_id} {self.subject_type}:{self.subject_id} [{self.status}]"


class StepEventKind(models.TextChoices):
    ENTERED = "ENTERED", "Step entered"
    COMPLETED = "COMPLETED", "Step completed"
    FAILED = "FAILED", "Step failed"
    COMPENSATION_STARTED = "COMPENSATION_STARTED", "Compensation started"
    COMPENSATED = "COMPENSATED", "Step compensated (new records, never deletes)"


class WorkflowStepEvent(models.Model):
    """Append-only history of an instance (trigger ``trg_workflow_step_event_append_only``)."""

    id = models.BigAutoField(primary_key=True)
    instance = models.ForeignKey(
        WorkflowInstance, on_delete=models.PROTECT, related_name="events", db_index=False
    )
    seq = models.IntegerField()
    step_key = models.CharField(max_length=64)
    event = models.CharField(max_length=24, choices=StepEventKind.choices)
    occurred_at = models.DateTimeField(db_default=Now())
    actor = _user_fk()
    detail = models.JSONField(default=dict)

    class Meta:
        db_table = "platform_workflow_step_event"
        constraints = [
            UniqueConstraint(fields=["instance", "seq"], name="uq_workflow_step_event_seq"),
            CheckConstraint(condition=Q(seq__gte=1), name="ck_workflow_step_event_seq_pos"),
            CheckConstraint(condition=~Q(step_key=""), name="ck_workflow_step_event_step_nonempty"),
            CheckConstraint(
                condition=in_values("event", StepEventKind.values), name="ck_workflow_step_event_kind"
            ),
            CheckConstraint(condition=_json_is_object("detail"), name="ck_workflow_step_event_detail_object"),
        ]
        indexes = [models.Index(fields=["actor"], name="ix_workflow_step_event_actor")]

    def __str__(self) -> str:
        return f"{self.instance_id}#{self.seq} {self.event}"


# -------------------------------------------------------------------------------------------- approval
class ApprovalStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"
    SUPERSEDED = "SUPERSEDED", "Superseded (resource got a new revision)"
    EXPIRED = "EXPIRED", "Expired (DEC-032: 30 days)"


APPROVAL_DECIDED = [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]


class RouteKind(models.TextChoices):
    ROLE_UNIT_SCOPE = "ROLE_UNIT_SCOPE", "Role + org-unit scope (DEC-048: the only PHASE_01 routing)"


class ApprovalRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.ForeignKey(
        "platform_core.Permission",
        on_delete=models.PROTECT,
        related_name="+",
        db_column="action",
        db_index=False,
    )
    resource_type = models.CharField(max_length=64)
    resource_id = models.CharField(max_length=64)
    resource_revision = models.BigIntegerField()
    status = models.CharField(
        max_length=12, choices=ApprovalStatus.choices, db_default=ApprovalStatus.PENDING
    )
    requested_by = _user_fk(null=False)
    requested_at = models.DateTimeField(db_default=Now())
    expires_at = models.DateTimeField()
    route_kind = models.CharField(
        max_length=20, choices=RouteKind.choices, db_default=RouteKind.ROLE_UNIT_SCOPE
    )
    route_scope_unit = models.ForeignKey(
        "platform_core.OrgUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    decided_by = _user_fk()
    decision_note = models.CharField(max_length=500, blank=True, default="")
    # DEC-055 (option B): the owner's one-time self-approval of the first holder of a business-approval role
    bootstrap_self_approval = models.BooleanField(db_default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    workflow_instance = models.ForeignKey(
        WorkflowInstance, on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_approval_request"
        constraints = [
            UniqueConstraint(
                fields=["resource_type", "resource_id", "resource_revision", "action"],
                condition=Q(status=ApprovalStatus.PENDING),
                name="uq_approval_request_one_pending",
            ),
            CheckConstraint(
                condition=in_values("status", ApprovalStatus.values), name="ck_approval_request_status"
            ),
            CheckConstraint(
                condition=Q(resource_type__regex=ENTITY_TYPE_PATTERN), name="ck_approval_request_resource_fmt"
            ),
            CheckConstraint(condition=~Q(resource_id=""), name="ck_approval_request_resource_id_nonempty"),
            CheckConstraint(
                condition=Q(resource_revision__gte=0), name="ck_approval_request_revision_nonneg"
            ),
            CheckConstraint(
                condition=in_values("route_kind", RouteKind.values), name="ck_approval_request_route_kind"
            ),
            # DEC-032: maker != checker, never self-approval - except the DEC-055 (option B) bootstrap
            # self-approval of the first holder of a business-approval role (trigger, migration 0013)
            CheckConstraint(
                condition=Q(decided_by__isnull=True)
                | ~Q(decided_by=F("requested_by"))
                | Q(bootstrap_self_approval=True, status=ApprovalStatus.APPROVED),
                name="ck_approval_request_maker_checker",
            ),
            CheckConstraint(
                condition=Q(bootstrap_self_approval=False)
                | Q(
                    status=ApprovalStatus.APPROVED,
                    action="platform.identity.assignment.grant",
                    resource_type="role_assignment",
                ),
                name="ck_approval_request_bootstrap_scope",
            ),
            CheckConstraint(
                condition=Q(expires_at__gt=F("requested_at")), name="ck_approval_request_expiry_after_request"
            ),
            CheckConstraint(
                condition=~in_values("status", APPROVAL_DECIDED) | Q(decided_by__isnull=False),
                name="ck_approval_request_decided_has_decider",
            ),
            CheckConstraint(
                condition=in_values("status", APPROVAL_DECIDED) | Q(decided_by__isnull=True),
                name="ck_approval_request_undecided_no_decider",
            ),
            CheckConstraint(
                condition=~Q(status=ApprovalStatus.REJECTED) | Q(min_length("decision_note", 3)),
                name="ck_approval_request_reject_note",
            ),
            CheckConstraint(
                condition=Q(status=ApprovalStatus.PENDING, closed_at__isnull=True)
                | (~Q(status=ApprovalStatus.PENDING) & Q(closed_at__isnull=False)),
                name="ck_approval_request_closed_at",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_approval_request_row_version_pos"),
        ]
        indexes = [
            models.Index(
                fields=["expires_at"],
                name="ix_approval_request_expiry",
                condition=Q(status=ApprovalStatus.PENDING),
            ),
            models.Index(fields=["requested_by", "status"], name="ix_approval_request_requester"),
            models.Index(fields=["route_scope_unit", "status"], name="ix_approval_request_scope"),
            models.Index(fields=["action"], name="ix_approval_request_action"),
            models.Index(fields=["decided_by"], name="ix_approval_request_decider"),
            models.Index(fields=["workflow_instance"], name="ix_approval_request_instance"),
            models.Index(fields=["resource_type", "resource_id"], name="ix_approval_request_resource"),
        ]

    def __str__(self) -> str:
        return f"{self.action_id} {self.resource_type}:{self.resource_id} [{self.status}]"


# ------------------------------------------------------------------------------------------------ task
class TaskStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    ASSIGNED = "ASSIGNED", "Assigned to a user"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    BLOCKED = "BLOCKED", "Blocked"
    DONE = "DONE", "Done (not yet verified)"
    CLOSED = "CLOSED", "Closed (verified by someone else)"
    CANCELLED = "CANCELLED", "Cancelled"


class AssigneeKind(models.TextChoices):
    USER = "USER", "User"
    ORG_UNIT = "ORG_UNIT", "Org unit"
    POSITION = "POSITION", "Position"


class WorkTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.CharField(max_length=300)
    related_type = models.CharField(max_length=64, blank=True, default="")
    related_id = models.CharField(max_length=64, blank=True, default="")
    related_revision = models.BigIntegerField(null=True, blank=True)
    assignee_kind = models.CharField(max_length=8, choices=AssigneeKind.choices)
    assignee_user = _user_fk()
    assignee_unit = models.ForeignKey(
        "platform_core.OrgUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    assignee_position = models.ForeignKey(
        "platform_core.Position",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    status = models.CharField(max_length=12, choices=TaskStatus.choices, db_default=TaskStatus.OPEN)
    due_at = models.DateTimeField(null=True, blank=True)  # informational only (no approved SLA rule)
    blocked_reason = models.CharField(max_length=500, blank=True, default="")
    blocked_by_ref = models.CharField(max_length=200, blank=True, default="")
    created_by = _user_fk()  # NULL = created by the system (workflow step)
    created_at = models.DateTimeField(db_default=Now())
    completed_by = _user_fk()
    completed_at = models.DateTimeField(null=True, blank=True)
    closed_by = _user_fk()
    closed_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = _user_fk()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=500, blank=True, default="")
    workflow_instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tasks",
        db_index=False,
    )
    updated_at = models.DateTimeField(db_default=Now())
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_work_task"
        constraints = [
            CheckConstraint(condition=in_values("status", TaskStatus.values), name="ck_work_task_status"),
            CheckConstraint(
                condition=in_values("assignee_kind", AssigneeKind.values), name="ck_work_task_assignee_kind"
            ),
            CheckConstraint(
                condition=Q(
                    assignee_kind=AssigneeKind.USER,
                    assignee_user__isnull=False,
                    assignee_unit__isnull=True,
                    assignee_position__isnull=True,
                )
                | Q(
                    assignee_kind=AssigneeKind.ORG_UNIT,
                    assignee_user__isnull=True,
                    assignee_unit__isnull=False,
                    assignee_position__isnull=True,
                )
                | Q(
                    assignee_kind=AssigneeKind.POSITION,
                    assignee_user__isnull=True,
                    assignee_unit__isnull=True,
                    assignee_position__isnull=False,
                ),
                name="ck_work_task_assignee_ref",
            ),
            CheckConstraint(
                condition=~Q(status=TaskStatus.ASSIGNED) | Q(assignee_kind=AssigneeKind.USER),
                name="ck_work_task_assigned_to_user",
            ),
            CheckConstraint(condition=~Q(subject=""), name="ck_work_task_subject_nonempty"),
            CheckConstraint(
                condition=Q(related_type="", related_id="", related_revision__isnull=True)
                | (Q(related_type__regex=ENTITY_TYPE_PATTERN) & ~Q(related_id="")),
                name="ck_work_task_related_ref",
            ),
            CheckConstraint(
                condition=~Q(status=TaskStatus.BLOCKED) | Q(min_length("blocked_reason", 3)),
                name="ck_work_task_blocked_reason",
            ),
            CheckConstraint(
                condition=~in_values("status", [TaskStatus.DONE, TaskStatus.CLOSED])
                | Q(completed_by__isnull=False, completed_at__isnull=False),
                name="ck_work_task_done_has_completer",
            ),
            CheckConstraint(
                condition=~Q(status=TaskStatus.CLOSED) | Q(closed_by__isnull=False, closed_at__isnull=False),
                name="ck_work_task_closed_has_verifier",
            ),
            # catalogue: closure verified by someone other than the completer
            CheckConstraint(
                condition=Q(closed_by__isnull=True) | ~Q(closed_by=F("completed_by")),
                name="ck_work_task_verifier",
            ),
            CheckConstraint(
                condition=~Q(status=TaskStatus.CANCELLED)
                | (Q(cancelled_at__isnull=False) & Q(min_length("cancel_reason", 3))),
                name="ck_work_task_cancel_reason",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_work_task_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["assignee_user", "status"], name="ix_work_task_assignee_user"),
            models.Index(fields=["assignee_unit", "status"], name="ix_work_task_assignee_unit"),
            models.Index(fields=["assignee_position", "status"], name="ix_work_task_assignee_pos"),
            models.Index(fields=["workflow_instance"], name="ix_work_task_instance"),
            models.Index(fields=["related_type", "related_id"], name="ix_work_task_related"),
            models.Index(fields=["created_by"], name="ix_work_task_created_by"),
            models.Index(fields=["completed_by"], name="ix_work_task_completed_by"),
            models.Index(fields=["closed_by"], name="ix_work_task_closed_by"),
            models.Index(fields=["cancelled_by"], name="ix_work_task_cancelled_by"),
            models.Index(fields=["updated_by"], name="ix_work_task_updated_by"),
        ]

    def __str__(self) -> str:
        return f"task {self.id} [{self.status}]"
