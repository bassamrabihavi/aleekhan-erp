"""OpenAPI contract tests (docs/api/openapi-draft.yaml is the contract; contract-first).

* the document is a valid OpenAPI 3.1 document;
* REV-0001: every operation except the allowlisted public probes declares security (top-level default or
  operation-level, never ``[]``); the public set in the spec equals ``permissions.PUBLIC_OPERATIONS``;
* route parity: the production URLconf serves exactly the paths of the spec under ``/api/v1`` and nothing
  from the test harness;
* every production view uses a permission from an explicit allowlist, and ``PublicEndpoint`` only on the
  public operations; no production view overrides the access policy;
* real responses of all phase-0 endpoints (success and error paths) validate against the declared schemas.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from django.test import Client, override_settings
from django.urls import URLPattern, URLResolver, get_resolver
from openapi_spec_validator import validate

from platform_core.api import permissions, views
from platform_core.api.base import AleekhanAPIView

from . import openapi_contract as oc

pytestmark = pytest.mark.usefixtures("clear_cache")


def test_openapi_document_is_valid_oas31() -> None:
    validate(oc.spec())
    assert oc.spec()["openapi"].startswith("3.1")


def test_contract_version_matches_code() -> None:
    assert oc.spec()["info"]["version"] == views.CONTRACT_VERSION


def _effective_security(op: dict[str, Any]) -> list[Any]:
    sec: list[Any] = op.get("security", oc.spec().get("security", []))
    return sec


def test_every_non_public_operation_declares_security() -> None:
    """REV-0001 regression test."""
    schemes = set(oc.spec()["components"]["securitySchemes"])
    assert oc.spec().get("security"), "top-level default security must be declared"
    public = set()
    for path, method, op in oc.operations():
        sec = _effective_security(op)
        if sec == []:
            public.add(op["operationId"])
            continue
        for requirement in sec:
            assert requirement, f"{method} {path}: empty security requirement object"
            assert set(requirement) <= schemes, f"{method} {path}: unknown scheme"
    assert public == set(permissions.PUBLIC_OPERATIONS)
    gate = oc.operation("/access-gate/check", "get")
    assert gate["security"] == [{"sessionCookie": []}]


def _walk(patterns: list[URLPattern | URLResolver], prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for p in patterns:
        if isinstance(p, URLResolver):
            out += _walk(list(p.url_patterns), prefix + str(p.pattern))
        else:
            out.append((prefix + str(p.pattern), p.callback))
    return out


def _production_routes() -> list[tuple[str, Any]]:
    return _walk(list(get_resolver("aleekhan.urls").url_patterns))


def _as_template(route: str) -> str:
    """Django ``<uuid:conflict_id>`` -> OpenAPI ``{conflict_id}``."""
    return re.sub(r"<(?:[a-z]+:)?([a-z_]+)>", lambda m: "{" + m.group(1) + "}", route)


def test_route_parity_with_openapi() -> None:
    routes = {_as_template(path) for path, _ in _production_routes()}
    spec_paths = {"api/v1" + p for p in oc.spec()["paths"]}
    assert routes == spec_paths


def test_no_test_harness_in_production_urlconf() -> None:
    for path, callback in _production_routes():
        view_cls = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
        assert view_cls is not None, path
        assert "tests" not in view_cls.__module__, (path, view_cls)
        assert "_test" not in path


ALLOWED_PERMISSIONS = {
    permissions.PublicEndpoint,
    permissions.AuthenticatedPrincipal,
    permissions.ScopedPermission,
    permissions.DenyByDefault,
}


def test_production_views_use_allowlisted_permissions_and_default_policy() -> None:
    op_ids = {"api/v1" + p: op["operationId"] for p, _m, op in oc.operations()}
    for raw_path, callback in _production_routes():
        path = _as_template(raw_path)
        view_cls = callback.view_class
        perms = set(view_cls.permission_classes)
        assert perms <= ALLOWED_PERMISSIONS, (path, perms)
        if permissions.PublicEndpoint in perms:
            assert op_ids[path] in permissions.PUBLIC_OPERATIONS, path
        assert getattr(view_cls, "access_policy", None) is None, path
        assert view_cls.authentication_classes == [], path  # no auth backend in PHASE_00
        assert issubclass(view_cls, AleekhanAPIView), path  # throttles before permissions
    assert isinstance(permissions.ACCESS_POLICY, permissions.DenyAllPolicy)


# ------------------------------------------------------------------------------------------- real responses
API = oc.BASE_PATH


@pytest.mark.django_db
def test_contract_health_live(client: Client) -> None:
    oc.validate_response("/health/live", "get", client.get(f"{API}/health/live"))


@pytest.mark.django_db
def test_contract_health_ready_200_and_503(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    r = client.get(f"{API}/health/ready")
    assert r.status_code == 200
    oc.validate_response("/health/ready", "get", r)
    monkeypatch.setattr(views, "_check_cache", lambda: "down")
    r = client.get(f"{API}/health/ready")
    assert r.status_code == 503
    oc.validate_response("/health/ready", "get", r)


def test_contract_version(client: Client) -> None:
    oc.validate_response("/version", "get", client.get(f"{API}/version"))


@override_settings(ALEEKHAN_ENV="prod", ALEEKHAN_BUILD_COMMIT="0123456789ab")
def test_contract_version_prod_environment_name(client: Client) -> None:
    oc.validate_response("/version", "get", client.get(f"{API}/version"))


def test_contract_access_gate_401(client: Client) -> None:
    r = client.get(f"{API}/access-gate/check", {"action": "warehouse.reservation.create"})
    assert r.status_code == 401
    oc.validate_response("/access-gate/check", "get", r)


@pytest.mark.urls("platform_core.tests.api_harness")
def test_contract_access_gate_200_deny_and_400_with_principal(client: Client) -> None:
    who: dict[str, Any] = {"HTTP_X_TEST_PRINCIPAL": str(uuid.uuid4())}
    r = client.get(f"{API}/_test/access-gate/check", {"action": "warehouse.reservation.create"}, **who)
    assert r.status_code == 200
    oc.validate_response("/access-gate/check", "get", r)
    r = client.get(f"{API}/_test/access-gate/check", {"action": "BAD"}, **who)
    assert r.status_code == 400
    oc.validate_response("/access-gate/check", "get", r)


@override_settings(ALEEKHAN_THROTTLE_RATES={"anon": "1/min", "principal": "1/min", "health": "1/min"})
@pytest.mark.parametrize("path", ["/health/live", "/version", "/access-gate/check"])
def test_contract_429(path: str) -> None:
    c = Client(REMOTE_ADDR="10.9.9.9")
    c.get(f"{API}{path}", {"action": "a.b"})
    r = c.get(f"{API}{path}", {"action": "a.b"})
    assert r.status_code == 429
    oc.validate_response(path, "get", r)


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/version"])
def test_contract_405_generic_problem(client: Client, path: str) -> None:
    r = client.delete(f"{API}{path}")
    assert r.status_code == 405
    oc.validate_response(path, "get", r)
