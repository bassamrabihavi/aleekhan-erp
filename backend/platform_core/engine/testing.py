"""TEST DOUBLES ONLY - never a real delivery channel.

``InMemoryTestPublisher`` records envelopes in process memory so tests can assert what the dispatcher would
publish. It delivers nothing anywhere and is refused outside ALEEKHAN_ENV dev/test, so it can never be
presented as a real broker (handoff: "no mock presented as real").
"""

from __future__ import annotations

import threading
import uuid

from django.conf import settings

from .errors import EngineContractError
from .outbox import EventEnvelope, PublishError


class InMemoryTestPublisher:
    """Test-only :class:`~platform_core.engine.outbox.OutboxPublisher`."""

    def __init__(self) -> None:
        env = getattr(settings, "ALEEKHAN_ENV", "")
        if env not in {"dev", "test"}:
            raise EngineContractError("InMemoryTestPublisher is a test double; refused in this environment")
        self._lock = threading.Lock()
        self.published: list[EventEnvelope] = []
        self.fail_event_ids: set[uuid.UUID] = set()
        self.fail_always = False

    def publish(self, envelope: EventEnvelope) -> None:
        if self.fail_always or envelope.event_id in self.fail_event_ids:
            raise PublishError("TEST_PUBLISHER_FAILURE")
        with self._lock:
            self.published.append(envelope)
