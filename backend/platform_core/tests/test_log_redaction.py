"""Log redaction (00.7, SECURITY_BASELINE 2 "no passwords/tokens in logs"): real requests carrying SYNTHETIC
secret markers in the query string, headers, cookies and JSON body - plus an unhandled error and a failing
readiness check whose exception messages contain a marker - must not leak any marker into the structured
JSON log lines (the production formatter + filter from settings.LOGGING).
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest
from django.test import Client

from platform_core.api import views
from platform_core.api.logging import JsonFormatter, RequestIdLogFilter

pytestmark = [pytest.mark.usefixtures("clear_cache"), pytest.mark.django_db]

API = "/api/v1"
MARKERS = (
    "SYNTHETIC-QS-TOKEN-0001",
    "SYNTHETIC-AUTH-HEADER-0002",
    "SYNTHETIC-COOKIE-0003",
    "SYNTHETIC-BODY-PASSWORD-0004",
    "SYNTHETIC-EXC-MESSAGE-0005",
    "SYNTHETIC-READY-EXC-0006",
)


@pytest.fixture
def captured() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdLogFilter())
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield buf
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def test_structured_logs_never_contain_secret_values(
    captured: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = Client(raise_request_exception=False)
    c.cookies["aleekhan_session"] = MARKERS[2]
    c.get(
        f"{API}/access-gate/check",
        {"action": "a.b", "token": MARKERS[0]},
        HTTP_AUTHORIZATION=f"Bearer {MARKERS[1]}",
    )
    c.post(
        f"{API}/integration/conflicts/00000000-0000-4000-8000-000000000001/resolve",
        json.dumps({"password": MARKERS[3], "رمز عبور": MARKERS[3]}),
        content_type="application/json",
    )

    def boom(self: object, request: object) -> None:
        raise RuntimeError(f"password={MARKERS[4]}")

    monkeypatch.setattr(views.VersionView, "get", boom)
    assert c.get(f"{API}/version").status_code == 500

    def ready_boom() -> str:
        raise RuntimeError(f"host=db.internal password={MARKERS[5]}")

    monkeypatch.setattr(views, "_check_database", ready_boom)
    assert c.get(f"{API}/health/ready").status_code == 503

    text = captured.getvalue()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) >= 4, text  # access log lines + error lines were produced
    for ln in lines:
        json.loads(ln)  # every line is one JSON object
    for marker in MARKERS:
        assert marker not in text, marker
    assert "db.internal" not in text
    events = [json.loads(ln).get("event") for ln in lines]
    assert "http_request" in events and "api_error" in events
