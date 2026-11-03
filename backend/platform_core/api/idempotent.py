"""DRF glue for idempotent writes (openapi-draft: ``Idempotency-Key`` on every mutating request).

``idempotent_response(request, endpoint=..., handler=...)``:

1. requires an authenticated principal (401) and a UUID ``Idempotency-Key`` (428 / 400);
2. runs ``engine.idempotency.run_idempotent`` with a :class:`RequestContext` carrying the actor and the
   request id (so audit/outbox rows are correlated);
3. turns the stored response into a DRF :class:`Response`; a replay carries ``Idempotent-Replayed: true``.

Deterministic client errors raised by the handler (e.g. 400, 404, 409 RULE_NOT_APPROVED, 412) are stored and
replayed for the same key + same request (REV-0012, docs/engine/README.md section 2). A replayed problem keeps
the ``request_id`` of the original request (it points to the original audit trail); the response header
``X-Request-ID`` is the id of the current request.
"""

from __future__ import annotations

from collections.abc import Callable

from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.idempotency import StoredResponse, parse_idempotency_key, run_idempotent
from platform_core.engine.uow import UnitOfWork

from .permissions import require_principal
from .request_id import request_id_of

REPLAY_HEADER = "Idempotent-Replayed"


def idempotent_response(
    request: Request, *, endpoint: str, handler: Callable[[UnitOfWork], StoredResponse]
) -> Response:
    principal = require_principal(request)
    if request.method is None:  # pragma: no cover - DRF always sets the method
        raise ValueError("request without method")
    key = parse_idempotency_key(request.headers.get("Idempotency-Key"))
    ctx = RequestContext(Actor.user(principal.actor_id), request_id=request_id_of(request))
    result = run_idempotent(
        ctx, key=key, method=request.method.upper(), endpoint=endpoint, body=request.data, handler=handler
    )
    stored = result.response
    headers = {k: v for k, v in stored.headers.items() if k.lower() != "content-type"}
    content_type = next((v for k, v in stored.headers.items() if k.lower() == "content-type"), None)
    if result.replayed:
        headers[REPLAY_HEADER] = "true"
    return Response(stored.body, status=stored.status, headers=headers, content_type=content_type)
