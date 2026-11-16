"""02.6 fix3: matrix v2.2 (DEC-057 amendment 2026-11-15) - who sees and resolves the Planning import conflict
queue, and the counts-only freshness feed of management_viewer (contract 0.8.4-draft).

Synthetic data only (R-38): the conflict items carry synthetic keys and cell references, no workbook value.
"""

from __future__ import annotations

import uuid
from importlib import import_module
from typing import Any

import pytest
from django.test import Client

from platform_core.devtools.phase02_engine import holder
from platform_core.engine.context import Actor, RequestContext
from platform_core.identity.models import Permission, RolePermission
from platform_core.integration.conflicts import raise_conflict
from platform_core.integration.models import ConflictItem, IntegrationSource

from . import openapi_contract as oc
from .phase01_api import API, body, code, get, if_match, post, session_client

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("api_db", "clear_cache")]
SOURCE = "planning_catalogue_xlsm"
V22 = import_module("platform_core.migrations.0027_dec057_matrix_v22")


@pytest.fixture(autouse=True)
def planning_source() -> IntegrationSource:
    seed = import_module("platform_core.migrations.0026_phase02_planning_catalogue_source").SOURCE
    src, _ = IntegrationSource.objects.get_or_create(
        code=seed["code"], defaults={k: v for k, v in seed.items() if k != "code"}
    )
    return src


def _raise(n: int = 1, *, by: Any = None) -> list[ConflictItem]:
    ctx = RequestContext(Actor.user(by) if by else Actor.system(), request_id=uuid.uuid4())
    return [
        raise_conflict(
            ctx,
            source_code=SOURCE,
            kind="legacy_code_disputed",
            key=f"SYN!FZ{i + 2}-{uuid.uuid4().hex[:6]}",
            details={"sheet": "SYN", "cell": f"FZ{i + 2}", "reason": "NOT_14_DIGITS"},
        ).item
        for i in range(n)
    ]


def _freshness(c: Client) -> dict[str, Any]:
    r = get(c, "/integration/freshness")
    assert r.status_code == 200, r.content[:300]
    oc.validate_response("/integration/freshness", "get", r)
    return {i["source_code"]: i for i in body(r)["items"]}


def _resolve(c: Client, item: ConflictItem, note: str = "تصمیم ساختگی") -> Any:
    item.refresh_from_db()
    return post(
        c,
        f"/integration/conflicts/{item.conflict_id}/resolve",
        {"outcome": "RESOLVED", "note": note},
        **if_match(item.row_version),
    )


def test_matrix_v22_seed() -> None:
    for action, (_d, mfa, ba, sod) in V22.NEW_PERMISSIONS.items():
        p = Permission.objects.get(action=action)
        assert (p.mfa_step_up, p.business_approval, p.maker_checker) == (mfa, ba, sod)
        assert (p.matrix_version, p.decision_id) == ("2.2", "DEC-057")
        holders = set(RolePermission.objects.filter(permission=p).values_list("role__code", flat=True))
        assert holders == set(V22.ADDED_GRANTS[action]), action
    assert not Permission.objects.get(action=V22.CONFLICT_RESOLVE).business_approval
    assert Permission.objects.get(action=V22.CONFLICT_RESOLVE).maker_checker  # SoD flag


@pytest.mark.parametrize("role", ["product_data_steward", "owner_admin"])
def test_steward_and_owner_read_and_resolve(role: str) -> None:
    items = _raise(2)
    c = session_client(holder(role).user)
    assert _freshness(c)[SOURCE]["open_conflicts"] == 2
    r = get(c, "/integration/conflicts", {"source_code": SOURCE})
    assert r.status_code == 200
    assert {i["conflict_id"] for i in body(r)["items"]} == {str(i.conflict_id) for i in items}
    one = get(c, f"/integration/conflicts/{items[0].conflict_id}")
    assert one.status_code == 200 and body(one)["details"]["reason"] == "NOT_14_DIGITS"
    done = _resolve(c, items[0])
    assert done.status_code == 200, done.content[:300]
    assert body(done)["status"] == "RESOLVED"
    assert _freshness(c)[SOURCE]["open_conflicts"] == 1


def test_management_viewer_sees_freshness_and_counts_only() -> None:
    items = _raise(3)
    c = session_client(holder("management_viewer").user)
    fresh = _freshness(c)
    assert fresh[SOURCE]["open_conflicts"] == 3 and "details" not in fresh[SOURCE]
    for path in ("/integration/conflicts", f"/integration/conflicts/{items[0].conflict_id}"):
        r = get(c, path)
        assert r.status_code == 403 and code(r) == "ACCESS_DENIED", path
    r = _resolve(c, items[0])
    assert r.status_code == 403 and code(r) == "ACCESS_DENIED"
    items[0].refresh_from_db()
    assert items[0].status == "OPEN"


@pytest.mark.parametrize(
    "roles", [("employee",), ("commercial_officer",), ("planning_officer",), ("code_rule_approver",)]
)
def test_other_roles_are_denied_everything(roles: tuple[str, ...]) -> None:
    items = _raise(1)
    c = session_client(holder(*roles).user)
    for r in (
        get(c, "/integration/freshness"),
        get(c, "/integration/conflicts"),
        get(c, f"/integration/conflicts/{items[0].conflict_id}"),
        _resolve(c, items[0]),
    ):
        assert r.status_code == 403 and code(r) == "ACCESS_DENIED"


def test_the_user_who_raised_an_item_never_resolves_it() -> None:
    steward = holder("product_data_steward")
    (mine,) = _raise(1, by=steward.pk)
    r = _resolve(session_client(steward.user), mine)
    assert r.status_code == 403 and code(r) == "SELF_APPROVAL_FORBIDDEN"
    mine.refresh_from_db()
    assert mine.status == "OPEN"
    other = _resolve(session_client(holder("owner_admin").user), mine)
    assert other.status_code == 200 and body(other)["status"] == "RESOLVED"


def test_anonymous_is_refused(client: Client) -> None:
    r = client.get(f"{API}/integration/conflicts")
    assert r.status_code == 401


def _matrix_state() -> tuple[set[tuple[str, bool, bool, bool]], set[tuple[str, str]], dict[str, str]]:
    from platform_core.identity.models import Role

    perms = {
        (p.action, p.mfa_step_up, p.business_approval, p.maker_checker)
        for p in Permission.objects.filter(action__in=list(V22.NEW_PERMISSIONS))
    }
    grants = set(
        RolePermission.objects.filter(permission_id__in=list(V22.NEW_PERMISSIONS)).values_list(
            "role__code", "permission_id"
        )
    )
    versions = dict(Role.objects.filter(code__in=V22.CHANGED_ROLES).values_list("code", "matrix_version"))
    return perms, grants, versions


def test_migration_0027_reverse_is_exact_and_forward_restores_it() -> None:
    from django.apps import apps
    from django.db import connection

    before = _matrix_state()
    assert before[2] == dict.fromkeys(V22.CHANGED_ROLES, "2.2")
    with connection.schema_editor(atomic=True) as editor:
        V22.backward(apps, editor)
    perms, grants, versions = _matrix_state()
    assert perms == set() and grants == set() and versions == V22.PREVIOUS_VERSIONS
    session = session_client(holder("product_data_steward").user)
    assert get(session, "/integration/conflicts").status_code == 403  # action no longer in the catalogue
    with connection.schema_editor(atomic=True) as editor:
        V22.forward(apps, editor)
    assert _matrix_state() == before
