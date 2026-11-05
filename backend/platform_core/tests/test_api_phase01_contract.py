"""01.4 contract parity of the PHASE_01 endpoints with docs/api/openapi-draft.yaml (0.6.0-draft).

* request-body specs (``api/phase01/common.BODIES``) == the OpenAPI request schemas (fields, required set,
  length/pattern/enum/nullable constraints; ``additionalProperties: false`` everywhere);
* every routed PHASE_01 operation: the view implements the method, uses the permission class of its security
  profile (public / session-only / scoped) and checks exactly the ``x-aleekhan-permission`` of the contract;
  the Idempotency-Key exemption of the view == ``x-aleekhan-conventions.idempotency_exempt``;
* the MFA step-up flag of every operation == the ``mfa_step_up`` flag of its permission in the seeded,
  APPROVED catalogue (the engine enforces the DB flag);
* real-session checks for EVERY mutating operation: missing Idempotency-Key -> 428, missing / weak /
  malformed If-Match -> 428 / 412 / 400 (where the contract declares If-Match);
* a role WITHOUT the permission gets 403 on every operation of that permission (matrix: employee).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest

from platform_core.api import permissions
from platform_core.api.phase01.common import BODIES, F
from platform_core.authz import policy as P
from platform_core.identity.models import Permission

from . import openapi_contract as oc
from .authz_urls import production_routes
from .phase01_api import code, session_client, superuser, with_roles
from .test_api_contract_planned import PHASE01_TAGS

MUTATING = {"post", "put", "patch", "delete"}
NESTED = {"EntityRef", "Scope", "Assignee", "TypedValue"}


def _resolve(node: dict[str, Any]) -> dict[str, Any]:
    return oc._resolve(dict(node))


def _phase01_ops() -> list[tuple[str, str, dict[str, Any]]]:
    return [(p, m, op) for p, m, op in oc.operations() if set(op["tags"]) & PHASE01_TAGS]


def _body_schema_names() -> set[str]:
    names = set(NESTED)
    for _p, _m, op in _phase01_ops():
        content = op.get("requestBody", {}).get("content", {})
        ref = content.get("application/json", {}).get("schema", {}).get("$ref")
        if ref:
            names.add(ref.rsplit("/", 1)[-1])
    return names


def _check_field(name: str, prop: str, spec: F, schema: dict[str, Any]) -> None:
    where = f"{name}.{prop}"
    one_of_null = False
    if "oneOf" in schema:  # oneOf: [<ref>, {type: null}]
        options = [_resolve(x) for x in schema["oneOf"]]
        one_of_null = any(o.get("type") == "null" for o in options)
        schema = next(o for o in options if o.get("type") != "null")
    schema = _resolve(schema)
    types = schema.get("type")
    nullable = one_of_null or (isinstance(types, list) and "null" in types)
    assert spec.nullable == nullable, where
    base = next(t for t in types if t != "null") if isinstance(types, list) else types
    if spec.kind == "obj":
        assert base == "object" or "properties" in schema, where
        return
    if spec.kind == "scalar":
        return
    expected_kind = {
        "string": {"str", "uuid", "ts"},
        "boolean": {"bool"},
        "integer": {"int"},
        "array": {"strlist"},
    }
    assert spec.kind in expected_kind[str(base)], (where, spec.kind, base)
    if spec.kind == "uuid":
        assert schema.get("format") == "uuid", where
    if spec.kind == "ts":
        assert schema.get("format") == "date-time", where
    if spec.kind == "str":
        assert spec.max_len == schema.get("maxLength"), where
        assert spec.min_len == schema.get("minLength", 0), where
        assert spec.pattern == schema.get("pattern"), where
        enum = tuple(x for x in schema.get("enum", ()) if x is not None)
        assert spec.choices == enum, where
    if spec.kind == "int":
        assert spec.minimum == schema.get("minimum") and spec.maximum == schema.get("maximum"), where
    if spec.kind == "strlist":
        items = _resolve(schema["items"])
        assert spec.max_items == schema.get("maxItems"), where
        assert spec.item_pattern == items.get("pattern") and spec.item_max_len == items.get("maxLength"), (
            where
        )


def test_request_body_specs_equal_the_openapi_request_schemas() -> None:
    names = _body_schema_names()
    assert names <= set(BODIES), sorted(names - set(BODIES))
    for name in sorted(names):
        schema = oc.spec()["components"]["schemas"][name]
        assert schema.get("additionalProperties") is False, name
        props = schema["properties"]
        assert set(BODIES[name]) == set(props), (name, sorted(set(BODIES[name]) ^ set(props)))
        required = set(schema.get("required", []))
        assert {k for k, f in BODIES[name].items() if f.required} == required, name
        for prop, spec in BODIES[name].items():
            _check_field(name, prop, spec, props[prop])


def _template(route: str) -> str:
    return re.sub(r"<(?:[a-z]+:)?([a-z_]+)>", lambda m: "{" + m.group(1) + "}", route)


def _routed() -> dict[str, Any]:
    return {_template(route).removeprefix("api/v1"): view for route, view in production_routes()}


def test_every_phase01_operation_is_routed_with_its_contract_permission() -> None:
    routed = _routed()
    exempt = set(oc.spec()["x-aleekhan-conventions"]["idempotency_exempt"]["operations"])
    checked = 0
    for path, method, op in _phase01_ops():
        view = routed["/" + path.lstrip("/")] if not path.startswith("/") else routed[path]
        assert hasattr(view, method), (method, path)
        perms = set(view.permission_classes)
        op_id = op["operationId"]
        perm = op.get("x-aleekhan-permission")
        if op.get("security") == []:
            assert perms == {permissions.PublicEndpoint}, op_id
        elif perm is None:
            assert perms == {permissions.SessionOperation}, op_id
        else:
            assert perms == {permissions.ScopedPermission}, op_id
            unsafe = method in MUTATING
            action = view.write_action if unsafe and view.write_action else view.required_action
            assert action == perm, (op_id, action, perm)
        if method in MUTATING and op.get("security") != []:
            assert view.idempotent is (op_id not in exempt), op_id
        checked += 1
    assert checked == len(_phase01_ops()) >= 99


@pytest.mark.django_db
def test_mfa_step_up_flags_equal_the_approved_catalogue() -> None:
    flags = dict(Permission.objects.values_list("action", "mfa_step_up"))
    for _path, _method, op in _phase01_ops():
        perm = op.get("x-aleekhan-permission")
        if perm is None:
            continue
        assert perm in flags, perm
        assert bool(op.get("x-aleekhan-mfa-step-up", False)) == flags[perm], op["operationId"]


# ------------------------------------------------------------------------- real-session preconditions
SAMPLE = {"session_id": str(uuid.uuid4()), "parameter_key": "syn_param_key", "field_key": "syn_field_key"}


def _url(path: str) -> str:
    def sub(m: re.Match[str]) -> str:
        return SAMPLE.get(m.group(1), str(uuid.uuid4()))

    return oc.BASE_PATH + re.sub(r"\{([a-z_]+)\}", sub, path)


def _param_refs(path: str, op: dict[str, Any]) -> set[str]:
    item = oc.spec()["paths"][path]
    return {
        p.get("$ref", "").rsplit("/", 1)[-1] for p in item.get("parameters", []) + op.get("parameters", [])
    }


EXEMPT = set(oc.spec()["x-aleekhan-conventions"]["idempotency_exempt"]["operations"])
WRITES = [
    (p, m, op)
    for p, m, op in _phase01_ops()
    if m in MUTATING and op.get("security") != [] and op["operationId"] not in EXEMPT
]
IF_MATCH_WRITES = [w for w in WRITES if "IfMatch" in _param_refs(w[0], w[2])]


def _call(c: Any, method: str, url: str, **headers: Any) -> Any:
    return getattr(c, method)(url, "{}", content_type="application/json", **headers)


@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache")
@pytest.mark.parametrize(("path", "method", "op"), WRITES, ids=[w[2]["operationId"] for w in WRITES])
def test_every_write_requires_an_idempotency_key(path: str, method: str, op: dict[str, Any]) -> None:
    c = session_client(superuser())
    r = _call(c, method, _url(path))
    assert r.status_code == 428 and code(r) == "IDEMPOTENCY_KEY_REQUIRED", (op["operationId"], r.content)
    oc.validate_response(path, method, r)
    r = _call(c, method, _url(path), HTTP_IDEMPOTENCY_KEY="not-a-uuid")
    assert r.status_code == 400 and code(r) == "VALIDATION_FAILED", op["operationId"]


@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache")
@pytest.mark.parametrize(
    ("path", "method", "op"), IF_MATCH_WRITES, ids=[w[2]["operationId"] for w in IF_MATCH_WRITES]
)
def test_every_versioned_write_requires_if_match(path: str, method: str, op: dict[str, Any]) -> None:
    c = session_client(superuser())
    key = {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}
    r = _call(c, method, _url(path), **key)
    assert r.status_code == 428 and code(r) == "PRECONDITION_REQUIRED", (op["operationId"], r.content)
    oc.validate_response(path, method, r)
    r = _call(c, method, _url(path), HTTP_IF_MATCH='W/"1"', **key)
    assert r.status_code == 412 and code(r) == "VERSION_CONFLICT", op["operationId"]
    oc.validate_response(path, method, r)
    r = _call(c, method, _url(path), HTTP_IF_MATCH="garbage", **key)
    assert r.status_code == 400 and code(r) == "VALIDATION_FAILED", op["operationId"]


def _employee_lacks(perm: str) -> bool:
    from importlib import import_module

    seed = import_module("platform_core.migrations.0010_seed_phase01_catalogue")
    return "employee" not in seed.GRANTS.get(perm, {})


DENIED = [
    (p, m, op)
    for p, m, op in _phase01_ops()
    if op.get("x-aleekhan-permission") and _employee_lacks(op["x-aleekhan-permission"])
]


@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache")
@pytest.mark.parametrize(("path", "method", "op"), DENIED, ids=[d[2]["operationId"] for d in DENIED])
def test_a_role_without_the_permission_is_refused_403(path: str, method: str, op: dict[str, Any]) -> None:
    """Gate: «منع دسترسی نقش نامجاز» - employee (matrix v1.0) on every operation it holds no grant for."""
    u = with_roles("employee")
    assert not P.can(P.Caller(u.pk), op["x-aleekhan-permission"])
    c = session_client(u)
    r = (
        c.get(_url(path), {"occurred_from": "2026-01-01T00:00:00Z", "occurred_to": "2026-12-31T00:00:00Z"})
        if method == "get"
        else _call(c, method, _url(path), HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()), HTTP_IF_MATCH='"1"')
    )
    assert r.status_code == 403 and code(r) == "ACCESS_DENIED", (op["operationId"], r.status_code)
    oc.validate_response(path, method, r)
