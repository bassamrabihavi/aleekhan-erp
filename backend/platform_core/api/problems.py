"""Every API error as an RFC 9457 ``application/problem+json`` body (openapi-draft ``Problem``).

* Engine errors (:class:`AleekhanError`) keep their stable ``code`` / HTTP status (ERROR_CODES.md).
* DRF / Django framework exceptions are mapped onto the same catalogue (e.g. ``Throttled`` -> 429
  ``RATE_LIMITED`` with ``Retry-After``; DRF ``ValidationError`` -> 400 ``VALIDATION_FAILED`` with field
  names and DRF error codes only - submitted values are never echoed).
* Anything else, including :class:`EngineContractError`, is 500 ``INTERNAL_ERROR`` with a generic body; the
  server log records the exception type and stack frames (no message, see ``api/logging.py``).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import RequestDataTooBig, SuspiciousOperation
from django.http import Http404, HttpRequest, JsonResponse
from rest_framework import exceptions as drf
from rest_framework.response import Response

from platform_core.engine import errors as E

from .request_id import request_id_of

PROBLEM_CONTENT_TYPE = "application/problem+json"
logger = logging.getLogger("aleekhan.api")


def _field_errors(detail: Any, prefix: str = "") -> list[E.FieldError]:
    """Flatten DRF ``ValidationError.detail`` into ``FieldError`` (field path + machine code only)."""
    out: list[E.FieldError] = []
    if isinstance(detail, Mapping):
        for key, value in detail.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_field_errors(value, path))
    elif isinstance(detail, list):
        for i, value in enumerate(detail):
            if isinstance(value, Mapping | list):
                out.extend(_field_errors(value, f"{prefix}[{i}]"))
            else:
                out.extend(_field_errors(value, prefix))
    else:
        code = getattr(detail, "code", None) or "INVALID"
        out.append(E.FieldError(field=prefix or "non_field_errors", code=str(code).upper()))
    return out


def to_aleekhan_error(exc: BaseException) -> E.AleekhanError:
    """Map any exception to a catalogue error (unknown -> INTERNAL_ERROR)."""
    if isinstance(exc, E.AleekhanError):
        return exc
    if isinstance(exc, drf.Throttled):
        return E.RateLimited()
    if isinstance(exc, drf.NotAuthenticated | drf.AuthenticationFailed):
        return E.AuthenticationRequired()
    if isinstance(exc, drf.PermissionDenied | DjangoPermissionDenied):
        return E.AccessDenied()
    if isinstance(exc, drf.NotFound | Http404):
        return E.NotFound()
    if isinstance(exc, drf.MethodNotAllowed):
        return E.MethodNotAllowed()
    if isinstance(exc, drf.ValidationError):
        return E.ValidationFailed(errors=_field_errors(exc.detail))
    if isinstance(exc, drf.ParseError):
        return E.ValidationFailed("request body is not valid JSON")
    if isinstance(exc, drf.UnsupportedMediaType):
        return E.ValidationFailed("unsupported Content-Type (application/json only)")
    if isinstance(exc, drf.NotAcceptable):
        return E.ValidationFailed("only application/json responses are available")
    if isinstance(exc, RequestDataTooBig):
        return E.PayloadTooLarge()
    if isinstance(exc, SuspiciousOperation):  # e.g. DisallowedHost: generic 400, details only in server log
        return E.ValidationFailed()
    return E.InternalError()


def _retry_after(exc: BaseException) -> int | None:
    if isinstance(exc, drf.Throttled):
        wait = getattr(exc, "wait", None) or 1.0
        return max(1, math.ceil(wait))
    return None


def problem_body(err: E.AleekhanError, request: object) -> dict[str, Any]:
    return err.to_problem(request_id_of(request))


def _log(exc: BaseException, err: E.AleekhanError) -> None:
    if err.http_status >= 500:
        logger.error(
            "unhandled error",
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={"event": "api_error", "error_code": err.code.value},
        )


def _mark(request: object, err: E.AleekhanError) -> None:
    raw: Any = getattr(request, "_request", request)
    try:
        raw.aleekhan_error_code = err.code.value
    except AttributeError:  # pragma: no cover - request objects always accept attributes
        pass


def exception_handler(exc: Exception, context: Mapping[str, Any]) -> Response:
    """DRF ``EXCEPTION_HANDLER``. Never returns ``None``: every exception becomes a problem response."""
    request = context.get("request")
    err = to_aleekhan_error(exc)
    _log(exc, err)
    _mark(request, err)
    from rest_framework.views import set_rollback  # local: DRF imports this module from its settings

    set_rollback()
    headers = {"Cache-Control": "no-store"}
    retry = _retry_after(exc)
    if retry is not None:
        headers["Retry-After"] = str(retry)
    return Response(
        problem_body(err, request),
        status=err.http_status,
        headers=headers,
        content_type=PROBLEM_CONTENT_TYPE,
    )


def _django_problem(request: HttpRequest, err: E.AleekhanError) -> JsonResponse:
    _mark(request, err)
    response = JsonResponse(
        problem_body(err, request),
        status=err.http_status,
        content_type=PROBLEM_CONTENT_TYPE,
        json_dumps_params={"ensure_ascii": False},
    )
    response["Cache-Control"] = "no-store"
    return response


# Django-level handlers (ROOT_URLCONF handler400/403/404/500): non-DRF failures (unknown URL, bad Host
# header, errors in middleware) also return problem+json with the request id.
def bad_request(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return _django_problem(request, E.ValidationFailed())


def permission_denied(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return _django_problem(request, E.AccessDenied())


def page_not_found(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return _django_problem(request, E.NotFound())


def server_error(request: HttpRequest) -> JsonResponse:
    return _django_problem(request, E.InternalError())


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    """``CSRF_FAILURE_VIEW``: the reason text is not returned (it describes the token check)."""
    return _django_problem(request, E.AccessDenied())
