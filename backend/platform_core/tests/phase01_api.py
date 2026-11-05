"""TEST-ONLY helpers for the PHASE_01 HTTP API tests (01.4). Synthetic people and units only.

* :func:`session_client` - a Django test client carrying a REAL session cookie for ``user`` (opened through
  ``identity.sessions.open_session``; optional fresh MFA verification), from an INTERNAL test address.
* :func:`all_permissions_role` - a synthetic BUSINESS role holding every catalogue permission (mode SCOPE).
  Used to reach the checks behind the permission (If-Match, Idempotency-Key, record scope) for every
  operation with one caller; assigned with an ORG_UNIT scope it is the BOLA probe of ``test_api_bola``.
"""

from __future__ import annotations

import json
import secrets
import uuid
from typing import Any

from django.test import Client

from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.engine.uow import unit_of_work
from platform_core.identity import sessions
from platform_core.identity.models import Permission, Role, RolePermission, User

from .engine_fixtures import INTERNAL_IP, give_role, person

API = "/api/v1"


def open_token(u: User, *, mfa: bool = True, zone: str = "INTERNAL") -> tuple[uuid.UUID, str]:
    with unit_of_work(RequestContext(Actor.system()), require_event=False) as uow:
        locked = User.objects.select_for_update().get(pk=u.pk)
        now = db_now()
        s, token = sessions.open_session(
            uow, locked, zone=zone, client_ip=INTERNAL_IP, mfa_pending=False, now=now
        )
        if mfa:
            sessions.mark_step_up(uow, s, now)
    return s.pk, token


def session_client(u: User, *, mfa: bool = True, csrf: bool = False, ip: str = INTERNAL_IP) -> Client:
    _sid, token = open_token(u, mfa=mfa)
    c = Client(REMOTE_ADDR=ip, enforce_csrf_checks=csrf)
    c.cookies["aleekhan_session"] = token
    return c


def all_permissions_role() -> Role:
    code = f"syn_all_{secrets.token_hex(3)}"
    r = Role.objects.create(
        code=code, name_fa="نقش ساختگی همه مجوزها (آزمایشی)", kind="BUSINESS", status="DRAFT"
    )
    for p in Permission.objects.all():
        RolePermission.objects.create(role=r, permission=p, grant_mode="SCOPE")
    Role.objects.filter(pk=r.pk).update(status="ACTIVE", matrix_version="1.0")
    r.refresh_from_db()
    return r


def superuser(**scope: Any) -> User:
    u = person()
    give_role(u, all_permissions_role().code, **scope)
    return u


def with_roles(*codes: str, **scope: Any) -> User:
    u = person()
    for code in codes:
        give_role(u, code, **scope)
    return u


def idem(**extra: Any) -> dict[str, Any]:
    return {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4()), **extra}


def if_match(version: int, **extra: Any) -> dict[str, Any]:
    return {"HTTP_IF_MATCH": f'"{version}"', **idem(), **extra}


def post(c: Client, path: str, body: Any = None, **headers: Any) -> Any:
    return c.post(
        f"{API}{path}",
        json.dumps(body if body is not None else {}),
        content_type="application/json",
        **headers,
    )


def patch(c: Client, path: str, body: Any, **headers: Any) -> Any:
    return c.patch(f"{API}{path}", json.dumps(body), content_type="application/json", **headers)


def get(c: Client, path: str, params: dict[str, Any] | None = None, **headers: Any) -> Any:
    return c.get(f"{API}{path}", params or {}, **headers)


def body(resp: Any) -> Any:
    return json.loads(resp.content.decode("utf-8"))


def code(resp: Any) -> str | None:
    if resp.get("Content-Type") != "application/problem+json":
        return None
    out: str | None = body(resp).get("code")
    return out


def etag_version(resp: Any) -> int:
    return int(resp["ETag"].strip('"'))
