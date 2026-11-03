"""Request correlation id (openapi-draft: ``X-Request-ID``) and access log.

* A client-supplied ``X-Request-ID`` is accepted only if it is a canonical UUID string (exactly 36 chars,
  8-4-4-4-12 hex). Anything else (missing, too long, other formats, control characters) is ignored and a new
  UUID4 is generated - the header is never echoed verbatim, so it cannot inject into logs or headers.
* The id is stored on ``request.request_id`` (``uuid.UUID``) and in a context variable for log records,
  echoed in the ``X-Request-ID`` response header, and copied into every problem body and audit/outbox row.
* One access-log line per request: method, path (no query string), status, duration, error code.
"""

from __future__ import annotations

import contextvars
import logging
import re
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponseBase

HEADER = "X-Request-ID"
_CANONICAL_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
MAX_HEADER_LEN = 36

current_request_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "aleekhan_request_id", default=None
)

access_log = logging.getLogger("aleekhan.access")


def parse_request_id(raw: str | None) -> uuid.UUID | None:
    """Return the client id if it is a canonical UUID string, else ``None``."""
    if raw is None or len(raw) != MAX_HEADER_LEN or not _CANONICAL_UUID_RE.fullmatch(raw):
        return None
    return uuid.UUID(raw)


def request_id_of(request: object) -> uuid.UUID:
    """The id assigned by the middleware (works for Django and DRF requests)."""
    rid = getattr(request, "request_id", None)
    if isinstance(rid, uuid.UUID):
        return rid
    ctx = current_request_id.get()
    return ctx if ctx is not None else uuid.uuid4()


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        rid = parse_request_id(request.headers.get(HEADER)) or uuid.uuid4()
        request.request_id = rid  # type: ignore[attr-defined]
        token = current_request_id.set(rid)
        started = time.perf_counter()
        try:
            response = self.get_response(request)
            response[HEADER] = str(rid)
            access_log.info(
                "request",
                extra={
                    "event": "http_request",
                    "request_id": str(rid),
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "error_code": getattr(request, "aleekhan_error_code", None),
                },
            )
            return response
        finally:
            current_request_id.reset(token)
