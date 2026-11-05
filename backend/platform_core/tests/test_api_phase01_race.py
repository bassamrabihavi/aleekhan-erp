"""01.4 race tests over HTTP on real PostgreSQL (multi-user concurrency, Gate-1): parallel requests through
the full stack (session authentication, idempotency, If-Match, row locks, DB guards). Synthetic data only."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from platform_core.identity.models import User
from platform_core.models import IdempotencyRecord
from platform_core.org.models import OrgUnit

from . import phase01_factories as f
from .engine_fixtures import INTERNAL_IP
from .engine_fixtures import network as set_network
from .phase01_api import body, code, open_token, post, session_client, with_roles
from .threads import run_concurrently

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("api_db", "clear_cache")]
N = 5
R = {"reason": "synthetic race"}


@pytest.fixture(autouse=True)
def _zones(settings: Any) -> None:
    set_network(settings)


def _clients(u: User, n: int = N) -> list[Any]:
    """``n`` browsers tabs sharing ONE session (the cap of 3 live sessions per user would end the oldest)."""
    from django.test import Client

    _sid, token = open_token(u)
    out = []
    for _ in range(n):
        c = Client(REMOTE_ADDR=INTERNAL_IP)
        c.cookies["aleekhan_session"] = token
        out.append(c)
    return out


def test_same_idempotency_key_in_parallel_executes_once() -> None:
    owner = with_roles("owner_admin")
    clients = _clients(owner)
    key = str(uuid.uuid4())
    new = {
        "username": f"syn.race.{uuid.uuid4().hex[:6]}",
        "display_name": f"کاربر ساختگی {f.SYN}",
        "account_kind": "PERSON",
        "network_policy": "ANY_WITH_MFA_OUTSIDE",
        "reason": "synthetic race",
    }

    def create(i: int) -> Any:
        return post(clients[i], "/admin/users", new, HTTP_IDEMPOTENCY_KEY=key)

    results = run_concurrently(create, N)
    assert not [r for r in results if isinstance(r, BaseException)], results
    statuses = sorted(r.status_code for r in results)
    assert set(statuses) <= {201, 409}, statuses  # 409 IDEMPOTENCY_IN_PROGRESS while the first one runs
    assert statuses.count(201) >= 1
    assert all(code(r) == "IDEMPOTENCY_IN_PROGRESS" for r in results if r.status_code == 409)
    assert User.objects.filter(username=new["username"]).count() == 1  # executed exactly once
    assert IdempotencyRecord.objects.filter(key=key).count() == 1
    created = {body(r)["user"]["user_id"] for r in results if r.status_code == 201}
    assert len(created) == 1


def test_parallel_updates_with_the_same_if_match_one_wins() -> None:
    owner = with_roles("owner_admin")
    unit = f.org_unit(unit_type_id="COMPANY")
    version = unit.row_version
    clients = _clients(owner)

    def rename(i: int) -> Any:
        return clients[i].patch(
            f"/api/v1/org/units/{unit.pk}",
            f'{{"reason": "synthetic race", "name_fa": "واحد ساختگی {i} {f.SYN}"}}'.encode(),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            HTTP_IF_MATCH=f'"{version}"',
        )

    results = run_concurrently(rename, N)
    assert not [r for r in results if isinstance(r, BaseException)], results
    statuses = sorted(r.status_code for r in results)
    assert statuses.count(200) == 1 and statuses.count(412) == N - 1, statuses
    unit.refresh_from_db()
    assert unit.row_version == version + 1  # one write, no lost update


def test_parallel_decisions_on_one_approval_exactly_one() -> None:
    owner = with_roles("owner_admin")
    target = with_roles("employee")
    from platform_core.identity import roles

    from .engine_fixtures import caller

    ra = roles.grant_role(caller(owner), user_id=target.pk, role_code="document_approver", reason="race")
    assert ra.approval_request_id is not None
    deciders = [session_client(with_roles("workflow_approver")) for _ in range(N)]

    def decide(i: int) -> Any:
        verb = "approve" if i % 2 == 0 else "reject"
        return post(
            deciders[i],
            f"/workflow/approvals/{ra.approval_request_id}/{verb}",
            {"resource_revision": 1, "note": "تصمیم ساختگی"},
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            HTTP_IF_MATCH='"1"',
        )

    results = run_concurrently(decide, N)
    assert not [r for r in results if isinstance(r, BaseException)], results
    statuses = sorted(r.status_code for r in results)
    assert statuses.count(200) == 1, statuses
    assert set(statuses) - {200} <= {409, 412}, statuses  # the row lock serialises: state or version moved on


def test_parallel_unit_creation_with_one_code_one_row() -> None:
    owner = with_roles("owner_admin")
    clients = _clients(owner)
    unit_code = f"syn_race_{uuid.uuid4().hex[:6]}"

    def create(i: int) -> Any:
        return post(
            clients[i],
            "/org/units",
            {
                **R,
                "code": unit_code,
                "name_fa": f"واحد ساختگی {f.SYN}",
                "unit_type": "COMPANY",
                "parent_unit_id": None,
            },
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

    results = run_concurrently(create, N)
    assert not [r for r in results if isinstance(r, BaseException)], results
    statuses = sorted(r.status_code for r in results)
    assert statuses.count(201) == 1 and set(statuses) <= {201, 400, 409}, statuses
    assert OrgUnit.objects.filter(code=unit_code).count() == 1
