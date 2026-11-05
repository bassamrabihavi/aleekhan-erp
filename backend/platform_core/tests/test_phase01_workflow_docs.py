"""PHASE_01 / 01.2: approvals, tasks, workflow, documents (DEC-032 maker-checker, DEC-048, DEC-053)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.db.models.functions import Now
from django.utils import timezone

from platform_core.documents.models import Document, DocumentRevision, StoredObject, UploadType
from platform_core.workflow.models import (
    ApprovalRequest,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStepEvent,
    WorkTask,
)

from .phase01_factories import (
    approval,
    db_refuses,
    document,
    org_unit,
    position,
    revision,
    stored_object,
    user,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------------------------- approvals
def test_approval_never_self_decided_and_one_time() -> None:
    """DEC-032: maker != checker; a decided request never changes."""
    maker, checker = user(), user()
    req = approval(maker)
    with db_refuses("ck_approval_request_maker_checker"):
        ApprovalRequest.objects.filter(pk=req.pk).update(status="APPROVED", decided_by=maker, closed_at=Now())
    with db_refuses("ck_approval_request_decided_has_decider"):
        ApprovalRequest.objects.filter(pk=req.pk).update(status="APPROVED", closed_at=Now())
    with db_refuses("ck_approval_request_reject_note"):
        ApprovalRequest.objects.filter(pk=req.pk).update(
            status="REJECTED", decided_by=checker, closed_at=Now()
        )
    ApprovalRequest.objects.filter(pk=req.pk).update(status="APPROVED", decided_by=checker, closed_at=Now())
    with db_refuses("terminal_immutable"):
        ApprovalRequest.objects.filter(pk=req.pk).update(status="PENDING", decided_by=None, closed_at=None)


def test_one_pending_request_per_resource_revision_action_and_expiry_required() -> None:
    maker = user()
    req = approval(maker)
    with db_refuses("uq_approval_request_one_pending"):
        approval(maker, resource_id=req.resource_id)
    approval(maker, resource_id=req.resource_id, resource_revision=2)  # new revision = new request
    now = timezone.now()
    with db_refuses("ck_approval_request_expiry_after_request"):
        approval(maker, requested_at=now, expires_at=now)
    with db_refuses("immutable_column"):
        ApprovalRequest.objects.filter(pk=req.pk).update(expires_at=now + timedelta(days=90))


def test_routing_is_role_plus_unit_scope_only() -> None:
    """DEC-048 item 4: PHASE_01 routes approvals by role + unit scope only."""
    maker = user()
    approval(maker, route_scope_unit=org_unit())
    with db_refuses("ck_approval_request_route_kind"):
        approval(maker, route_kind="REPORTS_TO")


# ---------------------------------------------------------------------------------------------- tasks
def _task(**over: object) -> WorkTask:
    data: dict[str, object] = {"subject": "کار ساختگی", "assignee_kind": "USER", "assignee_user": user()}
    data.update(over)
    return WorkTask.objects.create(**data)


def test_task_assignee_reference_matches_kind() -> None:
    with db_refuses("ck_work_task_assignee_ref"):
        _task(assignee_kind="ORG_UNIT")
    unit = org_unit()
    _task(assignee_kind="ORG_UNIT", assignee_user=None, assignee_unit=unit)
    _task(assignee_kind="POSITION", assignee_user=None, assignee_position=position(unit))
    with db_refuses("ck_work_task_assigned_to_user"):
        _task(assignee_kind="ORG_UNIT", assignee_user=None, assignee_unit=unit, status="ASSIGNED")


def test_done_is_not_closed_and_verifier_differs_from_completer() -> None:
    worker, verifier = user(), user()
    t = _task(assignee_user=worker, status="IN_PROGRESS")
    with db_refuses("ck_work_task_done_has_completer"):
        WorkTask.objects.filter(pk=t.pk).update(status="DONE")
    WorkTask.objects.filter(pk=t.pk).update(status="DONE", completed_by=worker, completed_at=Now())
    with db_refuses("ck_work_task_verifier"):
        WorkTask.objects.filter(pk=t.pk).update(status="CLOSED", closed_by=worker, closed_at=Now())
    WorkTask.objects.filter(pk=t.pk).update(status="CLOSED", closed_by=verifier, closed_at=Now())
    with db_refuses("terminal_immutable"):
        WorkTask.objects.filter(pk=t.pk).update(subject="changed")


def test_block_and_cancel_need_reasons() -> None:
    t = _task(status="IN_PROGRESS")
    with db_refuses("ck_work_task_blocked_reason"):
        WorkTask.objects.filter(pk=t.pk).update(status="BLOCKED")
    with db_refuses("ck_work_task_cancel_reason"):
        WorkTask.objects.filter(pk=t.pk).update(status="CANCELLED", cancelled_at=Now(), cancel_reason="x")


# ---------------------------------------------------------------------------------------------- workflow
def test_definition_frozen_once_active_and_instance_pins_active_definition() -> None:
    d = WorkflowDefinition.objects.create(key="syn_flow", version=1, name_fa="گردش ساختگی", steps=[])
    with db_refuses("ck_workflow_instance_definition_active"):
        WorkflowInstance.objects.create(definition=d, subject_type="synthetic", subject_id="1")
    with db_refuses("ck_workflow_definition_steps_array"):
        WorkflowDefinition.objects.create(key="syn_flow", version=2, name_fa="گردش", steps={"a": 1})
    WorkflowDefinition.objects.filter(pk=d.pk).update(status="ACTIVE", steps=[{"key": "s1", "kind": "TASK"}])
    with db_refuses("immutable_column"):
        WorkflowDefinition.objects.filter(pk=d.pk).update(steps=[])
    with db_refuses("uq_workflow_definition_active"):
        WorkflowDefinition.objects.create(
            key="syn_flow", version=2, name_fa="گردش", steps=[], status="ACTIVE"
        )
    inst = WorkflowInstance.objects.create(definition=d, subject_type="synthetic", subject_id="1")
    with db_refuses("ck_workflow_instance_cancel_reason"):
        WorkflowInstance.objects.filter(pk=inst.pk).update(
            status="CANCEL_REQUESTED", cancel_requested_at=Now()
        )
    ev = WorkflowStepEvent.objects.create(instance=inst, seq=1, step_key="s1", event="ENTERED")
    with db_refuses("append-only"):
        WorkflowStepEvent.objects.filter(pk=ev.pk).update(event="COMPLETED")
    WorkflowInstance.objects.filter(pk=inst.pk).update(status="COMPLETED", ended_at=Now())
    with db_refuses("terminal_immutable"):
        WorkflowInstance.objects.filter(pk=inst.pk).update(status="RUNNING", ended_at=None)


# ---------------------------------------------------------------------------------------------- documents
def test_upload_allow_list_is_the_dec_053_list() -> None:
    assert set(UploadType.objects.values_list("extension", flat=True)) == {
        "pdf",
        "png",
        "jpg",
        "jpeg",
        "dxf",
        "xlsx",
    }
    for ext in ("xlsm", "docm", "exe", "js", "ps1", "svg"):
        with db_refuses("ck_upload_type_never_forbidden"):
            UploadType.objects.create(
                extension=ext,
                media_type="application/x-test",
                label_fa="x",
                content_check="PDF",
                decision_id="DEC-053",
            )


def test_revision_starts_quarantined_with_matching_object_and_size_limit() -> None:
    uploader = user()
    doc = document(uploader)
    with db_refuses("ck_document_revision_starts_quarantined"):
        revision(doc, uploader, scan_status="CLEAN")
    obj = stored_object()
    with db_refuses("ck_document_revision_object_match"):
        revision(doc, uploader, obj=obj, sha256="0" * 64)
    big = stored_object(size=25_000_001)
    with db_refuses("ck_document_revision_max_size"):
        revision(doc, uploader, obj=big)
    with db_refuses("ck_document_revision_name_basename"):
        revision(doc, uploader, original_name="..\\..\\windows\\evil.pdf")
    revision(doc, uploader, obj=stored_object(size=25_000_000))


def test_review_needs_clean_scan_and_approver_differs_from_uploader() -> None:
    uploader, approver = user(), user()
    doc = document(uploader)
    rev = revision(doc, uploader)
    with db_refuses("ck_document_revision_review_needs_clean"):
        DocumentRevision.objects.filter(pk=rev.pk).update(status="IN_REVIEW")
    DocumentRevision.objects.filter(pk=rev.pk).update(scan_status="SCANNING")
    DocumentRevision.objects.filter(pk=rev.pk).update(scan_status="CLEAN", scanned_at=Now())
    DocumentRevision.objects.filter(pk=rev.pk).update(
        status="IN_REVIEW", submitted_by=uploader, submitted_at=Now()
    )
    with db_refuses("ck_document_revision_maker_checker"):
        DocumentRevision.objects.filter(pk=rev.pk).update(
            status="APPROVED", decided_by=uploader, decided_at=Now()
        )
    DocumentRevision.objects.filter(pk=rev.pk).update(
        status="APPROVED", decided_by=approver, decided_at=Now()
    )
    Document.objects.filter(pk=doc.pk).update(current_approved_revision=rev)
    with db_refuses("immutable_column"):
        DocumentRevision.objects.filter(pk=rev.pk).update(status="WORKING")
    with db_refuses("immutable_column"):
        DocumentRevision.objects.filter(pk=rev.pk).update(original_name="other.pdf")
    with db_refuses("immutable_column"):
        DocumentRevision.objects.filter(pk=rev.pk).update(scan_status="REJECTED", status="REJECTED")
    rev2 = revision(doc, uploader, revision_no=2, parent_revision=rev)
    DocumentRevision.objects.filter(pk=rev2.pk).update(scan_status="CLEAN", scanned_at=Now())
    DocumentRevision.objects.filter(pk=rev2.pk).update(status="IN_REVIEW")
    with db_refuses("uq_document_revision_one_approved"):
        DocumentRevision.objects.filter(pk=rev2.pk).update(
            status="APPROVED", decided_by=approver, decided_at=Now()
        )
    DocumentRevision.objects.filter(pk=rev.pk).update(status="SUPERSEDED")
    with db_refuses("terminal_immutable"):
        DocumentRevision.objects.filter(pk=rev.pk).update(status="APPROVED")


def test_current_revision_must_be_approved_revision_of_same_document() -> None:
    uploader = user()
    doc, other = document(uploader), document(uploader)
    rev = revision(other, uploader)
    with db_refuses("ck_document_current_revision"):
        Document.objects.filter(pk=doc.pk).update(current_approved_revision=rev)


def test_rejected_scan_keeps_metadata_and_schedules_purge_once() -> None:
    """DEC-053: rejected bytes are purged after the quarantine period; metadata + hash stay."""
    uploader = user()
    rev = revision(document(uploader), uploader)
    with db_refuses("ck_document_revision_scan_reject"):
        DocumentRevision.objects.filter(pk=rev.pk).update(scan_status="REJECTED", scanned_at=Now())
    DocumentRevision.objects.filter(pk=rev.pk).update(
        scan_status="REJECTED", status="REJECTED", scanned_at=Now(), scan_finding="MALWARE_SIGNATURE"
    )
    key = rev.stored_object_id
    StoredObject.objects.filter(pk=key).update(purge_after=timezone.now() + timedelta(days=30))
    StoredObject.objects.filter(pk=key).update(bytes_purged_at=Now())
    with db_refuses("append_only"):
        StoredObject.objects.filter(pk=key).update(sha256="1" * 64)
    with db_refuses("append_only"), connection.cursor() as cur:  # raw SQL: bypass the ORM PROTECT check
        cur.execute("DELETE FROM platform_stored_object WHERE storage_key = %s", [key])
    assert StoredObject.objects.get(pk=key).sha256 == rev.sha256
