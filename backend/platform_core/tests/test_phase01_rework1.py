"""01.3 rework round 1 regression tests.

REV-0111 operator sees only the current approved revision of documents linked to his tasks; REV-0112 list
scoping == object check (GLOBAL grants, sensitivity caps); REV-0113 a superseded future value never applies;
REV-0114 a refused outside login is a refusal; REV-0115 purge deletes bytes only after commit.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import timedelta

import pytest
from django.db import transaction

from platform_core.authz import policy as P
from platform_core.authz.policy import Caller
from platform_core.documents import scanner, service, storage
from platform_core.documents.models import Document, DocumentRevision, StoredObject
from platform_core.engine.context import db_now
from platform_core.engine.errors import MfaRequired, NotFound
from platform_core.identity import auth
from platform_core.identity.models import LoginAttempt, User
from platform_core.models import AuditEvent
from platform_core.org.models import OrgUnit
from platform_core.params import service as params
from platform_core.params.models import ParameterDefinition
from platform_core.params.values import effective_at, effective_int
from platform_core.workflow.models import ApprovalRequest, WorkTask

from .engine_fixtures import EXTERNAL_IP, PASSWORD, caller, give_role, network, person, with_role
from .phase01_factories import approval, org_unit, position, position_assignment

PDF = b"%PDF-1.7\n% synthetic test document\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@pytest.fixture
def store(settings, tmp_path) -> None:
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = str(tmp_path)


# ------------------------------------------------------------------------------------------- REV-0111
def _doc_team() -> tuple[Caller, Caller, User, Caller]:
    ctl, apr = person(), person()
    give_role(ctl, "document_controller")
    give_role(apr, "document_approver")
    op = person(account_kind="OPERATOR", network_policy="INTERNAL_ONLY")
    give_role(op, "operator_terminal")
    return caller(ctl), caller(apr), op, caller(op)


def _rev(ctl: Caller, doc: Document, data: bytes, *, clean: bool = True) -> DocumentRevision:
    rev = service.upload_revision(ctl, doc.pk, filename="sheet.pdf", data=data)
    if clean:
        service.scan_revision(rev.pk, scanner.FakeScannerForTests())
    rev.refresh_from_db()
    return rev


def _link(doc: Document, op: User, *, pinned: int | None = None) -> WorkTask:
    return WorkTask.objects.create(
        subject="کار ساختگی",
        related_type="document",
        related_id=str(doc.pk),
        related_revision=pinned,
        status="ASSIGNED",
        assignee_kind="USER",
        assignee_user=op,
    )


def _visible_revisions(c: Caller) -> set[uuid.UUID]:
    return set(DocumentRevision.objects.filter(service.revision_list_q(c)).values_list("pk", flat=True))


def _object_allowed(c: Caller, action: str = "platform.document.read") -> set[uuid.UUID]:
    out = set()
    for rev in DocumentRevision.objects.select_related("document"):
        if P.can(c, action, service.revision_scope(rev)):
            out.add(rev.pk)
    return out


@pytest.mark.django_db
def test_operator_gets_only_the_current_approved_revision_of_linked_documents(store) -> None:
    ctl, apr, op, c_op = _doc_team()
    doc = service.create_document(ctl, document_type="syn_drawing", title_fa="نقشه ساختگی", sensitivity="S1")
    r1 = _rev(ctl, doc, PDF)
    service.submit_revision(ctl, r1.pk)
    service.approve_revision(apr, r1.pk)
    with pytest.raises(NotFound):  # not linked to any task of the operator yet
        service.download(c_op, r1.pk)
    _link(doc, op)
    assert service.download(c_op, r1.pk).data == PDF
    working = _rev(ctl, doc, PDF + b"%working\n")
    in_review = _rev(ctl, doc, PDF + b"%review\n")
    service.submit_revision(ctl, in_review.pk)
    rejected = _rev(ctl, doc, PDF + b"%rejected\n")
    service.submit_revision(ctl, rejected.pk)
    service.reject_revision(apr, rejected.pk, reason="wrong dimensions")
    quarantined = _rev(ctl, doc, PDF + b"%quarantined\n", clean=False)
    for rev in (working, in_review, rejected, quarantined):
        with pytest.raises(NotFound):
            service.download(c_op, rev.pk)
        with pytest.raises(NotFound):
            service.get_revision(c_op, rev.pk)
    assert service.get_revision(c_op, r1.pk).pk == r1.pk
    # a newer approved revision supersedes r1: r1 disappears, r_new appears
    new = _rev(ctl, doc, PDF + b"%v2\n")
    service.submit_revision(ctl, new.pk)
    service.approve_revision(apr, new.pk)
    with pytest.raises(NotFound):
        service.download(c_op, r1.pk)
    assert service.download(c_op, new.pk).data == PDF + b"%v2\n"
    # list scoping == object check
    assert _visible_revisions(c_op) == _object_allowed(c_op) == {new.pk}
    assert set(Document.objects.filter(service.document_list_q(c_op)).values_list("pk", flat=True)) == {
        doc.pk
    }


@pytest.mark.django_db
def test_task_pinned_to_an_old_revision_gives_no_access_after_supersede(store) -> None:
    ctl, apr, op, c_op = _doc_team()
    doc = service.create_document(ctl, document_type="syn_drawing", title_fa="نقشه ساختگی", sensitivity="S1")
    r1 = _rev(ctl, doc, PDF)
    service.submit_revision(ctl, r1.pk)
    service.approve_revision(apr, r1.pk)
    _link(doc, op, pinned=r1.revision_no)
    assert service.download(c_op, r1.pk).data == PDF
    r2 = _rev(ctl, doc, PDF + b"%v2\n")
    service.submit_revision(ctl, r2.pk)
    service.approve_revision(apr, r2.pk)
    for rev in (r1, r2):  # r1 superseded; r2 not the pinned revision
        with pytest.raises(NotFound):
            service.download(c_op, rev.pk)
    assert _visible_revisions(c_op) == _object_allowed(c_op) == set()


@pytest.mark.django_db
def test_cancelled_task_link_and_unlinked_documents_are_invisible(store) -> None:
    ctl, apr, op, c_op = _doc_team()
    doc = service.create_document(ctl, document_type="syn_drawing", title_fa="نقشه ساختگی", sensitivity="S1")
    r1 = _rev(ctl, doc, PDF)
    service.submit_revision(ctl, r1.pk)
    service.approve_revision(apr, r1.pk)
    t = _link(doc, op)
    WorkTask.objects.filter(pk=t.pk).update(
        status="CANCELLED", cancelled_at=db_now(), cancel_reason="synthetic cancel"
    )
    with pytest.raises(NotFound):
        service.download(c_op, r1.pk)
    assert _visible_revisions(c_op) == set()


@pytest.mark.django_db
def test_revision_list_equals_object_check_for_every_document_role(store) -> None:
    ctl, apr, op, _c_op = _doc_team()
    docs = [
        service.create_document(ctl, document_type="syn_drawing", title_fa=f"سند {lvl}", sensitivity=lvl)
        for lvl in ("S1", "S2", "S3")
    ]
    for d in docs:
        r = _rev(ctl, d, PDF + d.sensitivity.encode())
        service.submit_revision(ctl, r.pk)
        service.approve_revision(apr, r.pk)
        _rev(ctl, d, PDF + b"%draft-" + d.sensitivity.encode())  # a WORKING revision as well
        _link(d, op)
    for role in ("management_viewer", "employee", "unit_manager", "document_controller", "document_approver",
                 "operator_terminal", "owner_admin", "config_approver"):  # fmt: skip
        u = person()
        give_role(u, role)
        _link(docs[0], u)
        c = caller(u)
        for action in ("platform.document.read", "platform.document.download"):
            if not P.can(c, action):
                assert _visible_revisions(c) == set() or action == "platform.document.download"
                continue
            got = set(
                DocumentRevision.objects.filter(service.revision_list_q(c, action)).values_list(
                    "pk", flat=True
                )
            )
            assert got == _object_allowed(c, action), (role, action)


# ------------------------------------------------------------------------------------------- REV-0112
def _approval_scope(r: ApprovalRequest) -> P.RecordScope:
    from platform_core.workflow.approvals import record_scope

    return record_scope(r)


@pytest.mark.django_db
def test_scope_q_equals_object_check_for_every_grant_shape() -> None:
    """For the scope kinds GLOBAL / ORG_UNIT / ORG_UNIT_SUBTREE and the grant modes SCOPE / OWN / OWN_UNIT /
    OWN_AND_OWN_UNIT: ``filter(scope_q)`` == the records the single-object check allows."""
    root = org_unit(unit_type_id="COMPANY")
    a = org_unit(parent=root)
    a_child = org_unit(parent=a)
    b = org_unit(parent=root)
    units: list[OrgUnit | None] = [None, root, a, a_child, b]
    people = [person() for _ in range(3)]
    for unit, who in itertools.product(units, people):
        approval(who, route_scope_unit=unit, resource_id=str(uuid.uuid4()))
    # (role, action) pairs covering every grant mode of the approved matrix
    cases = [
        ("unit_manager", "platform.workflow.approval.read"),  # SCOPE
        ("employee", "platform.workflow.approval.read"),  # OWN
        ("employee", "platform.workflow.task.create"),  # OWN_UNIT
        ("employee", "platform.workflow.task.read"),  # OWN_AND_OWN_UNIT
        ("security_auditor", "platform.workflow.approval.read"),  # SCOPE (technical role, non-BA action)
        ("owner_admin", "platform.workflow.approval.decide"),  # BA action: technical role never
    ]
    scopes = [("GLOBAL", None), ("ORG_UNIT", a), ("ORG_UNIT_SUBTREE", a), ("ORG_UNIT_SUBTREE", root)]
    for (role, action), (kind, unit) in itertools.product(cases, scopes):
        me = people[0]
        User.objects.filter(pk=me.pk).update(status="ACTIVE")
        from platform_core.identity.models import RoleAssignment

        RoleAssignment.objects.filter(user=me, status="ACTIVE").update(
            status="REVOKED", revoked_at=db_now(), revoke_reason="reset"
        )
        give_role(me, role, scope_kind=kind, scope_unit=unit)
        c = caller(me)
        q = P.scope_q(c, action, unit_field="route_scope_unit_id", owner_fields=("requested_by_id",))
        listed = set(ApprovalRequest.objects.filter(q).values_list("pk", flat=True))
        allowed = {r.pk for r in ApprovalRequest.objects.all() if P.can(c, action, _approval_scope(r))}
        assert listed == allowed, (role, action, kind)
    # own-unit facts: a position in unit b changes OWN_UNIT results consistently
    position_assignment(position(b, primary_capacity=5), people[0])
    c = caller(people[0])
    q = P.scope_q(
        c, "platform.workflow.task.read", unit_field="route_scope_unit_id", owner_fields=("requested_by_id",)
    )
    allowed = {
        r.pk
        for r in ApprovalRequest.objects.all()
        if P.can(c, "platform.workflow.task.read", _approval_scope(r))
    }
    assert set(ApprovalRequest.objects.filter(q).values_list("pk", flat=True)) == allowed


@pytest.mark.django_db
def test_global_grants_list_everything_and_caps_never_list_s3() -> None:
    ctl = person()
    give_role(ctl, "document_controller")
    c_ctl = caller(ctl)
    docs = {lvl: service.create_document(c_ctl, document_type="syn", title_fa=f"سند {lvl}", sensitivity=lvl)
            for lvl in ("S1", "S2", "S3")}  # fmt: skip
    expected = {"employee": {"S1"}, "management_viewer": {"S1", "S2"}, "unit_manager": {"S1", "S2"},
                "document_controller": {"S1", "S2", "S3"}}  # fmt: skip
    for role, levels in expected.items():
        _u, c = with_role(role)
        q = P.scope_q(
            c, "platform.document.read", unit_field=None, owner_fields=(), sensitivity_field="sensitivity"
        )
        got = set(Document.objects.filter(q).values_list("sensitivity", flat=True))
        assert got == levels, role
        for lvl, d in docs.items():
            assert P.can(c, "platform.document.read", service.document_scope(d)) is (lvl in levels)


@pytest.mark.django_db
def test_rbac_policy_adapter_lists_everything_for_global_grants() -> None:
    _u, c = with_role("security_auditor")

    class Principal:
        is_authenticated = True
        actor_id = c.user_id

    approval(person())
    pol = P.RbacPolicy(lambda obj: P.RecordScope())
    assert (
        pol.scope_queryset(
            Principal(), "platform.workflow.approval.read", ApprovalRequest.objects.all()
        ).count()
        == 1
    )


# ------------------------------------------------------------------------------------------- REV-0113
@pytest.mark.django_db
def test_superseded_future_value_never_takes_effect() -> None:
    ParameterDefinition.objects.create(
        key="syn_rev_param", label_fa="پارامتر ساختگی", datatype="INTEGER", owner_module="ops",
        classification="TECHNICAL",
    )  # fmt: skip
    _o, owner = with_role("owner_admin")
    apr = person()
    give_role(apr, "config_approver")
    fut = db_now() + timedelta(days=1)
    first = params.propose(owner, key="syn_rev_param", value="10", reason="future plan", effective_from=fut)
    params.publish(caller(apr), first.pk)
    second = params.propose(owner, key="syn_rev_param", value="20", reason="correction now")
    params.publish(caller(apr), second.pk)
    assert effective_int("syn_rev_param") == 20
    assert effective_at("syn_rev_param", db_now() + timedelta(days=2)) == "20"
    # a value that really was in force keeps answering for its period (history unchanged)
    third = params.propose(
        owner, key="syn_rev_param", value="30", reason="plan", effective_from=db_now() + timedelta(days=3)
    )
    params.publish(caller(apr), third.pk)
    assert effective_at("syn_rev_param", db_now() + timedelta(days=2)) == "20"
    assert effective_at("syn_rev_param", db_now() + timedelta(days=4)) == "30"


# ------------------------------------------------------------------------------------------- REV-0114
@pytest.mark.django_db
def test_refused_outside_login_is_recorded_as_a_refusal(settings) -> None:
    network(settings)
    u = person()
    give_role(u, "employee")
    ok = auth.login(u.username, PASSWORD, client_ip="10.20.1.10")  # inside: a real success
    assert ok.state == "ACTIVE"
    with pytest.raises(MfaRequired):
        auth.login(u.username, PASSWORD, client_ip=EXTERNAL_IP)
    attempt = LoginAttempt.objects.filter(user=u).order_by("-id").first()
    assert attempt is not None and attempt.outcome == "MFA_ENROLMENT_REQUIRED"
    audit = (
        AuditEvent.objects.filter(action="platform.identity.login.attempt", resource_id=str(u.pk))
        .order_by("-chain_seq")
        .first()
    )
    assert audit is not None and audit.outcome == "DENIED"
    # the refusal never resets the failure window: 4 wrong passwords, a refusal, 1 wrong password -> locked
    from platform_core.engine.errors import InvalidCredentials

    for _ in range(4):
        with pytest.raises(InvalidCredentials):
            auth.login(u.username, "Wrong-Pass-1!", client_ip="10.20.1.10")
    with pytest.raises(MfaRequired):
        auth.login(u.username, PASSWORD, client_ip=EXTERNAL_IP)
    with pytest.raises(InvalidCredentials):
        auth.login(u.username, "Wrong-Pass-1!", client_ip="10.20.1.10")
    u.refresh_from_db()
    assert u.status == "LOCKED"


# ------------------------------------------------------------------------------------------- REV-0115
@pytest.mark.django_db
def test_purge_keeps_the_bytes_when_the_transaction_rolls_back(
    store, django_capture_on_commit_callbacks
) -> None:
    ctl, _apr, _op, _c = _doc_team()
    doc = service.create_document(ctl, document_type="syn_drawing", title_fa="سند ساختگی", sensitivity="S1")
    rev = service.upload_revision(ctl, doc.pk, filename="eicar.pdf", data=PDF + EICAR)
    service.scan_revision(rev.pk, scanner.FakeScannerForTests())
    obj = StoredObject.objects.get(pk=rev.stored_object_id)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        try:
            with transaction.atomic():
                assert service.purge_rejected(now=db_now() + timedelta(days=31)) == 1
                raise RuntimeError("synthetic commit failure")
        except RuntimeError:
            pass
    assert callbacks == []  # the delete was discarded with the rolled-back savepoint
    obj.refresh_from_db()
    assert obj.bytes_purged_at is None
    assert storage.read(obj.storage_key, key_ref=obj.key_ref) == PDF + EICAR  # bytes kept, marker unset


@pytest.mark.django_db
def test_capped_grant_without_sensitivity_field_fails_closed() -> None:
    ctl = person()
    give_role(ctl, "document_controller")
    for lvl in ("S1", "S2", "S3"):
        service.create_document(caller(ctl), document_type="syn", title_fa=f"سند {lvl}", sensitivity=lvl)
    _u, c = with_role("unit_manager")  # capped at S2
    q = P.scope_q(c, "platform.document.read", unit_field=None, owner_fields=("created_by_id",))
    assert not Document.objects.filter(q).exists()
