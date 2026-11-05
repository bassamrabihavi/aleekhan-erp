"""Django settings for the Aleekhan platform.

All secrets and connection details come from the environment (SECURITY_BASELINE 2: no secrets in Git).
See ``backend/.env.example`` for the variable names (placeholders only) and ``docs/api/API_RUNTIME.md`` for
the API runtime settings (rate limits, cache, proxy, security headers).

Database configuration, in order of precedence:
1. ``DATABASE_URL`` (e.g. ``postgres://user:pass@host:5432/dbname``), parsed with dj-database-url;
2. libpq-style ``PGHOST`` / ``PGPORT`` / ``PGUSER`` / ``PGPASSWORD`` / ``PGDATABASE`` variables.

Only PostgreSQL is supported (ADR-001: PostgreSQL 17). There is no SQLite fallback on purpose: the
schema relies on PostgreSQL triggers, CHECK constraints with regular expressions and partial indexes.
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Any

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# REV-0011: the environment must be named explicitly; there is no default. A deploy that forgets the variable
# refuses to start instead of silently running with dev behaviour. Test runs use ``aleekhan.settings_test``,
# which pins ``test`` explicitly (pyproject.toml: pytest and mypy).
_raw_env = os.environ.get("ALEEKHAN_ENV")
if _raw_env is None or not _raw_env.strip():
    raise ImproperlyConfigured("ALEEKHAN_ENV must be set explicitly (dev, test, staging, prod)")
ALEEKHAN_ENV = _raw_env.strip().lower()
if ALEEKHAN_ENV not in {"dev", "test", "staging", "prod"}:
    raise ImproperlyConfigured("ALEEKHAN_ENV must be one of dev, test, staging, prod")
DEPLOYED = ALEEKHAN_ENV in {"staging", "prod"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean (0/1)")


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) < minimum:
        raise ImproperlyConfigured(f"{name} must be an integer >= {minimum}")
    return int(raw)


# DEBUG can never be switched on in staging/prod, whatever DJANGO_DEBUG says.
DEBUG = _env_bool("DJANGO_DEBUG", False) and not DEPLOYED

_secret = os.environ.get("DJANGO_SECRET_KEY", "")
if _secret == "CHANGE_ME":  # noqa: S105 - placeholder from .env.example is never a real key
    _secret = ""
if not _secret:
    if DEPLOYED:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set outside dev/test")
    # dev/test only: ephemeral per-process key, never persisted or logged.
    _secret = secrets.token_urlsafe(50)
SECRET_KEY = _secret

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS:
    if DEPLOYED:
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in staging/prod")
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]  # dev/test only (the test client adds "testserver")
if DEPLOYED and "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must not contain '*' in staging/prod")

# Build identity shown by GET /api/v1/version (C-17: API/contract version + short commit only; no Python,
# Django, DB or OS versions). Required in staging/prod so screenshots/reports can be tied to a commit.
_BUILD_COMMIT_RE = re.compile(r"[0-9a-f]{7,40}")
_build_commit = os.environ.get("ALEEKHAN_BUILD_COMMIT", "").strip().lower()
if _build_commit and not _BUILD_COMMIT_RE.fullmatch(_build_commit):
    raise ImproperlyConfigured("ALEEKHAN_BUILD_COMMIT must be a hex git sha (7-40 chars)")
if not _build_commit:
    if DEPLOYED:
        raise ImproperlyConfigured("ALEEKHAN_BUILD_COMMIT must be set in staging/prod")
    _build_commit = "0000000"  # documented sentinel: "unknown build" (dev/test only)
ALEEKHAN_BUILD_COMMIT = _build_commit[:12]

# PHASE_00 scope: platform skeleton only. django.contrib.auth / sessions / admin are added in PHASE_01
# (users are created only inside the system by the owner/admin, DEC-003; never AD/LDAP/SSO).
# DRF is used as a library; "rest_framework" is not an installed app because the browsable API (templates,
# static files) is disabled in every environment.
INSTALLED_APPS = [
    "platform_core.apps.PlatformCoreConfig",
]

MIDDLEWARE = [
    # first: every response (including 400/404/500 produced by later layers) carries X-Request-ID
    "platform_core.api.request_id.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    # DRF APIViews are csrf-exempt at this layer; DRF's SessionAuthentication (PHASE_01) enforces CSRF itself.
    # The middleware protects any non-DRF view and answers with problem+json (CSRF_FAILURE_VIEW).
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "aleekhan.urls"
WSGI_APPLICATION = "aleekhan.wsgi.application"
ASGI_APPLICATION = "aleekhan.asgi.application"
TEMPLATES: list[dict[str, Any]] = []
APPEND_SLASH = False  # API paths have no trailing slash; never redirect API calls


def _database_config() -> dict[str, Any]:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        cfg: dict[str, Any] = dict(dj_database_url.parse(url, conn_max_age=60))
    else:
        cfg = {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ.get("PGHOST", "127.0.0.1"),
            "PORT": os.environ.get("PGPORT", "5432"),
            "USER": os.environ.get("PGUSER", ""),
            "PASSWORD": os.environ.get("PGPASSWORD", ""),
            "NAME": os.environ.get("PGDATABASE", "aleekhan_dev"),
            "CONN_MAX_AGE": 60,
        }
    if cfg.get("ENGINE") != "django.db.backends.postgresql":
        raise ImproperlyConfigured("Only PostgreSQL is supported (ADR-001)")
    options = dict(cfg.get("OPTIONS", {}))
    options.setdefault("application_name", "aleekhan-backend")
    sslmode = os.environ.get("PGSSLMODE", "").strip()
    if sslmode:
        options["sslmode"] = sslmode
    cfg["OPTIONS"] = options
    test_name = os.environ.get("ALEEKHAN_TEST_DB_NAME", "").strip()
    if test_name:
        cfg["TEST"] = {"NAME": test_name}
    # The idempotency protocol commits its claim on its own and must not run inside a request-wide
    # transaction (engine/idempotency.run_idempotent); writes use engine.uow.unit_of_work explicitly.
    cfg["ATOMIC_REQUESTS"] = False
    return cfg


DATABASES = {"default": _database_config()}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache: rate-limit counters and the readiness probe. Local memory (per process) in dev/test. Staging/prod
# should set ALEEKHAN_REDIS_URL so limits are shared by all workers (docs/api/API_RUNTIME.md); the redis
# client library is added to requirements together with the deployment step (00.7), not before.
_redis_url = os.environ.get("ALEEKHAN_REDIS_URL", "").strip()
CACHES: dict[str, dict[str, Any]] = {
    "default": (
        {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _redis_url}
        if _redis_url
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "aleekhan-default"}
    )
}

# Time: stored in UTC (timestamptz); Jalali / Asia/Tehran is a UI concern only (ADR-001).
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "fa"
USE_I18N = True

# Request size limit (problem 413 PAYLOAD_TOO_LARGE). 1 MiB is enough for JSON APIs; file uploads get their
# own limit with the module that needs them.
DATA_UPLOAD_MAX_MEMORY_SIZE = _env_int("ALEEKHAN_MAX_BODY_BYTES", 1_048_576, minimum=1024)

# ---------------------------------------------------------------------------------------------- security
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = DEPLOYED
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "aleekhan_session"  # openapi-draft securitySchemes.sessionCookie (PHASE_01)
CSRF_COOKIE_SECURE = DEPLOYED
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "platform_core.api.problems.csrf_failure"
# TLS terminates at the internal reverse proxy (DEC-042). Trust X-Forwarded-Proto only when the operator says
# the proxy sets it (otherwise a client could spoof "https").
_TRUST_PROXY_TLS_HEADER = _env_bool("ALEEKHAN_TRUST_PROXY_TLS_HEADER", False)
if _TRUST_PROXY_TLS_HEADER:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = _env_bool("ALEEKHAN_SSL_REDIRECT", DEPLOYED)
# Probes from the proxy/orchestrator on the private network may use plain HTTP.
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/"]
SECURE_HSTS_SECONDS = _env_int("ALEEKHAN_HSTS_SECONDS", 31_536_000 if ALEEKHAN_ENV == "prod" else 0)
if DEPLOYED and ALEEKHAN_ENV == "prod" and SECURE_HSTS_SECONDS < 86_400:
    raise ImproperlyConfigured("ALEEKHAN_HSTS_SECONDS must be >= 86400 in prod")
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("ALEEKHAN_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = False  # internal host; never submitted to browser preload lists
# `check --deploy` W005 (include subdomains) and W021 (preload) are deliberate for the internal host
# (docs/api/API_RUNTIME.md section 7).

# ---------------------------------------------------------------------------------------------- API (DRF)
# Rate limits ("<n>/<s|m|h|d>"), per client IP for anonymous callers and per principal once PHASE_01 adds
# authentication. Read at request time by platform_core.api.throttling (so tests can override them).
_RATE_RE = re.compile(r"[1-9][0-9]{0,6}/(s|sec|m|min|h|hour|d|day)")


def _env_rate(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip() or default
    if not _RATE_RE.fullmatch(value):
        raise ImproperlyConfigured(f"{name} must look like '60/min'")
    return value


ALEEKHAN_THROTTLE_RATES: dict[str, str] = {
    "anon": _env_rate("ALEEKHAN_RATE_ANON", "60/min"),
    "principal": _env_rate("ALEEKHAN_RATE_PRINCIPAL", "600/min"),
    "health": _env_rate("ALEEKHAN_RATE_HEALTH", "120/min"),
}

# REV-0015: behind the DEC-042 reverse proxy every client would share the proxy's IP bucket if NUM_PROXIES
# stayed 0. Trusting the proxy's X-Forwarded-Proto while ignoring its X-Forwarded-For is inconsistent, so a
# deployed environment refuses that combination (staging/prod config sets ALEEKHAN_NUM_PROXIES=1).
_NUM_PROXIES = _env_int("ALEEKHAN_NUM_PROXIES", 0)
if DEPLOYED and _TRUST_PROXY_TLS_HEADER and _NUM_PROXIES == 0:
    raise ImproperlyConfigured(
        "ALEEKHAN_TRUST_PROXY_TLS_HEADER=1 requires ALEEKHAN_NUM_PROXIES >= 1 in staging/prod"
    )

# ---------------------------------------------------------------------------------- identity (PHASE_01)
# Password hashing: Django's PBKDF2-SHA256 hasher (built in, no new dependency; Django 5.2 default work
# factor).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]


def _env_cidrs(name: str) -> tuple[str, ...]:
    """DEC-052: explicit CIDR list in server config only (never in Git or the DB). Validated at start-up."""
    import ipaddress

    out: list[str] = []
    for part in os.environ.get(name, "").split(","):
        item = part.strip()
        if not item:
            continue
        try:
            out.append(str(ipaddress.ip_network(item, strict=False)))
        except ValueError:
            raise ImproperlyConfigured(f"{name} contains an invalid CIDR range") from None
    return tuple(out)


# Factory network ranges (INTERNAL) and VPN ranges (always EXTERNAL, DEC-052). Empty = nothing is internal:
# every login then needs MFA and operator accounts cannot log in (safe default until IT supplies the list).
ALEEKHAN_INTERNAL_CIDRS = _env_cidrs("ALEEKHAN_INTERNAL_CIDRS")
ALEEKHAN_VPN_CIDRS = _env_cidrs("ALEEKHAN_VPN_CIDRS")

# Data keys for secrets at rest (TOTP seeds, stored files): "<key_ref>:<base64url 32 bytes>[,...]" from the
# secret store; ALEEKHAN_DATA_KEY_CURRENT names the key used for new ciphertexts. Never logged or stored.
_KEY_REF_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _env_data_keys() -> dict[str, bytes]:
    import base64

    keys: dict[str, bytes] = {}
    for part in os.environ.get("ALEEKHAN_DATA_KEYS", "").split(","):
        item = part.strip()
        if not item:
            continue
        ref, sep, encoded = item.partition(":")
        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)) if sep else b""
        except ValueError:
            raw = b""
        if not _KEY_REF_RE.fullmatch(ref) or len(raw) != 32:
            raise ImproperlyConfigured("ALEEKHAN_DATA_KEYS must be '<key_ref>:<base64url 32-byte key>' items")
        keys[ref] = raw
    return keys


ALEEKHAN_DATA_KEYS = _env_data_keys()
ALEEKHAN_DATA_KEY_CURRENT = os.environ.get("ALEEKHAN_DATA_KEY_CURRENT", "").strip()
if ALEEKHAN_DATA_KEY_CURRENT and ALEEKHAN_DATA_KEY_CURRENT not in ALEEKHAN_DATA_KEYS:
    raise ImproperlyConfigured("ALEEKHAN_DATA_KEY_CURRENT must name a key of ALEEKHAN_DATA_KEYS")

# ---------------------------------------------------------------------------------- documents (DEC-053)
# Root folder of stored files: must be on the encrypted server volume (ST-A); files are additionally encrypted
# per object (AES-256-GCM, key ALEEKHAN_DATA_KEY_CURRENT). Empty = uploads refused (DEPENDENCY_UNAVAILABLE).
ALEEKHAN_DOCUMENT_STORAGE_ROOT = os.environ.get("ALEEKHAN_DOCUMENT_STORAGE_ROOT", "").strip()
ALEEKHAN_DOCUMENT_VOLUME = os.environ.get("ALEEKHAN_DOCUMENT_VOLUME", "").strip() or "documents"
# ClamAV daemon in the isolated container (DEC-053 AV-A): TCP host/port or a unix socket path. Empty = no
# scanner configured: revisions stay QUARANTINED (never auto-CLEAN).
ALEEKHAN_CLAMD_HOST = os.environ.get("ALEEKHAN_CLAMD_HOST", "").strip()
ALEEKHAN_CLAMD_PORT = _env_int("ALEEKHAN_CLAMD_PORT", 3310, minimum=1)
ALEEKHAN_CLAMD_SOCKET = os.environ.get("ALEEKHAN_CLAMD_SOCKET", "").strip()
ALEEKHAN_CLAMD_TIMEOUT_SECONDS = _env_int("ALEEKHAN_CLAMD_TIMEOUT_SECONDS", 30, minimum=1)

REST_FRAMEWORK: dict[str, Any] = {
    # No authentication backend exists in PHASE_00 (login is PHASE_01; DEC-003: local users only).
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
    # Deny by default: a view that does not declare a permission explicitly is closed.
    "DEFAULT_PERMISSION_CLASSES": ["platform_core.api.permissions.DenyByDefault"],
    "DEFAULT_THROTTLE_CLASSES": [
        "platform_core.api.throttling.AnonIpThrottle",
        "platform_core.api.throttling.PrincipalThrottle",
    ],
    # JSON only: no browsable API in any environment.
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "platform_core.api.pagination.AleekhanCursorPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "platform_core.api.problems.exception_handler",
    # Number of trusted reverse proxies in front of the app (X-Forwarded-For); 0 = use REMOTE_ADDR only.
    "NUM_PROXIES": _NUM_PROXIES,
    "UNICODE_JSON": True,
    "COMPACT_JSON": True,
    "STRICT_JSON": True,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# ---------------------------------------------------------------------------------------------- logging
# Structured JSON lines to stdout with request_id; no request bodies, query strings, headers or exception
# messages are logged (platform_core.api.logging).
LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "platform_core.api.logging.RequestIdLogFilter"}},
    "formatters": {"json": {"()": "platform_core.api.logging.JsonFormatter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json", "filters": ["request_id"]}
    },
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}
