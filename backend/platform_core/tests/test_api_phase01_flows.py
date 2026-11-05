"""PHASE_01 / 01.4 end-to-end HTTP flows over the real engine (synthetic data only). Every response is
validated against docs/api/openapi-draft.yaml (status declared, schema, headers).

Covered: user administration (ETag / If-Match 428/412, pagination), roles + assignments (DEC-049 activation
refusal, DEC-032 second approval, DEC-055 bootstrap self-approval), org tree / units / positions / holders,
tasks (maker-checker verify, cancel, reassign), approvals inbox, documents (SEC-03 quarantine, attachment-only
download, audited), parameters (OWNER_POLICY one-step, TECHNICAL propose -> publish by a second person),
dynamic-field drafts, jobs (safe cancel QUEUED -> CANCELLED, E-7), health detail, audit query / integrity.
"""

from __future__ import annotations

import io
import os
import subprocess
import uuid
import zipfile
from typing import Any

import pytest

from platform_core.api.phase01.common import utc_req
from platform_core.documents import scanner
from platform_core.documents import service as docs
from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.identity.models import RoleAssignment, Session, User
from platform_core.jobs import service as jobs
from platform_core.models import AuditEvent
from platform_core.workflow.models import WorkTask

from . import openapi_contract as oc
from . import phase01_factories as f
from .engine_fixtures import give_role, person
from .engine_fixtures import network as set_network
from .phase01_api import (
    API,
    body,
    code,
    etag_version,
    get,
    idem,
    if_match,
    patch,
    post,
    session_client,
    with_roles,
)

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("api_db", "clear_cache")]

PDF = b"%PDF-1.7\n% synthetic test document\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
R = {"reason": "synthetic API test"}


@pytest.fixture(autouse=True)
def _env(settings: Any, tmp_path: Any) -> None:
    set_network(settings)
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = str(tmp_path)


def ok(resp: Any, path: str, method: str, status: int = 200) -> Any:
    assert resp.status_code == status, (method, path, resp.status_code, resp.content[:400])
    oc.validate_response(path, method, resp)
    return body(resp) if resp.content and "json" in resp.get("Content-Type", "") else None


def refused(resp: Any, path: str, method: str, status: int, error: str) -> None:
    assert resp.status_code == status and code(resp) == error, (path, resp.status_code, resp.content[:300])
    oc.validate_response(path, method, resp)


# ----------------------------------------------------------------------------------------------- users
def test_user_administration_with_etag_if_match_and_pagination() -> None:
    owner = with_roles("owner_admin")
    c = session_client(owner)
    target = person()
    Session.objects.filter(user=target).delete()
    # list + cursor pagination
    page = ok(get(c, "/admin/users", {"page_size": 1}), "/admin/users", "get")
    assert len(page["items"]) == 1 and page["page"]["next_cursor"]
    nxt = ok(
        get(c, "/admin/users", {"page_size": 1, "cursor": page["page"]["next_cursor"]}), "/admin/users", "get"
    )
    assert nxt["items"][0]["user_id"] != page["items"][0]["user_id"]
    refused(get(c, "/admin/users", {"page_size": 0}), "/admin/users", "get", 400, "VALIDATION_FAILED")
    refused(get(c, "/admin/users", {"cursor": "cD1ub3Bl"}), "/admin/users", "get", 400, "VALIDATION_FAILED")
    filtered = ok(get(c, "/admin/users", {"q": target.username}), "/admin/users", "get")
    assert [u["user_id"] for u in filtered["items"]] == [str(target.pk)]
    # object + ETag
    path = "/admin/users/{user_id}"
    r = get(c, f"/admin/users/{target.pk}")
    ok(r, path, "get")
    v = etag_version(r)
    upd = {**R, "display_name": f"نام تازه ساختگی {f.SYN}"}
    refused(patch(c, f"/admin/users/{target.pk}", upd, **idem()), path, "patch", 428, "PRECONDITION_REQUIRED")
    refused(
        patch(c, f"/admin/users/{target.pk}", upd, **if_match(v + 7)), path, "patch", 412, "VERSION_CONFLICT"
    )
    r = patch(c, f"/admin/users/{target.pk}", upd, **if_match(v))
    out = ok(r, path, "patch")
    assert out["display_name"] == upd["display_name"] and etag_version(r) == out["row_version"] > v
    # a DB guard refusal is a 409 naming the rule, never a 500 (synthetic rows must keep their label)
    r = patch(
        c, f"/admin/users/{target.pk}", {**R, "display_name": "بدون برچسب"}, **if_match(out["row_version"])
    )
    refused(r, path, "patch", 409, "STATE_TRANSITION_NOT_ALLOWED")
    assert body(r)["errors"][0]["code"] == "CK_USER_SYNTHETIC_LABEL"
    refused(
        patch(c, f"/admin/users/{target.pk}", {**R, "bogus": 1}, **if_match(out["row_version"])),
        path,
        "patch",
        400,
        "VALIDATION_FAILED",
    )
    # disable revokes sessions, enable, effective permissions, sessions, revoke-all
    session_client(target)
    v = out["row_version"]
    out = ok(
        post(c, f"/admin/users/{target.pk}/disable", R, **if_match(v)),
        "/admin/users/{user_id}/disable",
        "post",
    )
    assert out["status"] == "DISABLED"
    assert not Session.objects.filter(user=target, state__in=["ACTIVE", "MFA_PENDING"]).exists()
    out = ok(
        post(c, f"/admin/users/{target.pk}/enable", R, **if_match(out["row_version"])),
        "/admin/users/{user_id}/enable",
        "post",
    )
    assert out["status"] == "ACTIVE"
    refused(
        post(c, f"/admin/users/{target.pk}/unlock", R, **if_match(out["row_version"])),
        "/admin/users/{user_id}/unlock",
        "post",
        409,
        "STATE_TRANSITION_NOT_ALLOWED",
    )
    session_client(target)
    ok(get(c, f"/admin/users/{target.pk}/sessions"), "/admin/users/{user_id}/sessions", "get")
    ok(
        get(c, f"/admin/users/{target.pk}/effective-permissions"),
        "/admin/users/{user_id}/effective-permissions",
        "get",
    )
    v = User.objects.get(pk=target.pk).row_version
    ok(
        post(c, f"/admin/users/{target.pk}/sessions/revoke-all", R, **if_match(v)),
        "/admin/users/{user_id}/sessions/revoke-all",
        "post",
    )
    # reset password: one-time credential shown once; reset MFA
    v = User.objects.get(pk=target.pk).row_version
    cred = ok(
        post(c, f"/admin/users/{target.pk}/reset-password", R, **if_match(v)),
        "/admin/users/{user_id}/reset-password",
        "post",
    )
    assert cred["user_id"] == str(target.pk) and len(cred["one_time_password"]) >= 12
    v = User.objects.get(pk=target.pk).row_version
    ok(
        post(c, f"/admin/users/{target.pk}/reset-mfa", R, **if_match(v)),
        "/admin/users/{user_id}/reset-mfa",
        "post",
    )
    # never on oneself
    v = User.objects.get(pk=owner.pk).row_version
    refused(
        post(c, f"/admin/users/{owner.pk}/reset-password", R, **if_match(v)),
        "/admin/users/{user_id}/reset-password",
        "post",
        403,
        "ACCESS_DENIED",
    )


def test_it_ops_may_unlock_but_not_create_users() -> None:
    it = with_roles("it_ops")
    c = session_client(it)
    locked = person(status="LOCKED")
    v = locked.row_version
    out = ok(
        post(c, f"/admin/users/{locked.pk}/unlock", R, **if_match(v)), "/admin/users/{user_id}/unlock", "post"
    )
    assert out["status"] == "ACTIVE"
    refused(post(c, "/admin/users", {}, **idem()), "/admin/users", "post", 403, "ACCESS_DENIED")


# ----------------------------------------------------------------------------------------------- roles
def test_roles_and_assignments_with_dec049_and_dec032() -> None:
    owner = with_roles("owner_admin")
    c = session_client(owner)
    roles = ok(get(c, "/admin/roles", {"page_size": 100}), "/admin/roles", "get")
    assert {r["code"] for r in roles["items"]} >= {"owner_admin", "employee", "workflow_approver"}
    ok(get(c, "/admin/permissions", {"page_size": 100}), "/admin/permissions", "get")
    new = {
        **R,
        "code": f"syn_role_{uuid.uuid4().hex[:6]}",
        "name_fa": "نقش ساختگی",
        "kind": "TECHNICAL",
        "permissions": ["platform.org.read"],
    }
    created = ok(post(c, "/admin/roles", new, **idem()), "/admin/roles", "post", 201)
    assert created["status"] == "DRAFT" and created["permissions"] == ["platform.org.read"]
    path = "/admin/roles/{role_id}"
    r = get(c, f"/admin/roles/{created['role_id']}")
    ok(r, path, "get")
    upd = ok(
        patch(
            c,
            f"/admin/roles/{created['role_id']}",
            {**R, "permissions": ["platform.org.read", "platform.audit.integrity.read"]},
            **if_match(etag_version(r)),
        ),
        path,
        "patch",
    )
    assert upd["permissions"] == ["platform.audit.integrity.read", "platform.org.read"]
    refused(  # DEC-003: a technical role never holds a business-approval permission
        patch(
            c,
            f"/admin/roles/{created['role_id']}",
            {**R, "permissions": ["platform.document.approve"]},
            **if_match(upd["row_version"]),
        ),
        path,
        "patch",
        409,
        "STATE_TRANSITION_NOT_ALLOWED",
    )
    refused(  # DEC-049: a runtime role has no approved permission set
        post(c, f"/admin/roles/{created['role_id']}/activate", R, **if_match(upd["row_version"])),
        "/admin/roles/{role_id}/activate",
        "post",
        409,
        "RULE_NOT_APPROVED",
    )
    # assignment of a non-BA role is ACTIVE at once; of a BA role waits for a second person (DEC-032)
    emp = person()
    employee_role = next(x for x in roles["items"] if x["code"] == "employee")
    approver_role = next(x for x in roles["items"] if x["code"] == "document_approver")
    a = ok(
        post(
            c,
            "/admin/role-assignments",
            {
                **R,
                "user_id": str(emp.pk),
                "role_id": employee_role["role_id"],
                "scope": {"kind": "GLOBAL", "ref_id": None},
            },
            **idem(),
        ),
        "/admin/role-assignments",
        "post",
        201,
    )
    assert a["status"] == "ACTIVE" and a["granted_by"] == str(owner.pk)
    p = ok(
        post(
            c,
            "/admin/role-assignments",
            {**R, "user_id": str(emp.pk), "role_id": approver_role["role_id"], "scope": {"kind": "GLOBAL"}},
            **idem(),
        ),
        "/admin/role-assignments",
        "post",
        201,
    )
    assert p["status"] == "PENDING_APPROVAL" and p["approval_id"]
    listed = ok(get(c, "/admin/role-assignments", {"user_id": str(emp.pk)}), "/admin/role-assignments", "get")
    assert {x["assignment_id"] for x in listed["items"]} == {a["assignment_id"], p["assignment_id"]}
    r = get(c, f"/admin/role-assignments/{p['assignment_id']}")
    ok(r, "/admin/role-assignments/{assignment_id}", "get")
    # self-assignment must be explicit (DEC-003)
    refused(
        post(
            c,
            "/admin/role-assignments",
            {**R, "user_id": str(owner.pk), "role_id": employee_role["role_id"], "scope": {"kind": "GLOBAL"}},
            **idem(),
        ),
        "/admin/role-assignments",
        "post",
        400,
        "VALIDATION_FAILED",
    )
    # the owner (granter) cannot decide the request; a workflow approver can
    refused(
        post(
            c,
            f"/workflow/approvals/{p['approval_id']}/approve",
            {"resource_revision": 1, "note": "ok"},
            **if_match(1),
        ),
        "/workflow/approvals/{approval_id}/approve",
        "post",
        403,
        "ACCESS_DENIED",
    )  # fmt: skip  - owner_admin is TECHNICAL: no business approval (DEC-003)
    decider = with_roles("workflow_approver")
    dc = session_client(decider)
    inbox = ok(get(dc, "/workflow/approvals", {"inbox": "to_decide"}), "/workflow/approvals", "get")
    assert p["approval_id"] in {x["approval_id"] for x in inbox["items"]}
    r = get(dc, f"/workflow/approvals/{p['approval_id']}")
    ok(r, "/workflow/approvals/{approval_id}", "get")
    out = ok(
        post(
            dc,
            f"/workflow/approvals/{p['approval_id']}/approve",
            {"resource_revision": 1, "note": "تأیید ساختگی"},
            **if_match(etag_version(r)),
        ),
        "/workflow/approvals/{approval_id}/approve",
        "post",
    )
    assert out["status"] == "APPROVED" and out["decided_by"] == str(decider.pk)
    assert RoleAssignment.objects.get(pk=p["assignment_id"]).status == "ACTIVE"
    # revoke
    v = RoleAssignment.objects.get(pk=a["assignment_id"]).row_version
    out = ok(
        post(c, f"/admin/role-assignments/{a['assignment_id']}/revoke", R, **if_match(v)),
        "/admin/role-assignments/{assignment_id}/revoke",
        "post",
    )
    assert out["status"] == "REVOKED"


def test_dec055_bootstrap_self_approval_over_http() -> None:
    owner = with_roles("owner_admin")
    c = session_client(owner)
    role_id = str(f.role("workflow_approver").pk)
    p = ok(
        post(
            c,
            "/admin/role-assignments",
            {
                **R,
                "user_id": str(owner.pk),
                "role_id": role_id,
                "scope": {"kind": "GLOBAL"},
                "confirm_self_assignment": True,
            },
            **idem(),
        ),
        "/admin/role-assignments",
        "post",
        201,
    )
    assert p["self_assignment"] is True and p["status"] == "PENDING_APPROVAL"
    path = "/workflow/approvals/{approval_id}/bootstrap-approve"
    # owner_admin holds no platform.workflow.approval.read (matrix v1.0): a fresh request has row_version 1
    assert get(c, f"/workflow/approvals/{p['approval_id']}").status_code == 403
    v = 1
    refused(
        post(c, f"/workflow/approvals/{p['approval_id']}/bootstrap-approve", {"reason": "x"}, **if_match(v)),
        path,
        "post",
        400,
        "VALIDATION_FAILED",
    )
    out = ok(
        post(
            c,
            f"/workflow/approvals/{p['approval_id']}/bootstrap-approve",
            {"reason": "DEC-055 first approver"},
            **if_match(v),
        ),
        path,
        "post",
    )
    assert out["status"] == "APPROVED" and out["bootstrap_self_approval"] is True
    assert out["decided_by"] == out["requested_by"] == str(owner.pk)
    assert RoleAssignment.objects.get(pk=p["assignment_id"]).status == "ACTIVE"
    assert AuditEvent.objects.filter(
        resource_id=p["approval_id"], scope={"bootstrap_self_approval": True}
    ).exists()
    # second holder of the same role: never bootstrap again (DEC-032 applies)
    other = person()
    q = ok(
        post(
            session_client(owner),
            "/admin/role-assignments",
            {**R, "user_id": str(other.pk), "role_id": role_id, "scope": {"kind": "GLOBAL"}},
            **idem(),
        ),
        "/admin/role-assignments",
        "post",
        201,
    )
    refused(
        post(c, f"/workflow/approvals/{q['approval_id']}/bootstrap-approve", R, **if_match(1)),
        path,
        "post",
        403,
        "SELF_APPROVAL_FORBIDDEN",
    )
    # a non-owner never bootstraps (no assignment.grant) -> 403
    refused(
        post(
            session_client(with_roles("workflow_approver")),
            f"/workflow/approvals/{q['approval_id']}/bootstrap-approve",
            R,
            **if_match(1),
        ),
        path,
        "post",
        403,
        "ACCESS_DENIED",
    )


# ------------------------------------------------------------------------------------------------- org
def test_org_tree_units_positions_and_holders() -> None:
    owner = with_roles("owner_admin")
    c = session_client(owner)
    root = ok(
        post(
            c,
            "/org/units",
            {
                **R,
                "code": f"syn_root_{uuid.uuid4().hex[:4]}",
                "name_fa": "ریشه ساختگی",
                "unit_type": "COMPANY",
                "parent_unit_id": None,
            },
            **idem(),
        ),
        "/org/units",
        "post",
        201,
    )
    dept = ok(
        post(
            c,
            "/org/units",
            {
                **R,
                "code": f"syn_dept_{uuid.uuid4().hex[:4]}",
                "name_fa": "واحد ساختگی",
                "unit_type": "DEPARTMENT",
                "parent_unit_id": root["unit_id"],
            },
            **idem(),
        ),
        "/org/units",
        "post",
        201,
    )
    other = ok(
        post(
            c,
            "/org/units",
            {
                **R,
                "code": f"syn_dep2_{uuid.uuid4().hex[:4]}",
                "name_fa": "واحد دوم ساختگی",
                "unit_type": "DEPARTMENT",
                "parent_unit_id": root["unit_id"],
            },
            **idem(),
        ),
        "/org/units",
        "post",
        201,
    )
    path = "/org/units/{unit_id}"
    r = get(c, f"/org/units/{dept['unit_id']}")
    ok(r, path, "get")
    upd = ok(
        patch(
            c,
            f"/org/units/{dept['unit_id']}",
            {**R, "name_fa": "واحد ساختگی تازه"},
            **if_match(etag_version(r)),
        ),
        path,
        "patch",
    )
    now = utc_req(db_now())
    moved = ok(
        post(
            c,
            f"/org/units/{dept['unit_id']}/move",
            {**R, "new_parent_unit_id": other["unit_id"], "effective_from": now},
            **if_match(upd["row_version"]),
        ),
        "/org/units/{unit_id}/move",
        "post",
    )
    assert moved["parent_unit_id"] == other["unit_id"]
    refused(
        post(
            c,
            f"/org/units/{dept['unit_id']}/move",
            {**R, "new_parent_unit_id": root["unit_id"], "effective_from": "2020-01-01T00:00:00Z"},
            **if_match(moved["row_version"]),
        ),
        "/org/units/{unit_id}/move",
        "post",
        400,
        "VALIDATION_FAILED",
    )  # never back-dated
    pos = ok(
        post(
            c,
            "/org/positions",
            {
                **R,
                "unit_id": dept["unit_id"],
                "code": f"syn_pos_{uuid.uuid4().hex[:4]}",
                "title_fa": "سمت ساختگی",
                "is_unit_head": True,
            },
            **idem(),
        ),
        "/org/positions",
        "post",
        201,
    )
    r = get(c, f"/org/positions/{pos['position_id']}")
    ok(r, "/org/positions/{position_id}", "get")
    ok(
        patch(
            c,
            f"/org/positions/{pos['position_id']}",
            {**R, "title_fa": "سمت ساختگی تازه"},
            **if_match(etag_version(r)),
        ),
        "/org/positions/{position_id}",
        "patch",
    )
    holder = person()
    pa = ok(
        post(
            c,
            "/org/position-assignments",
            {
                **R,
                "position_id": pos["position_id"],
                "user_id": str(holder.pk),
                "kind": "PRIMARY",
                "valid_from": now,
            },
            **idem(),
        ),
        "/org/position-assignments",
        "post",
        201,
    )
    ok(
        get(c, "/org/position-assignments", {"position_id": pos["position_id"]}),
        "/org/position-assignments",
        "get",
    )
    ok(get(c, "/org/positions", {"unit_id": dept["unit_id"]}), "/org/positions", "get")
    ok(get(c, "/org/units", {"parent_unit_id": other["unit_id"]}), "/org/units", "get")
    tree = ok(get(c, "/org/tree", {"root_unit_id": root["unit_id"]}), "/org/tree", "get")
    child = next(n for n in tree["roots"][0]["children"] if n["unit"]["unit_id"] == other["unit_id"])
    grand = child["children"][0]
    assert grand["positions"][0]["holders"][0]["user_id"] == str(holder.pk)
    shallow = ok(get(c, "/org/tree", {"root_unit_id": root["unit_id"], "depth": 1}), "/org/tree", "get")
    assert shallow["roots"][0]["children"] == [] and shallow["roots"][0]["truncated"] is True
    refused(
        get(c, "/org/tree", {"as_of": "2020-01-01T00:00:00Z"}), "/org/tree", "get", 400, "VALIDATION_FAILED"
    )
    ok(
        post(
            c,
            f"/org/position-assignments/{pa['position_assignment_id']}/end",
            R,
            **if_match(pa["row_version"]),
        ),
        "/org/position-assignments/{position_assignment_id}/end",
        "post",
    )
    empty = ok(
        post(
            c,
            "/org/units",
            {
                **R,
                "code": f"syn_empty_{uuid.uuid4().hex[:4]}",
                "name_fa": "واحد خالی ساختگی",
                "unit_type": "DEPARTMENT",
                "parent_unit_id": root["unit_id"],
            },
            **idem(),
        ),
        "/org/units",
        "post",
        201,
    )
    out = ok(
        post(c, f"/org/units/{empty['unit_id']}/deactivate", R, **if_match(empty["row_version"])),
        "/org/units/{unit_id}/deactivate",
        "post",
    )
    assert out["status"] == "INACTIVE"
    refused(
        post(
            c,
            f"/org/units/{other['unit_id']}/deactivate",
            R,
            **if_match(etag_version(get(c, f"/org/units/{other['unit_id']}"))),
        ),
        "/org/units/{unit_id}/deactivate",
        "post",
        409,
        "STATE_TRANSITION_NOT_ALLOWED",
    )  # not empty


# ----------------------------------------------------------------------------------------------- tasks
def test_tasks_maker_checker_and_inbox() -> None:
    unit = f.org_unit(unit_type_id="COMPANY")
    manager = with_roles("unit_manager", scope_kind="ORG_UNIT", scope_unit=unit)
    worker = person()
    give_role(worker, "employee")
    f.position_assignment(f.position(unit), worker)
    f.position_assignment(f.position(unit), manager)
    mc, wc = session_client(manager), session_client(worker)
    t = ok(
        post(
            mc,
            "/workflow/tasks",
            {
                "subject": "کار ساختگی",
                "assignee": {"kind": "USER", "ref_id": str(worker.pk)},
                "due_at": None,
                "note": "یادداشت",
            },
            **idem(),
        ),
        "/workflow/tasks",
        "post",
        201,
    )
    mine = ok(get(wc, "/workflow/tasks", {"inbox": "mine"}), "/workflow/tasks", "get")
    assert [x["task_id"] for x in mine["items"]] == [t["task_id"]]
    tid = t["task_id"]
    path = "/workflow/tasks/{task_id}"
    v = etag_version(get(wc, f"/workflow/tasks/{tid}"))
    s = ok(post(wc, f"/workflow/tasks/{tid}/start", {"note": "شروع"}, **if_match(v)), path + "/start", "post")
    s = ok(
        post(
            wc,
            f"/workflow/tasks/{tid}/block",
            {**R, "blocked_by": {"entity_type": "syn_thing", "entity_id": "7"}},
            **if_match(s["row_version"]),
        ),
        path + "/block",
        "post",
    )
    assert s["status"] == "BLOCKED" and s["blocked_by"]["entity_id"] == "7"
    s = ok(
        post(wc, f"/workflow/tasks/{tid}/unblock", {}, **if_match(s["row_version"])),
        path + "/unblock",
        "post",
    )
    s = ok(
        post(wc, f"/workflow/tasks/{tid}/complete", {}, **if_match(s["row_version"])),
        path + "/complete",
        "post",
    )
    assert s["status"] == "DONE" and s["completed_by"] == str(worker.pk)
    refused(
        post(wc, f"/workflow/tasks/{tid}/verify-close", {}, **if_match(s["row_version"])),
        path + "/verify-close",
        "post",
        403,
        "ACCESS_DENIED",
    )  # employee has no verify
    s = ok(
        post(mc, f"/workflow/tasks/{tid}/verify-close", {}, **if_match(s["row_version"])),
        path + "/verify-close",
        "post",
    )
    assert s["status"] == "CLOSED" and s["closed_by"] == str(manager.pk)
    # the completer never verifies his own task (SoD)
    t2 = ok(
        post(
            mc,
            "/workflow/tasks",
            {"subject": "کار دوم", "assignee": {"kind": "USER", "ref_id": str(manager.pk)}},
            **idem(),
        ),
        "/workflow/tasks",
        "post",
        201,
    )
    s = ok(
        post(mc, f"/workflow/tasks/{t2['task_id']}/start", {}, **if_match(t2["row_version"])),
        path + "/start",
        "post",
    )
    s = ok(
        post(mc, f"/workflow/tasks/{t2['task_id']}/complete", {}, **if_match(s["row_version"])),
        path + "/complete",
        "post",
    )
    refused(
        post(mc, f"/workflow/tasks/{t2['task_id']}/verify-close", {}, **if_match(s["row_version"])),
        path + "/verify-close",
        "post",
        403,
        "SELF_APPROVAL_FORBIDDEN",
    )
    t3 = ok(
        post(
            mc,
            "/workflow/tasks",
            {"subject": "کار سوم", "assignee": {"kind": "ORG_UNIT", "ref_id": str(unit.pk)}},
            **idem(),
        ),
        "/workflow/tasks",
        "post",
        201,
    )
    units = ok(get(wc, "/workflow/tasks", {"inbox": "mine"}), "/workflow/tasks", "get")
    assert t3["task_id"] in {x["task_id"] for x in units["items"]}  # holder of a position in the unit
    s = ok(
        post(
            mc,
            f"/workflow/tasks/{t3['task_id']}/reassign",
            {**R, "assignee": {"kind": "USER", "ref_id": str(worker.pk)}},
            **if_match(t3["row_version"]),
        ),
        path + "/reassign",
        "post",
    )
    refused(
        post(
            mc,
            f"/workflow/tasks/{t3['task_id']}/reassign",
            {**R, "assignee": {"kind": "POSITION", "ref_id": str(uuid.uuid4())}},
            **if_match(s["row_version"]),
        ),
        path + "/reassign",
        "post",
        400,
        "VALIDATION_FAILED",
    )
    s = ok(
        post(mc, f"/workflow/tasks/{t3['task_id']}/cancel", R, **if_match(s["row_version"])),
        path + "/cancel",
        "post",
    )
    assert s["status"] == "CANCELLED"
    refused(
        get(mc, "/workflow/tasks", {"cursor": "bm9wZQ"}), "/workflow/tasks", "get", 400, "VALIDATION_FAILED"
    )
    page = ok(get(mc, "/workflow/tasks", {"page_size": 1}), "/workflow/tasks", "get")
    assert len(page["items"]) == 1 and page["page"]["next_cursor"]
    nxt = ok(
        get(mc, "/workflow/tasks", {"page_size": 1, "cursor": page["page"]["next_cursor"]}),
        "/workflow/tasks",
        "get",
    )
    assert nxt["items"][0]["task_id"] != page["items"][0]["task_id"]


# ------------------------------------------------------------------------------------------- documents
def _xlsm() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<Types><Override ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"/></Types>',
        )
        zf.writestr("xl/vbaProject.bin", b"\x00synthetic")
    return buf.getvalue()


@pytest.fixture
def no_exec(monkeypatch: Any) -> None:
    def refuse(*a: object, **k: object) -> None:
        raise AssertionError("a process was started")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(os, "system", refuse)
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", refuse)


def _upload(c: Any, doc_id: str, name: str, data: bytes, **extra: Any) -> Any:
    upload = io.BytesIO(data)
    upload.name = name
    return c.post(f"{API}/documents/{doc_id}/revisions", {"file": upload, **extra}, **idem())


@pytest.mark.usefixtures("no_exec")
def test_documents_sec03_quarantine_review_and_attachment_download(monkeypatch: Any) -> None:
    ctl = with_roles("document_controller")
    apr = with_roles("document_approver")
    cc, ac = session_client(ctl), session_client(apr)
    doc = ok(
        post(
            cc,
            "/documents",
            {
                "document_type": "syn_drawing",
                "title_fa": "نقشه ساختگی",
                "sensitivity": "S1",
                "owner_entity": {"entity_type": "syn_product", "entity_id": "00012345678901"},
                "legacy_location_ref": "قفسه ساختگی 1",
            },
            **idem(),
        ),
        "/documents",
        "post",
        201,
    )
    assert doc["owner_entity"]["entity_id"] == "00012345678901"  # 14-digit code stays a string
    did = doc["document_id"]
    path = "/documents/{document_id}/revisions"
    rev = ok(_upload(cc, did, "sheet.pdf", PDF, change_note="نسخه اول"), path, "post", 202)
    assert rev["status"] == "WORKING" and rev["scan_status"] == "QUARANTINED"
    rid = rev["revision_id"]
    content = "/documents/{document_id}/revisions/{revision_id}/content"
    refused(
        cc.get(f"{API}/documents/{did}/revisions/{rid}/content"), content, "get", 409, "FILE_NOT_RELEASED"
    )
    refused(_upload(cc, did, "tool.exe", b"MZ\x90\x00synthetic"), path, "post", 415, "FILE_TYPE_NOT_ALLOWED")
    refused(_upload(cc, did, "book.xlsm", _xlsm()), path, "post", 415, "FILE_TYPE_NOT_ALLOWED")
    refused(_upload(cc, did, "fake.pdf", b"MZ not a pdf"), path, "post", 415, "FILE_TYPE_NOT_ALLOWED")
    refused(
        _upload(cc, did, "a.pdf", PDF, parent_revision_id=str(uuid.uuid4())),
        path,
        "post",
        409,
        "STATE_TRANSITION_NOT_ALLOWED",
    )  # stale parent
    import platform_core.api.phase01.document_views as dv

    monkeypatch.setattr(dv, "effective_int", lambda key: 16)
    refused(_upload(cc, did, "big.pdf", PDF), path, "post", 413, "PAYLOAD_TOO_LARGE")
    monkeypatch.undo()
    docs.scan_revision(uuid.UUID(rid), scanner.FakeScannerForTests())
    sub = "/documents/{document_id}/revisions/{revision_id}"
    r = cc.get(f"{API}/documents/{did}/revisions/{rid}")
    ok(r, sub, "get")
    s = ok(
        post(cc, f"/documents/{did}/revisions/{rid}/submit-review", {}, **if_match(etag_version(r))),
        sub + "/submit-review",
        "post",
    )
    assert s["status"] == "IN_REVIEW"
    refused(
        post(cc, f"/documents/{did}/revisions/{rid}/approve", {}, **if_match(s["row_version"])),
        sub + "/approve",
        "post",
        403,
        "ACCESS_DENIED",
    )  # controller has no approve right
    a = ok(
        post(
            ac, f"/documents/{did}/revisions/{rid}/approve", {"note": "تأیید"}, **if_match(s["row_version"])
        ),
        sub + "/approve",
        "post",
    )
    assert a["status"] == "APPROVED" and a["approved_by"] == str(apr.pk)
    r = cc.get(f"{API}/documents/{did}/revisions/{rid}/content")
    ok(r, content, "get")
    assert r.content == PDF
    assert r["Content-Type"] == "application/octet-stream"
    assert r["Content-Disposition"].startswith("attachment;")
    assert r["X-Content-Type-Options"] == "nosniff" and "sandbox" in r["Content-Security-Policy"]
    assert AuditEvent.objects.filter(action="platform.document.download", resource_id=rid).count() == 1
    ok(cc.get(f"{API}/documents/{did}/revisions"), path, "get")
    listed = ok(
        cc.get(f"{API}/documents", {"entity_type": "syn_product", "entity_id": "00012345678901"}),
        "/documents",
        "get",
    )
    assert [d["document_id"] for d in listed["items"]] == [did]
    r = cc.get(f"{API}/documents/{did}")
    upd = ok(
        patch(
            cc,
            f"/documents/{did}",
            {"title_fa": "نقشه ساختگی تازه", "legacy_location_ref": None},
            **if_match(etag_version(r)),
        ),
        "/documents/{document_id}",
        "patch",
    )
    assert upd["legacy_location_ref"] is None
    # a second revision rejected by the approver
    rev2 = ok(_upload(cc, did, "sheet2.pdf", PDF + b"%2", parent_revision_id=rid), path, "post", 202)
    docs.scan_revision(uuid.UUID(rev2["revision_id"]), scanner.FakeScannerForTests())
    r2 = cc.get(f"{API}/documents/{did}/revisions/{rev2['revision_id']}")
    s2 = ok(
        post(
            cc,
            f"/documents/{did}/revisions/{rev2['revision_id']}/submit-review",
            {},
            **if_match(etag_version(r2)),
        ),
        sub + "/submit-review",
        "post",
    )
    rj = ok(
        post(
            ac, f"/documents/{did}/revisions/{rev2['revision_id']}/reject", R, **if_match(s2["row_version"])
        ),
        sub + "/reject",
        "post",
    )
    assert rj["status"] == "REJECTED"


def test_employee_sees_s1_documents_only() -> None:
    owner = person()
    s1, s2 = f.document(owner, sensitivity="S1"), f.document(owner, sensitivity="S2")
    c = session_client(with_roles("employee"))
    got = {d["document_id"] for d in body(c.get(f"{API}/documents", {"page_size": 100}))["items"]}
    assert str(s1.pk) in got and str(s2.pk) not in got
    assert c.get(f"{API}/documents/{s1.pk}").status_code == 200
    r = c.get(f"{API}/documents/{s2.pk}")
    assert r.status_code == 404 and code(r) == "NOT_FOUND"


# ----------------------------------------------------------------------------------------- parameters
def test_parameters_owner_policy_and_technical_four_eyes() -> None:
    owner = with_roles("owner_admin")
    c = session_client(owner)
    page = ok(get(c, "/admin/parameters", {"page_size": 100}), "/admin/parameters", "get")
    assert any(p["parameter_key"] == "mfa_step_up_window_minutes" for p in page["items"])
    one = ok(
        get(c, "/admin/parameters/mfa_step_up_window_minutes"), "/admin/parameters/{parameter_key}", "get"
    )
    assert one["active_value"]["value"] == {"datatype": "INTEGER", "value": "15"}
    vals = "/admin/parameters/{parameter_key}/values"
    ok(get(c, "/admin/parameters/mfa_step_up_window_minutes/values"), vals, "get")
    refused(
        get(c, "/admin/parameters/NOT-A-KEY"), "/admin/parameters/{parameter_key}", "get", 404, "NOT_FOUND"
    )
    # OWNER_POLICY: proposed and published by the owner at once (Q-0103)
    now = utc_req(db_now())
    pv = ok(
        post(
            c,
            "/admin/parameters/mfa_step_up_window_minutes/values",
            {**R, "value": {"datatype": "INTEGER", "value": "15"}, "effective_from": now},
            **idem(),
        ),
        vals,
        "post",
        201,
    )
    assert pv["status"] == "PUBLISHED"
    refused(
        post(
            c,
            "/admin/parameters/mfa_step_up_window_minutes/values",
            {**R, "value": {"datatype": "BOOLEAN", "value": True}, "effective_from": now},
            **idem(),
        ),
        vals,
        "post",
        400,
        "VALIDATION_FAILED",
    )
    # TECHNICAL definition: proposed by it_ops, published by a config approver (BUSINESS role, MFA)
    key = f"syn_tech_{uuid.uuid4().hex[:6]}"
    d = ok(
        post(
            c,
            "/admin/parameters",
            {
                **R,
                "parameter_key": key,
                "label_fa": "پارامتر فنی ساختگی",
                "datatype": "INTEGER",
                "owner_module": "platform",
                "classification": "TECHNICAL",
            },
            **idem(),
        ),
        "/admin/parameters",
        "post",
        201,
    )
    assert d["active_value"] is None
    it = session_client(with_roles("it_ops"))
    pv = ok(
        post(
            it,
            f"/admin/parameters/{key}/values",
            {**R, "value": {"datatype": "INTEGER", "value": "42"}, "effective_from": now},
            **idem(),
        ),
        vals,
        "post",
        201,
    )
    assert pv["status"] == "PENDING_APPROVAL"
    pub = "/admin/parameters/{parameter_key}/values/{value_revision_id}/publish"
    from platform_core.params.models import ParameterValue

    v = ParameterValue.objects.get(pk=pv["value_revision_id"]).row_version
    refused(
        post(it, f"/admin/parameters/{key}/values/{pv['value_revision_id']}/publish", {}, **if_match(v)),
        pub,
        "post",
        403,
        "ACCESS_DENIED",
    )
    refused(
        post(
            session_client(with_roles("config_approver")),
            f"/admin/parameters/mfa_step_up_window_minutes/values/{pv['value_revision_id']}/publish",
            {},
            **if_match(v),
        ),
        pub,
        "post",
        404,
        "NOT_FOUND",
    )  # value of another parameter
    out = ok(
        post(
            session_client(with_roles("config_approver")),
            f"/admin/parameters/{key}/values/{pv['value_revision_id']}/publish",
            {},
            **if_match(v),
        ),
        pub,
        "post",
    )
    assert out["status"] == "PUBLISHED"
    # dynamic fields (DRAFT only)
    fk = f"syn_field_{uuid.uuid4().hex[:6]}"
    fd = ok(
        post(
            c,
            "/admin/dynamic-fields",
            {
                "field_key": fk,
                "entity_scope": "syn_entity",
                "label_fa": "فیلد ساختگی",
                "datatype": "STRING",
                "security_class": "S1",
            },
            **idem(),
        ),
        "/admin/dynamic-fields",
        "post",
        201,
    )
    assert fd["status"] == "DRAFT"
    r = get(c, f"/admin/dynamic-fields/{fk}")
    ok(r, "/admin/dynamic-fields/{field_key}", "get")
    ok(
        patch(
            c,
            f"/admin/dynamic-fields/{fk}",
            {"label_fa": "فیلد ساختگی تازه", "help_fa": None},
            **if_match(etag_version(r)),
        ),
        "/admin/dynamic-fields/{field_key}",
        "patch",
    )
    ok(get(c, "/admin/dynamic-fields"), "/admin/dynamic-fields", "get")


# ------------------------------------------------------------------------------------- jobs / health / audit
def test_jobs_safe_cancel_health_and_audit() -> None:
    owner = with_roles("owner_admin")
    c = session_client(owner)
    ctx = RequestContext(Actor.system())
    queued = jobs.enqueue(ctx, job_type="session_expiry_sweep", task_key=f"syn-{uuid.uuid4()}")
    ok(get(c, "/admin/job-definitions"), "/admin/job-definitions", "get")
    listed = ok(get(c, "/admin/jobs", {"state": "QUEUED"}), "/admin/jobs", "get")
    assert str(queued.pk) in {j["job_id"] for j in listed["items"]}
    r = get(c, f"/admin/jobs/{queued.pk}")
    ok(r, "/admin/jobs/{job_id}", "get")
    out = ok(
        post(c, f"/admin/jobs/{queued.pk}/request-cancel", R, **if_match(etag_version(r))),
        "/admin/jobs/{job_id}/request-cancel",
        "post",
    )
    assert out["state"] == "CANCELLED" and out["cancel_requested_by"] == str(owner.pk)  # 4.7 / E-7
    running = jobs.enqueue(ctx, job_type="session_expiry_sweep", task_key=f"syn-{uuid.uuid4()}")
    jobs.start(running.pk)
    running.refresh_from_db()
    out = ok(
        post(c, f"/admin/jobs/{running.pk}/request-cancel", R, **if_match(running.row_version)),
        "/admin/jobs/{job_id}/request-cancel",
        "post",
    )
    assert out["state"] == "CANCEL_REQUESTED"
    from platform_core.jobs.models import JobDefinition, JobRun

    JobDefinition.objects.get_or_create(
        job_type="syn_protected_job",
        defaults={"name_fa": "کار محافظت‌شده ساختگی", "cancellable": False, "protected": True},
    )
    prot = JobRun.objects.create(job_type_id="syn_protected_job", task_key=f"syn-{uuid.uuid4()}")
    prot.refresh_from_db()
    refused(
        post(c, f"/admin/jobs/{prot.pk}/request-cancel", R, **if_match(prot.row_version)),
        "/admin/jobs/{job_id}/request-cancel",
        "post",
        409,
        "JOB_PROTECTED",
    )
    health = ok(get(c, "/admin/health"), "/admin/health", "get")
    assert {x["name"] for x in health["components"]} >= {"database", "migrations", "cache"}
    assert health["jobs"]["running"] >= 1
    integrity = ok(get(c, "/audits/integrity"), "/audits/integrity", "get")
    assert integrity["status"] in {"NEVER_RUN", "OK", "BROKEN", "ERROR"}
    refused(get(c, "/audits"), "/audits", "get", 400, "VALIDATION_FAILED")
    window = {
        "occurred_from": "2026-01-01T00:00:00Z",
        "occurred_to": "2030-01-01T00:00:00Z",
        "resource_type": "platform.job_run",
    }
    events = ok(get(c, "/audits", window), "/audits", "get")
    assert events["items"]
    one = events["items"][0]
    ok(get(c, f"/audits/{one['audit_event_id']}"), "/audits/{audit_event_id}", "get")
    # the auditor reads, but needs a fresh MFA step-up for the audit trail (matrix MFA row)
    aud = with_roles("security_auditor")
    refused(get(session_client(aud, mfa=False), "/audits", window), "/audits", "get", 401, "MFA_REQUIRED")
    ok(get(session_client(aud), "/audits", window), "/audits", "get")
    # no route can modify or delete an audit event
    for method in ("post", "put", "patch", "delete"):
        r = getattr(c, method)(
            f"{API}/audits/{one['audit_event_id']}", "{}", content_type="application/json", **idem()
        )
        assert r.status_code == 405, method


def test_workflow_definitions_and_instance_cancel() -> None:
    from platform_core.workflow import instances
    from platform_core.workflow.models import WorkflowDefinition

    d = WorkflowDefinition.objects.create(
        key=f"syn_flow_{uuid.uuid4().hex[:6]}",
        version=1,
        name_fa="جریان ساختگی",
        status="ACTIVE",
        steps=[{"step_key": "syn_step", "kind": "TASK"}],
    )
    manager = with_roles("unit_manager")
    c = session_client(manager)
    ok(get(c, "/workflow/definitions"), "/workflow/definitions", "get")
    ok(get(c, f"/workflow/definitions/{d.pk}"), "/workflow/definitions/{definition_id}", "get")
    inst = instances.start_instance(
        RequestContext(Actor.user(manager.pk)),
        definition_key=d.key,
        subject_type="syn_subject",
        subject_id="1",
    )
    task = WorkTask.objects.create(
        subject="کار نمونه", assignee_kind="USER", assignee_user=manager, workflow_instance=inst
    )
    r = get(c, f"/workflow/instances/{inst.pk}")
    ok(r, "/workflow/instances/{instance_id}", "get")
    out = ok(
        post(c, f"/workflow/instances/{inst.pk}/cancel", R, **if_match(etag_version(r))),
        "/workflow/instances/{instance_id}/cancel",
        "post",
    )
    assert out["status"] in {"CANCELLED", "COMPENSATING"}
    task.refresh_from_db()
    assert task.status == "CANCELLED"
