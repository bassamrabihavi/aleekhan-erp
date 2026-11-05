"""PHASE_00 endpoints (openapi-draft): liveness, readiness, version, access-gate stub. No business data.

Integration endpoints (00.6) live in ``integration_views.py``.
"""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from datetime import UTC, datetime
from typing import Any, Final

from django.conf import settings
from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.engine.errors import FieldError, ValidationFailed

from .base import AleekhanAPIView
from .concurrency import representation_etag
from .permissions import AuthenticatedPrincipal, PublicEndpoint
from .request_id import request_id_of
from .throttling import HealthIpThrottle

# Version of docs/api/openapi-draft.yaml (``info.version``); a contract test keeps them equal.
CONTRACT_VERSION: Final = "0.6.0-draft"
API_VERSION: Final = "v1"
_ENVIRONMENT_NAMES: Final = {"dev": "dev", "test": "test", "staging": "staging", "prod": "production"}
NO_STORE: Final = {"Cache-Control": "no-store"}
READY_RETRY_AFTER_SECONDS: Final = 5

logger = logging.getLogger("aleekhan.health")


class _ProbeView(AleekhanAPIView):
    permission_classes = [PublicEndpoint]
    throttle_classes = [HealthIpThrottle]


class LivenessView(_ProbeView):
    """GET /health/live - the process answers. Touches no dependency."""

    def get(self, request: Request) -> Response:
        return Response({"status": "ok"}, headers=NO_STORE)


def _check_database() -> str:
    with connections[DEFAULT_DB_ALIAS].cursor() as cur:
        cur.execute("SELECT 1")
        row = cur.fetchone()
    return "up" if row == (1,) else "down"


# REV-0016: building a MigrationExecutor loads the whole migration graph from disk; the public readiness probe
# caches the result per process for a short time. TECHNICAL DEFAULT (10 s), not a business rule.
MIGRATIONS_CHECK_TTL_SECONDS: Final = 10.0
_migrations_lock = threading.Lock()
_migrations_cached: tuple[float, str] | None = None
_monotonic = time.monotonic  # indirection for tests


def _compute_migrations_status() -> str:
    executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return "up" if not plan else "down"


def reset_migrations_check_cache() -> None:
    global _migrations_cached
    with _migrations_lock:
        _migrations_cached = None


def _check_migrations() -> str:
    """Cached for :data:`MIGRATIONS_CHECK_TTL_SECONDS`; failures are never cached (they raise)."""
    global _migrations_cached
    with _migrations_lock:
        now = _monotonic()
        cached = _migrations_cached
        if cached is not None and now - cached[0] < MIGRATIONS_CHECK_TTL_SECONDS:
            return cached[1]
        status = _compute_migrations_status()
        _migrations_cached = (now, status)
        return status


def _check_cache() -> str:
    key = "aleekhan:readiness:probe"
    token = secrets.token_hex(8)
    cache.set(key, token, timeout=10)
    return "up" if cache.get(key) == token else "down"


def _safe(component: str, check: Any) -> str:
    try:
        result: str = check()
        return result
    except Exception:  # never leak hostnames/DSNs/error text; log type + frames only
        logger.warning("readiness check failed", exc_info=True, extra={"component": component})
        return "down"


class ReadinessView(_ProbeView):
    """GET /health/ready - database reachable, migrations applied, cache usable. Names + up/down only."""

    def get(self, request: Request) -> Response:
        database = _safe("database", _check_database)
        migrations = _safe("migrations", _check_migrations) if database == "up" else "unknown"
        cache_status = _safe("cache", _check_cache)
        components = [
            {"name": "database", "status": database},
            {"name": "migrations", "status": migrations},
            {"name": "cache", "status": cache_status},
        ]
        ready = all(c["status"] == "up" for c in components)
        body = {
            "status": "ready" if ready else "not_ready",
            "checked_at": datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "components": components,
        }
        headers = dict(NO_STORE)
        if not ready:
            headers["Retry-After"] = str(READY_RETRY_AFTER_SECONDS)
        return Response(body, status=200 if ready else 503, headers=headers)


class VersionView(_ProbeView):
    """GET /version - API/contract version and short build commit (C-17: no runtime/dependency versions)."""

    def get(self, request: Request) -> Response:
        body = {
            "api_version": API_VERSION,
            "contract_version": CONTRACT_VERSION,
            "build_commit": settings.ALEEKHAN_BUILD_COMMIT,
            "environment": _ENVIRONMENT_NAMES[settings.ALEEKHAN_ENV],
        }
        return Response(body, headers={"ETag": representation_etag(body), "Cache-Control": "no-cache"})


ACTION_RE: Final = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}")
RESOURCE_TYPE_RE: Final = re.compile(r"[a-z][a-z0-9_]{0,63}")
UUID_RE: Final = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
MAX_ACTION_LEN: Final = 120


class AccessGateCheckView(AleekhanAPIView):
    """GET /access-gate/check - deny-by-default stub of the central authorization gate.

    No principal -> 401 (always the case in PHASE_00: no authentication backend exists). With a principal
    (test harness only) the parameters are validated and the decision is DENY / POLICY_NOT_DEFINED.
    This view has no code path that produces ``ALLOW``.
    """

    permission_classes = [AuthenticatedPrincipal]

    def get(self, request: Request) -> Response:
        params = request.query_params
        action = params.get("action")
        errors: list[FieldError] = []
        if action is None or action == "":
            errors.append(FieldError(field="action", code="REQUIRED"))
        elif len(action) > MAX_ACTION_LEN or not ACTION_RE.fullmatch(action):
            errors.append(FieldError(field="action", code="PATTERN_MISMATCH"))
        resource_type = params.get("resource_type")
        if resource_type is not None and not RESOURCE_TYPE_RE.fullmatch(resource_type):
            errors.append(FieldError(field="resource_type", code="PATTERN_MISMATCH"))
        resource_id = params.get("resource_id")
        if resource_id is not None and not UUID_RE.fullmatch(resource_id):
            errors.append(FieldError(field="resource_id", code="INVALID_UUID"))
        if errors:
            raise ValidationFailed(errors=errors)
        body = {
            "decision": "DENY",
            "reason_code": "POLICY_NOT_DEFINED",
            "action": action,
            "decision_id": None,
            "request_id": str(request_id_of(request)),
        }
        return Response(body, headers=NO_STORE)
