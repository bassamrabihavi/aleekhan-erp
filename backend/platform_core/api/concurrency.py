"""ETag / If-Match helpers for DRF views (wrap ``platform_core.engine.concurrency``).

* Versioned resources: ``ETag: "<row_version>"`` (strong). Updates call :func:`expected_version` which maps a
  missing ``If-Match`` to 428, a malformed one to 400 and a weak/stale one to 412 (engine rules), then use
  ``engine.concurrency.update_versioned`` on a *scoped* queryset (out of scope -> 404).
* Non-versioned representations (e.g. ``/version``): :func:`representation_etag` = strong hash of the
  canonical JSON body.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.engine.concurrency import make_etag, parse_if_match


def expected_version(request: Request) -> int:
    return parse_if_match(request.headers.get("If-Match"))


def with_row_etag(response: Response, row_version: int) -> Response:
    response["ETag"] = make_etag(row_version)
    return response


def representation_etag(data: Any) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return '"' + hashlib.sha256(canonical).hexdigest()[:32] + '"'
