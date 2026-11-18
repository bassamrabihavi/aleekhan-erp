"""PHASE_02 / 02.7 privacy and permission tests, driven by the SEEDED permission matrix v2.2 and the OpenAPI
contract. Real session authentication, real PostgreSQL, synthetic users and data only (R-38, DEC-060).

1. The matrix is the seed: on the migrated database (non-transactional test), the grants of every PHASE_02
   (``identity.*`` / ``commercial.*``) and integration (``platform.integration.*``) action, for every seeded
   role, equal the union of the frozen migration constants 0022 (v2.0) + 0024 (v2.1) + 0027 (v2.2); the HTTP
   walk below uses exactly that union - no hand-written role or permission list.
2. Allow / deny exactly per matrix, every seeded role x every PHASE_02 + integration operation: a holder of
   only that role (fresh MFA) gets 403 ``ACCESS_DENIED`` on every operation whose permission the role lacks,
   and never 401 / 403 ``ACCESS_DENIED`` on an operation it holds (the request then fails later - 400 / 404 /
   422 on a synthetic empty body or an unknown id - or succeeds; the authorization layer let it through).
3. Fresh MFA: every MFA-flagged PHASE_02 operation answers 401 ``MFA_REQUIRED`` to every holder role whose
   session has no fresh MFA verification (DEC-057: issue, code-rule approve, order confirm, change decide,
   planning approve).
"""

from __future__ import annotations

import re
import uuid
from importlib import import_module
from typing import Any

import pytest
from django.test import Client

from platform_core.identity.models import Permission, Role, RolePermission

from . import openapi_contract as oc
from .phase01_api import code, session_client, with_roles

SCOPE_TAGS = frozenset({"identity", "commercial", "integration"})
SCOPE_ACTION = re.compile(r"^(identity|commercial|platform\.integration)\.")
MUTATING = {"post", "put", "patch", "delete"}

_SEED = import_module("platform_core.migrations.0010_seed_phase01_catalogue")
_V20 = import_module("platform_core.migrations.0022_dec057_matrix_v20")
_V21 = import_module("platform_core.migrations.0024_dec057_dec059_matrix_v21")
_V22 = import_module("platform_core.migrations.0027_dec057_matrix_v22")

# every seeded role: PHASE_01 (0010) + the five PHASE_02 business roles (0022)
ROLES: tuple[str, ...] = tuple(sorted({*_SEED.ROLES, *_V20.ROLES}))


def seeded_phase02_matrix() -> dict[str, frozenset[str]]:
    """Role -> PHASE_02 + integration actions of matrix v2.2, from the frozen seed constants only."""
    out: dict[str, set[str]] = {r: set() for r in ROLES}
    for grants in (_V20.GRANTS, _V21.ADDED_GRANTS, _V22.ADDED_GRANTS):
        for action, codes in grants.items():
            for role in codes:
                out[role].add(action)
    return {r: frozenset(a) for r, a in out.items()}


MATRIX = seeded_phase02_matrix()
MFA_ACTIONS = frozenset(
    {a for a, (_d, mfa, *_rest) in _V20.PERMISSIONS.items() if mfa}
    | {a for a, (_d, mfa, *_rest) in _V21.NEW_PERMISSIONS.items() if mfa}
    | {a for a, (_d, mfa, *_rest) in _V22.NEW_PERMISSIONS.items() if mfa}
)


def _ops() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (p, m, op)
        for p, m, op in oc.operations()
        if set(op["tags"]) & SCOPE_TAGS and op.get("x-aleekhan-permission")
    ]


OPS = _ops()


def _url(path: str) -> str:
    def sub(m: re.Match[str]) -> str:
        return "1" if m.group(1) == "order_version" else str(uuid.uuid4())

    return oc.BASE_PATH + re.sub(r"\{([a-z_]+)\}", sub, path)


def _call(c: Client, method: str, path: str) -> Any:
    if method == "get":
        return c.get(_url(path), {"q": "syn"} if "style-suggestions" in path else {})
    return getattr(c, method)(
        _url(path),
        "{}",
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        HTTP_IF_MATCH='"1"',
    )


# ------------------------------------------------------------------------------- 1. matrix == the seed
def test_scope_covers_every_phase02_and_integration_operation() -> None:
    assert len(ROLES) == 16, ROLES  # 11 PHASE_01 roles + 5 PHASE_02 business roles
    # 65 PHASE_02 operations (0.8.2-draft) + 4 integration operations (0.8.4-draft)
    # + getChangeRequestCounts (REV-0295)
    assert len(OPS) == 70
    perms = {op["x-aleekhan-permission"] for _p, _m, op in OPS}
    seeded = {*_V20.PERMISSIONS, *_V21.NEW_PERMISSIONS, *_V22.NEW_PERMISSIONS}
    # identity.serial.allocate stays seeded without an operation (allocateSerial removed 2026-11-14)
    assert perms == seeded - {"identity.serial.allocate"}
    assert MFA_ACTIONS == {
        "identity.product_code.issue",
        "identity.code_rule.approve",
        "commercial.order.confirm",
        "commercial.change.decide",
        "commercial.change.planning_approve",
    }


@pytest.mark.django_db
def test_migrated_grants_equal_the_seed_constants() -> None:
    """Non-transactional: the database as the migrations left it (0001-head), not a test re-creation."""
    rows = RolePermission.objects.filter(permission__action__regex=SCOPE_ACTION.pattern).values_list(
        "role__code", "permission__action"
    )
    db: dict[str, set[str]] = {r: set() for r in ROLES}
    for role, action in rows:
        db[role].add(action)
    assert {r: frozenset(a) for r, a in db.items()} == MATRIX
    assert set(Role.objects.values_list("code", flat=True)) == set(ROLES)
    flagged = set(
        Permission.objects.filter(action__regex=SCOPE_ACTION.pattern, mfa_step_up=True).values_list(
            "action", flat=True
        )
    )
    assert flagged == MFA_ACTIONS
    # decisions DEC-057 (unchanged): employee and the technical/audit roles hold no PHASE_02 permission
    for role in ("employee", "it_ops", "security_auditor"):
        assert MATRIX[role] == frozenset(), role


# --------------------------------------------------------------------- 2. allow / deny, every role x op
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache")
@pytest.mark.parametrize("role", ROLES)
def test_every_role_gets_exactly_the_operations_the_matrix_grants(role: str) -> None:
    c = session_client(with_roles(role))
    held = MATRIX[role]
    refused = allowed = 0
    for path, method, op in OPS:
        perm = op["x-aleekhan-permission"]
        r = _call(c, method, path)
        oc.validate_response(path, method, r)
        if perm in held:
            assert r.status_code != 401, (role, op["operationId"], r.status_code)
            assert not (r.status_code == 403 and code(r) == "ACCESS_DENIED"), (role, op["operationId"])
            allowed += 1
        else:
            assert r.status_code == 403 and code(r) == "ACCESS_DENIED", (
                role,
                op["operationId"],
                r.status_code,
            )
            refused += 1
    assert allowed + refused == len(OPS)
    held_ops = {op["x-aleekhan-permission"] for _p, _m, op in OPS} & held
    assert (allowed > 0) is bool(held_ops), role


# ------------------------------------------------------------------------------------- 3. fresh MFA
def _mfa_cases() -> list[tuple[str, str, dict[str, Any], str]]:
    out = []
    for path, method, op in OPS:
        perm = op["x-aleekhan-permission"]
        if perm not in MFA_ACTIONS:
            continue
        assert op.get("x-aleekhan-mfa-step-up") is True, op["operationId"]
        for role in ROLES:
            if perm in MATRIX[role]:
                out.append((path, method, op, role))
    return out


MFA_CASES = _mfa_cases()
MFA_HOLDERS = sorted({h for *_x, h in MFA_CASES})


def test_every_mfa_operation_has_holders() -> None:
    assert MFA_HOLDERS == sorted(
        [
            "product_data_steward",
            "code_rule_approver",
            "owner_admin",
            "planning_officer",
            "commercial_manager",
        ]
    )
    assert (
        len({op["operationId"] for _p, _m, op, _h in MFA_CASES}) == 7
    )  # issue, rule approve/reject/activate, ...


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache")
@pytest.mark.parametrize("holder", MFA_HOLDERS)
def test_mfa_operations_need_a_fresh_step_up_for_every_holder_role(holder: str) -> None:
    stale = session_client(with_roles(holder), mfa=False)
    checked = 0
    for path, method, op, h in MFA_CASES:
        if h != holder:
            continue
        r = _call(stale, method, path)
        assert r.status_code == 401 and code(r) == "MFA_REQUIRED", (holder, op["operationId"], r.status_code)
        oc.validate_response(path, method, r)
        checked += 1
    assert checked > 0
