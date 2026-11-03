"""Structured JSON logging (one JSON object per line) with ``request_id``.

Privacy rules (SECURITY_BASELINE, handoff guardrails):
* only an allowlist of ``extra`` keys is emitted - arbitrary attributes passed by libraries are dropped;
* for exceptions only the exception *type* and the stack frames (file:line:function) are logged, never the
  exception message, local variables, SQL parameters, request bodies, headers or query strings;
* callers must not put secrets/PII in log messages (code review rule; see docs/api/API_RUNTIME.md).
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import UTC, datetime
from typing import Any

from .request_id import current_request_id

ALLOWED_EXTRA_KEYS: tuple[str, ...] = (
    "event",
    "method",
    "path",
    "status",
    "duration_ms",
    "error_code",
    "exc_type",
    "component",
)
MAX_FRAMES = 30


class RequestIdLogFilter(logging.Filter):
    """Attach the current request id (or ``None`` outside a request) to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            rid = current_request_id.get()
            if rid is None:
                # django.request logs 4xx/5xx after the middleware chain returned; it attaches the request
                rid = getattr(getattr(record, "request", None), "request_id", None)
            record.request_id = str(rid) if rid is not None else None
        return True


def _frames(tb: Any) -> list[str]:
    return [f"{f.filename}:{f.lineno}:{f.name}" for f in traceback.extract_tb(tb)[-MAX_FRAMES:]]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for key in ALLOWED_EXTRA_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                out[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            exc_type, _exc, tb = record.exc_info
            out["exc_type"] = f"{exc_type.__module__}.{exc_type.__qualname__}"
            out["stack"] = _frames(tb)
        return json.dumps(out, ensure_ascii=False, default=str)
