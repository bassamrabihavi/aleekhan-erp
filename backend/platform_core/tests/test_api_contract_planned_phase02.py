"""Rules for the PHASE_02 operations PLANNED in docs/api/openapi-draft.yaml 0.7.0-draft (step 02.1).

The operations are contract drafts for step 02.4 and are NOT routed (route parity in ``test_api_contract``
covers implemented paths only and asserts that no planned path is served). These tests pin what 02.4 may not
weaken:

* every PHASE_02 path (tags ``identity``/``commercial``) is planned for 02.4; every planned path is PHASE_02;
* every operation needs the session and a proposed ``identity.*``/``commercial.*`` permission (none public);
* mutations carry ``Idempotency-Key`` unless listed in ``side_effect_free_operations``; PATCH and actions on
  an existing resource carry ``If-Match``;
* blocked operations name decisions that EXIST in the decision register (REV-0202: a typo or an unknown id
  such
  as DEC-999 fails) and declare 409; a marker may name an APPROVED decision only if it is one of the
  markers the
  02.4 contract update owes (DEC-005/006/057/059 were approved on 2026-11-12, after the 0.7.0-draft contract;
  the API step lifts them together with the routed operations); the key P0 guards stay pinned until then;
* 14-digit codes are ``Code14`` strings; the serial number is text of the DB width (a contract pattern, when
  02.4 adds it, must equal the DB pattern of DEC-006);
* the PHASE_02 permissions seeded by migration 0022 (DEC-057, matrix v2.0) equal the planned operations'
  permissions and MFA flags exactly.
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
    """Latest decided status per id (DECISION_LOG.csv holds decided entries only; later rows win)."""
    log = oc.REPO_ROOT / "control" / "decisions" / "DECISION_LOG.csv"
    with log.open(encoding="utf-8", newline="") as fh:
        return {row["decision_id"]: row["status"] for row in csv.DictReader(fh)}


def _registered_decisions() -> set[str]:
    """Every decision id that exists (REV-0202): the handoff register, the addendum and the decided log."""
    ids: set[str] = set()
    for path in (
        oc.REPO_ROOT / "handoff" / "11_PROJECT_MANAGEMENT" / "DECISION_REGISTER.csv",
        oc.REPO_ROOT / "control" / "decisions" / "DECISIONS_ADDENDUM.csv",
        oc.REPO_ROOT / "control" / "decisions" / "DECISION_LOG.csv",
    ):
        with path.open(encoding="utf-8-sig", newline="") as fh:
            ids |= {row["decision_id"].strip() for row in csv.DictReader(fh)}
    return ids


# Approved on 2026-11-12 (DECISION_LOG.md) after the 0.7.0-draft contract was written; the markers are
# removed by
# the 02.4 contract update together with the routed operations. No other APPROVED decision may be named.
APPROVED_MARKERS_OWED_TO_02_4 = frozenset({"DEC-005", "DEC-006", "DEC-057", "DEC-059"})


def blocked_marker_problems(op_id: str, decisions: list[str]) -> list[str]:
    registered, status = _registered_decisions(), _decision_status()
    problems = []
    if not decisions:
        problems.append(f"{op_id}: empty x-aleekhan-blocked-by")
    for d in decisions:
        if not DEC.match(d):
            problems.append(f"{op_id}: {d!r} is not a decision id")
        elif d not in registered:
            problems.append(f"{op_id}: {d} does not exist in the decision register")
        elif status.get(d) == "APPROVED" and d not in APPROVED_MARKERS_OWED_TO_02_4:
            problems.append(f"{op_id}: {d} is APPROVED, the marker must go")
    return problems


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


def test_blocked_phase02_operations_name_registered_decisions_and_declare_409() -> None:
    blocked: dict[str, set[str]] = {}
    for _path, _method, op in phase02_operations():
        decs = op.get("x-aleekhan-blocked-by")
        if decs is None:
            continue
        assert blocked_marker_problems(op["operationId"], decs) == []
        assert "409" in op["responses"], op["operationId"]
        assert "RULE_NOT_APPROVED" in op["description"], op["operationId"]
        blocked[op["operationId"]] = set(decs)
    for op_id, required in REQUIRED_BLOCKS.items():
        assert required <= blocked.get(op_id, set()), op_id


def test_rev0202_unknown_or_mistyped_decision_ids_are_reported() -> None:
    """Regression REV-0202: the old check accepted any id that was simply absent from the decided log."""
    assert blocked_marker_problems("syn", ["DEC-999"]) == [
        "syn: DEC-999 does not exist in the decision register"
    ]
    assert blocked_marker_problems("syn", ["DEC-5"]) == ["syn: 'DEC-5' is not a decision id"]
    assert blocked_marker_problems("syn", []) == ["syn: empty x-aleekhan-blocked-by"]
    assert blocked_marker_problems("syn", ["DEC-049"]) == ["syn: DEC-049 is APPROVED, the marker must go"]
    assert blocked_marker_problems("syn", ["DEC-005"]) == []  # owed to the 02.4 contract update


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


def test_serial_number_is_text_of_the_db_width_and_any_contract_pattern_equals_dec_006() -> None:
    """DEC-006 (APPROVED 2026-11-12): plain integer text from 63001; the DB enforces it (0019/0021)."""
    from platform_core.product_identity.models import SERIAL_NUMBER_PATTERN

    assert _decision_status().get("DEC-006") == "APPROVED"
    serial_number = _schema("SerialNumber")
    assert serial_number["type"] == "string" and serial_number["maxLength"] == 32  # = varchar(32)
    assert serial_number.get("pattern", SERIAL_NUMBER_PATTERN) == SERIAL_NUMBER_PATTERN
    assert SERIAL_NUMBER_PATTERN == r"^[1-9][0-9]*$"


def test_product_code_segments_are_text_in_the_contract_and_fixed_width_in_the_db() -> None:
    """DEC-005 (APPROVED 2026-11-12): segments are DB columns with fixed-width digit CHECKs (migration 0019);
    the contract keeps them as nullable strings (never numbers) until the 02.4 update."""
    from platform_core.product_identity.models import FOUR_DIGITS, TWO_DIGITS, Product, ProductClass, Style

    assert _decision_status().get("DEC-005") == "APPROVED"
    for name, prop in (("ProductClass", "segment_value"), ("Product", "product_no"), ("Style", "style_no")):
        node = _schema(name)["properties"][prop]
        assert "string" in node["type"] and "integer" not in node["type"], (name, prop)
        assert prop in _schema(name)["required"]
    names = {c.name for model in (ProductClass, Product, Style) for c in model._meta.constraints}
    assert {
        "ck_identity_class_segment_fmt",
        "ck_identity_product_no_fmt",
        "ck_identity_style_no_fmt",
    } <= names
    assert (TWO_DIGITS, FOUR_DIGITS) == (r"^[0-9]{2}$", r"^[0-9]{4}$")


@pytest.mark.django_db
def test_seeded_phase02_permissions_equal_the_planned_operations_and_mfa_flags() -> None:
    """DEC-057 (APPROVED 2026-11-12, matrix v2.0, migration 0022): exactly the planned permissions, same
    MFA."""
    planned: dict[str, set[bool]] = {}
    for _p, _m, op in phase02_operations():
        planned.setdefault(op["x-aleekhan-permission"], set()).add(
            bool(op.get("x-aleekhan-mfa-step-up", False))
        )
    seeded = {
        p.action: p.mfa_step_up for p in Permission.objects.filter(action__regex=r"^(identity|commercial)[.]")
    }
    assert _decision_status().get("DEC-057") == "APPROVED"
    assert {a: {m} for a, m in seeded.items()} == planned
    assert len(seeded) == 22
