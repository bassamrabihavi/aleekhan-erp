"""Session authentication for the PHASE_01 API (01.4; openapi-draft ``securitySchemes.sessionCookie``).

* The browser holds the session token in the ``aleekhan_session`` cookie (HttpOnly, Secure outside dev/test,
  SameSite=Lax, path ``/``). The database stores only its SHA-256 (``identity.sessions``); the public handle
  is ``Session.id``. Browser only (DEC-002): no bearer tokens (CONFLICTS C-35).
* Every request with the cookie is validated by ``identity.sessions.authenticate`` (expiry, network policy,
  MFA pending, forced password change). A failure is NOT raised here: it is recorded on the request and raised
  by the permission check (``api.permissions.require_principal``), i.e. after the throttles ran, so rejected
  requests are rate limited too (``api/base.py``).
* CSRF: DRF views are CSRF-exempt at the Django level, so unsafe methods of an authenticated session are
  checked here with Django's own ``CsrfViewMiddleware`` logic (cookie ``csrftoken`` + header ``X-CSRFToken``,
  Origin/Referer checks). The public ``login`` checks CSRF itself (login CSRF). Failure -> 403
  ``ACCESS_DENIED`` (the reason text is never returned).
* Views may set ``allow_mfa_pending`` (``verifyMfa``, ``logout``) and ``allow_password_change``
  (``changeMyPassword``, ``logout``, ``getCurrentSession``, ``verifyMfa``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Final

from django.conf import settings
from django.http import HttpRequest, HttpResponseBase
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request
from rest_framework.throttling import BaseThrottle

from platform_core.authz.policy import Caller
from platform_core.engine.errors import AccessDenied, AleekhanError
from platform_core.identity import sessions

from .permissions import AUTH_ERROR_ATTR
from .request_id import request_id_of

SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})
MAX_TOKEN_LEN: Final = 128


@dataclass(frozen=True)
class SessionPrincipal:
    """The authenticated caller of one request (``api.permissions.Principal``)."""

    caller: Caller
    is_authenticated: bool = True

    @property
    def actor_id(self) -> uuid.UUID:
        return self.caller.user_id

    @property
    def session_id(self) -> uuid.UUID | None:
        return self.caller.session_id

    @property
    def pk(self) -> uuid.UUID:
        return self.caller.user_id


def client_ip(request: Request | HttpRequest) -> str | None:
    """Client address with the trusted-proxy rule of the throttles (``ALEEKHAN_NUM_PROXIES``)."""
    ident = BaseThrottle().get_ident(request)  # type: ignore[arg-type]
    return ident or None


def user_agent(request: Request | HttpRequest) -> str:
    return str(request.META.get("HTTP_USER_AGENT", ""))[:512]


class _CsrfCheck(CsrfViewMiddleware):
    def _reject(self, request: HttpRequest, reason: str) -> HttpResponseBase:
        raise AccessDenied("CSRF verification failed")


def enforce_csrf(request: Request | HttpRequest) -> None:
    """403 ``ACCESS_DENIED`` unless the request passes Django's CSRF checks (test clients opt out)."""
    raw: HttpRequest = getattr(request, "_request", request)

    def _no_response(_request: HttpRequest) -> HttpResponseBase:  # pragma: no cover - never called
        raise AssertionError

    check = _CsrfCheck(_no_response)
    check.process_request(raw)
    check.process_view(raw, None, (), {})  # type: ignore[arg-type]


def session_token(request: Request | HttpRequest) -> str | None:
    token = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
    if not token or len(token) > MAX_TOKEN_LEN:
        return None
    return str(token)


class SessionCookieAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[SessionPrincipal, None] | None:
        token = session_token(request)
        if token is None:
            return None
        view: Any = (getattr(request, "parser_context", None) or {}).get("view")
        try:
            caller = sessions.authenticate(
                token,
                client_ip=client_ip(request),
                request_id=request_id_of(request),
                allow_mfa_pending=bool(getattr(view, "allow_mfa_pending", False)),
                allow_password_change=bool(getattr(view, "allow_password_change", False)),
            )
            if request.method not in SAFE_METHODS:
                enforce_csrf(request)
        except AleekhanError as err:
            setattr(request._request, AUTH_ERROR_ATTR, err)
            return None
        return SessionPrincipal(caller), None

    def authenticate_header(self, request: Request) -> str:
        return "Cookie"


def set_session_cookie(response: HttpResponseBase, token: str) -> None:
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        token,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",  # = settings.SESSION_COOKIE_SAMESITE (openapi sessionCookie)
        path="/",
    )


def clear_session_cookie(response: HttpResponseBase) -> None:
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/", samesite="Lax")
