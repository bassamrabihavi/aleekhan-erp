"""Upload size limit before any byte of the body is parsed (PHASE_01 / 01.7, REV-0124).

Django parses a ``multipart/form-data`` body as soon as anything reads ``request.POST`` / ``request.FILES`` -
including the CSRF check of the session authentication - and spools large files to a temporary file. So a
size check inside the upload view (``document_views``) comes after the bytes are already on disk. This
middleware answers 413 ``PAYLOAD_TOO_LARGE`` from the declared ``Content-Length`` **before** the body is read:

* applies to ``multipart/form-data`` requests only (every other body is already capped by Django's
  ``DATA_UPLOAD_MAX_MEMORY_SIZE`` = ``ALEEKHAN_MAX_BODY_BYTES`` before it is read);
* limit = parameter ``document_upload_max_bytes`` (DEC-053) + :data:`MULTIPART_OVERHEAD_BYTES` (TECHNICAL
  DEFAULT: boundaries, part headers, ``change_note`` <= 500 characters and ``parent_revision_id``). The view
  still checks the exact file size afterwards (defence in depth);
* if the parameter cannot be read (database down), the request is passed on unchanged: the view then fails
  on the same database and never stores anything.

A body sent without ``Content-Length`` (chunked) is read by Django's WSGI handler as empty, so it cannot carry
a file past this point. The reverse proxy (DEC-042) must also cap the body - nginx ``client_max_body_size``
(see docs/ops/DEPLOYMENT_LIMITS.md); that limit protects the app server itself.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from django.http import HttpRequest, HttpResponseBase

from platform_core.engine.errors import PayloadTooLarge

# TECHNICAL DEFAULT: multipart framing allowance on top of the file limit.
MULTIPART_OVERHEAD_BYTES: Final = 64 * 1024


def upload_limit_bytes() -> int:
    from platform_core.params.values import effective_int

    return effective_int("document_upload_max_bytes") + MULTIPART_OVERHEAD_BYTES


class UploadSizeLimitMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        content_type = request.META.get("CONTENT_TYPE", "")
        if content_type.lower().startswith("multipart/form-data"):
            try:
                declared = int(request.META.get("CONTENT_LENGTH") or 0)
            except ValueError:
                declared = 0
            if declared > 0:
                try:
                    limit = upload_limit_bytes()
                except Exception:  # database not readable: the view decides (see the module docstring)
                    limit = None
                if limit is not None and declared > limit:
                    from .problems import _django_problem

                    return _django_problem(
                        request, PayloadTooLarge("the upload exceeds document_upload_max_bytes (DEC-053)")
                    )
        return self.get_response(request)
