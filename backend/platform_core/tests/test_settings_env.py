"""Settings safety (REV-0011 + 00.4 security settings) and the REV-0008 test-DB guard.

Settings are imported in a fresh subprocess with a controlled environment (no DB connection is made); the
child prints only non-secret values as JSON.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from .conftest import assert_throwaway_test_db

BACKEND = Path(__file__).resolve().parents[2]
PROBE = """
import json, sys
from django.core.exceptions import ImproperlyConfigured
try:
    import importlib
    s = importlib.import_module(sys.argv[1])
except ImproperlyConfigured as exc:
    print(json.dumps({"error": str(exc)}))
    sys.exit(0)
print(json.dumps({k: getattr(s, k) for k in (
    "ALEEKHAN_ENV", "DEBUG", "ALLOWED_HOSTS", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE",
    "SECURE_SSL_REDIRECT", "SECURE_HSTS_SECONDS", "ALEEKHAN_BUILD_COMMIT", "REST_FRAMEWORK")}, default=str))
"""
DEPLOY_OK = {
    "DJANGO_SECRET_KEY": "synthetic-not-a-real-key-" + "x" * 40,
    "DJANGO_ALLOWED_HOSTS": "erp.internal.example",
    "ALEEKHAN_BUILD_COMMIT": "abcdef1",
}


def _settings(env: dict[str, str], module: str = "aleekhan.settings") -> dict[str, Any]:
    child = {k: v for k, v in os.environ.items() if not k.startswith(("ALEEKHAN_", "DJANGO_"))}
    child.update(env)
    child["PYTHONIOENCODING"] = "utf-8"
    out = subprocess.run(
        [sys.executable, "-c", PROBE, module],
        cwd=BACKEND,
        env=child,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    result: dict[str, Any] = json.loads(out.stdout.strip().splitlines()[-1])
    return result


def test_missing_aleekhan_env_refuses_to_start() -> None:
    assert "ALEEKHAN_ENV must be set" in _settings({})["error"]
    assert "ALEEKHAN_ENV must be set" in _settings({"ALEEKHAN_ENV": "  "})["error"]


def test_unknown_env_refused() -> None:
    assert "must be one of" in _settings({"ALEEKHAN_ENV": "production"})["error"]


def test_test_settings_pin_test_env_and_refuse_others() -> None:
    assert _settings({}, "aleekhan.settings_test")["ALEEKHAN_ENV"] == "test"
    assert (
        "requires ALEEKHAN_ENV=test" in _settings({"ALEEKHAN_ENV": "prod"}, "aleekhan.settings_test")["error"]
    )


@pytest.mark.parametrize("env", ["staging", "prod"])
@pytest.mark.parametrize("missing", ["DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "ALEEKHAN_BUILD_COMMIT"])
def test_deployed_envs_require_secret_hosts_and_build(env: str, missing: str) -> None:
    cfg = {k: v for k, v in DEPLOY_OK.items() if k != missing}
    assert "error" in _settings({"ALEEKHAN_ENV": env, **cfg})


def test_prod_settings_are_hardened() -> None:
    s = _settings({"ALEEKHAN_ENV": "prod", "DJANGO_DEBUG": "1", **DEPLOY_OK})
    assert s["DEBUG"] is False  # DJANGO_DEBUG ignored outside dev/test
    assert s["ALLOWED_HOSTS"] == ["erp.internal.example"]
    assert s["SESSION_COOKIE_SECURE"] is True and s["CSRF_COOKIE_SECURE"] is True
    assert s["SECURE_SSL_REDIRECT"] is True
    assert s["SECURE_HSTS_SECONDS"] >= 31_536_000
    assert s["REST_FRAMEWORK"]["DEFAULT_RENDERER_CLASSES"] == ["rest_framework.renderers.JSONRenderer"]
    assert s["REST_FRAMEWORK"]["DEFAULT_AUTHENTICATION_CLASSES"] == []


def test_prod_refuses_wildcard_host_and_weak_hsts() -> None:
    assert "error" in _settings({"ALEEKHAN_ENV": "prod", **DEPLOY_OK, "DJANGO_ALLOWED_HOSTS": "*"})
    assert "error" in _settings({"ALEEKHAN_ENV": "prod", **DEPLOY_OK, "ALEEKHAN_HSTS_SECONDS": "60"})


def test_invalid_build_commit_and_rate_refused() -> None:
    assert "error" in _settings({"ALEEKHAN_ENV": "dev", "ALEEKHAN_BUILD_COMMIT": "not-hex!"})
    assert "error" in _settings({"ALEEKHAN_ENV": "dev", "ALEEKHAN_RATE_ANON": "lots"})


def test_dev_defaults() -> None:
    s = _settings({"ALEEKHAN_ENV": "dev"})
    assert s["DEBUG"] is False  # DEBUG is opt-in even in dev
    assert s["ALLOWED_HOSTS"] == ["127.0.0.1", "localhost"]
    assert s["ALEEKHAN_BUILD_COMMIT"] == "0000000"
    assert s["SESSION_COOKIE_SECURE"] is False


# ------------------------------------------------------------------------------------------- REV-0015
@pytest.mark.parametrize("env", ["staging", "prod"])
def test_deployed_refuses_trusted_tls_header_without_proxies(env: str) -> None:
    base = {"ALEEKHAN_ENV": env, **DEPLOY_OK, "ALEEKHAN_TRUST_PROXY_TLS_HEADER": "1"}
    assert "ALEEKHAN_NUM_PROXIES" in _settings(base)["error"]
    assert "ALEEKHAN_NUM_PROXIES" in _settings({**base, "ALEEKHAN_NUM_PROXIES": "0"})["error"]
    ok = _settings({**base, "ALEEKHAN_NUM_PROXIES": "1"})
    assert "error" not in ok and ok["REST_FRAMEWORK"]["NUM_PROXIES"] == 1


def test_dev_allows_tls_header_without_proxies() -> None:
    s = _settings({"ALEEKHAN_ENV": "dev", "ALEEKHAN_TRUST_PROXY_TLS_HEADER": "1"})
    assert "error" not in s and s["REST_FRAMEWORK"]["NUM_PROXIES"] == 0


# ------------------------------------------------------------------------------------------- REV-0014
SETTINGS_PY = BACKEND / "aleekhan" / "settings.py"
ENV_EXAMPLE = BACKEND / ".env.example"
_ENV_READ_RE = re.compile(
    r"""(?:os\.environ\.get|os\.getenv|_env_bool|_env_int|_env_rate)\(\s*["']((?:ALEEKHAN|DJANGO)_[A-Z0-9_]+)["']"""
)


def settings_env_names() -> set[str]:
    """Every ALEEKHAN_* / DJANGO_* variable name read by settings.py."""
    return set(_ENV_READ_RE.findall(SETTINGS_PY.read_text(encoding="utf-8")))


def test_settings_env_names_are_discovered() -> None:
    names = settings_env_names()
    expected_subset = {
        "ALEEKHAN_ENV",
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "ALEEKHAN_BUILD_COMMIT",
        "ALEEKHAN_NUM_PROXIES",
        "ALEEKHAN_TRUST_PROXY_TLS_HEADER",
        "ALEEKHAN_REDIS_URL",
        "ALEEKHAN_RATE_ANON",
    }
    assert expected_subset <= names, sorted(expected_subset - names)


@pytest.mark.skip(
    reason=(
        "REV-0014 pending: backend/.env.example could not be updated by the 00.7 agent (file access "
        "denied by the agent permission rules). The orchestrator/employer adds the placeholders, then "
        "removes this skip."
    )
)
def test_env_example_lists_every_settings_variable() -> None:
    declared = {
        line.split("=", 1)[0].strip().removeprefix("export ").strip()
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    missing = sorted(settings_env_names() - declared)
    assert not missing, f".env.example is missing: {missing}"  # names only, never values


# ------------------------------------------------------------------------------------------- REV-0008
def test_throwaway_db_guard_refuses_non_test_db() -> None:
    assert_throwaway_test_db({"NAME": "test_aleekhan_dev"}, "test")
    with pytest.raises(RuntimeError, match="not a test_ database"):
        assert_throwaway_test_db({"NAME": "aleekhan_dev"}, "test")
    with pytest.raises(RuntimeError, match="not 'test'"):
        assert_throwaway_test_db({"NAME": "test_aleekhan_dev"}, "dev")
    with pytest.raises(RuntimeError):
        assert_throwaway_test_db({"NAME": ""}, "test")


@pytest.mark.django_db
def test_connected_test_db_passes_the_guard() -> None:
    from django.conf import settings
    from django.db import connection

    assert_throwaway_test_db(connection.settings_dict, settings.ALEEKHAN_ENV)
