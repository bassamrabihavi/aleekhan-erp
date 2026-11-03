"""PHASE_00 endpoints over real HTTP (Django test client): health, version, access gate, request id, problems,
rate limiting, logging. Contract validation of every response: ``test_api_contract.py``."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import pytest
from django.test import Client, override_settings
from hypothesis import given
from hypothesis import strategies as st

from platform_core.api import views
from platform_core.api.logging import JsonFormatter, RequestIdLogFilter
from platform_core.api.request_id import parse_request_id

pytestmark = pytest.mark.usefixtures("clear_cache")

API = "/api/v1"


def _json(resp: Any) -> Any:
    return json.loads(resp.content.decode("utf-8"))


# ------------------------------------------------------------------------------------------- health
def test_liveness_is_public_and_minimal(client: Client) -> None:
    r = client.get(f"{API}/health/live")
    assert r.status_code == 200
    assert _json(r) == {"status": "ok"}
    assert r["Cache-Control"] == "no-store"
    assert r["Content-Type"] == "application/json"


@pytest.mark.django_db
def test_readiness_checks_db_migrations_cache(client: Client) -> None:
    r = client.get(f"{API}/health/ready")
    assert r.status_code == 200, r.content
    body = _json(r)
    assert body["status"] == "ready"
    assert body["checked_at"].endswith("Z")
    assert body["components"] == [
        {"name": "database", "status": "up"},
        {"name": "migrations", "status": "up"},
        {"name": "cache", "status": "up"},
    ]
    assert r["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_down_reports_503_without_details(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> str:
        raise RuntimeError("SYNTHETIC host=db.internal password=hunter2")

    monkeypatch.setattr(views, "_check_database", boom)
    r = client.get(f"{API}/health/ready")
    assert r.status_code == 503
    assert r["Retry-After"] == "5"
    body = _json(r)
    assert body["status"] == "not_ready"
    assert {"name": "database", "status": "down"} in body["components"]
    assert {"name": "migrations", "status": "unknown"} in body["components"]
    text = r.content.decode()
    assert "hunter2" not in text and "db.internal" not in text and "SYNTHETIC" not in text


@pytest.mark.django_db
def test_readiness_pending_migration_is_not_ready(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(views, "_check_migrations", lambda: "down")
    r = client.get(f"{API}/health/ready")
    assert r.status_code == 503
    assert {"name": "migrations", "status": "down"} in _json(r)["components"]


# ------------------------------------------------------------------------------------------- version (C-17)
def test_version_exposes_only_contract_and_build(client: Client) -> None:
    r = client.get(f"{API}/version")
    assert r.status_code == 200
    body = _json(r)
    assert set(body) == {"api_version", "contract_version", "build_commit", "environment"}
    assert body["api_version"] == "v1"
    assert body["environment"] == "test"
    assert r["ETag"].startswith('"') and r["ETag"].endswith('"')
    text = r.content.decode().lower()
    for leak in ("python", "django", "postgres", "windows", "linux", "\\\\", "/home/", "version_info"):
        assert leak not in text


@override_settings(ALEEKHAN_BUILD_COMMIT="abc1234def56", ALEEKHAN_ENV="prod")
def test_version_maps_prod_to_contract_name_and_etag_changes(client: Client) -> None:
    r = client.get(f"{API}/version")
    body = _json(r)
    assert body["environment"] == "production"
    assert body["build_commit"] == "abc1234def56"
    with override_settings(ALEEKHAN_BUILD_COMMIT="fff1234def56"):
        assert client.get(f"{API}/version")["ETag"] != r["ETag"]


# ------------------------------------------------------------------------------------------- access gate
def test_access_gate_without_principal_is_401_problem(client: Client) -> None:
    r = client.get(f"{API}/access-gate/check", {"action": "warehouse.reservation.create"})
    assert r.status_code == 401
    assert r["Content-Type"] == "application/problem+json"
    body = _json(r)
    assert body["code"] == "AUTHENTICATION_REQUIRED"
    assert body["request_id"] == r["X-Request-ID"]
    assert "decision" not in body


@given(
    action=st.text(max_size=150),
    extra=st.dictionaries(st.sampled_from(["resource_type", "resource_id", "x"]), st.text(max_size=70)),
)
def test_access_gate_never_allows_anonymous(action: str, extra: dict[str, str]) -> None:
    """Whatever the parameters, PHASE_00 production code never answers ALLOW (nor anything but 401/429)."""
    from django.core.cache import cache

    cache.clear()
    params = {"action": action, **extra}
    params = {k: v.replace("\x00", "") for k, v in params.items()}
    r = Client().get(f"{API}/access-gate/check", params)
    assert r.status_code == 401
    assert b"ALLOW" not in r.content


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_access_gate_rejects_writes(client: Client, method: str) -> None:
    r = getattr(client, method)(f"{API}/access-gate/check")
    # authentication is checked before the method (DRF initial()); either way never a 2xx
    assert r.status_code in {401, 405}
    assert r["Content-Type"] == "application/problem+json"


# ------------------------------------------------------------------------------------------- request id
def test_valid_request_id_is_echoed(client: Client) -> None:
    rid = str(uuid.uuid4())
    r = client.get(f"{API}/health/live", HTTP_X_REQUEST_ID=rid)
    assert r["X-Request-ID"] == rid


def test_uppercase_uuid_is_accepted_and_normalised(client: Client) -> None:
    rid = str(uuid.uuid4())
    r = client.get(f"{API}/health/live", HTTP_X_REQUEST_ID=rid.upper())
    assert r["X-Request-ID"] == rid


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "abc",
        "not-a-uuid-at-all-but-36-characters",
        "{" + str(uuid.uuid4()) + "}",
        str(uuid.uuid4()).replace("-", ""),
        str(uuid.uuid4()) + "x",
        "x" * 5000,
        str(uuid.uuid4())[:-1] + "\n",
        "urn:uuid:" + str(uuid.uuid4()),
    ],
)
def test_invalid_request_id_is_replaced(client: Client, bad: str) -> None:
    r = client.get(f"{API}/health/live", HTTP_X_REQUEST_ID=bad)
    out = r["X-Request-ID"]
    assert out != bad
    assert str(uuid.UUID(out)) == out and uuid.UUID(out).version == 4


@given(st.text(max_size=80))
def test_parse_request_id_accepts_only_canonical_uuids(raw: str) -> None:
    parsed = parse_request_id(raw)
    if parsed is not None:
        assert len(raw) == 36 and str(parsed) == raw.lower()


def test_request_id_on_django_level_404(client: Client) -> None:
    rid = str(uuid.uuid4())
    r = client.get(f"{API}/no-such-endpoint", HTTP_X_REQUEST_ID=rid)
    assert r.status_code == 404
    assert r["Content-Type"] == "application/problem+json"
    body = _json(r)
    assert body["code"] == "NOT_FOUND" and body["request_id"] == rid
    assert r["X-Request-ID"] == rid


def test_trailing_slash_is_not_redirected(client: Client) -> None:
    r = client.get(f"{API}/health/live/")
    assert r.status_code == 404


def test_disallowed_host_is_400_problem() -> None:
    r = Client(HTTP_HOST="evil.example").get(f"{API}/health/live")
    assert r.status_code == 400
    assert r["Content-Type"] == "application/problem+json"
    assert _json(r)["code"] == "VALIDATION_FAILED"
    assert b"evil.example" not in r.content


def test_method_not_allowed_is_405_problem(client: Client) -> None:
    r = client.post(f"{API}/health/live", data={}, content_type="application/json")
    assert r.status_code == 405
    body = _json(r)
    assert body["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in r["Allow"]


def test_no_browsable_api(client: Client) -> None:
    r = client.get(f"{API}/health/live", HTTP_ACCEPT="text/html")
    assert r["Content-Type"] != "text/html"
    assert b"<html" not in r.content.lower()


def test_security_headers(client: Client) -> None:
    r = client.get(f"{API}/health/live")
    assert r["X-Content-Type-Options"] == "nosniff"
    assert r["X-Frame-Options"] == "DENY"
    assert r["Referrer-Policy"] == "same-origin"


# ------------------------------------------------------------------------------------------- rate limit
@override_settings(ALEEKHAN_THROTTLE_RATES={"anon": "3/min", "principal": "100/min", "health": "2/min"})
def test_rate_limit_per_ip_returns_429_problem_with_retry_after() -> None:
    ip_a = Client(REMOTE_ADDR="10.0.0.1")
    ip_b = Client(REMOTE_ADDR="10.0.0.2")
    codes = [ip_a.get(f"{API}/health/live").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = ip_a.get(f"{API}/version")
    assert r.status_code == 429
    assert r["Content-Type"] == "application/problem+json"
    assert int(r["Retry-After"]) >= 1
    body = _json(r)
    assert body["code"] == "RATE_LIMITED" and body["status"] == 429
    # another IP has its own bucket; the anonymous API bucket is separate from the probe bucket
    assert ip_b.get(f"{API}/health/live").status_code == 200
    gate = [ip_a.get(f"{API}/access-gate/check", {"action": "a.b"}).status_code for _ in range(4)]
    assert gate == [401, 401, 401, 429]


@override_settings(ALEEKHAN_THROTTLE_RATES={"anon": "1/min", "principal": "1/min", "health": "1/min"})
def test_x_forwarded_for_is_not_trusted_without_proxies() -> None:
    c = Client(REMOTE_ADDR="10.0.0.9")
    assert c.get(f"{API}/health/live", HTTP_X_FORWARDED_FOR="1.1.1.1").status_code == 200
    assert c.get(f"{API}/health/live", HTTP_X_FORWARDED_FOR="2.2.2.2").status_code == 429


# ------------------------------------------------------------------------------------------- logging
def _record(msg: str = "m", **extra: Any) -> logging.LogRecord:
    rec = logging.LogRecord("aleekhan.test", logging.INFO, __file__, 1, msg, None, None)
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def test_json_log_contains_request_id_and_only_allowlisted_extras() -> None:
    rec = _record(event="http_request", status=200, password="<synthetic-not-a-secret>", body={"salary": 1})
    RequestIdLogFilter().filter(rec)
    out = json.loads(JsonFormatter().format(rec))
    assert out["event"] == "http_request" and out["status"] == 200
    assert "request_id" in out
    assert "password" not in out and "body" not in out
    assert "<synthetic-not-a-secret>" not in json.dumps(out)


def test_json_log_exception_has_type_and_frames_but_no_message() -> None:
    try:
        raise ValueError("SYNTHETIC-SECRET password=hunter2")
    except ValueError:
        import sys

        rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "unhandled error", None, sys.exc_info())
    text = JsonFormatter().format(rec)
    out = json.loads(text)
    assert out["exc_type"] == "builtins.ValueError"
    assert out["stack"] and all(":" in f for f in out["stack"])
    assert "hunter2" not in text and "SYNTHETIC-SECRET" not in text


def test_access_log_line_has_request_id(client: Client, caplog: pytest.LogCaptureFixture) -> None:
    rid = str(uuid.uuid4())
    with caplog.at_level(logging.INFO, logger="aleekhan.access"):
        client.get(f"{API}/access-gate/check?action=a.b&secret=hunter2", HTTP_X_REQUEST_ID=rid)
    recs = [r for r in caplog.records if r.name == "aleekhan.access"]
    assert recs, "no access log"
    rec = recs[-1]
    assert getattr(rec, "status", None) == 401
    assert getattr(rec, "error_code", None) == "AUTHENTICATION_REQUIRED"
    assert getattr(rec, "path", None) == f"{API}/access-gate/check"  # no query string
    RequestIdLogFilter().filter(rec)
    line = JsonFormatter().format(rec)
    assert "hunter2" not in line
    assert json.loads(line)["request_id"] == rid


def test_csrf_failure_view_returns_problem() -> None:
    from django.test import RequestFactory

    from platform_core.api.problems import csrf_failure

    r = csrf_failure(RequestFactory().post("/x"), reason="CSRF cookie not set.")
    assert r.status_code == 403
    assert r["Content-Type"] == "application/problem+json"
    body = _json(r)
    assert body["code"] == "ACCESS_DENIED"
    assert b"CSRF cookie" not in r.content
