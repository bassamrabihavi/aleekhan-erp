"""PHASE_01 / 01.5 backend items: DEC-056 (owner approval rights, matrix v1.1; v1.2 since 01.6), REV-0120
(upload parent check under the document row lock, HTTP race), REV-0121 (withdraw reason in the audit row,
HTTP happy path), REV-0122 (publish note -> audit reason). REV-0123 (CSRF rotation) is asserted in
test_api_phase01_auth.py. Synthetic data only."""

from __future__ import annotations

import io
import uuid
from typing import Any

import pytest
from django.db import connection
from django.test import Client

from platform_core.engine.errors import SelfApprovalForbidden
from platform_core.identity import roles, users
from platform_core.identity.models import Role, RoleAssignment, RolePermission
from platform_core.models import AuditEvent
from platform_core.workflow import approvals
from platform_core.workflow.models import ApprovalRequest

from . import openapi_contract as oc
from . import phase01_factories as f
from .engine_fixtures import INTERNAL_IP, PASSWORD, caller, person, with_role
from .engine_fixtures import network as set_network
from .phase01_api import (
    API,
    body,
    code,
    etag_version,
    get,
    if_match,
    open_token,
    post,
    session_client,
    superuser,
    with_roles,
)
from .phase01_factories import db_refuses
from .threads import run_concurrently

PDF = b"%PDF-1.7\n% synthetic test document\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
DECIDE = "platform.workflow.approval.decide"


# --------------------------------------------------------------------------------------------- DEC-056
@pytest.mark.django_db
def test_dec056_owner_holds_approval_read_and_decide_in_the_db() -> None:
    owner = Role.objects.get(code="owner_admin")
    held = set(RolePermission.objects.filter(role=owner).values_list("permission_id", "grant_mode"))
    assert {("platform.workflow.approval.read", "SCOPE"), (DECIDE, "SCOPE")} <= held
    # matrix v1.2 (DEC-056 extension, 0015): document.approve + parameter.publish as well
    assert {("platform.document.approve", "SCOPE"), ("platform.config.parameter.publish", "SCOPE")} <= held
    # matrix v2.0 (DEC-057, 0022) moved the owner on again (three PHASE_02 decisions, below); v2.1 (0024,
    # DEC-057 amendment 2026-11-12) added his PHASE_02 read permissions (no business approval)
    assert owner.matrix_version == "2.1" and owner.kind == "TECHNICAL"
    # no other business-approval permission for the owner, and none at all for it_ops / security_auditor
    assert set(
        RolePermission.objects.filter(
            role__code="owner_admin", permission__business_approval=True
        ).values_list("permission_id", flat=True)
    ) == {
        DECIDE,
        "platform.document.approve",
        "platform.config.parameter.publish",
        # DEC-057 (matrix v2.0): code-rule approval, order confirm, change-request decision
        "identity.code_rule.approve",
        "commercial.order.confirm",
        "commercial.change.decide",
    }
    assert not RolePermission.objects.filter(
        role__code__in=["it_ops", "security_auditor"], permission__business_approval=True
    ).exists()


@pytest.mark.django_db
def test_dec056_guard_exception_is_only_the_three_owner_pairs() -> None:
    """Any other TECHNICAL + business-approval pair is still refused by the DB (DEC-003)."""
    tech = Role.objects.create(code="syn_tech56", name_fa="نقش فنی ساختگی", kind="TECHNICAL", status="DRAFT")
    for action in (DECIDE, "platform.document.approve", "platform.config.parameter.publish"):
        with db_refuses("ck_role_technical_no_business_approval"):
            RolePermission.objects.create(role=tech, permission_id=action, grant_mode="SCOPE")
    # the owner's grants are frozen like every ACTIVE role (no runtime way to add or drop a cell)
    with db_refuses("ck_role_permission_draft_only"):
        RolePermission.objects.filter(
            role=Role.objects.get(code="owner_admin"), permission_id="platform.document.approve"
        ).delete()


@pytest.mark.django_db
def test_dec056_owner_decides_a_request_of_another_person_audited_with_his_role() -> None:
    # requester: a synthetic BUSINESS role holding assignment.grant (in PHASE_01 only the owner grants roles,
    # so the "other requester" is a test-only role)
    requester = superuser()
    target = person()
    ra = roles.grant_role(
        caller(requester), user_id=target.pk, role_code="document_approver", reason="synthetic grant"
    )
    assert ra.status == "PENDING_APPROVAL" and ra.approval_request_id
    o, owner = with_role("owner_admin")
    req = ApprovalRequest.objects.get(pk=ra.approval_request_id)
    assert approvals.can_decide(owner, req)  # appears in the owner's to_decide inbox
    out = approvals.approve(owner, req.pk, note="تأیید ساختگی مالک")
    assert out.request.status == "APPROVED" and out.request.decided_by_id == o.pk
    audit = AuditEvent.objects.get(action="platform.workflow.approval.approve", resource_id=str(req.pk))
    assert audit.scope["via_role"] == "owner_admin"  # DEC-056: every owner decision names his role
    ra.refresh_from_db()
    assert ra.status == "ACTIVE"


@pytest.mark.django_db
def test_dec056_owner_never_decides_his_own_request() -> None:
    _o, owner = with_role("owner_admin")
    ra = roles.grant_role(owner, user_id=person().pk, role_code="document_approver", reason="synthetic")
    assert ra.approval_request_id is not None
    req = ApprovalRequest.objects.get(pk=ra.approval_request_id)
    assert not approvals.can_decide(owner, req)
    with pytest.raises(SelfApprovalForbidden):
        approvals.approve(owner, req.pk, note="خودتأیید")
    with pytest.raises(SelfApprovalForbidden):
        approvals.reject(owner, req.pk, note="خودرد ساختگی")


@pytest.mark.django_db
def test_dec056_console_bootstrap_of_the_owner_still_works_and_needs_no_second_person() -> None:
    RoleAssignment.objects.filter(role__code="owner_admin").update(status="REVOKED")
    u = users.bootstrap_owner(
        username=f"syn.owner.{uuid.uuid4().hex[:6]}",
        display_name=f"مالک ساختگی {f.SYN}",
        password=PASSWORD,
        reason="synthetic console bootstrap",
    )
    ra = RoleAssignment.objects.get(user=u, role__code="owner_admin")
    assert ra.status == "ACTIVE" and ra.granted_via == "CONSOLE_BOOTSTRAP"
    assert ra.requires_second_approval is False
    # an UPDATE keeps the requirement fixed at grant time (cannot be flipped, never breaks the owner)
    RoleAssignment.objects.filter(pk=ra.pk).update(requires_second_approval=True)
    ra.refresh_from_db()
    assert ra.requires_second_approval is False and ra.status == "ACTIVE"


@pytest.mark.django_db
def test_dec056_in_app_grant_of_owner_admin_waits_for_a_second_person() -> None:
    """DEC-032 read literally: owner_admin now holds a business-approval permission."""
    _o, owner = with_role("owner_admin")
    ra = roles.grant_role(
        owner, user_id=person().pk, role_code="owner_admin", reason="synthetic second owner"
    )
    assert ra.status == "PENDING_APPROVAL" and ra.requires_second_approval
    with db_refuses("ck_role_assignment_second_approval"):
        RoleAssignment.objects.filter(pk=ra.pk).update(status="ACTIVE")
    # no DEC-055 bootstrap: owner_admin already has an ACTIVE holder
    with pytest.raises(SelfApprovalForbidden):
        assert ra.approval_request_id is not None
        approvals.bootstrap_self_approve(owner, ra.approval_request_id, reason="synthetic bootstrap")


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache")
def test_dec056_owner_lists_all_approvals_over_http(settings: Any) -> None:
    set_network(settings)
    requester = superuser()
    ra = roles.grant_role(
        caller(requester), user_id=person().pk, role_code="document_approver", reason="synthetic grant"
    )
    owner = with_roles("owner_admin")
    c = session_client(owner)
    r = get(c, "/workflow/approvals")
    assert r.status_code == 200, r.content
    oc.validate_response("/workflow/approvals", "get", r)
    assert str(ra.approval_request_id) in {x["approval_id"] for x in body(r)["items"]}
    r = get(c, "/workflow/approvals", {"inbox": "to_decide"})
    assert str(ra.approval_request_id) in {x["approval_id"] for x in body(r)["items"]}
    r = get(c, f"/workflow/approvals/{ra.approval_request_id}")
    assert r.status_code == 200
    r = post(
        c,
        f"/workflow/approvals/{ra.approval_request_id}/approve",
        {"resource_revision": 1, "note": "تأیید ساختگی"},
        **if_match(etag_version(r)),
    )
    assert r.status_code == 200, r.content
    oc.validate_response("/workflow/approvals/{approval_id}/approve", "post", r)
    assert body(r)["status"] == "APPROVED"


# --------------------------------------------------------------------------------------------- REV-0121
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache")
def test_rev0121_withdraw_over_http_stores_the_reason_in_the_audit_row(settings: Any) -> None:
    set_network(settings)
    requester = superuser()  # holds platform.workflow.approval.request (own requests) and assignment.grant
    ra = roles.grant_role(
        caller(requester), user_id=person().pk, role_code="document_approver", reason="synthetic grant"
    )
    c = session_client(requester)
    path = f"/workflow/approvals/{ra.approval_request_id}/withdraw"
    r = get(c, f"/workflow/approvals/{ra.approval_request_id}")
    assert r.status_code == 200, r.content
    v = etag_version(r)
    r = post(c, path, {"reason": "درخواست اشتباه ساختگی"}, **if_match(v + 5))
    assert r.status_code == 412 and code(r) == "VERSION_CONFLICT"
    r = post(c, path, {"reason": "درخواست اشتباه ساختگی"}, **if_match(v))
    assert r.status_code == 200, r.content
    oc.validate_response("/workflow/approvals/{approval_id}/withdraw", "post", r)
    assert body(r)["status"] == "WITHDRAWN"
    assert etag_version(r) > v
    audit = AuditEvent.objects.get(
        action="platform.workflow.approval.withdraw", resource_id=str(ra.approval_request_id)
    )
    assert audit.reason == "درخواست اشتباه ساختگی"
    ra.refresh_from_db()
    assert ra.status != "ACTIVE"


# --------------------------------------------------------------------------------------------- REV-0122
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache")
def test_rev0122_publish_note_is_the_audit_reason(settings: Any) -> None:
    from django.utils import timezone

    from platform_core.api.phase01.common import utc_req

    set_network(settings)
    owner = session_client(with_roles("owner_admin"))
    key = f"syn_tech_{uuid.uuid4().hex[:6]}"
    r = post(
        owner,
        "/admin/parameters",
        {
            "reason": "synthetic",
            "parameter_key": key,
            "label_fa": "پارامتر فنی ساختگی",
            "datatype": "INTEGER",
            "owner_module": "platform",
            "classification": "TECHNICAL",
        },
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert r.status_code == 201, r.content
    it = session_client(with_roles("it_ops"))
    r = post(
        it,
        f"/admin/parameters/{key}/values",
        {
            "reason": "پیشنهاد ساختگی",
            "value": {"datatype": "INTEGER", "value": "7"},
            "effective_from": utc_req(timezone.now()),
        },
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert r.status_code == 201, r.content
    pv = body(r)
    pv["row_version"] = etag_version(r)
    r = post(
        session_client(with_roles("config_approver")),
        f"/admin/parameters/{key}/values/{pv['value_revision_id']}/publish",
        {"note": "یادداشت انتشار ساختگی"},
        **if_match(pv["row_version"]),
    )
    assert r.status_code == 200, r.content
    audit = AuditEvent.objects.get(
        action="platform.config.parameter.publish", resource_id=pv["value_revision_id"]
    )
    assert audit.reason == "یادداشت انتشار ساختگی"


# --------------------------------------------------------------------------------------------- REV-0120
def _upload(c: Client, doc_id: str, data: bytes, parent: str | None, key: str | None = None) -> Any:
    upload = io.BytesIO(data)
    upload.name = "sheet.pdf"
    form: dict[str, Any] = {"file": upload}
    if parent is not None:
        form["parent_revision_id"] = parent
    return c.post(f"{API}/documents/{doc_id}/revisions", form, HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache")
def test_rev0120_concurrent_uploads_on_the_same_parent_one_202_one_409(settings: Any, tmp_path: Any) -> None:
    set_network(settings)
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = str(tmp_path)
    ctl = with_roles("document_controller")
    first = session_client(ctl)
    r = post(
        first,
        "/documents",
        {"document_type": "syn_drawing", "title_fa": "نقشه ساختگی", "sensitivity": "S1"},
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert r.status_code == 201, r.content
    did = body(r)["document_id"]
    r = _upload(first, did, PDF, None)
    assert r.status_code == 202, r.content
    parent = body(r)["revision_id"]
    _sid, token = open_token(ctl)
    clients = []
    for _ in range(2):
        c = Client(REMOTE_ADDR=INTERNAL_IP)
        c.cookies["aleekhan_session"] = token
        clients.append(c)

    def upload(i: int) -> Any:
        return _upload(clients[i], did, PDF + f"%{i}".encode(), parent)

    results = run_concurrently(upload, 2)
    assert not [x for x in results if isinstance(x, BaseException)], results
    statuses = sorted(x.status_code for x in results)
    assert statuses == [202, 409], [(x.status_code, x.content[:200]) for x in results]
    loser = next(x for x in results if x.status_code == 409)
    assert code(loser) == "STATE_TRANSITION_NOT_ALLOWED"
    oc.validate_response("/documents/{document_id}/revisions", "post", loser)
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM platform_document_revision WHERE document_id = %s", [did])
        assert cur.fetchone()[0] == 2  # revision 1 + exactly one child of it


@pytest.mark.django_db
def test_rev0120_service_checks_the_parent_under_the_lock(settings: Any, tmp_path: Any) -> None:
    from platform_core.documents import service as docs
    from platform_core.engine.errors import StateTransitionNotAllowed

    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = str(tmp_path)
    ctl, c = with_role("document_controller")
    doc = f.document(ctl)
    with pytest.raises(StateTransitionNotAllowed):  # no revision yet: any parent is stale
        docs.upload_revision(c, doc.pk, filename="a.pdf", data=PDF, expected_parent_id=uuid.uuid4())
    first = docs.upload_revision(c, doc.pk, filename="a.pdf", data=PDF)
    second = docs.upload_revision(c, doc.pk, filename="b.pdf", data=PDF + b"%2", expected_parent_id=first.pk)
    assert second.parent_revision_id == first.pk and second.revision_no == 2
    with pytest.raises(StateTransitionNotAllowed):  # first is no longer the latest
        docs.upload_revision(c, doc.pk, filename="c.pdf", data=PDF + b"%3", expected_parent_id=first.pk)
