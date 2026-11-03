"""Cursor pagination (openapi-draft: ``cursor``, ``page_size`` default 25 / max 100, ``next_cursor``).

Response shape::

    {"items": [...], "page": {"page_size": 25, "next_cursor": "<opaque>" | null}}

* ``page_size`` must be an integer 1..100; anything else is 400 ``VALIDATION_FAILED`` (no silent clamping, so
  clients notice contract violations).
* ``cursor`` is opaque (DRF base64 cursor), at most 512 characters; a malformed or tampered cursor is 400
  ``VALIDATION_FAILED`` - never a 404 or a 500.
* Views must define a stable, unique ``ordering`` (e.g. ``("id",)``); there are no unbounded lists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import NotFound as DrfNotFound
from rest_framework.pagination import Cursor, CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.engine.errors import FieldError, ValidationFailed

if TYPE_CHECKING:  # DRF imports these modules from its settings; avoid an import cycle
    from rest_framework.views import APIView

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
MAX_CURSOR_LEN = 512


class AleekhanCursorPagination(CursorPagination):
    page_size = DEFAULT_PAGE_SIZE
    max_page_size = MAX_PAGE_SIZE
    page_size_query_param = "page_size"
    cursor_query_param = "cursor"
    ordering = "id"

    def get_page_size(self, request: Request) -> int:
        raw = request.query_params.get(self.page_size_query_param)
        if raw is None:
            return self.page_size
        if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= MAX_PAGE_SIZE:
            raise ValidationFailed(
                f"page_size must be an integer between 1 and {MAX_PAGE_SIZE}",
                errors=[FieldError(field="page_size", code="OUT_OF_RANGE")],
            )
        return int(raw)

    def decode_cursor(self, request: Request) -> Cursor | None:
        raw = request.query_params.get(self.cursor_query_param)
        if raw is not None and len(raw) > MAX_CURSOR_LEN:
            raise _invalid_cursor()
        try:
            return super().decode_cursor(request)
        except DrfNotFound:
            raise _invalid_cursor() from None

    def encode_cursor(self, cursor: Cursor) -> str:
        """Return only the opaque token (``next_cursor``), not a full URL."""
        url = super().encode_cursor(cursor)
        values = parse_qs(urlsplit(url).query).get(self.cursor_query_param, [])
        return values[0] if values else ""

    def paginate_queryset(
        self, queryset: Any, request: Request, view: APIView | None = None
    ) -> list[Any] | None:
        try:
            return super().paginate_queryset(queryset, request, view)
        except (ValueError, TypeError, DjangoValidationError):
            # a tampered cursor position that does not fit the ordering field's type
            raise _invalid_cursor() from None

    def get_paginated_response(self, data: Any) -> Response:
        return Response(
            {"items": data, "page": {"page_size": self.page_size, "next_cursor": self.next_cursor}}
        )

    @property
    def next_cursor(self) -> str | None:
        link = self.get_next_link()
        return link or None


def _invalid_cursor() -> ValidationFailed:
    return ValidationFailed(
        "cursor is malformed or expired", errors=[FieldError(field="cursor", code="INVALID_CURSOR")]
    )
