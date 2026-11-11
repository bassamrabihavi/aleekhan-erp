"""Rules for the PHASE_02 operations PLANNED in docs/api/openapi-draft.yaml 0.7.0-draft (step 02.1).

The operations are contract drafts for step 02.4 and are NOT routed (route parity in ``test_api_contract``
covers implemented paths only and asserts that no planned path is served). These tests pin what 02.4 may not
weaken:

* every PHASE_02 path (tags ``identity``/``commercial``) is planned for 02.4; every planned path is PHASE_02;
* every operation needs the session and a proposed ``identity.*``/``commercial.*`` permission (none public);
* mutations carry ``Idempotency-Key`` unless listed in ``side_effect_free_operations``; PATCH and actions on
  an existing resource carry ``If-Match``;
* blocked operations name an OPEN decision and declare 409; the key P0 guards (DEC-005 code issue/preview,
  DEC-006 serial allocation, DEC-059 change requests) are pinned;
* 14-digit codes are ``Code14`` strings; the serial number has no pattern while DEC-006 is open (no invented
  format);
* no PHASE_02 permission is seeded before DEC-057 (the seed equals the implemented operations only).
"""

from __future__ import annotations

import csv
import re
from typing import Any

import pytest

from platform_core.identity.models import Permission

from . import openapi_contract as oc

PHASE02_TAGS = {"identity", "commercial"}
PHASE02_STEP = "02.4"
PERMISSION = re.compile(r"^(identity|commercial)\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$")
DEC = re.compile(r"^DEC-[0-9]{3}$")
MUTATING = {"post", "put", "patch", "delete"}
SIDE_EFFECT_FREE = {"validateProductCode", "previewProductCode"}
# POST on these sub-collections creates a child resource (no If-Match on the parent required by the rules).
SUB_COLLECTIONS = {"brands", "styles", "revisions", "lines"}
# P0 guards of 02.1 (docs/discovery/decisions/*): the operation must stay blocked by at least these decisions.
REQUIRED_BLOCKS = {
    "issueProductCode": {"DEC-005"},
    "previewProductCode": {"DEC-005"},
    "createCodeRuleRevision": {"DEC-005"},
    "approveCodeRuleRevision": {"DEC-005"},
    "activateCodeRuleRevision": {"DEC-005"},
    "allocateSerial": {"DEC-006"},
    "confirmCustomerOrder": {"DEC-006"},
    "createChangeRequest": {"DEC-059"},
    "decideChangeRequest": {"DEC-059"},
    "applyChangeRequest": {"DEC-059"},
}


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


def test_phase02_paths_are_planned_for_02_4_and_only_phase02_is_planned() -> None:
    ops = phase02_operations()
    assert len(ops) >= 60
    phase02_paths = {p for p, _m, _op in ops}
    for path in phase02_paths:
        item = oc.spec()["paths"][path]
        assert oc.is_planned(path), path
        assert item["x-aleekhan-step"] == PHASE02_STEP, path
        assert path.startswith(("/identity/", "/commercial/")), path  # owning-module prefix (C-63)
    assert oc.planned_paths() == phase02_paths
    tags = {t["name"] for t in oc.spec()["tags"]}
    assert tags >= PHASE02_TAGS


def test_contract_conventions_name_the_phase02_rules() -> None:
    conv = oc.spec()["x-aleekhan-conventions"]
    assert set(conv["side_effect_free_operations"]["operations"]) == SIDE_EFFECT_FREE
    assert conv["planned_phase02"]["step"] == PHASE02_STEP
    assert set(conv["planned_phase02"]["tags"]) == PHASE02_TAGS
    assert set(conv["planned_error_codes"]) == {
        "SERIAL_ALREADY_ALLOCATED",
        "PRODUCT_CODE_TAKEN",
        "POSSIBLE_DUPLICATE",
        "ORDER_VERSION_STALE",
    }


def test_every_phase02_operation_needs_session_and_a_proposed_permission() -> None:
    schemes = set(oc.spec()["components"]["securitySchemes"])
    for path, method, op in phase02_operations():
        sec = op.get("security", oc.spec()["security"])
        assert sec and all(req and set(req) <= schemes for req in sec), (method, path)
        assert PERMISSION.match(op.get("x-aleekhan-permission", "")), op["operationId"]
        assert {"401", "403", "429"} <= set(op["responses"]), op["operationId"]
        if "{" in path:
            assert "404" in op["responses"], op["operationId"]  # out of scope = 404 (BOLA/IDOR)


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


def test_blocked_phase02_operations_name_open_decisions_and_declare_409() -> None:
    status = _decision_status()
    blocked: dict[str, set[str]] = {}
    for _path, _method, op in phase02_operations():
        decs = op.get("x-aleekhan-blocked-by")
        if decs is None:
            continue
        assert decs and all(DEC.match(d) for d in decs), op["operationId"]
        assert all(status.get(d) != "APPROVED" for d in decs), (op["operationId"], decs)
        assert "409" in op["responses"], op["operationId"]
        assert "RULE_NOT_APPROVED" in op["description"], op["operationId"]
        blocked[op["operationId"]] = set(decs)
    for op_id, required in REQUIRED_BLOCKS.items():
        assert required <= blocked.get(op_id, set()), op_id


def test_operations_sharing_a_phase02_permission_share_the_mfa_flag() -> None:
    flags: dict[str, set[bool]] = {}
    for _path, _method, op in phase02_operations():
        mfa = bool(op.get("x-aleekhan-mfa-step-up", False))
        flags.setdefault(op["x-aleekhan-permission"], set()).add(mfa)
    assert {p: f for p, f in flags.items() if len(f) > 1} == {}
    # business approvals need a fresh MFA (SECURITY_BASELINE: commercial approvals; DEC-049)
    for perm in (
        "identity.product_code.issue",
        "identity.code_rule.approve",
        "commercial.order.confirm",
        "commercial.change.decide",
    ):
        assert flags[perm] == {True}, perm


def _schema(name: str) -> dict[str, Any]:
    node: dict[str, Any] = oc.spec()["components"]["schemas"][name]
    return node


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
    """ID-01: every 14-digit code is the Code14 string type (leading zeros kept), never a number."""
    assert _refs_code14(_schema(schema)["properties"][prop]), (schema, prop)
    code14 = _schema("Code14")
    assert code14["type"] == "string" and code14["pattern"] == "^[0-9]{14}$"


def test_no_phase02_schema_types_a_code_or_serial_as_a_number() -> None:
    names = {n for _p, _m, op in phase02_operations() for n in _response_and_body_schemas(op)}
    suspicious = re.compile(r"(^|_)(code|serial_number|product_no|style_no|segment_value)$")
    for name in names:
        for prop_name, prop in _schema(name).get("properties", {}).items():
            if suspicious.search(prop_name):
                types = prop.get("type", "string")
                types = types if isinstance(types, list) else [types]
                assert "integer" not in types and "number" not in types, (name, prop_name)


def _response_and_body_schemas(op: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    nodes = [r for r in op["responses"].values() if "content" in r]
    body = op.get("requestBody")
    if body:
        nodes.append(body)
    for node in nodes:
        ref = node["content"]["application/json"]["schema"].get("$ref", "")
        if ref:
            out.add(ref.rsplit("/", 1)[-1])
    return out


def test_serial_number_has_no_invented_format_while_dec_006_is_open() -> None:
    assert _decision_status().get("DEC-006") != "APPROVED"
    serial_number = _schema("SerialNumber")
    assert serial_number["type"] == "string"
    assert "pattern" not in serial_number  # DEC-006: the format is not approved, nothing is invented
    assert "DEC-006" in serial_number["description"]


def test_product_code_segments_are_not_modelled_while_dec_005_is_open() -> None:
    assert _decision_status().get("DEC-005") != "APPROVED"
    for name, prop in (("ProductClass", "segment_value"), ("Product", "product_no"), ("Style", "style_no")):
        node = _schema(name)["properties"][prop]
        assert "null" in node["type"] and "DEC-005" in node["description"], (name, prop)
        assert prop in _schema(name)["required"]  # present and nullable, never defaulted to a guess


@pytest.mark.django_db
def test_no_planned_phase02_permission_is_seeded_before_dec_057() -> None:
    """The seeded catalogue (01.2/01.7 migrations) holds platform permissions only."""
    perms = {op["x-aleekhan-permission"] for _p, _m, op in phase02_operations()}
    assert _decision_status().get("DEC-057") != "APPROVED"
    assert not perms & set(Permission.objects.values_list("action", flat=True))
