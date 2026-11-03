"""Reusable API utilities over real HTTP against the TEST-ONLY harness URLconf (``api_harness.py``):
deny-by-default, scoped permission (404 out of scope), cursor pagination, ETag/If-Match, Idempotency-Key
replay (incl. stored 4xx, REV-0012), global exception handler."""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any

import pytest
from django.test import Client

from platform_core.models import AuditEvent, IdempotencyRecord, IdempotencyState, OutboxEvent

from . import factories

pytestmark = [pytest.mark.urls("platform_core.tests.api_harness"), pytest.mark.usefixtures("clear_cache")]

T = "/api/v1/_test"


def _json(resp: Any) -> Any:
    return json.loads(resp.content.decode("utf-8"))


def _who(scope: str = "", actor: uuid.UUID | None = None) -> dict[str, Any]:
    return {"HTTP_X_TEST_PRINCIPAL": str(actor or uuid.uuid4()), "HTTP_X_TEST_SCOPE": scope}


def _rows(scope: str, n: int) -> list[OutboxEvent]:
    return [factories.outbox_event(aggregate_id=scope) for _ in range(n)]


# ------------------------------------------------------------------------------------------- permissions
def test_default_permission_denies_anonymous_with_401(client: Client) -> None:
    r = client.get(f"{T}/default-permission")
    assert r.status_code == 401 and _json(r)["code"] == "AUTHENTICATION_REQUIRED"


def test_default_permission_denies_principal_with_403(client: Client) -> None:
    r = client.get(f"{T}/default-permission", **_who())
    assert r.status_code == 403 and _json(r)["code"] == "ACCESS_DENIED"


def test_harness_access_gate_with_principal_is_always_deny(client: Client) -> None:
    r = client.get(
        f"{T}/access-gate/check",
        {
            "action": "warehouse.reservation.create",
            "resource_type": "reservation",
            "resource_id": str(uuid.uuid4()),
        },
        **_who(),
    )
    assert r.status_code == 200
    body = _json(r)
    assert body["decision"] == "DENY" and body["reason_code"] == "POLICY_NOT_DEFINED"
    assert body["request_id"] == r["X-Request-ID"]


@pytest.mark.parametrize(
    ("params", "field", "code"),
    [
        ({}, "action", "REQUIRED"),
        ({"action": "NoDots"}, "action", "PATTERN_MISMATCH"),
        ({"action": "a." + "b" * 130}, "action", "PATTERN_MISMATCH"),
        ({"action": "a.b", "resource_type": "Bad-Type"}, "resource_type", "PATTERN_MISMATCH"),
        ({"action": "a.b", "resource_id": "123"}, "resource_id", "INVALID_UUID"),
    ],
)
def test_harness_access_gate_validates_parameters(
    client: Client, params: dict[str, str], field: str, code: str
) -> None:
    r = client.get(f"{T}/access-gate/check", params, **_who())
    assert r.status_code == 400
    body = _json(r)
    assert body["code"] == "VALIDATION_FAILED"
    assert {"field": field, "code": code} in body["errors"]


@pytest.mark.django_db
def test_scoped_list_only_shows_records_in_scope(client: Client) -> None:
    mine = _rows("scope-a", 3)
    _rows("scope-b", 2)
    r = client.get(f"{T}/synthetic", **_who("scope-a"))
    assert r.status_code == 200
    body = _json(r)
    assert [i["id"] for i in body["items"]] == [o.pk for o in mine]
    assert body["page"] == {"page_size": 25, "next_cursor": None}


@pytest.mark.django_db
def test_out_of_scope_record_is_404_not_403(client: Client) -> None:
    other = _rows("scope-b", 1)[0]
    r = client.get(f"{T}/synthetic/{other.pk}", **_who("scope-a"))
    assert r.status_code == 404
    assert _json(r)["code"] == "NOT_FOUND"
    missing = client.get(f"{T}/synthetic/999999999", **_who("scope-a"))
    # indistinguishable from a missing record except for the request id
    a, b = _json(r), _json(missing)
    a.pop("request_id"), b.pop("request_id")
    assert a == b


@pytest.mark.django_db
def test_in_scope_record_has_strong_etag(client: Client) -> None:
    row = _rows("scope-a", 1)[0]
    r = client.get(f"{T}/synthetic/{row.pk}", **_who("scope-a"))
    assert r.status_code == 200
    assert r["ETag"] == '"1"'


# ------------------------------------------------------------------------------------------- pagination
@pytest.mark.django_db
def test_cursor_pagination_walks_all_pages_without_duplicates(client: Client) -> None:
    rows = _rows("scope-a", 7)
    seen: list[int] = []
    cursor = None
    pages = 0
    while True:
        params: dict[str, Any] = {"page_size": 3}
        if cursor:
            params["cursor"] = cursor
        r = client.get(f"{T}/synthetic", params, **_who("scope-a"))
        assert r.status_code == 200, r.content
        body = _json(r)
        assert body["page"]["page_size"] == 3
        seen += [i["id"] for i in body["items"]]
        cursor = body["page"]["next_cursor"]
        pages += 1
        if cursor is None:
            break
        assert "http" not in cursor and "/" not in cursor.replace("=", "")  # opaque token, not a URL
    assert seen == [r.pk for r in rows]
    assert pages == 3


@pytest.mark.django_db
def test_page_size_default_and_max(client: Client) -> None:
    _rows("scope-a", 101)
    r = client.get(f"{T}/synthetic", **_who("scope-a"))
    assert len(_json(r)["items"]) == 25
    r = client.get(f"{T}/synthetic", {"page_size": 100}, **_who("scope-a"))
    body = _json(r)
    assert len(body["items"]) == 100 and body["page"]["next_cursor"]


@pytest.mark.parametrize("bad", ["0", "101", "-1", "abc", "1.5", "٣", "", "1e2"])
def test_invalid_page_size_is_400(client: Client, bad: str) -> None:
    r = client.get(f"{T}/synthetic", {"page_size": bad}, **_who("scope-a"))
    assert r.status_code == 400
    assert {"field": "page_size", "code": "OUT_OF_RANGE"} in _json(r)["errors"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cursor",
    [
        "garbage!!",
        "x" * 600,
        base64.b64encode(b"p=not-a-number").decode(),
        base64.b64encode(b"o=-5").decode(),
    ],
)
def test_malformed_or_tampered_cursor_is_400(client: Client, cursor: str) -> None:
    _rows("scope-a", 2)
    r = client.get(f"{T}/synthetic", {"cursor": cursor}, **_who("scope-a"))
    assert r.status_code == 400, r.content
    assert {"field": "cursor", "code": "INVALID_CURSOR"} in _json(r)["errors"]


# ------------------------------------------------------------------------------ If-Match + idempotency
def _patch(client: Client, pk: int, body: Any, *, if_match: str | None, key: str | None, **who: Any) -> Any:
    headers: dict[str, Any] = dict(who)
    if if_match is not None:
        headers["HTTP_IF_MATCH"] = if_match
    if key is not None:
        headers["HTTP_IDEMPOTENCY_KEY"] = key
    return client.patch(f"{T}/synthetic/{pk}/update", data=body, content_type="application/json", **headers)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_update_with_if_match_and_idempotency_key_then_replay(client: Client) -> None:
    row = _rows("scope-a", 1)[0]
    who = _who("scope-a")
    key = str(uuid.uuid4())
    r1 = _patch(client, row.pk, {"last_error": "note-1"}, if_match='"1"', key=key, **who)
    assert r1.status_code == 200, r1.content
    assert r1["ETag"] == '"2"' and _json(r1) == {"id": row.pk, "row_version": 2}
    assert "Idempotent-Replayed" not in r1
    r2 = _patch(client, row.pk, {"last_error": "note-1"}, if_match='"1"', key=key, **who)
    assert r2.status_code == 200 and r2["Idempotent-Replayed"] == "true"
    assert _json(r2) == _json(r1) and r2["ETag"] == '"2"'
    row.refresh_from_db()
    assert row.row_version == 2 and row.last_error == "note-1"
    assert AuditEvent.objects.count() == 1
    assert OutboxEvent.objects.filter(event_type="platform.synthetic.updated").count() == 1
    audit = AuditEvent.objects.get()
    assert str(audit.request_id) == r1["X-Request-ID"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("if_match", "status", "code"),
    [
        (None, 428, "PRECONDITION_REQUIRED"),
        ("*", 400, "VALIDATION_FAILED"),
        ('W/"1"', 412, "VERSION_CONFLICT"),
    ],
)
def test_if_match_preconditions(client: Client, if_match: str | None, status: int, code: str) -> None:
    row = _rows("scope-a", 1)[0]
    r = _patch(
        client, row.pk, {"last_error": "x"}, if_match=if_match, key=str(uuid.uuid4()), **_who("scope-a")
    )
    assert r.status_code == status and _json(r)["code"] == code


@pytest.mark.django_db
def test_missing_or_bad_idempotency_key(client: Client) -> None:
    row = _rows("scope-a", 1)[0]
    r = _patch(client, row.pk, {"last_error": "x"}, if_match='"1"', key=None, **_who("scope-a"))
    assert r.status_code == 428 and _json(r)["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    r = _patch(client, row.pk, {"last_error": "x"}, if_match='"1"', key="nope", **_who("scope-a"))
    assert r.status_code == 400 and _json(r)["code"] == "VALIDATION_FAILED"


@pytest.mark.django_db
def test_update_requires_principal(client: Client) -> None:
    row = _rows("scope-a", 1)[0]
    r = _patch(client, row.pk, {"last_error": "x"}, if_match='"1"', key=str(uuid.uuid4()))
    assert r.status_code == 401


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_stale_if_match_412_is_stored_and_replayed(client: Client) -> None:
    """REV-0012 at HTTP level: a final 4xx is replayed for the same key + same request."""
    row = _rows("scope-a", 1)[0]
    who = _who("scope-a")
    assert (
        _patch(client, row.pk, {"last_error": "a"}, if_match='"1"', key=str(uuid.uuid4()), **who).status_code
        == 200
    )
    key = str(uuid.uuid4())
    r1 = _patch(client, row.pk, {"last_error": "b"}, if_match='"1"', key=key, **who)
    assert r1.status_code == 412 and _json(r1)["code"] == "VERSION_CONFLICT"
    rec = IdempotencyRecord.objects.get(key=key)
    assert rec.state == IdempotencyState.COMPLETED and rec.response_status == 412
    r2 = _patch(client, row.pk, {"last_error": "b"}, if_match='"1"', key=key, **who)
    assert r2.status_code == 412
    assert r2["Content-Type"] == "application/problem+json"
    assert r2["Idempotent-Replayed"] == "true"
    assert _json(r2) == _json(r1)  # original request_id kept
    assert r2["X-Request-ID"] != r1["X-Request-ID"]
    row.refresh_from_db()
    assert row.last_error == "a" and row.row_version == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_out_of_scope_update_is_404_and_writes_nothing(client: Client) -> None:
    other = _rows("scope-b", 1)[0]
    r = _patch(
        client, other.pk, {"last_error": "x"}, if_match='"1"', key=str(uuid.uuid4()), **_who("scope-a")
    )
    assert r.status_code == 404 and _json(r)["code"] == "NOT_FOUND"
    other.refresh_from_db()
    assert other.row_version == 1 and other.last_error == ""
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_invalid_json_body_is_400(client: Client) -> None:
    row = _rows("scope-a", 1)[0]
    r = client.patch(
        f"{T}/synthetic/{row.pk}/update",
        data="{not json",
        content_type="application/json",
        HTTP_IF_MATCH='"1"',
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        **_who("scope-a"),
    )
    assert r.status_code == 400 and _json(r)["code"] == "VALIDATION_FAILED"


# ------------------------------------------------------------------------------ exception handler
@pytest.mark.parametrize("kind", ["contract", "runtime"])
def test_unexpected_errors_are_generic_500(
    client: Client, kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    r = client.get(f"{T}/errors/{kind}")
    assert r.status_code == 500
    assert r["Content-Type"] == "application/problem+json"
    body = _json(r)
    assert body["code"] == "INTERNAL_ERROR"
    assert set(body) == {"type", "title", "status", "code", "message_fa", "request_id"}
    for leak in (b"SYNTHETIC-SECRET", b"hunter2", b"SELECT", b"Traceback", b".py"):
        assert leak not in r.content
    assert any(getattr(rec, "error_code", None) == "INTERNAL_ERROR" for rec in caplog.records)


def test_rule_not_approved_is_409_with_decision_id(client: Client) -> None:
    r = client.get(f"{T}/errors/rule")
    assert r.status_code == 409
    body = _json(r)
    assert body["code"] == "RULE_NOT_APPROVED" and body["decision_id"] == "DEC-005"


def test_drf_validation_error_maps_fields_without_values(client: Client) -> None:
    r = client.get(f"{T}/errors/drf-validation")
    assert r.status_code == 400
    body = _json(r)
    assert body["code"] == "VALIDATION_FAILED"
    assert {"field": "qty", "code": "INVALID"} in body["errors"]
    assert {"field": "nested.x", "code": "INVALID"} in body["errors"]
    assert b"must be positive" not in r.content


def test_payload_too_large_is_413(client: Client, settings: Any) -> None:
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 1024
    r = client.patch(
        f"{T}/synthetic/1/update",
        data=json.dumps({"last_error": "x" * 5000}),
        content_type="application/json",
        HTTP_IF_MATCH='"1"',
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        **_who("scope-a"),
    )
    assert r.status_code == 413 and _json(r)["code"] == "PAYLOAD_TOO_LARGE"
