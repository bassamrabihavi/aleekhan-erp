"""Synthetic test data builders (no real factory data)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from typing import Any

from django.utils import timezone

from platform_core.integration.models import IntegrationSource
from platform_core.models import (
    ActorType,
    AuditEvent,
    AuditOutcome,
    HttpMethod,
    IdempotencyRecord,
    OutboxEvent,
)


def audit_event(**over: Any) -> AuditEvent:
    data: dict[str, Any] = {
        "actor_type": ActorType.SYSTEM,
        "action": "platform.test.synthetic",
        "outcome": AuditOutcome.SUCCESS,
        "resource_type": "platform.synthetic",
        "resource_id": "synthetic-1",
    }
    data.update(over)
    obj = AuditEvent(**data)
    obj.save()
    return obj


def outbox_event(**over: Any) -> OutboxEvent:
    data: dict[str, Any] = {
        "event_type": "platform.synthetic.created",
        "aggregate_type": "platform.synthetic",
        "aggregate_id": "synthetic-1",
        "aggregate_version": 1,
        "actor_type": ActorType.SYSTEM,
        "payload": {"note": "synthetic"},
    }
    data.update(over)
    return OutboxEvent.objects.create(**data)


def idempotency_record(**over: Any) -> IdempotencyRecord:
    data: dict[str, Any] = {
        "actor_id": uuid.uuid4(),
        "key": uuid.uuid4(),
        "method": HttpMethod.POST,
        "endpoint": "/api/v1/synthetic",
        "request_hash": hashlib.sha256(b"synthetic").hexdigest(),
        "expires_at": timezone.now() + timedelta(days=1),
    }
    data.update(over)
    return IdempotencyRecord.objects.create(**data)


def integration_source(**over: Any) -> IntegrationSource:
    """SYNTHETIC source (code prefix ``synthetic_``); never one of the real seeded systems."""
    data: dict[str, Any] = {
        "code": f"synthetic_{uuid.uuid4().hex[:12]}",
        "name_fa": "منبع ساختگی آزمایشی",
        "kind": "EXCEL_FILE",
        "policy_decision_id": "DEC-016",
        "staleness_threshold": timedelta(hours=24),
    }
    data.update(over)
    return IntegrationSource.objects.create(**data)
