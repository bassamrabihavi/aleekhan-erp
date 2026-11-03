"""Django settings for the Aleekhan platform.

All secrets and connection details come from the environment (SECURITY_BASELINE 2: no secrets in Git).
See ``backend/.env.example`` for the variable names (placeholders only).

Database configuration, in order of precedence:
1. ``DATABASE_URL`` (e.g. ``postgres://user:pass@host:5432/dbname``), parsed with dj-database-url;
2. libpq-style ``PGHOST`` / ``PGPORT`` / ``PGUSER`` / ``PGPASSWORD`` / ``PGDATABASE`` variables.

Only PostgreSQL is supported (ADR-001: PostgreSQL 17). There is no SQLite fallback on purpose: the
schema relies on PostgreSQL triggers, CHECK constraints with regular expressions and partial indexes.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

ALEEKHAN_ENV = os.environ.get("ALEEKHAN_ENV", "dev").strip().lower()
if ALEEKHAN_ENV not in {"dev", "test", "staging", "prod"}:
    raise ImproperlyConfigured("ALEEKHAN_ENV must be one of dev, test, staging, prod")

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1" and ALEEKHAN_ENV in {"dev", "test"}

_secret = os.environ.get("DJANGO_SECRET_KEY", "")
if _secret == "CHANGE_ME":  # placeholder from .env.example is never a real key
    _secret = ""
if not _secret:
    if ALEEKHAN_ENV in {"staging", "prod"}:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set outside dev/test")
    # dev/test only: ephemeral per-process key, never persisted or logged.
    _secret = secrets.token_urlsafe(50)
SECRET_KEY = _secret

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]

# PHASE_00 scope: platform skeleton only. django.contrib.auth / sessions / admin are added in PHASE_01
# (users are created only inside the system by the owner/admin, DEC-003). DRF is pinned for step 00.4.
INSTALLED_APPS = [
    "platform_core.apps.PlatformCoreConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "aleekhan.urls"
WSGI_APPLICATION = "aleekhan.wsgi.application"
ASGI_APPLICATION = "aleekhan.asgi.application"
TEMPLATES: list[dict[str, Any]] = []


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
    return cfg


DATABASES = {"default": _database_config()}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Time: stored in UTC (timestamptz); Jalali / Asia/Tehran is a UI concern only (ADR-001).
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "fa"
USE_I18N = True

# Security headers baseline (full hardening in 00.7).
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = ALEEKHAN_ENV in {"staging", "prod"}
CSRF_COOKIE_SECURE = ALEEKHAN_ENV in {"staging", "prod"}

LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}
