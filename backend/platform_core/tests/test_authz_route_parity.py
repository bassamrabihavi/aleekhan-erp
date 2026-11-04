"""Deny-by-default on EVERY /api/v1 route, discovered automatically from the production URLconf (00.7).

For each production route and each HTTP method (GET/POST/PUT/PATCH/DELETE):

* anonymous caller -> 401 ``AUTHENTICATION_REQUIRED`` (problem+json), for every non-public route;
* authenticated SYNTHETIC principal that even *claims* the view's action (``X-Test-Actions``) and a record
  scope -> 403 ``ACCESS_DENIED``: the production policy (``DenyAllPolicy``) grants nothing in PHASE_00;
* the only exception is the access-gate *decision* endpoint (``AuthenticatedPrincipal``): an authenticated
  GET returns ``decision = DENY`` (never ``ALLOW``), other methods are refused;
* public probes (``PublicEndpoint``, allowlisted in ``PUBLIC_OPERATIONS``) refuse every write method (405).

A new route is covered without editing this file; a new permission class makes
``test_every_route_has_a_known_permission_profile`` fail until its expected outcome is defined here.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from django.test import Client

from platform_core.api import permissions

from .authz_urls import production_routes

pytestmark = [pytest.mark.usefixtures("clear_cache"), pytest.mark.django_db]

METHODS = ("get", "post", "put", "patch", "delete")
PUBLIC = "public"
DECISION_ONLY = "decision_only"
CLOSED = "closed"
PROFILES = {
    frozenset({permissions.PublicEndpoint}): PUBLIC,
    frozenset({permissions.AuthenticatedPrincipal}): DECISION_ONLY,
    frozenset({permissions.ScopedPermission}): CLOSED,
    frozenset({permissions.DenyByDefault}): CLOSED,
}
SAMPLE_UUID = "00000000-0000-4000-8000-00000000a0a0"  # synthetic


def _url(route: str) -> str:
    out = route
    while "<" in out:
        start, end = out.index("<"), out.index(">")
        out = out[:start] + SAMPLE_UUID + out[end + 1 :]
    return "/" + out


def _profile(view_cls: Any) -> str:
    perms = frozenset(view_cls.permission_classes)
    return PROFILES.get(perms, f"UNKNOWN:{sorted(p.__name__ for p in perms)}")


ROUTES = production_routes()
CASES = [(route, view_cls, m) for route, view_cls in ROUTES for m in METHODS]
CLOSED_CASES = [c for c in CASES if _profile(c[1]) != PUBLIC]


def _call(client: Client, method: str, url: str, **headers: Any) -> Any:
    if method == "get":
        return client.get(url, {"action": "a.b"}, **headers)
    return getattr(client, method)(url, "{}", content_type="application/json", **headers)


def _code(resp: Any) -> str | None:
    if resp.get("Content-Type") != "application/problem+json":
        return None
    body: dict[str, Any] = json.loads(resp.content.decode("utf-8"))
    return body.get("code")


def test_routes_were_discovered() -> None:
    assert len(ROUTES) >= 8  # PHASE_00 has 8 routes; the list grows automatically
    assert all(route.startswith("api/v1/") for route, _ in ROUTES)


def test_every_route_has_a_known_permission_profile() -> None:
    unknown = {route: _profile(v) for route, v in ROUTES if _profile(v).startswith("UNKNOWN")}
    assert not unknown, f"define the expected deny behaviour for: {unknown}"


@pytest.mark.parametrize(("route", "view_cls", "method"), CASES, ids=[f"{m}:{r}" for r, _, m in CASES])
def test_anonymous_is_denied_on_every_non_public_route(
    client: Client, route: str, view_cls: Any, method: str
) -> None:
    resp = _call(client, method, _url(route))
    if _profile(view_cls) == PUBLIC:
        allowed = {m for m in METHODS if hasattr(view_cls, m)}
        assert resp.status_code in ({200, 503} if method in allowed else {405}), (route, method)
        return
    assert resp.status_code == 401, (route, method, resp.status_code)
    assert _code(resp) == "AUTHENTICATION_REQUIRED"


@pytest.mark.urls("platform_core.tests.authz_urls")
@pytest.mark.parametrize(
    ("route", "view_cls", "method"), CLOSED_CASES, ids=[f"{m}:{r}" for r, _, m in CLOSED_CASES]
)
def test_authenticated_without_permission_is_denied_on_every_route(
    client: Client, route: str, view_cls: Any, method: str
) -> None:
    profile = _profile(view_cls)
    claimed = getattr(view_cls, "required_action", None) or "platform.synthetic.read"
    headers = {
        "HTTP_X_TEST_PRINCIPAL": str(uuid.uuid4()),
        "HTTP_X_TEST_ACTIONS": claimed,
        "HTTP_X_TEST_SCOPE": "synthetic_scope",
    }
    resp = _call(client, method, _url(route), **headers)
    if profile == DECISION_ONLY:
        if method == "get":
            assert resp.status_code == 200, resp.content
            assert json.loads(resp.content.decode("utf-8"))["decision"] == "DENY"
        else:
            assert resp.status_code == 405, (route, method)
        return
    assert resp.status_code == 403, (route, method, resp.status_code)
    assert _code(resp) == "ACCESS_DENIED"


def test_production_policy_is_deny_all() -> None:
    assert isinstance(permissions.ACCESS_POLICY, permissions.DenyAllPolicy)
