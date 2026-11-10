"""PHASE_01 / 01.6 carried item: DEC-056 extension (employer 2026-11-10, matrix v1.2, REV-0125 / REV-0128).

The owner (``owner_admin``) decides document revisions (approve / reject) and BUSINESS_RULE parameter publish
directly; never his own request / upload / proposal (DEC-032); TECHNICAL values are not part of the extension.
Service level and HTTP level (real session auth, real PostgreSQL). Synthetic data only.
"""

from __future__ import annotations

import io
import uuid
from types import MappingProxyType
from typing import Any

import pytest
from django.db.models.functions import Now
from django.test import Client

from platform_core.documents import scanner
from platform_core.documents import service as docs
from platform_core.engine import rules
from platform_core.engine.errors import AccessDenied, RuleNotApproved, SelfApprovalForbidden
from platform_core.models import AuditEvent
from platform_core.params import service as params
from platform_core.params.models import ParameterDefinition, ParameterValue
from platform_core.workflow import approvals
from platform_core.workflow.models import ApprovalRequest

from . import openapi_contract as oc
from .engine_fixtures import caller, give_role, person, with_role
from .engine_fixtures import network as set_network
from .phase01_api import API, body, code, etag_version, get, if_match, post, session_client, with_roles

PDF = b"%PDF-1.7\n% synthetic test document\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


@pytest.fixture
def store(settings: Any, tmp_path: Any) -> None:
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = str(tmp_path)


def _in_review(ctl_caller: Any, *, title: str = "نقشه ساختگی") -> Any:
    doc = docs.create_document(ctl_caller, document_type="syn_drawing", title_fa=title, sensitivity="S1")
    rev = docs.upload_revision(ctl_caller, doc.pk, filename="sheet.pdf", data=PDF + uuid.uuid4().bytes)
    docs.scan_revision(rev.pk, scanner.FakeScannerForTests())
    return docs.submit_revision(ctl_caller, rev.pk)


def _br_definition(key: str) -> ParameterDefinition:
    return ParameterDefinition.objects.create(
        key=key, label_fa="آستانه ساختگی", datatype="INTEGER", owner_module="quality",
        classification="BUSINESS_RULE", decision_id="DEC-016",
    )  # fmt: skip


def _pending(definition: ParameterDefinition, proposer: Any, value: str = "3") -> ParameterValue:
    pv = ParameterValue.objects.create(
        definition=definition,
        value=value,
        status="PENDING_APPROVAL",
        effective_from=Now(),
        decision_id=definition.decision_id,
        reason="پیشنهاد ساختگی",
        proposed_by=proposer,
    )
    pv.refresh_from_db()
    return pv


@pytest.fixture
def dec016_approved_for_this_test(monkeypatch: Any) -> None:
    """TEST-ONLY: pretend DEC-016 were approved so the publish path past the rule gate can be exercised. The
    real registry stays empty (test_engine_rules_state guards it)."""
    monkeypatch.setattr(
        rules, "APPROVED_RULE_DECISIONS", MappingProxyType({"DEC-016": "synthetic (test only)"})
    )


# ------------------------------------------------------------------------------------- document revisions
@pytest.mark.django_db
@pytest.mark.usefixtures("store")
def test_owner_approves_a_document_revision_uploaded_by_another_person() -> None:
    _ctl, ctl = with_role("document_controller")
    rev = _in_review(ctl)
    o, owner = with_role("owner_admin")
    req = ApprovalRequest.objects.get(pk=rev.approval_request_id)
    assert approvals.can_decide(owner, req)  # in the owner's to_decide inbox
    rev = docs.approve_revision(owner, rev.pk, note="تأیید ساختگی مالک")
    assert rev.status == "APPROVED" and rev.decided_by_id == o.pk
    audit = AuditEvent.objects.get(action="platform.workflow.approval.approve", resource_id=str(req.pk))
    assert audit.scope["via_role"] == "owner_admin" and audit.actor_id == o.pk


@pytest.mark.django_db
@pytest.mark.usefixtures("store")
def test_owner_rejects_a_document_revision_with_reason() -> None:
    _ctl, ctl = with_role("document_controller")
    rev = _in_review(ctl)
    _o, owner = with_role("owner_admin")
    rev = docs.reject_revision(owner, rev.pk, reason="نقشه ناقص ساختگی")
    assert rev.status == "REJECTED" and rev.reject_reason == "نقشه ناقص ساختگی"


@pytest.mark.django_db
@pytest.mark.usefixtures("store")
def test_owner_never_approves_his_own_upload() -> None:
    """The owner may self-assign document_controller (DEC-003, audited); own upload stays maker != checker."""
    o = person()
    give_role(o, "owner_admin")
    give_role(o, "document_controller")
    me = caller(o)
    rev = _in_review(me)
    req = ApprovalRequest.objects.get(pk=rev.approval_request_id)
    assert not approvals.can_decide(me, req)
    with pytest.raises(SelfApprovalForbidden):
        docs.approve_revision(me, rev.pk)
    with pytest.raises(SelfApprovalForbidden):
        docs.reject_revision(me, rev.pk, reason="خودرد ساختگی")


@pytest.mark.django_db
@pytest.mark.usefixtures("store")
def test_it_ops_and_auditor_still_cannot_decide_documents() -> None:
    _ctl, ctl = with_role("document_controller")
    rev = _in_review(ctl)
    for code_ in ("it_ops", "security_auditor"):
        _u, tech = with_role(code_)
        with pytest.raises(AccessDenied):
            docs.approve_revision(tech, rev.pk)


# --------------------------------------------------------------------------------- BUSINESS_RULE publish
@pytest.mark.django_db
def test_owner_reaches_the_rule_gate_for_business_rule_publish_in_phase01() -> None:
    """Honest PHASE_01 behaviour: the permission now counts, the definition's own decision still blocks."""
    d = _br_definition("syn_br_gate")
    pv = _pending(d, person())
    _o, owner = with_role("owner_admin")
    with pytest.raises(RuleNotApproved) as exc:
        params.publish(owner, pv.pk)
    assert exc.value.decision_id == "DEC-016"


@pytest.mark.django_db
@pytest.mark.usefixtures("dec016_approved_for_this_test")
def test_owner_publishes_a_business_rule_value_proposed_by_another_person() -> None:
    d = _br_definition("syn_br_pub")
    proposer = person()
    pv = _pending(d, proposer)
    o, owner = with_role("owner_admin")
    out = params.publish(owner, pv.pk, note="انتشار ساختگی مالک")
    assert out.status == "PUBLISHED" and out.published_by_id == o.pk
    audit = AuditEvent.objects.get(action="platform.config.parameter.publish", resource_id=str(pv.pk))
    assert audit.actor_id == o.pk and audit.reason == "انتشار ساختگی مالک"


@pytest.mark.django_db
@pytest.mark.usefixtures("dec016_approved_for_this_test")
def test_owner_never_publishes_or_rejects_his_own_business_rule_proposal() -> None:
    d = _br_definition("syn_br_own")
    o, owner = with_role("owner_admin")
    pv = _pending(d, o)
    with pytest.raises(SelfApprovalForbidden):
        params.publish(owner, pv.pk)
    with pytest.raises(SelfApprovalForbidden):
        params.reject(owner, pv.pk, reason="خودرد ساختگی")
    pv.refresh_from_db()
    assert pv.status == "PENDING_APPROVAL"


@pytest.mark.django_db
@pytest.mark.usefixtures("dec016_approved_for_this_test")
def test_owner_rejects_a_business_rule_value_of_another_person() -> None:
    d = _br_definition("syn_br_rej")
    pv = _pending(d, person())
    _o, owner = with_role("owner_admin")
    assert params.reject(owner, pv.pk, reason="مقدار ساختگی نادرست").status == "REJECTED"


@pytest.mark.django_db
def test_owner_grant_does_not_count_for_technical_values() -> None:
    """The extension names BUSINESS_RULE publish only: TECHNICAL values still need a config approver."""
    ParameterDefinition.objects.create(
        key="syn_tech_v12", label_fa="پارامتر فنی ساختگی", datatype="INTEGER", owner_module="ops",
        classification="TECHNICAL",
    )  # fmt: skip
    _it, ops = with_role("it_ops")
    pv = params.propose(ops, key="syn_tech_v12", value="5", reason="پیشنهاد ساختگی")
    _o, owner = with_role("owner_admin")
    with pytest.raises(AccessDenied):
        params.publish(owner, pv.pk)
    with pytest.raises(AccessDenied):
        params.reject(owner, pv.pk, reason="رد ساختگی")
    # the owner who also holds config_approver explicitly (self-assignment, DEC-003) may publish it
    both = person()
    give_role(both, "owner_admin")
    give_role(both, "config_approver")
    assert params.publish(caller(both), pv.pk).status == "PUBLISHED"


# ------------------------------------------------------------------------------------------- HTTP (REV-0128)
def _upload(c: Client, doc_id: str) -> Any:
    upload = io.BytesIO(PDF + uuid.uuid4().bytes)
    upload.name = "sheet.pdf"
    return c.post(
        f"{API}/documents/{doc_id}/revisions", {"file": upload}, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache", "store")
def test_http_owner_approves_a_document_revision_of_another_person(settings: Any) -> None:
    set_network(settings)
    ctl = session_client(with_roles("document_controller"))
    r = post(
        ctl,
        "/documents",
        {"document_type": "syn_drawing", "title_fa": "نقشه ساختگی", "sensitivity": "S1"},
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert r.status_code == 201, r.content
    did = body(r)["document_id"]
    r = _upload(ctl, did)
    assert r.status_code == 202, r.content
    rid = body(r)["revision_id"]
    docs.scan_revision(uuid.UUID(rid), scanner.FakeScannerForTests())
    r = get(ctl, f"/documents/{did}/revisions/{rid}")
    r = post(ctl, f"/documents/{did}/revisions/{rid}/submit-review", {}, **if_match(etag_version(r)))
    assert r.status_code == 200, r.content

    owner = session_client(with_roles("owner_admin"))
    r = get(owner, "/workflow/approvals", {"inbox": "to_decide"})
    assert r.status_code == 200, r.content
    items = [x for x in body(r)["items"] if (x["resource"] or {}).get("entity_id") == rid]
    assert len(items) == 1 and items[0]["status"] == "PENDING"
    approval_id = items[0]["approval_id"]
    r = get(owner, f"/workflow/approvals/{approval_id}")
    assert r.status_code == 200, r.content
    r = post(
        owner,
        f"/workflow/approvals/{approval_id}/approve",
        {"resource_revision": 1, "note": "تأیید ساختگی مالک"},
        **if_match(etag_version(r)),
    )
    assert r.status_code == 200, r.content
    oc.validate_response("/workflow/approvals/{approval_id}/approve", "post", r)
    assert body(r)["status"] == "APPROVED"
    r = get(ctl, f"/documents/{did}/revisions/{rid}")
    assert body(r)["status"] == "APPROVED"


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache", "store")
def test_http_owner_decides_via_the_document_endpoint_and_never_his_own(settings: Any) -> None:
    set_network(settings)
    owner_user = with_roles("owner_admin")
    owner = session_client(owner_user)
    _ctl, ctl = with_role("document_controller")
    rev = _in_review(ctl)
    path = f"/documents/{rev.document_id}/revisions/{rev.pk}"
    r = post(owner, f"{path}/reject", {"reason": "نقشه ناقص ساختگی"}, **if_match(rev.row_version))
    assert r.status_code == 200, r.content
    oc.validate_response("/documents/{document_id}/revisions/{revision_id}/reject", "post", r)
    assert body(r)["status"] == "REJECTED"
    # own upload: the owner self-assigns document_controller (audited) -> 403 SELF_APPROVAL_FORBIDDEN
    give_role(owner_user, "document_controller")
    mine = _in_review(caller(owner_user))
    path = f"/documents/{mine.document_id}/revisions/{mine.pk}"
    r = post(owner, f"{path}/approve", {}, **if_match(mine.row_version))
    assert r.status_code == 403 and code(r) == "SELF_APPROVAL_FORBIDDEN", r.content


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache")
def test_http_owner_parameter_publish_br_gate_and_technical_denied(settings: Any) -> None:
    set_network(settings)
    owner = session_client(with_roles("owner_admin"))
    d = _br_definition("syn_br_http")
    pv = _pending(d, person())
    r = post(owner, f"/admin/parameters/{d.key}/values/{pv.pk}/publish", {}, **if_match(pv.row_version))
    assert r.status_code == 409 and code(r) == "RULE_NOT_APPROVED", r.content
    assert body(r)["decision_id"] == "DEC-016"
    ParameterDefinition.objects.create(
        key="syn_tech_http", label_fa="پارامتر فنی ساختگی", datatype="INTEGER", owner_module="ops",
        classification="TECHNICAL",
    )  # fmt: skip
    tech = _pending(ParameterDefinition.objects.get(key="syn_tech_http"), person(), value="9")
    r = post(
        owner, f"/admin/parameters/syn_tech_http/values/{tech.pk}/publish", {}, **if_match(tech.row_version)
    )
    assert r.status_code == 403 and code(r) == "ACCESS_DENIED", r.content
