"""Rules for PLANNED operations in docs/api/openapi-draft.yaml (0.5.0-draft, PHASE_01 / 01.1).

Planned path items (``x-aleekhan-status: planned``) are contract drafts that a later step implements. They are
not routed (``test_route_parity_with_openapi``), but they must already respect the conventions so that the
implementing step cannot weaken them silently:

* every planned path names the implementing step;
* operation ids are unique across the whole document;
* every non-public planned operation declares a session security requirement and, outside the caller's own
  ``auth``/``me`` resources, an explicit permission (``x-aleekhan-permission``);
* every mutating planned operation requires ``Idempotency-Key`` unless it is an explicitly exempt
  authentication ceremony; every PATCH requires ``If-Match``;
* blocked operations name an OPEN decision id and declare the 409 answer (``RULE_NOT_APPROVED``); operations
  whose decision was approved carry ``x-aleekhan-decided-by`` instead (01.2);
* operations sharing one permission share its MFA step-up flag (REV-0101);
* planned error codes are not yet in the implemented ``ErrorCode`` enum (they join it with the engine change).
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from typing import Any

from . import openapi_contract as oc
from .test_api_contract import PLANNED_PUBLIC_OPERATIONS

STEP = re.compile(r"^(0[0-9]|1[0-4])\.[1-8]$")
DEC = re.compile(r"^DEC-[0-9]{3}$")
PERMISSION = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$")
MUTATING = {"post", "put", "patch", "delete"}
SESSION_ONLY_TAGS = {"auth", "me"}


def _conventions() -> dict[str, Any]:
    conv: dict[str, Any] = oc.spec()["x-aleekhan-conventions"]
    return conv


def _param_refs(path: str, op: dict[str, Any]) -> set[str]:
    item = oc.spec()["paths"][path]
    refs = [p.get("$ref", "") for p in item.get("parameters", []) + op.get("parameters", [])]
    return {r.rsplit("/", 1)[-1] for r in refs}


def test_there_are_planned_paths_and_each_names_its_step() -> None:
    planned = oc.planned_paths()
    assert planned, "0.5.0-draft must contain the PHASE_01 planned operations"
    for path in planned:
        step = oc.spec()["paths"][path].get("x-aleekhan-step")
        assert isinstance(step, str) and STEP.match(step), path


def test_operation_ids_are_unique() -> None:
    counts = Counter(op["operationId"] for _p, _m, op in oc.operations())
    assert [k for k, n in counts.items() if n > 1] == []


def test_planned_operations_require_session_and_permission() -> None:
    schemes = set(oc.spec()["components"]["securitySchemes"])
    for path, method, op in oc.operations(planned=True):
        op_id = op["operationId"]
        sec = op.get("security", oc.spec()["security"])
        if op_id in PLANNED_PUBLIC_OPERATIONS:
            assert sec == [], op_id
            assert "x-aleekhan-mfa-step-up" not in op, op_id
            continue
        assert sec and all(req and set(req) <= schemes for req in sec), (method, path)
        perm = op.get("x-aleekhan-permission")
        if set(op["tags"]) <= SESSION_ONLY_TAGS:
            assert perm is None or PERMISSION.match(perm), op_id
        else:
            assert isinstance(perm, str) and PERMISSION.match(perm), op_id
        assert "401" in op["responses"] and "403" in op["responses"], op_id


def test_planned_public_operations_match_conventions() -> None:
    assert set(_conventions()["planned_public_operations"]) == PLANNED_PUBLIC_OPERATIONS


def test_planned_mutations_require_idempotency_key_unless_exempt() -> None:
    exempt = set(_conventions()["idempotency_exempt"]["operations"])
    planned_ids = {op["operationId"] for _p, _m, op in oc.operations(planned=True)}
    assert exempt <= planned_ids
    for path, method, op in oc.operations(planned=True):
        if method not in MUTATING:
            continue
        refs = _param_refs(path, op)
        if op["operationId"] in exempt:
            assert "IdempotencyKey" not in refs, op["operationId"]
        else:
            assert "IdempotencyKey" in refs, op["operationId"]
            assert "428" in op["responses"] and "422" in op["responses"], op["operationId"]
        if method == "patch":
            assert "IfMatch" in refs and "412" in op["responses"], op["operationId"]


def _decision_status() -> dict[str, str]:
    """decision_id -> status from the governance log (read-only; control/ is the source of truth)."""
    log = oc.REPO_ROOT / "control" / "decisions" / "DECISION_LOG.csv"
    with log.open(encoding="utf-8", newline="") as fh:
        return {row["decision_id"]: row["status"] for row in csv.DictReader(fh)}


def test_blocked_operations_name_an_open_decision_and_declare_409() -> None:
    """Blocked-by stays honest (01.2): an APPROVED decision no longer blocks; decided-by keeps the trace."""
    status = _decision_status()
    for _path, _method, op in oc.operations(planned=True):
        blocked = op.get("x-aleekhan-blocked-by")
        if blocked is not None:
            assert blocked and all(DEC.match(d) for d in blocked), op["operationId"]
            assert all(status.get(d) != "APPROVED" for d in blocked), (op["operationId"], blocked)
            assert "409" in op["responses"], op["operationId"]
        decided = op.get("x-aleekhan-decided-by")
        if decided is not None:
            assert decided and all(status.get(d) == "APPROVED" for d in decided), (op["operationId"], decided)
            assert blocked is None, op["operationId"]


def test_operations_sharing_a_permission_share_the_mfa_step_up() -> None:
    """REV-0101: the MFA step-up belongs to the permission (matrix row), not to a single operation."""
    flags: dict[str, set[tuple[str, bool]]] = {}
    for _path, _method, op in oc.operations():
        perm = op.get("x-aleekhan-permission")
        if perm:
            flags.setdefault(perm, set()).add(
                (op["operationId"], bool(op.get("x-aleekhan-mfa-step-up", False)))
            )
    mixed = {p: sorted(v) for p, v in flags.items() if len({f for _o, f in v}) > 1}
    assert mixed == {}


def test_planned_error_codes_are_not_yet_implemented_codes() -> None:
    implemented = set(oc.spec()["components"]["schemas"]["ErrorCode"]["enum"])
    planned = _conventions()["planned_error_codes"]
    assert not implemented & set(planned)
    assert all(400 <= status <= 599 for status in planned.values())


def test_implemented_paths_carry_no_planned_marker_fields() -> None:
    for path in oc.implemented_paths():
        assert "x-aleekhan-step" not in oc.spec()["paths"][path], path
