"""Dead-letter handling from the server console (PHASE_01 / 01.7, REV-0129; roles REV-0133).

The contract has no HTTP operation for dead letters (docs/integration/README.md section 9), so the two human
moves on a DEAD_LETTER event run as ``manage.py outbox_dead_letter`` on the server console:

* ``replay``  - DEAD_LETTER -> PENDING (the cause was fixed; the event is delivered again);
* ``discard`` - DEAD_LETTER -> DISCARDED (terminal; the event is never delivered and later events of the same
  aggregate are released - a poison head no longer blocks its aggregate forever).

Both need a reason (>= 3 characters) and are audited as the named user (``platform.outbox.replay`` /
``platform.outbox.discard``). The named user must be ACTIVE and hold an ACTIVE, currently valid
``owner_admin``
assignment; the check runs in the same transaction as the write. Console access to the server is a second
factor of its own (DEC-054 C reasoning, same as ``bootstrap_owner``). No payload, error text or actor id is
printed by the command.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from django.db import transaction

from platform_core.authz.policy import OWNER_ROLE, holds_role
from platform_core.engine import outbox
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import AccessDenied, NotFound
from platform_core.identity.models import User, UserStatus
from platform_core.models import DeliveryStatus, OutboxEvent

ACTIONS: Final = ("replay", "discard")
IT_OPS_ROLE: Final = "it_ops"
# Employer decision 2026-11-10 (REV-0133): IT may replay; discard (terminal) stays with the owner.
ALLOWED_ROLES: Final[dict[str, tuple[str, ...]]] = {
    "replay": (OWNER_ROLE, IT_OPS_ROLE),
    "discard": (OWNER_ROLE,),
}


@dataclass(frozen=True)
class DeadLetterRow:
    event_id: uuid.UUID
    event_type: str
    aggregate_type: str
    occurred_at: str
    attempts: int
    held_behind: int


def _authorised(username: str, action: str) -> User:
    roles = ALLOWED_ROLES[action]
    user = User.objects.filter(username=username, status=UserStatus.ACTIVE).first()
    if user is None or not any(holds_role(user.pk, r) for r in roles):
        raise AccessDenied(f"{action} of a dead-letter event needs an active role in: {', '.join(roles)}")
    return user


def handle(*, action: str, username: str, event_id: uuid.UUID, reason: str) -> str:
    """Replay or discard one DEAD_LETTER event as ``username`` (see :data:`ALLOWED_ROLES`). Returns the new
    delivery status."""
    if action not in ACTIONS:
        raise ValueError(action)
    with transaction.atomic():
        user = _authorised(username, action)
        ctx = RequestContext(Actor.user(user.pk), request_id=uuid.uuid4(), network_zone="INTERNAL")
        if action == "replay":
            outbox.replay_dead_letter(ctx, event_id, reason=reason)
        else:
            outbox.discard_dead_letter(ctx, event_id, reason=reason)
        row = OutboxEvent.objects.filter(event_id=event_id).values_list("delivery_status", flat=True).first()
        if row is None:  # pragma: no cover - the engine raised NotFound before
            raise NotFound()
        return str(row)


def list_dead_letters(*, limit: int = 100) -> list[DeadLetterRow]:
    """DEAD_LETTER events, oldest first, with the number of later undelivered events of the same aggregate."""
    out: list[DeadLetterRow] = []
    rows = OutboxEvent.objects.filter(delivery_status=DeliveryStatus.DEAD_LETTER).order_by("id")[:limit]
    for r in rows:
        held = (
            OutboxEvent.objects.filter(
                aggregate_type=r.aggregate_type, aggregate_id=r.aggregate_id, id__gt=r.id
            )
            .exclude(delivery_status__in=outbox.SETTLED)
            .exclude(delivery_status=DeliveryStatus.DEAD_LETTER)
            .count()
        )
        out.append(
            DeadLetterRow(
                event_id=r.event_id,
                event_type=r.event_type,
                aggregate_type=r.aggregate_type,
                occurred_at=r.occurred_at.isoformat(),
                attempts=r.attempts,
                held_behind=held,
            )
        )
    return out
