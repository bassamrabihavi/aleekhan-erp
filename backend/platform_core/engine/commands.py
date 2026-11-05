"""Idempotent domain commands (PHASE_01 / 01.3): the engine's idempotency protocol for service calls.

``execute(caller_ctx, key=, command=, payload=, fn=)`` runs ``fn`` at most once per (actor, Idempotency-Key,
command, payload) and replays the stored result otherwise (``engine.idempotency.run_idempotent``: same key +
different payload -> 422 ``IDEMPOTENCY_KEY_REUSED``; a deterministic client error is stored and replayed).
The command result must be JSON-serialisable (ids, states) - never a secret: authentication ceremonies are
exempt from idempotency (C-27) and must not use this wrapper.

``fn`` runs inside the idempotency unit of work; services open their own (nested) unit of work, so their
writes, audit rows, outbox events and the stored response commit together.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Any

from .context import RequestContext
from .errors import EngineContractError
from .idempotency import StoredResponse, run_idempotent
from .redaction import sensitive_paths

COMMAND_ENDPOINT_PREFIX = "command:"


def execute(
    ctx: RequestContext,
    *,
    key: uuid.UUID | None,
    command: str,
    payload: Mapping[str, Any],
    fn: Callable[[], Mapping[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """Returns ``(result, replayed)``."""
    if list(sensitive_paths(dict(payload))):
        raise EngineContractError("idempotent command payloads must not contain secrets")

    def handler(_uow: Any) -> StoredResponse:
        result = dict(fn())
        return StoredResponse(status=200, body=result, headers={})

    outcome = run_idempotent(
        ctx,
        key=key,
        method="POST",
        endpoint=f"{COMMAND_ENDPOINT_PREFIX}{command}",
        body=dict(payload),
        handler=handler,
        require_event=False,
    )
    body = outcome.response.body
    return (dict(body) if isinstance(body, dict) else {"result": body}), outcome.replayed
