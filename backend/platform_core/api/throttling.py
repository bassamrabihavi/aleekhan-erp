"""Rate limiting (DRF throttles) -> 429 ``RATE_LIMITED`` with ``Retry-After`` (api/problems.py).

Rates come from ``settings.ALEEKHAN_THROTTLE_RATES`` (env ``ALEEKHAN_RATE_*``) and are read per request.
Counters live in the default cache: local memory per process in dev/test, Redis in staging/prod
(``ALEEKHAN_REDIS_URL``; docs/api/API_RUNTIME.md). The client IP is ``REMOTE_ADDR`` unless
``ALEEKHAN_NUM_PROXIES`` trusted proxies are configured (then DRF uses X-Forwarded-For accordingly).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle

from .permissions import principal_of

if TYPE_CHECKING:  # DRF imports these modules from its settings; avoid an import cycle
    from rest_framework.views import APIView


class _ConfiguredRateThrottle(SimpleRateThrottle):
    def get_rate(self) -> str | None:
        rates: dict[str, str] = getattr(settings, "ALEEKHAN_THROTTLE_RATES", {})
        rate = rates.get(self.scope or "")
        if not rate:
            raise ImproperlyConfigured(f"no rate configured for throttle scope {self.scope!r}")
        return rate


class AnonIpThrottle(_ConfiguredRateThrottle):
    """Anonymous callers, per client IP."""

    scope = "anon"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        if principal_of(request) is not None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PrincipalThrottle(_ConfiguredRateThrottle):
    """Authenticated callers, per principal (no-op in PHASE_00: there is no authentication yet)."""

    scope = "principal"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        principal = principal_of(request)
        if principal is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": principal.actor_id.hex}


class HealthIpThrottle(_ConfiguredRateThrottle):
    """Probe endpoints, per client IP (separate bucket so probes and API calls do not starve each other)."""

    scope = "health"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
