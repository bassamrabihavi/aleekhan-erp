"""00.6 integration endpoints over real HTTP, validated against docs/api/openapi-draft.yaml.

* Production URLconf: no authentication backend in PHASE_00 -> every integration endpoint answers 401.
* TEST-ONLY harness (``api_harness.py``): synthetic principal; actions granted explicitly via
  ``X-Test-Actions``
  and record scope = source codes via ``X-Test-Scope``. Proves deny-by-default (403 without the action),
  BOLA/IDOR (404 out of scope), cursor pagination, ETag/If-Match, Idempotency-Key replay.
All sources and conflicts are SYNTHETIC.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from django.test import Client

from platform_core.api import integration_views as iv
from platform_core.engine.context import Actor, RequestContext
from platform_core.integration import conflicts as cf
from platform_core.integration.models import ConflictItem, IntegrationSource
from platform_core.models import AuditEvent, OutboxEvent

from . import factories
from . import openapi_contract as oc

pytestmark = pytest.mark.usefixtures("clear_cache")

API = oc.BASE_PATH
T = "/api/v1/_test"
ALL = ",".join([iv.READ_FRESHNESS, iv.READ_CONFLICTS, iv.RESOLVE_CONFLICT])
FRESHNESS = "/integration/freshness"
CONFLICTS = "/integration/conflicts"
CONFLICT = "/integration/conflicts/{conflict_id}"
RESOLVE = "/integration/conflicts/{conflict_id}/resolve"


def _json(resp: Any) -> Any:
    return json.loads(resp.content.decode("utf-8"))


def _who(scope: str = "", actions: str = ALL, actor: uuid.UUID | None = None) -> dict[str, Any]:
    return {
        "HTTP_X_TEST_PRINCIPAL": str(actor or uuid.uuid4()),
        "HTTP_X_TEST_SCOPE": scope,
        "HTTP_X_TEST_ACTIONS": actions,
    }


def _conflict(src: IntegrationSource, key: str = "k1") -> ConflictItem:
    return cf.raise_conflict(
        RequestContext(Actor.system()),
        source_code=src.code,
        kind="synthetic_kind",
        key=key,
        details={"cell": "A1"},
    ).item


# ------------------------------------------------------------------------------------------- production
@pytest.mark.django_db
@pytest.mark.parametrize("method", ["get", "post"])
def test_production_endpoints_require_authentication(client: Client, method: str) -> None:
    cid = str(uuid.uuid4())
    cases = [(FRESHNESS, "get"), (CONFLICTS, "get"), (CONFLICT, "get"), (RESOLVE, "post")]
    for spec_path, m in cases:
        if m != method:
            continue
        url = API + spec_path.format(conflict_id=cid)
        r = client.get(url) if m == "get" else client.post(url, {}, content_type="application/json")
        assert r.status_code == 401, spec_path
        assert _json(r)["code"] == "AUTHENTICATION_REQUIRED"
        oc.validate_response(spec_path, m, r)


# ------------------------------------------------------------------------------------------- permission
@pytest.mark.django_db
@pytest.mark.urls("platform_core.tests.api_harness")
def test_principal_without_explicit_action_is_403(client: Client) -> None:
    src = factories.integration_source()
    item = _conflict(src)
    for spec_path, m, missing in [
        (FRESHNESS, "get", iv.READ_FRESHNESS),
        (CONFLICTS, "get", iv.READ_CONFLICTS),
        (CONFLICT, "get", iv.READ_CONFLICTS),
        (RESOLVE, "post", iv.RESOLVE_CONFLICT),
    ]:
        granted = ",".join(a for a in ALL.split(",") if a != missing)
        url = T + spec_path.format(conflict_id=item.conflict_id)
        who = _who(src.code, granted)
        r = (
            client.get(url, **who)
            if m == "get"
            else client.post(url, {}, content_type="application/json", **who)
        )
        assert r.status_code == 403 and _json(r)["code"] == "ACCESS_DENIED", spec_path
        oc.validate_response(spec_path, m, r)
    item.refresh_from_db()
    assert item.status == "OPEN"


# ------------------------------------------------------------------------------------------- freshness
@pytest.mark.django_db
@pytest.mark.urls("platform_core.tests.api_harness")
def test_freshness_scoped_paginated_with_etag(client: Client) -> None:
    a, b, hidden = (factories.integration_source() for _ in range(3))
    scope = ",".join([a.code, b.code, "rahkaran_excel"])
    r = client.get(f"{T}{FRESHNESS}", **_who(scope))
    assert r.status_code == 200
    oc.validate_response(FRESHNESS, "get", r)
    body = _json(r)
    codes = [i["source_code"] for i in body["items"]]
    assert codes == sorted([a.code, b.code, "rahkaran_excel"]) and hidden.code not in codes
    rk = next(i for i in body["items"] if i["source_code"] == "rahkaran_excel")
    assert rk["direction"] == "READ_ONLY" and rk["threshold_basis"] == "TECHNICAL_DEFAULT"
    assert rk["policy_decision_id"] == "DEC-016" and rk["staleness_threshold_seconds"] == 86400
    assert all(i["freshness"] == "never" and i["last_success_at"] is None for i in body["items"])
    assert r["ETag"] == client.get(f"{T}{FRESHNESS}", **_who(scope))["ETag"]  # stable while nothing changes
    # walk pages of 1
    seen, cursor = [], None
    for _ in range(5):
        params = {"page_size": "1", **({"cursor": cursor} if cursor else {})}
        page = client.get(f"{T}{FRESHNESS}", params, **_who(scope))
        oc.validate_response(FRESHNESS, "get", page)
        data = _json(page)
        seen += [i["source_code"] for i in data["items"]]
        cursor = data["page"]["next_cursor"]
        if cursor is None:
            break
    assert seen == codes
    bad = client.get(f"{T}{FRESHNESS}", {"page_size": "0"}, **_who(scope))
    assert bad.status_code == 400
    oc.validate_response(FRESHNESS, "get", bad)


@pytest.mark.django_db
@pytest.mark.urls("platform_core.tests.api_harness")
def test_freshness_reports_fresh_after_validated_import(client: Client) -> None:
    from platform_core.integration import imports as im

    src = factories.integration_source()
    before = client.get(f"{T}{FRESHNESS}", **_who(src.code))
    ctx = RequestContext(Actor.system())
    batch = im.receive_file(ctx, source_code=src.code, content=b"SYNTHETIC", original_name="s.xlsx").batch
    im.stage_rows(ctx, batch.id, [im.StagingInput(1, {"a": "1"})])
    im.validate_batch(ctx, batch.id)
    after = client.get(f"{T}{FRESHNESS}", **_who(src.code))
    oc.validate_response(FRESHNESS, "get", after)
    item = _json(after)["items"][0]
    assert item["freshness"] == "fresh" and item["last_success_at"].endswith("Z")
    assert before["ETag"] != after["ETag"]


# ------------------------------------------------------------------------------------------- conflicts
@pytest.mark.django_db
@pytest.mark.urls("platform_core.tests.api_harness")
def test_conflict_list_scope_and_filters(client: Client) -> None:
    mine, other = factories.integration_source(), factories.integration_source()
    c1, c2 = _conflict(mine, "k1"), _conflict(mine, "k2")
    _conflict(other, "k3")
    cf.resolve_conflict(
        RequestContext(Actor.user(uuid.uuid4())),
        ConflictItem.objects.all(),
        c2.conflict_id,
        expected_version=c2.row_version,
        outcome="DISMISSED",
        note="synthetic",
    )
    r = client.get(f"{T}{CONFLICTS}", **_who(mine.code))
    oc.validate_response(CONFLICTS, "get", r)
    assert [i["conflict_id"] for i in _json(r)["items"]] == [str(c1.conflict_id), str(c2.conflict_id)]
    r = client.get(f"{T}{CONFLICTS}", {"status": "OPEN", "source_code": mine.code}, **_who(mine.code))
    oc.validate_response(CONFLICTS, "get", r)
    assert [i["conflict_id"] for i in _json(r)["items"]] == [str(c1.conflict_id)]
    r = client.get(f"{T}{CONFLICTS}", {"source_code": other.code}, **_who(mine.code))
    assert _json(r)["items"] == []  # filter cannot widen the scope
    for bad in ({"status": "open"}, {"source_code": "Bad-Code"}):
        r = client.get(f"{T}{CONFLICTS}", bad, **_who(mine.code))
        assert r.status_code == 400
        oc.validate_response(CONFLICTS, "get", r)


@pytest.mark.django_db
@pytest.mark.urls("platform_core.tests.api_harness")
def test_conflict_detail_etag_and_out_of_scope_404(client: Client) -> None:
    mine, other = factories.integration_source(), factories.integration_source()
    item = _conflict(mine)
    r = client.get(f"{T}/integration/conflicts/{item.conflict_id}", **_who(mine.code))
    assert r.status_code == 200 and r["ETag"] == f'"{item.row_version}"'
    oc.validate_response(CONFLICT, "get", r)
    assert _json(r)["details"] == {"cell": "A1"}
    for who in (_who(other.code), _who("")):
        r = client.get(f"{T}/integration/conflicts/{item.conflict_id}", **who)
        assert r.status_code == 404
        oc.validate_response(CONFLICT, "get", r)
    r = client.get(f"{T}/integration/conflicts/{uuid.uuid4()}", **_who(mine.code))
    assert r.status_code == 404


def _resolve(
    client: Client,
    item: ConflictItem,
    body: Any,
    *,
    who: dict[str, Any],
    key: str | None = None,
    if_match: str | None = None,
) -> Any:
    headers: dict[str, Any] = dict(who)
    if key is not None:
        headers["HTTP_IDEMPOTENCY_KEY"] = key
    if if_match is not None:
        headers["HTTP_IF_MATCH"] = if_match
    r = client.post(
        f"{T}/integration/conflicts/{item.conflict_id}/resolve",
        body,
        content_type="application/json",
        **headers,
    )
    oc.validate_response(RESOLVE, "post", r)
    return r


@pytest.mark.django_db(transaction=True)  # run_idempotent refuses an outer transaction
@pytest.mark.usefixtures("audit_cleanup")
@pytest.mark.urls("platform_core.tests.api_harness")
def test_resolve_flow_preconditions_replay_and_terminal(client: Client) -> None:
    src = factories.integration_source()
    item = _conflict(src)
    actor = uuid.uuid4()
    who = _who(src.code, actor=actor)
    etag = f'"{item.row_version}"'
    body = {"outcome": "RESOLVED", "note": "synthetic: tracker value kept"}
    assert _resolve(client, item, body, who=who, key=str(uuid.uuid4())).status_code == 428  # no If-Match
    r = _resolve(client, item, body, who=who, if_match=etag)
    assert r.status_code == 428 and _json(r)["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    r = _resolve(
        client, item, {"outcome": "APPLY", "note": "x"}, who=who, key=str(uuid.uuid4()), if_match=etag
    )
    assert r.status_code == 400 and _json(r)["errors"][0]["field"] == "outcome"
    r = _resolve(client, item, {**body, "extra": 1}, who=who, key=str(uuid.uuid4()), if_match=etag)
    assert r.status_code == 400 and _json(r)["errors"][0] == {"field": "extra", "code": "UNKNOWN_FIELD"}
    r = _resolve(client, item, body, who=who, key=str(uuid.uuid4()), if_match=f'"{item.row_version + 1}"')
    assert r.status_code == 412
    key = str(uuid.uuid4())
    ok = _resolve(client, item, body, who=who, key=key, if_match=etag)
    assert ok.status_code == 200 and ok["ETag"] == f'"{item.row_version + 1}"'
    assert _json(ok)["status"] == "RESOLVED" and _json(ok)["resolution_note"] == body["note"]
    replay = _resolve(client, item, body, who=who, key=key, if_match=etag)
    assert replay.status_code == 200 and replay["Idempotent-Replayed"] == "true"
    assert _json(replay) == _json(ok)
    reused = _resolve(client, item, {**body, "note": "different"}, who=who, key=key, if_match=etag)
    assert reused.status_code == 422
    again = _resolve(
        client,
        item,
        {"outcome": "DISMISSED", "note": "x"},
        who=who,
        key=str(uuid.uuid4()),
        if_match=ok["ETag"],
    )
    assert again.status_code == 409 and _json(again)["code"] == "STATE_TRANSITION_NOT_ALLOWED"
    item.refresh_from_db()
    assert (item.status, item.resolved_by) == ("RESOLVED", actor)
    assert AuditEvent.objects.filter(action="platform.integration.conflict.resolve").count() == 1
    assert OutboxEvent.objects.filter(event_type="platform.integration.conflict_resolved").count() == 1


@pytest.mark.django_db(transaction=True)  # run_idempotent refuses an outer transaction
@pytest.mark.usefixtures("audit_cleanup")
@pytest.mark.urls("platform_core.tests.api_harness")
def test_resolve_out_of_scope_is_404_and_writes_nothing(client: Client) -> None:
    mine, other = factories.integration_source(), factories.integration_source()
    item = _conflict(other)
    r = _resolve(
        client,
        item,
        {"outcome": "DISMISSED", "note": "x"},
        who=_who(mine.code),
        key=str(uuid.uuid4()),
        if_match=f'"{item.row_version}"',
    )
    assert r.status_code == 404
    item.refresh_from_db()
    assert item.status == "OPEN"
    assert not AuditEvent.objects.filter(action="platform.integration.conflict.resolve").exists()
