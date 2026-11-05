"""Who/which request performs a write (carried into audit and outbox rows)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import connections

from platform_core.models import ActorType

from .errors import EngineContractError


@dataclass(frozen=True)
class Actor:
    actor_type: ActorType
    actor_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.actor_type == ActorType.USER and self.actor_id is None:
            raise EngineContractError("a USER actor needs an actor_id")

    @classmethod
    def system(cls) -> Actor:
        return cls(ActorType.SYSTEM)

    @classmethod
    def user(cls, actor_id: uuid.UUID) -> Actor:
        return cls(ActorType.USER, actor_id)


# Values allowed in ``platform_audit_event.network_zone`` (CHECK ``ck_audit_event_network_zone``); '' =
# unknown
# to the writer (system jobs, PHASE_00 callers).
AUDIT_NETWORK_ZONES = frozenset({"", "INTERNAL", "EXTERNAL", "UNKNOWN"})


@dataclass(frozen=True)
class RequestContext:
    actor: Actor
    request_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    # PHASE_01 / 01.3: public session handle and network zone of the caller, copied into every audit row
    # (STATE_TRANSITIONS 4: "every transition records actor, reason, request_id and session handle").
    session_id: uuid.UUID | None = None
    network_zone: str = ""

    def __post_init__(self) -> None:
        if self.network_zone not in AUDIT_NETWORK_ZONES:
            raise EngineContractError(f"unknown network zone {self.network_zone!r}")

    @property
    def effective_correlation_id(self) -> uuid.UUID | None:
        return self.correlation_id or self.request_id


def db_now(using: str = "default") -> datetime:
    """Database clock (``statement_timestamp()``), the same clock used by ``db_default=Now()`` and triggers.

    Using one clock for ``created_at``/``updated_at`` (DB) and expiry/backoff comparisons avoids app/DB skew.
    """
    with connections[using].cursor() as cur:
        cur.execute("SELECT statement_timestamp()")
        row = cur.fetchone()
    if row is None:  # pragma: no cover - SELECT always returns one row
        raise EngineContractError("database clock unavailable")
    value: datetime = row[0]
    return value
