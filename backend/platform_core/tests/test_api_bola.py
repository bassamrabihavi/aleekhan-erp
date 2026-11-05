"""SEC-01 (P0) over HTTP, 01.4: an object outside the caller's scope answers 404 ``NOT_FOUND`` - for EVERY
``{id}`` path family and EVERY method of the PHASE_01 contract, reads and writes alike (BOLA / IDOR) - and the
list endpoints never show what the object endpoints hide (list == object check).

The probe holds a synthetic role with EVERY catalogue permission, assigned with scope ORG_UNIT = unit A. The
objects live in unit B or carry no unit at all (identity, documents, parameters, jobs, audit: GLOBAL-only
records). So every refusal below comes from the record scope, never from a missing permission. Writes carry a
valid body, an Idempotency-Key and the CURRENT If-Match version, so a 404 cannot be a 400/412 in disguise. A
GLOBAL holder of the same role reads every object (200): the ids are real.
"""

from __future__ import annotations

import json
import re
import secrets
import uuid
from typing import Any

import pytest

from platform_core.engine.context import Actor, RequestContext
from platform_core.identity.models import Role, RoleAssignment, Session, User
from platform_core.jobs import service as jobs
from platform_core.models import AuditEvent
from platform_core.org.models import OrgUnit, Position, PositionAssignment
from platform_core.params.models import DynamicFieldDefinition, ParameterValue
from platform_core.workflow.models import ApprovalRequest, WorkflowDefinition, WorkflowInstance, WorkTask

from . import openapi_contract as oc
from . import phase01_factories as f
from .engine_fixtures import give_role, person
from .engine_fixtures import network as set_network
from .phase01_api import body, code, open_token, session_client, superuser
from .test_api_contract_planned import PHASE01_TAGS

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("api_db", "clear_cache")]

REASON = {"reason": "synthetic BOLA probe"}
NOW = "2026-11-05T00:00:00Z"


@pytest.fixture(autouse=True)
def _zones(settings: Any) -> None:
    set_network(settings)


def _world() -> dict[str, Any]:
    unit_a = f.org_unit(unit_type_id="COMPANY")
    unit_b = f.org_unit(unit_type_id="COMPANY")
    pos_b = f.position(unit_b)
    other = person()
    give_role(other, "employee")
    assignment = RoleAssignment.objects.filter(user=other).first()
    sid, _token = open_token(other)
    holder = f.position_assignment(pos_b, other)
    role = Role.objects.create(
        code=f"syn_draft_{secrets.token_hex(3)}", name_fa="نقش پیش‌نویس ساختگی", kind="BUSINESS"
    )
    task = WorkTask.objects.create(
        subject="کار ساختگی واحد ب", assignee_kind="ORG_UNIT", assignee_unit=unit_b, created_by=other
    )
    approval = f.approval(other, route_scope_unit=unit_b)
    definition = WorkflowDefinition.objects.create(
        key=f"syn_flow_{secrets.token_hex(3)}", version=1, name_fa="جریان ساختگی", steps=[], status="ACTIVE"
    )
    instance = WorkflowInstance.objects.create(
        definition=definition, subject_type="syn_subject", subject_id="1", started_by=other
    )
    run = jobs.enqueue(
        RequestContext(Actor.system()), job_type="session_expiry_sweep", task_key=f"syn-{uuid.uuid4()}"
    )
    doc = f.document(other)
    rev = f.revision(doc, other)
    value = ParameterValue.objects.filter(definition_id="mfa_step_up_window_minutes").first()
    assert value is not None
    field = DynamicFieldDefinition.objects.create(
        field_key=f"syn_field_{secrets.token_hex(3)}",
        entity_scope="syn_entity",
        label_fa="فیلد ساختگی",
        datatype="STRING",
        security_class="S1",
    )
    audit = AuditEvent.objects.order_by("-occurred_at").first()
    assert audit is not None
    return {
        "unit_a": unit_a,
        "ids": {
            "session_id": sid,
            "user_id": other.pk,
            "role_id": role.pk,
            "assignment_id": assignment.pk if assignment else None,
            "unit_id": unit_b.pk,
            "position_id": pos_b.pk,
            "position_assignment_id": holder.pk,
            "task_id": task.pk,
            "approval_id": approval.pk,
            "definition_id": definition.pk,
            "instance_id": instance.pk,
            "audit_event_id": audit.pk,
            "job_id": run.pk,
            "document_id": doc.pk,
            "revision_id": rev.pk,
            "parameter_key": "mfa_step_up_window_minutes",
            "value_revision_id": value.pk,
            "field_key": field.field_key,
        },
        # the object whose row_version If-Match must carry, per path parameter
        "models": {
            "session_id": Session,
            "user_id": User,
            "role_id": Role,
            "assignment_id": RoleAssignment,
            "unit_id": OrgUnit,
            "position_id": Position,
            "position_assignment_id": PositionAssignment,
            "task_id": WorkTask,
            "approval_id": ApprovalRequest,
            "instance_id": WorkflowInstance,
            "job_id": type(run),
            "document_id": type(doc),
            "revision_id": type(rev),
            "value_revision_id": ParameterValue,
            "field_key": DynamicFieldDefinition,
        },
    }


def _bodies(w: dict[str, Any], probe: User) -> dict[str, Any]:
    from platform_core.api.phase01.common import utc_req
    from platform_core.engine.context import db_now

    now = utc_req(db_now())
    note: dict[str, Any] = {}
    return {
        "revokeMySession": REASON,
        "updateUser": {**REASON, "display_name": "نام ساختگی"},
        "disableUser": REASON,
        "enableUser": REASON,
        "unlockUser": REASON,
        "resetUserPassword": REASON,
        "resetUserMfa": REASON,
        "revokeUserSessions": REASON,
        "updateRole": {**REASON, "name_fa": "نام ساختگی"},
        "activateRole": REASON,
        "retireRole": REASON,
        "revokeRoleAssignment": REASON,
        "updateOrgUnit": {**REASON, "name_fa": "نام ساختگی"},
        "moveOrgUnit": {**REASON, "new_parent_unit_id": str(w["unit_a"].pk), "effective_from": now},
        "deactivateOrgUnit": REASON,
        "updatePosition": {**REASON, "title_fa": "سمت ساختگی"},
        "endPositionAssignment": REASON,
        "startTask": note,
        "completeTask": note,
        "blockTask": REASON,
        "unblockTask": note,
        "reassignTask": {**REASON, "assignee": {"kind": "USER", "ref_id": str(probe.pk)}},
        "verifyCloseTask": note,
        "cancelTask": REASON,
        "approveRequest": {"resource_revision": 1, "note": "synthetic"},
        "rejectRequest": {"resource_revision": 1, "note": "synthetic"},
        "withdrawRequest": REASON,
        "bootstrapSelfApproveRequest": REASON,
        "cancelWorkflowInstance": REASON,
        "requestJobCancel": REASON,
        "updateDocument": {"title_fa": "عنوان ساختگی"},
        "uploadDocumentRevision": note,
        "submitDocumentRevision": note,
        "approveDocumentRevision": note,
        "rejectDocumentRevision": REASON,
        "proposeParameterValue": {
            **REASON,
            "value": {"datatype": "INTEGER", "value": "15"},
            "effective_from": NOW,
        },
        "publishParameterValue": note,
        "updateDynamicField": {"label_fa": "برچسب ساختگی"},
    }


ID_OPS = [(p, m, op) for p, m, op in oc.operations() if "{" in p and set(op["tags"]) & PHASE01_TAGS]


def _params(path: str) -> list[str]:
    return re.findall(r"\{([a-z_]+)\}", path)


def _url(path: str, ids: dict[str, Any]) -> str:
    return oc.BASE_PATH + re.sub(r"\{([a-z_]+)\}", lambda m: str(ids[m.group(1)]), path)


def _version(w: dict[str, Any], path: str) -> int:
    last = _params(path)[-1]
    model = w["models"].get(last)
    if model is None:
        return 1
    pk_field = "field_key" if last == "field_key" else "pk"
    obj = model._default_manager.get(**{pk_field: w["ids"][last]})
    return int(obj.row_version)


def test_every_id_path_family_has_a_bola_case() -> None:
    families = {p for p, _m, _op in ID_OPS}
    assert len(families) >= 50  # 50 {id} path families in 0.6.0-draft
    covered = {
        "session_id",
        "user_id",
        "role_id",
        "assignment_id",
        "unit_id",
        "position_id",
        "position_assignment_id",
        "task_id",
        "approval_id",
        "definition_id",
        "instance_id",
        "audit_event_id",
        "job_id",
        "document_id",
        "revision_id",
        "parameter_key",
        "value_revision_id",
        "field_key",
    }
    for p in families:
        assert set(_params(p)) <= covered, p


def test_out_of_scope_object_ids_answer_404_on_every_operation() -> None:
    w = _world()
    probe = superuser(scope_kind="ORG_UNIT", scope_unit=w["unit_a"])
    glob = session_client(superuser())
    c = session_client(probe)
    bodies = _bodies(w, probe)
    failures: list[str] = []
    checked = 0
    for path, method, op in ID_OPS:
        op_id = op["operationId"]
        url = _url(path, w["ids"])
        if method == "get":
            query = {"occurred_from": NOW, "occurred_to": NOW} if op_id == "listAuditEvents" else {}
            r = c.get(url, query)
            if op_id not in ("listUserSessions",) and op_id != "revokeMySession":
                g = glob.get(url, query)
                ok = {200, 409} if op_id == "downloadDocumentRevision" else {200}  # quarantined: 409
                if g.status_code not in ok:
                    failures.append(f"{op_id}: GLOBAL holder got {g.status_code} {g.content[:200]!r}")
        else:
            headers = {
                "HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4()),
                "HTTP_IF_MATCH": f'"{_version(w, path)}"',
            }
            r = getattr(c, method)(url, json.dumps(bodies[op_id]), content_type="application/json", **headers)
        checked += 1
        if r.status_code != 404 or code(r) != "NOT_FOUND":
            failures.append(f"{op_id} {method.upper()} {path}: {r.status_code} {r.content[:200]!r}")
        else:
            oc.validate_response(path, method, r)
    assert checked == len(ID_OPS)
    assert failures == [], " | ".join(failures)


def test_lists_never_show_what_the_object_endpoints_hide() -> None:
    w = _world()
    probe = superuser(scope_kind="ORG_UNIT", scope_unit=w["unit_a"])
    in_a = f.org_unit(parent=w["unit_a"])
    pos_a = f.position(w["unit_a"])
    task_a = WorkTask.objects.create(
        subject="کار ساختگی واحد الف", assignee_kind="ORG_UNIT", assignee_unit=w["unit_a"], created_by=probe
    )
    approval_a = f.approval(person(), route_scope_unit=w["unit_a"])
    c = session_client(probe)
    expectations = {
        "/admin/users": ("user_id", set()),
        "/admin/roles": ("role_id", set()),
        "/admin/role-assignments": ("assignment_id", set()),
        "/org/units": ("unit_id", {str(w["unit_a"].pk)}),
        "/org/positions": ("position_id", {str(pos_a.pk)}),
        "/workflow/tasks": ("task_id", {str(task_a.pk)}),
        "/workflow/approvals": ("approval_id", {str(approval_a.pk)}),
        "/workflow/definitions": ("definition_id", set()),
        "/admin/jobs": ("job_id", set()),
        "/documents": ("document_id", set()),
        "/admin/parameters": ("parameter_key", set()),
        "/admin/dynamic-fields": ("field_key", set()),
        "/admin/permissions": ("action", set()),
    }
    for path, (key, expected) in expectations.items():
        r = c.get(oc.BASE_PATH + path, {"page_size": 100})
        assert r.status_code == 200, (path, r.content)
        oc.validate_response(path, "get", r)
        got = {str(item[key]) for item in body(r)["items"]}
        if path == "/org/units":  # ORG_UNIT scope = the unit itself, not its children
            assert str(in_a.pk) not in got
        assert got == expected, (path, got)
    r = c.get(
        oc.BASE_PATH + "/audits",
        {"occurred_from": "2026-01-01T00:00:00Z", "occurred_to": "2030-01-01T00:00:00Z"},
    )
    assert r.status_code == 200 and body(r)["items"] == []
    tree = c.get(oc.BASE_PATH + "/org/tree")
    assert tree.status_code == 200
    oc.validate_response("/org/tree", "get", tree)
    assert [n["unit"]["unit_id"] for n in body(tree)["roots"]] == [str(w["unit_a"].pk)]


def test_subtree_scope_covers_children_in_lists_and_objects() -> None:
    root = f.org_unit(unit_type_id="COMPANY")
    child = f.org_unit(parent=root)
    outside = f.org_unit(unit_type_id="COMPANY")
    u = person()
    give_role(u, "employee", scope_kind="ORG_UNIT_SUBTREE", scope_unit=root)
    c = session_client(u)
    got = {i["unit_id"] for i in body(c.get(oc.BASE_PATH + "/org/units", {"page_size": 100}))["items"]}
    assert got == {str(root.pk), str(child.pk)}
    assert c.get(f"{oc.BASE_PATH}/org/units/{child.pk}").status_code == 200
    r = c.get(f"{oc.BASE_PATH}/org/units/{outside.pk}")
    assert r.status_code == 404 and code(r) == "NOT_FOUND"
    tree = body(c.get(oc.BASE_PATH + "/org/tree"))
    assert [n["unit"]["unit_id"] for n in tree["roots"]] == [str(root.pk)]
    assert [n["unit"]["unit_id"] for n in tree["roots"][0]["children"]] == [str(child.pk)]


def test_revision_of_another_document_is_404_even_when_both_are_visible() -> None:
    owner = person()
    doc_x = f.document(owner)
    doc_y = f.document(owner)
    rev_x = f.revision(doc_x, owner)
    c = session_client(superuser())
    assert c.get(f"{oc.BASE_PATH}/documents/{doc_x.pk}/revisions/{rev_x.pk}").status_code == 200
    for suffix in ("", "/content"):
        r = c.get(f"{oc.BASE_PATH}/documents/{doc_y.pk}/revisions/{rev_x.pk}{suffix}")
        assert r.status_code == 404 and code(r) == "NOT_FOUND", suffix
