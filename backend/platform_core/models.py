"""Platform skeleton tables (PHASE_00 / 00.2).

* ``AuditEvent``        append-only audit trail (DB trigger rejects UPDATE/DELETE/TRUNCATE).
* ``OutboxEvent``       transactional outbox; dispatcher reads PENDING/FAILED rows by ``next_attempt_at``.
* ``IdempotencyRecord`` stored outcome of a mutating request per (actor_id, key).
* ``SchemaMeta``        single-row, non-sensitive schema/contract marker (seed, migration 0003).
* ``InboxEvent``        (00.6) consumer-side dedupe per (consumer, event_id); ``engine/consumers.py``.
* ``CompensationRecord`` (00.6) append-only record of a permanent consumer failure (mechanism only).
* Integration tables (00.6): ``platform_core/integration/models.py`` (source registry seeded in 0006 with
  metadata of three read-only sources, import batch, staging row, conflict item).

No business tables here. PHASE_01 platform tables (identity, org, workflow, documents, params, jobs) live in
sibling modules registered at the end of this file. ``actor_id`` columns are plain UUIDs for now;
the FK to the user table is added in PHASE_01 when that table exists.
Behaviour (dispatching, idempotency protocol, redaction) is the domain engine of step 00.3.
"""

from __future__ import annotations

import uuid
from typing import Any, NoReturn

from django.db import models
from django.db.models import CheckConstraint, F, Func, Q, UniqueConstraint, Value
from django.db.models.functions import Now
from django.db.models.lookups import Exact


class ActorType(models.TextChoices):
    USER = "USER", "User"
    SYSTEM = "SYSTEM", "System / job"
    ANONYMOUS = "ANONYMOUS", "Anonymous"


# A USER actor must carry its id (FK to the user table is added in PHASE_01).
ACTOR_CONSISTENT = ~Q(actor_type=ActorType.USER) | Q(actor_id__isnull=False)
# dotted lower-case identifier, e.g. "platform.outbox.replay" / "production.batch.start-cut"
DOTTED_NAME_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)+$"


def _json_is_object(field: str) -> Exact:
    """Boolean expression ``jsonb_typeof(<field>) = 'object'`` for named CHECK constraints."""
    return Exact(Func(F(field), function="jsonb_typeof", output_field=models.CharField()), Value("object"))


class AuditAppendOnlyError(Exception):
    """Raised by the ORM guard; the DB trigger raises SQLSTATE 'P0001' with the same intent."""


class AuditOutcome(models.TextChoices):
    SUCCESS = "SUCCESS", "Success"
    DENIED = "DENIED", "Denied"
    FAILED = "FAILED", "Failed"


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(db_default=Now())
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_id = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    correlation_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=150)
    outcome = models.CharField(max_length=16, choices=AuditOutcome.choices)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=64, blank=True, default="")
    resource_version = models.BigIntegerField(null=True, blank=True)
    scope = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True, default="")
    # before/after must be REDACTED by the writer (no salary, password, PII); enforced in 00.3/00.7.
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    # PHASE_01 / 01.2 additions (DATA_TABLE "AuditEvent extended"). Filled by the 01.3 engine; NULL / '' for
    # PHASE_00 rows; DB defaults keep older/raw INSERTs valid (backward compatible). session_id is the public
    # session handle (no FK: audit is evidence and must stay writable and readable independently of identity
    # rows). Hash chain: chain_seq is the order, event_hash = sha256(prev_hash || canonical event);
    # verification results go to platform_audit_integrity_run.
    session_id = models.UUIDField(null=True, blank=True)
    network_zone = models.CharField(max_length=8, blank=True, db_default="")
    chain_seq = models.BigIntegerField(null=True, blank=True)
    prev_hash = models.CharField(max_length=64, blank=True, db_default="")
    event_hash = models.CharField(max_length=64, blank=True, db_default="")

    class Meta:
        db_table = "platform_audit_event"
        constraints = [
            CheckConstraint(condition=Q(actor_type__in=ActorType.values), name="ck_audit_event_actor_type"),
            CheckConstraint(condition=ACTOR_CONSISTENT, name="ck_audit_event_actor_id_for_user"),
            CheckConstraint(condition=Q(outcome__in=AuditOutcome.values), name="ck_audit_event_outcome"),
            CheckConstraint(condition=Q(action__regex=DOTTED_NAME_PATTERN), name="ck_audit_event_action_fmt"),
            CheckConstraint(condition=~Q(resource_type=""), name="ck_audit_event_resource_type_nonempty"),
            CheckConstraint(condition=_json_is_object("scope"), name="ck_audit_event_scope_object"),
            CheckConstraint(
                condition=Q(resource_version__isnull=True) | Q(resource_version__gte=0),
                name="ck_audit_event_resource_version_nonneg",
            ),
            CheckConstraint(
                condition=Q(network_zone__in=["", "INTERNAL", "EXTERNAL", "UNKNOWN"]),
                name="ck_audit_event_network_zone",
            ),
            CheckConstraint(
                condition=Q(prev_hash="") | Q(prev_hash__regex=r"^[0-9a-f]{64}$"),
                name="ck_audit_event_prev_hash_fmt",
            ),
            CheckConstraint(
                condition=Q(event_hash="") | Q(event_hash__regex=r"^[0-9a-f]{64}$"),
                name="ck_audit_event_event_hash_fmt",
            ),
            CheckConstraint(
                condition=Q(chain_seq__isnull=True, event_hash="")
                | Q(chain_seq__gte=1, event_hash__regex=r"^[0-9a-f]{64}$"),
                name="ck_audit_event_chain_consistent",
            ),
            UniqueConstraint(fields=["chain_seq"], name="uq_audit_event_chain_seq"),
        ]
        indexes = [
            models.Index(fields=["occurred_at"], name="ix_audit_event_occurred"),
            models.Index(fields=["session_id"], name="ix_audit_event_session"),
            models.Index(
                fields=["resource_type", "resource_id", "occurred_at"], name="ix_audit_event_resource"
            ),
            models.Index(fields=["actor_id", "occurred_at"], name="ix_audit_event_actor"),
            models.Index(fields=["request_id"], name="ix_audit_event_request"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.resource_type}:{self.resource_id} ({self.outcome})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # ORM-level guard (defence in depth; the DB trigger is the real enforcement).
        if not self._state.adding:
            raise AuditAppendOnlyError("AuditEvent is append-only")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise AuditAppendOnlyError("AuditEvent is append-only")


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    DISPATCHED = "DISPATCHED", "Dispatched"
    ACKED = "ACKED", "Acknowledged"
    FAILED = "FAILED", "Failed (will retry)"
    DEAD_LETTER = "DEAD_LETTER", "Dead letter"


class OutboxEvent(models.Model):
    # Internal surrogate (dispatch order); never exposed. ``event_id`` is the public, unique identity.
    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=150)
    schema_version = models.IntegerField(db_default=1)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=64)
    aggregate_version = models.BigIntegerField()
    occurred_at = models.DateTimeField(db_default=Now())
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_id = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    correlation_id = models.UUIDField(null=True, blank=True)
    causation_id = models.UUIDField(null=True, blank=True)
    # No salary/password/PII in payloads (DATA_TABLE.md: OutboxEvent sensitivity S1).
    payload = models.JSONField(default=dict)
    delivery_status = models.CharField(
        max_length=16, choices=DeliveryStatus.choices, db_default=DeliveryStatus.PENDING
    )
    attempts = models.IntegerField(db_default=0)
    next_attempt_at = models.DateTimeField(db_default=Now())
    last_error = models.TextField(blank=True, default="")
    dispatched_at = models.DateTimeField(null=True, blank=True)
    acked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    # Bumped by DB trigger trg_outbox_event_touch on every UPDATE (optimistic concurrency / ETag).
    row_version = models.BigIntegerField(db_default=1)
    # Provenance (PHASE_01 / 01.6, engine/events.py): owning module, build commit and newest migration of the
    # producing code. '' = row written before migration 0016 (or by a test factory) - provenance unknown.
    producer = models.CharField(max_length=100, db_default="", blank=True)
    build_commit = models.CharField(max_length=12, db_default="", blank=True)
    schema_migration = models.CharField(max_length=100, db_default="", blank=True)

    class Meta:
        db_table = "platform_outbox_event"
        constraints = [
            UniqueConstraint(fields=["event_id"], name="uq_outbox_event_event_id"),
            CheckConstraint(
                condition=Q(delivery_status__in=DeliveryStatus.values),
                name="ck_outbox_event_delivery_status",
            ),
            CheckConstraint(condition=Q(actor_type__in=ActorType.values), name="ck_outbox_event_actor_type"),
            CheckConstraint(condition=ACTOR_CONSISTENT, name="ck_outbox_event_actor_id_for_user"),
            CheckConstraint(
                condition=Q(event_type__regex=DOTTED_NAME_PATTERN), name="ck_outbox_event_type_fmt"
            ),
            CheckConstraint(condition=Q(schema_version__gte=1), name="ck_outbox_event_schema_version_pos"),
            CheckConstraint(condition=Q(aggregate_version__gte=0), name="ck_outbox_event_agg_version_nonneg"),
            CheckConstraint(condition=Q(attempts__gte=0), name="ck_outbox_event_attempts_nonneg"),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_outbox_event_row_version_pos"),
            CheckConstraint(condition=_json_is_object("payload"), name="ck_outbox_event_payload_object"),
            CheckConstraint(
                condition=~Q(delivery_status=DeliveryStatus.ACKED) | Q(acked_at__isnull=False),
                name="ck_outbox_event_acked_has_ts",
            ),
            CheckConstraint(
                condition=~Q(delivery_status=DeliveryStatus.DISPATCHED) | Q(dispatched_at__isnull=False),
                name="ck_outbox_event_dispatched_has_ts",
            ),
            CheckConstraint(
                condition=Q(producer="") | Q(producer__regex=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"),
                name="ck_outbox_event_producer_fmt",
            ),
            CheckConstraint(
                condition=Q(build_commit__regex=r"^([0-9a-f]{7,12})?$"),
                name="ck_outbox_event_build_commit_fmt",
            ),
            CheckConstraint(
                condition=Q(schema_migration="")
                | Q(schema_migration__regex=r"^[a-z][a-z0-9_]*\.[0-9]{4}_[a-z0-9_]+$"),
                name="ck_outbox_event_schema_migration_fmt",
            ),
        ]
        indexes = [
            # Dispatcher poll: WHERE delivery_status IN ('PENDING','FAILED') ORDER BY next_attempt_at, id
            models.Index(
                fields=["next_attempt_at", "id"],
                name="ix_outbox_event_dispatch",
                condition=Q(delivery_status__in=[DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
            ),
            models.Index(
                fields=["occurred_at"],
                name="ix_outbox_event_dead_letter",
                condition=Q(delivery_status=DeliveryStatus.DEAD_LETTER),
            ),
            models.Index(
                fields=["aggregate_type", "aggregate_id", "aggregate_version"],
                name="ix_outbox_event_aggregate",
            ),
            models.Index(fields=["correlation_id"], name="ix_outbox_event_correlation"),
            # Per-aggregate ordering (01.6): "is there an earlier undelivered event of this aggregate?"
            models.Index(
                fields=["aggregate_type", "aggregate_id", "id"],
                name="ix_outbox_event_agg_open",
                condition=~Q(delivery_status=DeliveryStatus.ACKED),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.event_id} [{self.delivery_status}]"


class IdempotencyState(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    FAILED_RETRYABLE = "FAILED_RETRYABLE", "Failed (retry allowed)"


class HttpMethod(models.TextChoices):
    POST = "POST", "POST"
    PUT = "PUT", "PUT"
    PATCH = "PATCH", "PATCH"
    DELETE = "DELETE", "DELETE"


class IdempotencyRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Mutating endpoints are authenticated (openapi-draft write_requirements), so actor_id is required.
    actor_id = models.UUIDField()
    key = models.UUIDField()
    method = models.CharField(max_length=7, choices=HttpMethod.choices)
    endpoint = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)  # SHA-256 hex of the canonical request
    state = models.CharField(
        max_length=20, choices=IdempotencyState.choices, db_default=IdempotencyState.IN_PROGRESS
    )
    response_status = models.SmallIntegerField(null=True, blank=True)
    response_headers = models.JSONField(default=dict, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    # Retention window is not decided here (proposal 24h, STATE_TRANSITIONS 1.2): the writer sets it.
    expires_at = models.DateTimeField()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_idempotency_record"
        constraints = [
            UniqueConstraint(fields=["actor_id", "key"], name="uq_idempotency_record_actor_key"),
            CheckConstraint(condition=Q(method__in=HttpMethod.values), name="ck_idempotency_record_method"),
            CheckConstraint(
                condition=Q(state__in=IdempotencyState.values), name="ck_idempotency_record_state"
            ),
            CheckConstraint(
                condition=Q(request_hash__regex=r"^[0-9a-f]{64}$"), name="ck_idempotency_record_hash_fmt"
            ),
            CheckConstraint(condition=~Q(endpoint=""), name="ck_idempotency_record_endpoint_nonempty"),
            CheckConstraint(
                condition=Q(response_status__isnull=True)
                | Q(response_status__gte=100, response_status__lte=599),
                name="ck_idempotency_record_status_range",
            ),
            CheckConstraint(
                condition=~Q(state=IdempotencyState.COMPLETED) | Q(response_status__isnull=False),
                name="ck_idempotency_record_completed_has_status",
            ),
            CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="ck_idempotency_record_expiry_after_create",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_idempotency_record_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["expires_at"], name="ix_idempotency_record_expires"),
        ]

    def __str__(self) -> str:
        return f"{self.method} {self.endpoint} key={self.key} [{self.state}]"


class SchemaMeta(models.Model):
    """Single-row marker of the platform schema contract (non-sensitive seed, migration 0003)."""

    id = models.SmallIntegerField(primary_key=True, default=1)
    schema_contract = models.CharField(max_length=32)
    seeded_by_migration = models.CharField(max_length=100)
    updated_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "platform_schema_meta"
        constraints = [
            CheckConstraint(condition=Q(id=1), name="ck_schema_meta_singleton"),
            CheckConstraint(condition=~Q(schema_contract=""), name="ck_schema_meta_contract_nonempty"),
        ]

    def __str__(self) -> str:
        return f"schema {self.schema_contract}"


# ---------------------------------------------------------------------------------------------- 00.6
# Consumer side of the outbox (step 00.6, docs/integration/README.md section 3/4).


class InboxEvent(models.Model):
    """Consumer-side dedupe: one row per (consumer, event_id) that a handler processed successfully.

    Inserted in the *same* transaction as the handler's own writes, so either both commit or neither does;
    a redelivered event (at-least-once outbox) finds the row and is skipped.
    """

    id = models.BigAutoField(primary_key=True)
    consumer = models.CharField(max_length=150)
    event_id = models.UUIDField()
    event_type = models.CharField(max_length=150)
    attempt = models.IntegerField()
    processed_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "platform_inbox_event"
        constraints = [
            UniqueConstraint(fields=["consumer", "event_id"], name="uq_inbox_event_consumer_event"),
            CheckConstraint(
                condition=Q(consumer__regex=DOTTED_NAME_PATTERN), name="ck_inbox_event_consumer_fmt"
            ),
            CheckConstraint(
                condition=Q(event_type__regex=DOTTED_NAME_PATTERN), name="ck_inbox_event_type_fmt"
            ),
            CheckConstraint(condition=Q(attempt__gte=1), name="ck_inbox_event_attempt_pos"),
        ]
        indexes = [models.Index(fields=["event_id"], name="ix_inbox_event_event")]

    def __str__(self) -> str:
        return f"{self.consumer} <- {self.event_id}"


class CompensationOutcome(models.TextChoices):
    MANUAL_REQUIRED = "MANUAL_REQUIRED", "No hook: manual compensation required"
    COMPLETED = "COMPLETED", "Hook completed"
    HOOK_FAILED = "HOOK_FAILED", "Hook failed: manual compensation required"


class CompensationTrigger(models.TextChoices):
    DEAD_LETTER = "DEAD_LETTER", "Event dead-lettered (permanent failure)"


class CompensationRecord(models.Model):
    """What happened when an event failed permanently for a consumer (mechanism only, no business logic)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.UUIDField()
    event_type = models.CharField(max_length=150)
    consumer = models.CharField(max_length=150)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=64)
    trigger = models.CharField(max_length=16, choices=CompensationTrigger.choices)
    failure_code = models.CharField(
        max_length=500
    )  # safe code only (outbox last_error), never exception text
    outcome = models.CharField(max_length=16, choices=CompensationOutcome.choices)
    hook_error = models.CharField(max_length=150, blank=True, default="")  # exception class name only
    recorded_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "platform_compensation_record"
        constraints = [
            UniqueConstraint(fields=["consumer", "event_id"], name="uq_compensation_record_consumer_event"),
            CheckConstraint(
                condition=Q(consumer__regex=DOTTED_NAME_PATTERN), name="ck_compensation_record_consumer_fmt"
            ),
            CheckConstraint(
                condition=Q(event_type__regex=DOTTED_NAME_PATTERN), name="ck_compensation_record_type_fmt"
            ),
            CheckConstraint(
                condition=Q(trigger__in=CompensationTrigger.values), name="ck_compensation_record_trigger"
            ),
            CheckConstraint(
                condition=Q(outcome__in=CompensationOutcome.values), name="ck_compensation_record_outcome"
            ),
            CheckConstraint(
                condition=~Q(outcome=CompensationOutcome.HOOK_FAILED) | ~Q(hook_error=""),
                name="ck_compensation_record_hook_error",
            ),
        ]
        indexes = [
            models.Index(fields=["event_id"], name="ix_compensation_record_event"),
            models.Index(fields=["outcome", "recorded_at"], name="ix_compensation_record_outcome"),
        ]

    def __str__(self) -> str:
        return f"{self.consumer} {self.event_id} [{self.outcome}]"


# Integration tables (00.6, platform_core.integration.models) and the PHASE_01 / 01.2 platform tables (one
# module per area: identity, org, workflow, documents, params, jobs; same app, same migration history) are
# registered here so Django's app loading sees them.
from platform_core.documents import models as _documents_models  # noqa: E402,F401
from platform_core.identity import models as _identity_models  # noqa: E402,F401
from platform_core.integration import models as _integration_models  # noqa: E402,F401
from platform_core.jobs import models as _jobs_models  # noqa: E402,F401
from platform_core.org import models as _org_models  # noqa: E402,F401
from platform_core.params import models as _params_models  # noqa: E402,F401
from platform_core.workflow import models as _workflow_models  # noqa: E402,F401
