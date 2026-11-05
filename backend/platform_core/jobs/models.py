"""Job registry/runs (page 36, STATE_TRANSITIONS 4.7) and audit integrity runs (PHASE_01 / 01.2).

* ``JobDefinition``  seeded by migration; ``protected`` types (migrations, backup, restore) are never
  cancellable (CHECK) - the complete protected list is DEC-024 (PHASE_11); force kill does not exist.
* ``JobRun``         one row per run; ``task_key`` unique (idempotent enqueue). Trigger
  ``trg_job_run_cancel_guard`` refuses CANCEL_REQUESTED/CANCELLED for protected or non-cancellable types
  (DB side of 409 JOB_PROTECTED, Gate-1 "Job kill under permission and reason"); terminal runs are immutable.
* ``AuditIntegrityRun``  append-only result of an audit hash-chain verification (engine 01.3 computes it).
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint
from django.db.models.functions import Now

from platform_core.schema_common import (
    DECISION_ID_PATTERN,
    ERROR_CODE_PATTERN,
    SYSTEM_KEY_PATTERN,
    Provenance,
    in_values,
    min_length,
)


class JobDefinition(models.Model):
    job_type = models.CharField(max_length=64, primary_key=True)
    name_fa = models.CharField(max_length=200)
    cancellable = models.BooleanField()
    protected = models.BooleanField()
    decision_id = models.CharField(max_length=7, blank=True, default="")
    provenance = models.CharField(
        max_length=16, choices=Provenance.choices, db_default=Provenance.MIGRATION_SEED
    )
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_job_definition"
        constraints = [
            CheckConstraint(
                condition=Q(job_type__regex=SYSTEM_KEY_PATTERN), name="ck_job_definition_type_fmt"
            ),
            CheckConstraint(condition=~Q(name_fa=""), name="ck_job_definition_name_nonempty"),
            CheckConstraint(
                condition=~Q(protected=True, cancellable=True),
                name="ck_job_definition_protected_not_cancellable",
            ),
            CheckConstraint(
                condition=Q(decision_id="") | Q(decision_id__regex=DECISION_ID_PATTERN),
                name="ck_job_definition_decision_fmt",
            ),
            CheckConstraint(
                condition=in_values("provenance", [Provenance.MIGRATION_SEED]),
                name="ck_job_definition_provenance",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_job_definition_row_version_pos"),
        ]

    def __str__(self) -> str:
        return self.job_type


class JobState(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    CANCEL_REQUESTED = "CANCEL_REQUESTED", "Cancel requested (stops at next checkpoint)"
    CANCELLED = "CANCELLED", "Cancelled"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"


JOB_TERMINAL = [JobState.CANCELLED, JobState.SUCCEEDED, JobState.FAILED]


class JobRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_type = models.ForeignKey(
        JobDefinition, on_delete=models.PROTECT, related_name="runs", db_column="job_type", db_index=False
    )
    task_key = models.CharField(max_length=200)
    worker_task_id = models.CharField(max_length=64, blank=True, default="")  # Celery task id (DEC-001)
    state = models.CharField(max_length=20, choices=JobState.choices, db_default=JobState.QUEUED)
    requested_by = models.ForeignKey(
        "platform_core.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    queued_at = models.DateTimeField(db_default=Now())
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    progress = models.SmallIntegerField(null=True, blank=True)  # only if the job reports it
    last_checkpoint_at = models.DateTimeField(null=True, blank=True)
    cancel_requested_by = models.ForeignKey(
        "platform_core.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=500, blank=True, default="")
    cancel_too_late = models.BooleanField(db_default=False)
    error_code = models.CharField(max_length=64, blank=True, default="")  # code only, never exception text
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_job_run"
        constraints = [
            UniqueConstraint(fields=["task_key"], name="uq_job_run_task_key"),
            UniqueConstraint(
                fields=["worker_task_id"], condition=~Q(worker_task_id=""), name="uq_job_run_worker_task_id"
            ),
            CheckConstraint(condition=in_values("state", JobState.values), name="ck_job_run_state"),
            CheckConstraint(condition=~Q(task_key=""), name="ck_job_run_task_key_nonempty"),
            CheckConstraint(
                condition=Q(progress__isnull=True) | Q(progress__gte=0, progress__lte=100),
                name="ck_job_run_progress_range",
            ),
            CheckConstraint(
                condition=~in_values("state", [JobState.RUNNING, JobState.CANCEL_REQUESTED])
                | Q(started_at__isnull=False),
                name="ck_job_run_running_started",
            ),
            CheckConstraint(
                condition=~in_values("state", JOB_TERMINAL) | Q(finished_at__isnull=False),
                name="ck_job_run_terminal_finished",
            ),
            CheckConstraint(
                condition=in_values("state", JOB_TERMINAL) | Q(finished_at__isnull=True),
                name="ck_job_run_live_not_finished",
            ),
            # a cancel request always carries who + when + a reason of >= 3 characters (STATE_TRANSITIONS 4.7)
            CheckConstraint(
                condition=Q(cancel_requested_at__isnull=True)
                | (Q(cancel_requested_by__isnull=False) & Q(min_length("cancel_reason", 3))),
                name="ck_job_run_cancel_reason",
            ),
            CheckConstraint(
                condition=~in_values("state", [JobState.CANCEL_REQUESTED, JobState.CANCELLED])
                | Q(cancel_requested_at__isnull=False),
                name="ck_job_run_cancel_requested",
            ),
            CheckConstraint(
                condition=~Q(cancel_too_late=True)
                | Q(cancel_requested_at__isnull=False, state__in=[JobState.SUCCEEDED, JobState.FAILED]),
                name="ck_job_run_cancel_too_late",
            ),
            CheckConstraint(
                condition=~Q(state=JobState.FAILED) | Q(error_code__regex=ERROR_CODE_PATTERN),
                name="ck_job_run_failed_has_code",
            ),
            CheckConstraint(
                condition=Q(error_code="") | Q(error_code__regex=ERROR_CODE_PATTERN),
                name="ck_job_run_error_code_fmt",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_job_run_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["state", "queued_at"], name="ix_job_run_state"),
            models.Index(fields=["job_type", "queued_at"], name="ix_job_run_type"),
            models.Index(fields=["requested_by"], name="ix_job_run_requested_by"),
            models.Index(fields=["cancel_requested_by"], name="ix_job_run_cancel_by"),
        ]

    def __str__(self) -> str:
        return f"{self.job_type_id} {self.id} [{self.state}]"


class IntegrityStatus(models.TextChoices):
    OK = "OK", "Chain intact"
    BROKEN = "BROKEN", "Chain broken (first_broken_event_id)"
    ERROR = "ERROR", "Check could not complete (error_code)"


class AuditIntegrityRun(models.Model):
    """Append-only result of one audit integrity check (trigger ``trg_audit_integrity_run_append_only``)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    status = models.CharField(max_length=8, choices=IntegrityStatus.choices)
    events_checked = models.BigIntegerField()
    checked_up_to_seq = models.BigIntegerField(null=True, blank=True)
    first_broken_event_id = models.UUIDField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    job_run = models.ForeignKey(
        JobRun, on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )

    class Meta:
        db_table = "platform_audit_integrity_run"
        constraints = [
            CheckConstraint(
                condition=in_values("status", IntegrityStatus.values), name="ck_audit_integrity_run_status"
            ),
            CheckConstraint(condition=Q(events_checked__gte=0), name="ck_audit_integrity_run_count_nonneg"),
            CheckConstraint(
                condition=Q(finished_at__gte=F("started_at")),
                name="ck_audit_integrity_run_finished_after_start",
            ),
            CheckConstraint(
                condition=~Q(status=IntegrityStatus.BROKEN) | Q(first_broken_event_id__isnull=False),
                name="ck_audit_integrity_run_broken_ref",
            ),
            CheckConstraint(
                condition=~Q(status=IntegrityStatus.ERROR) | Q(error_code__regex=ERROR_CODE_PATTERN),
                name="ck_audit_integrity_run_error_code",
            ),
        ]
        indexes = [
            models.Index(fields=["finished_at"], name="ix_audit_integrity_finished"),
            models.Index(fields=["job_run"], name="ix_audit_integrity_job"),
        ]

    def __str__(self) -> str:
        return f"integrity {self.finished_at} {self.status}"
