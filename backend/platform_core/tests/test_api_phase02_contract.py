"""02.4 contract parity of the PHASE_02 endpoints with docs/api/openapi-draft.yaml (0.8.0-draft).

Successor of ``test_api_contract_planned_phase02`` (02.1 planned rules): every PHASE_02 operation is now
IMPLEMENTED, so the rules pin what is served:

* no planned path is left; every PHASE_02 path is routed (route parity in ``test_api_contract``) under the
  owning module prefix; no blocked-by marker remains, decided-by names APPROVED decisions;
* session + ``identity.*``/``commercial.*`` permission on every operation (none public); mutations carry
  ``Idempotency-Key`` except the two side-effect free POSTs; PATCH and actions carry ``If-Match``;
* request-body specs (``api/phase02/bodies``) == the OpenAPI request schemas; every routed view checks exactly
  the contract permission; the seeded permission catalogue (matrix v2.1) == the operations' permissions and
  MFA flags; the refusal reasons of the contract == the engine catalogue;
* 14-digit codes are ``Code14`` strings, serial numbers have the DEC-006 pattern, technical numbers the
  DEC-058 amendment pattern (equal to the engine constants);
* real sessions on EVERY operation: missing Idempotency-Key 428, missing / weak / malformed If-Match
  428 / 412 / 400, a role without the permission 403 (employee: no PHASE_02 access; management_viewer: no
  write), each response validated against the contract.
"""

from __future__ import annotations

import csv
import re
import uuid
from typing import Any

import pytest

from platform_core.api import permissions
from platform_core.api.phase01.common import BODIES, F
from platform_core.api.phase02.bodies import PHASE02_BODIES
from platform_core.authz import policy as P
from platform_core.identity.models import Permission
from platform_core.product_identity.models import SERIAL_NUMBER_PATTERN
from platform_core.product_identity.refusals import REASON_CODE
from platform_core.product_identity.usecase import NUMBER_PATTERN

from . import openapi_contract as oc
from .authz_urls import production_routes
from .phase01_api import code, session_client, superuser, with_roles

PHASE02_TAGS = {"identity", "commercial"}
PERMISSION = re.compile(r"^(identity|commercial)\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$")
DEC = re.compile(r"^DEC-[0-9]{3}$")
MUTATING = {"post", "put", "patch", "delete"}
SIDE_EFFECT_FREE = {"validateProductCode", "previewProductCode"}
# POST on these sub-collections creates a child resource (no If-Match on the parent required by the rules).
SUB_COLLECTIONS = {"brands", "styles", "revisions", "lines", "golden-cases"}
ADDED_IN_02_4 = {"updateCustomerBrand", "addCodeRuleGoldenCases", "decidePlanningChangeRequest"}


def phase02_operations() -> list[tuple[str, str, dict[str, Any]]]:
    return [(p, m, op) for p, m, op in oc.operations() if set(op["tags"]) & PHASE02_TAGS]


def _param_refs(path: str, op: dict[str, Any]) -> set[str]:
    item = oc.spec()["paths"][path]
    refs = [p.get("$ref", "") for p in item.get("parameters", []) + op.get("parameters", [])]
    return {r.rsplit("/", 1)[-1] for r in refs}


def _decision_status() -> dict[str, str]:
    log = oc.REPO_ROOT / "control" / "decisions" / "DECISION_LOG.csv"
    with log.open(encoding="utf-8", newline="") as fh:
        return {row["decision_id"]: row["status"] for row in csv.DictReader(fh)}


def _schema(name: str) -> dict[str, Any]:
    node: dict[str, Any] = oc.spec()["components"]["schemas"][name]
    return node


# ---------------------------------------------------------------------------------------- static rules
def test_every_phase02_operation_is_implemented_and_nothing_is_planned() -> None:
    ops = phase02_operations()
    assert len(ops) == 66
    assert oc.planned_paths() == set()
    for path, _m, _op in ops:
        assert path.startswith(("/identity/", "/commercial/")), path  # owning-module prefix (C-63)
        assert "x-aleekhan-step" not in oc.spec()["paths"][path], path
    assert ADDED_IN_02_4 <= {op["operationId"] for _p, _m, op in ops}


def test_contract_conventions_name_the_phase02_rules() -> None:
    conv = oc.spec()["x-aleekhan-conventions"]
    assert set(conv["side_effect_free_operations"]["operations"]) == SIDE_EFFECT_FREE
    assert "planned_phase02" not in conv
    assert set(conv["implemented_phase02"]["tags"]) == PHASE02_TAGS
    assert conv["planned_error_codes"] == {}
    assert conv["phase02_refusal_reasons"] == {r.value: c.value for r, c in REASON_CODE.items()}


def test_every_phase02_operation_needs_session_and_a_decided_permission() -> None:
    schemes = set(oc.spec()["components"]["securitySchemes"])
    approved = {d for d, s in _decision_status().items() if s == "APPROVED"}
    for path, method, op in phase02_operations():
        sec = op.get("security", oc.spec()["security"])
        assert sec and all(req and set(req) <= schemes for req in sec), (method, path)
        assert PERMISSION.match(op.get("x-aleekhan-permission", "")), op["operationId"]
        assert {"401", "403", "429"} <= set(op["responses"]), op["operationId"]
        if "{" in path:
            assert "404" in op["responses"], op["operationId"]  # out of scope = 404 (BOLA/IDOR)
        assert "x-aleekhan-blocked-by" not in op, op["operationId"]  # DEC-005/006/057/059 APPROVED
        for d in op.get("x-aleekhan-decided-by", []):
            assert DEC.match(d) and d in approved, (op["operationId"], d)


def test_phase02_mutations_require_idempotency_and_if_match() -> None:
    for path, method, op in phase02_operations():
        op_id = op["operationId"]
        refs = _param_refs(path, op)
        if op_id in SIDE_EFFECT_FREE:
            assert method == "post" and "IdempotencyKey" not in refs, op_id
            continue
        if method not in MUTATING:
            assert "IdempotencyKey" not in refs, op_id
            continue
        assert "IdempotencyKey" in refs, op_id
        assert {"409", "422", "428"} <= set(op["responses"]), op_id
        last = path.rsplit("/", 1)[-1]
        is_action = (
            method == "post" and "{" in path and not last.startswith("{") and last not in SUB_COLLECTIONS
        )
        if method == "patch" or is_action:
            assert "IfMatch" in refs and "412" in op["responses"], op_id


def test_operations_sharing_a_phase02_permission_share_the_mfa_flag() -> None:
    flags: dict[str, set[bool]] = {}
    for _path, _method, op in phase02_operations():
        flags.setdefault(op["x-aleekhan-permission"], set()).add(
            bool(op.get("x-aleekhan-mfa-step-up", False))
        )
    assert {p: f for p, f in flags.items() if len(f) > 1} == {}
    for perm in (
        "identity.product_code.issue",
        "identity.code_rule.approve",
        "commercial.order.confirm",
        "commercial.change.decide",
        "commercial.change.planning_approve",
    ):
        assert flags[perm] == {True}, perm


def _refs_code14(prop: dict[str, Any]) -> bool:
    if prop.get("$ref") == "#/components/schemas/Code14":
        return True
    return any(alt.get("$ref") == "#/components/schemas/Code14" for alt in prop.get("oneOf", []))


@pytest.mark.parametrize(
    ("schema", "prop"),
    [
        ("ProductCode", "code"),
        ("ProductCodePreview", "code"),
        ("Serial", "product_code"),
        ("SerialSnapshotImage", "product_code"),
        ("CustomerOrderLine", "product_code"),
        ("HistoricalOrderRecord", "normalised_product_code"),
    ],
)
def test_14_digit_codes_are_code14_strings(schema: str, prop: str) -> None:
    assert _refs_code14(_schema(schema)["properties"][prop]), (schema, prop)
    code14 = _schema("Code14")
    assert code14["type"] == "string" and code14["pattern"] == "^[0-9]{14}$"


def _phase02_schema_names() -> set[str]:
    """Every component schema reachable from a PHASE_02 operation."""
    seen: set[str] = set()
    todo: list[Any] = [op for _p, _m, op in phase02_operations()]
    while todo:
        node = todo.pop()
        if isinstance(node, dict):
            ref = node.get("$ref", "")
            if ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[-1]
                if name not in seen:
                    seen.add(name)
                    todo.append(_schema(name))
            todo.extend(node.values())
        elif isinstance(node, list):
            todo.extend(node)
    return seen


def test_no_phase02_schema_types_a_code_serial_or_number_as_a_number() -> None:
    suspicious = re.compile(
        r"(^|_)(code|serial_number|product_no|style_no|segment_value|customer_no|order_no)$"
    )
    names = _phase02_schema_names()
    assert {"Customer", "CustomerOrder", "Serial", "ProductCode"} <= names
    for name in names:
        for prop_name, prop in _schema(name).get("properties", {}).items():
            if suspicious.search(prop_name):
                types = prop.get("type", "string")
                types = types if isinstance(types, list) else [types]
                assert "integer" not in types and "number" not in types, (name, prop_name)


def test_serial_number_and_technical_numbers_carry_the_decided_patterns() -> None:
    """DEC-006 (plain integer text from 63001) and the DEC-058 amendment of 2026-11-14 (Jalali year)."""
    serial_number = _schema("SerialNumber")
    assert serial_number["type"] == "string" and serial_number["maxLength"] == 32  # = varchar(32)
    assert serial_number["pattern"] == SERIAL_NUMBER_PATTERN == r"^[1-9][0-9]*$"
    assert _schema("TechnicalNumber")["pattern"] == NUMBER_PATTERN
    for schema, prop in (
        ("Customer", "customer_no"),
        ("CustomerOrder", "order_no"),
        ("ChangeRequest", "request_no"),
    ):
        assert _schema(schema)["properties"][prop]["$ref"] == "#/components/schemas/TechnicalNumber"
    for name, prop in (("ProductClass", "segment_value"), ("Product", "product_no"), ("Style", "style_no")):
        node = _schema(name)["properties"][prop]
        assert node["type"] == "string" and node["pattern"] in (r"^[0-9]{2}$", r"^[0-9]{4}$"), (name, prop)
    assert "PAUSED" not in _schema("CustomerOrderStatus")["enum"]
    assert "SERIAL_ALLOCATED" not in _schema("CustomerOrderLine")["properties"]["status"]["enum"]
    assert "category_id" in _schema("Style")["required"]
    assert "customer_representative_name" in _schema("CustomerOrder")["required"]


# ---------------------------------------------------------------------------------------- body parity
def _resolve(node: dict[str, Any]) -> dict[str, Any]:
    return oc._resolve(dict(node))


def _check_field(where: str, spec: F, schema: dict[str, Any]) -> None:
    one_of_null = False
    if "oneOf" in schema:
        options = [_resolve(x) for x in schema["oneOf"]]
        one_of_null = any(o.get("type") == "null" for o in options)
        schema = next(o for o in options if o.get("type") != "null")
    if "$ref" in schema and spec.kind == "obj":
        assert schema["$ref"].rsplit("/", 1)[-1] == spec.nested, where
        return
    schema = _resolve(schema)
    types = schema.get("type")
    assert spec.nullable == (one_of_null or (isinstance(types, list) and "null" in types)), where
    base = next(t for t in types if t != "null") if isinstance(types, list) else types
    kinds = {
        "string": {"str", "uuid", "date"},
        "boolean": {"bool"},
        "integer": {"int"},
        "array": {"strlist", "objlist"},
    }
    assert spec.kind in kinds[str(base)], (where, spec.kind, base)
    if spec.kind == "uuid":
        assert schema.get("format") == "uuid", where
    if spec.kind == "date":
        assert schema.get("format") == "date", where
    if spec.kind == "str":
        assert spec.max_len == schema.get("maxLength") and spec.min_len == schema.get("minLength", 0), where
        assert spec.pattern == schema.get("pattern"), where
        assert spec.choices == tuple(x for x in schema.get("enum", ()) if x is not None), where
    if spec.kind == "int":
        assert spec.minimum == schema.get("minimum") and spec.maximum == schema.get("maximum"), where
    if spec.kind in ("strlist", "objlist"):
        assert spec.max_items == schema.get("maxItems"), where
        assert spec.min_items == schema.get("minItems", 0), where
        items = schema["items"]
        if spec.kind == "objlist":
            assert items["$ref"].rsplit("/", 1)[-1] == spec.nested, where
        else:
            assert spec.item_pattern == items.get("pattern") and spec.item_max_len == items.get(
                "maxLength"
            ), where


def _phase02_body_names() -> set[str]:
    names: set[str] = set()
    for _p, _m, op in phase02_operations():
        ref = (
            op.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )
        if ref:
            names.add(ref.rsplit("/", 1)[-1])
    return names


def test_request_body_specs_equal_the_openapi_request_schemas() -> None:
    names = _phase02_body_names() | {"StyleAttributes", "GoldenCase", "GoldenCaseInputs", "ChangeRequestItem"}
    assert names <= set(BODIES), sorted(names - set(BODIES))
    assert set(PHASE02_BODIES) <= names | {"StyleAttributes"}, sorted(set(PHASE02_BODIES) - names)
    for name in sorted(names):
        schema = _schema(name)
        assert schema.get("additionalProperties") is False, name
        props = schema["properties"]
        assert set(BODIES[name]) == set(props), (name, sorted(set(BODIES[name]) ^ set(props)))
        assert {k for k, f in BODIES[name].items() if f.required} == set(schema.get("required", [])), name
        for prop, spec in BODIES[name].items():
            _check_field(f"{name}.{prop}", spec, props[prop])


def _template(route: str) -> str:
    return re.sub(r"<(?:[a-z]+:)?([a-z_]+)>", lambda m: "{" + m.group(1) + "}", route)


def test_every_phase02_operation_is_routed_with_its_contract_permission() -> None:
    routed = {_template(route).removeprefix("api/v1"): view for route, view in production_routes()}
    for path, method, op in phase02_operations():
        view = routed[path]
        assert hasattr(view, method), (method, path)
        assert set(view.permission_classes) == {permissions.ScopedPermission}, op["operationId"]
        unsafe = method in MUTATING
        action = view.write_action if unsafe and view.write_action else view.required_action
        assert action == op["x-aleekhan-permission"], (op["operationId"], action)
        if unsafe:
            assert view.idempotent is (op["operationId"] not in SIDE_EFFECT_FREE), op["operationId"]


@pytest.mark.django_db
def test_seeded_phase02_permissions_equal_the_operations_and_mfa_flags() -> None:
    """DEC-057 (matrix v2.0, 0022) + amendment (v2.1, 0024): exactly the operations' permissions, same MFA."""
    operations: dict[str, set[bool]] = {}
    for _p, _m, op in phase02_operations():
        operations.setdefault(op["x-aleekhan-permission"], set()).add(
            bool(op.get("x-aleekhan-mfa-step-up", False))
        )
    seeded = {
        p.action: p.mfa_step_up for p in Permission.objects.filter(action__regex=r"^(identity|commercial)[.]")
    }
    assert {a: {m} for a, m in seeded.items()} == operations
    assert len(seeded) == 23


# ------------------------------------------------------------------------- real-session preconditions
def _url(path: str) -> str:
    def sub(m: re.Match[str]) -> str:
        return "1" if m.group(1) == "order_version" else str(uuid.uuid4())

    return oc.BASE_PATH + re.sub(r"\{([a-z_]+)\}", sub, path)


def _call(c: Any, method: str, url: str, **headers: Any) -> Any:
    return getattr(c, method)(url, "{}", content_type="application/json", **headers)


WRITES = [
    (p, m, op)
    for p, m, op in phase02_operations()
    if m in MUTATING and op["operationId"] not in SIDE_EFFECT_FREE
]
IF_MATCH_WRITES = [w for w in WRITES if "IfMatch" in _param_refs(w[0], w[2])]


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


ALL_OPS = phase02_operations()
VIEWER_WRITES = [
    (p, m, op) for p, m, op in ALL_OPS if m in MUTATING and op["operationId"] not in SIDE_EFFECT_FREE
]


def _probe(c: Any, path: str, method: str) -> Any:
    if method == "get":
        return c.get(_url(path), {"q": "x"} if "style-suggestions" in path else {})
    return _call(c, method, _url(path), HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()), HTTP_IF_MATCH='"1"')


@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache")
@pytest.mark.parametrize(("path", "method", "op"), ALL_OPS, ids=[o[2]["operationId"] for o in ALL_OPS])
def test_employee_has_no_phase02_access(path: str, method: str, op: dict[str, Any]) -> None:
    """DEC-057: ``employee`` holds no PHASE_02 permission -> 403 on every operation."""
    u = with_roles("employee")
    assert not P.can(P.Caller(u.pk), op["x-aleekhan-permission"])
    r = _probe(session_client(u), path, method)
    assert r.status_code == 403 and code(r) == "ACCESS_DENIED", (op["operationId"], r.status_code)
    oc.validate_response(path, method, r)


@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache")
@pytest.mark.parametrize(
    ("path", "method", "op"), VIEWER_WRITES, ids=[o[2]["operationId"] for o in VIEWER_WRITES]
)
def test_management_viewer_never_writes(path: str, method: str, op: dict[str, Any]) -> None:
    """DEC-057: ``management_viewer`` is read-only -> 403 on every PHASE_02 write."""
    r = _probe(session_client(with_roles("management_viewer")), path, method)
    assert r.status_code == 403 and code(r) == "ACCESS_DENIED", (op["operationId"], r.status_code)
    oc.validate_response(path, method, r)
