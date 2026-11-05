"""Documents, revisions and the upload quarantine pipeline (STATE_TRANSITIONS 4.6; DEC-053 / DEC-032; SEC-03).

Upload (``platform.document.upload``):
  size <= ``document_upload_max_bytes`` (413) -> extension in the allow-list (415) -> content check of the
  type:
  magic bytes, OOXML without macros, parser-bomb guards (415) -> bytes encrypted under a random key ->
  revision
  WORKING / QUARANTINED. Nothing is ever executed or rendered.
Scan (job function :func:`scan_pending` / :func:`scan_revision`):
  QUARANTINED -> SCANNING -> CLEAN, or -> REJECTED (revision REJECTED, finding = signature name, bytes purged
  after ``document_rejected_quarantine_days``, metadata + hash kept). Scanner unavailable -> back to
  QUARANTINED (never auto-CLEAN).
Review: WORKING -> IN_REVIEW (``platform.document.update``, scan CLEAN; raises an approval request) ->
  APPROVED (``platform.document.approve``: BUSINESS role, MFA step-up, approver != uploader, DEC-032) - the
  previous approved revision becomes SUPERSEDED - or REJECTED (reason).
Download (``platform.document.download``): only CLEAN, not purged (409 ``FILE_NOT_RELEASED``); always an
  attachment (``Content-Disposition: attachment``, ``application/octet-stream``, ``nosniff``, sandbox CSP) -
  never inline.
Sensitivity: grants may cap the class (matrix: EMP S1, MGR/MGT S1-S2); documents carry no org unit in
PHASE_01,
  so ● grants need a GLOBAL assignment. The operator's ○ = approved documents linked to his own tasks.
"""

from __future__ import annotations

import functools
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final
from urllib.parse import quote

from django.db import transaction
from django.db.models import F, Q

from platform_core.authz.policy import (
    Caller,
    RecordScope,
    require_permission,
    require_record,
)
from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.engine.dbrules import db_rules
from platform_core.engine.errors import (
    DependencyUnavailable,
    FieldError,
    FileNotReleased,
    FileTypeNotAllowed,
    NotFound,
    PayloadTooLarge,
    SelfApprovalForbidden,
    ValidationFailed,
)
from platform_core.engine.state import StateMachine
from platform_core.engine.uow import NothingToDo, UnitOfWork, unit_of_work, unit_of_work_or_nothing
from platform_core.identity.models import GrantMode
from platform_core.params.values import effective_days, effective_int
from platform_core.workflow import approvals
from platform_core.workflow.models import ApprovalRequest, ApprovalStatus

from . import filetypes, storage
from .models import Document, DocumentRevision, RevisionStatus, ScanStatus, StoredObject, UploadType
from .scanner import Scanner, configured_scanner

APPROVE: Final = "platform.document.approve"
RESOURCE: Final = "document_revision"
R = RevisionStatus
S = ScanStatus
REVISION_MACHINE: Final = StateMachine(
    name="document_revision",
    states=frozenset(RevisionStatus.values),
    transitions={
        R.WORKING: frozenset({R.IN_REVIEW, R.REJECTED}),
        R.IN_REVIEW: frozenset({R.APPROVED, R.REJECTED}),
        R.APPROVED: frozenset({R.SUPERSEDED}),
        R.REJECTED: frozenset(),
        R.SUPERSEDED: frozenset(),
    },
)
SCAN_MACHINE: Final = StateMachine(
    name="document_scan",
    states=frozenset(ScanStatus.values),
    transitions={
        S.QUARANTINED: frozenset({S.SCANNING}),
        # SCANNING -> QUARANTINED: scanner unavailable, the file goes back to the queue (TECH, never CLEAN)
        S.SCANNING: frozenset({S.CLEAN, S.REJECTED, S.QUARANTINED}),
        S.CLEAN: frozenset(),
        S.REJECTED: frozenset(),
    },
)


@dataclass(frozen=True)
class DownloadFile:
    data: bytes
    filename: str
    sha256: str
    headers: dict[str, str] = field(default_factory=dict)


def download_headers(filename: str, size: int) -> dict[str, str]:
    """Download-only metadata: attachment, never inline; no content sniffing; sandboxed if ever opened."""
    ascii_name = (
        "".join(ch if 32 <= ord(ch) < 127 and ch not in '"\\;' else "_" for ch in filename) or "download"
    )
    return {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": (
            f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
        ),
        "Content-Length": str(size),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'",
        "Cache-Control": "no-store",
    }


# --------------------------------------------------------------------------------------------- scopes
# Matrix v1.0, operator_terminal on platform.document.read/download: "○ approved, linked to own tasks"
# (REV-0111). ○ for documents means: the caller is the assignee of a live (not CANCELLED) task linked
# to the document (``related_type = "document"``), and only the CURRENT APPROVED, CLEAN revision is visible;
# a task that pins ``related_revision`` gives access to that revision number only while it is the current
# approved one. The document creator is not an "owner" in this sense (creators hold ● grants anyway).
def _linked_tasks(document_id: uuid.UUID) -> list[tuple[uuid.UUID, int | None]]:
    from platform_core.workflow.models import TaskStatus, WorkTask

    rows = (
        WorkTask.objects.filter(
            related_type="document", related_id=str(document_id), assignee_user__isnull=False
        )
        .exclude(status=TaskStatus.CANCELLED)
        .values_list("assignee_user_id", "related_revision")
    )
    return [(u, r) for u, r in rows if u is not None]


def document_scope(doc: Document) -> RecordScope:
    """Document level (getDocument / upload / submit): ○ owners only while an approved revision exists."""
    owners = {u for u, _r in _linked_tasks(doc.pk)} if doc.current_approved_revision_id is not None else set()
    return RecordScope(owners=frozenset(owners), sensitivity=doc.sensitivity)


def is_released_for_task_holders(rev: DocumentRevision) -> bool:
    return (
        rev.status == R.APPROVED
        and rev.scan_status == S.CLEAN
        and rev.document.current_approved_revision_id == rev.pk
    )


def revision_scope(rev: DocumentRevision) -> RecordScope:
    """Revision level (read / download): ○ only for the current approved, clean revision (REV-0111)."""
    owners: set[uuid.UUID] = set()
    if is_released_for_task_holders(rev):
        owners = {
            u for u, pinned in _linked_tasks(rev.document_id) if pinned is None or pinned == rev.revision_no
        }
    return RecordScope(owners=frozenset(owners), sensitivity=rev.document.sensitivity)


def _own_task_links(user_id: uuid.UUID) -> list[tuple[uuid.UUID, int | None]]:
    from platform_core.workflow.models import TaskStatus, WorkTask

    out: list[tuple[uuid.UUID, int | None]] = []
    rows = (
        WorkTask.objects.filter(related_type="document", assignee_user_id=user_id)
        .exclude(status=TaskStatus.CANCELLED)
        .values_list("related_id", "related_revision")
    )
    for rid, rev_no in rows:
        try:
            out.append((uuid.UUID(rid), rev_no))
        except ValueError:
            continue
    return out


def revision_list_q(caller: Caller, action: str = "platform.document.read") -> Q:
    """List scoping of revisions = the object check :func:`revision_scope` + ``decide`` (REV-0111/0112)."""
    from platform_core.authz import policy as P

    grants = P.effective_grants(caller.user_id, action)
    facts = P.ScopeFacts(caller.user_id)
    links = _own_task_links(caller.user_id)
    own = P.MATCH_NONE
    for doc_id, pinned in links:
        own = own | (Q(document_id=doc_id) & (P.MATCH_ALL if pinned is None else Q(revision_no=pinned)))
    own = own & Q(status=R.APPROVED, scan_status=S.CLEAN, document__current_approved_revision=F("pk"))
    q = P.MATCH_NONE
    for g in grants:
        q = q | P.grant_q(
            g,
            facts,
            caller.user_id,
            unit_field=None,
            owner_fields=(),
            sensitivity_field="document__sensitivity",
        )
        if g.mode in (GrantMode.OWN, GrantMode.OWN_AND_OWN_UNIT):
            q = q | (own & P.sensitivity_q(g, "document__sensitivity"))
    return q


def document_list_q(caller: Caller, action: str = "platform.document.read") -> Q:
    """List scoping of documents, equal to :func:`document_scope` + ``decide``."""
    from platform_core.authz import policy as P

    grants = P.effective_grants(caller.user_id, action)
    facts = P.ScopeFacts(caller.user_id)
    own = Q(pk__in=[d for d, _r in _own_task_links(caller.user_id)], current_approved_revision__isnull=False)
    q = P.MATCH_NONE
    for g in grants:
        q = q | P.grant_q(
            g, facts, caller.user_id, unit_field=None, owner_fields=(), sensitivity_field="sensitivity"
        )
        if g.mode in (GrantMode.OWN, GrantMode.OWN_AND_OWN_UNIT):
            q = q | (own & P.sensitivity_q(g, "sensitivity"))
    return q


def get_revision(caller: Caller, revision_id: uuid.UUID) -> DocumentRevision:
    """Revision read (``platform.document.read``) with the same scope as download."""
    action = "platform.document.read"
    require_permission(caller, action)
    rev = DocumentRevision.objects.select_related("document").filter(pk=revision_id).first()
    if rev is None:
        raise NotFound()
    require_record(caller, action, revision_scope(rev))
    return rev


def _reason(text: str) -> str:
    value = text.strip()
    if len(value) < 3:
        raise ValidationFailed("a reason is required", errors=[FieldError("reason", "REQUIRED")])
    return value[:500]


def _rev_view(r: DocumentRevision) -> dict[str, object]:
    return {
        "document_id": str(r.document_id),
        "revision_no": r.revision_no,
        "status": r.status,
        "scan_status": r.scan_status,
        "scan_finding": r.scan_finding,
        "sha256": r.sha256,
        "size_bytes": r.size_bytes,
        "upload_extension": r.upload_type_id,
    }


def _audit(
    uow: UnitOfWork, verb: str, r: DocumentRevision, *, before: dict[str, object] | None, reason: str = ""
) -> None:
    uow.audit(
        action=f"platform.document.revision.{verb}",
        resource_type="platform.document_revision",
        resource_id=str(r.pk),
        resource_version=r.row_version,
        before=before,
        after=_rev_view(r),
        reason=reason,
        scope={"document_id": str(r.document_id)},
    )
    uow.emit(
        event_type="platform.document.revision.changed",
        aggregate_type="platform.document_revision",
        aggregate_id=str(r.pk),
        aggregate_version=r.row_version,
        payload={
            "id": str(r.pk),
            "document_id": str(r.document_id),
            "status": r.status,
            "scan_status": r.scan_status,
        },
    )


# -------------------------------------------------------------------------------------------- commands
def create_document(
    caller: Caller,
    *,
    document_type: str,
    title_fa: str,
    sensitivity: str,
    owner_entity_type: str = "",
    owner_entity_id: str = "",
    request_id: uuid.UUID | None = None,
) -> Document:
    require_permission(caller, "platform.document.create")
    if sensitivity not in ("S1", "S2", "S3"):
        raise ValidationFailed(errors=[FieldError("sensitivity", "INVALID")])
    with unit_of_work(caller.context(request_id)) as uow:
        doc = Document.objects.create(
            document_type=document_type,
            title_fa=title_fa,
            sensitivity=sensitivity,
            owner_entity_type=owner_entity_type,
            owner_entity_id=owner_entity_id,
            created_by_id=caller.user_id,
            updated_by_id=caller.user_id,
        )
        doc.refresh_from_db()
        uow.audit(
            action="platform.document.create",
            resource_type="platform.document",
            resource_id=str(doc.pk),
            resource_version=doc.row_version,
            after={"document_type": document_type, "sensitivity": sensitivity},
        )
        uow.emit(
            event_type="platform.document.created",
            aggregate_type="platform.document",
            aggregate_id=str(doc.pk),
            aggregate_version=doc.row_version,
            payload={"id": str(doc.pk)},
        )
    return doc


def _lock_doc(document_id: uuid.UUID) -> Document:
    doc = Document.objects.select_for_update().filter(pk=document_id).first()
    if doc is None:
        raise NotFound()
    return doc


def upload_revision(
    caller: Caller,
    document_id: uuid.UUID,
    *,
    filename: str,
    data: bytes,
    change_note: str = "",
    request_id: uuid.UUID | None = None,
) -> DocumentRevision:
    import hashlib

    action = "platform.document.upload"
    require_permission(caller, action)
    doc = Document.objects.filter(pk=document_id).first()
    if doc is None:
        raise NotFound()
    require_record(caller, action, document_scope(doc))
    if len(data) > effective_int("document_upload_max_bytes"):
        raise PayloadTooLarge("the file exceeds document_upload_max_bytes (DEC-053)")
    name = filetypes.sanitise_filename(filename)
    utype = UploadType.objects.filter(extension=filetypes.extension_of(name), is_allowed=True).first()
    if utype is None:
        raise FileTypeNotAllowed(
            "the file type is not in the allow-list (DEC-053)",
            errors=[FieldError("file", "TYPE_NOT_ALLOWED")],
        )
    filetypes.check_content(utype.content_check, data)
    key = storage.new_storage_key()
    key_ref = storage.write(key, data)  # encrypted bytes first; removed again if the DB write fails
    try:
        with unit_of_work(caller.context(request_id)) as uow:
            doc = _lock_doc(document_id)
            last = DocumentRevision.objects.filter(document=doc).order_by("-revision_no").first()
            obj = StoredObject.objects.create(
                storage_key=key,
                volume=storage.volume_name(),
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                encryption_scheme="ENCRYPTED_VOLUME",
                key_ref=key_ref,
            )
            rev = DocumentRevision.objects.create(
                document=doc,
                revision_no=(last.revision_no + 1) if last else 1,
                parent_revision=last,
                stored_object=obj,
                upload_type=utype,
                sha256=obj.sha256,
                size_bytes=obj.size_bytes,
                media_type_detected=utype.media_type,
                original_name=name,
                change_note=change_note.strip()[:500],
                uploaded_by_id=caller.user_id,
            )
            rev.refresh_from_db()
            _audit(uow, "upload", rev, before=None)
    except BaseException:
        storage.delete(key)
        raise
    return rev


def _lock_rev(revision_id: uuid.UUID) -> DocumentRevision:
    rev = (
        DocumentRevision.objects.select_for_update()
        .select_related("document", "stored_object")
        .filter(pk=revision_id)
        .first()
    )
    if rev is None:
        raise NotFound()
    return rev


def _system_ctx(request_id: uuid.UUID | None) -> RequestContext:
    return RequestContext(Actor.system(), request_id=request_id)


def scan_revision(
    revision_id: uuid.UUID, scanner: Scanner | None, *, request_id: uuid.UUID | None = None
) -> str:
    """One scan of one QUARANTINED revision. Returns the resulting scan status."""
    if scanner is None:
        return S.QUARANTINED  # no scanner configured: stays quarantined
    claimed = False
    with unit_of_work_or_nothing(_system_ctx(request_id)) as uow:
        rev = _lock_rev(revision_id)
        if rev.scan_status != S.QUARANTINED:
            raise NothingToDo()
        before = _rev_view(rev)
        DocumentRevision.objects.filter(pk=rev.pk).update(scan_status=S.SCANNING)
        rev.refresh_from_db()
        _audit(uow, "scan_start", rev, before=before)
        claimed = True
    if not claimed:
        return DocumentRevision.objects.get(pk=revision_id).scan_status
    obj = StoredObject.objects.get(pk=rev.stored_object_id)
    try:
        data = storage.read(obj.storage_key, key_ref=obj.key_ref)
        filetypes.check_content(rev.upload_type.content_check, data)  # re-check at scan time
        verdict = scanner.scan(data)
        result = (
            (S.CLEAN, "", verdict.scanner_version)
            if verdict.clean
            else (S.REJECTED, verdict.finding, verdict.scanner_version)
        )
    except FileTypeNotAllowed as exc:
        result = (S.REJECTED, exc.errors[0].code if exc.errors else "MAGIC_MISMATCH", "content-check")
    except DependencyUnavailable:
        result = (S.QUARANTINED, "", "")
    status, finding, version = result
    with unit_of_work(_system_ctx(request_id)) as uow:
        rev = _lock_rev(revision_id)
        SCAN_MACHINE.assert_transition(rev.scan_status, status)
        before = _rev_view(rev)
        now = db_now()
        if status == S.QUARANTINED:
            DocumentRevision.objects.filter(pk=rev.pk).update(scan_status=S.QUARANTINED)
        elif status == S.CLEAN:
            DocumentRevision.objects.filter(pk=rev.pk).update(
                scan_status=S.CLEAN, scanned_at=now, scanner_version=version[:64]
            )
        else:
            REVISION_MACHINE.assert_transition(rev.status, R.REJECTED)
            DocumentRevision.objects.filter(pk=rev.pk).update(
                scan_status=S.REJECTED,
                status=R.REJECTED,
                scan_finding=finding[:200],
                scanned_at=now,
                scanner_version=version[:64],
            )
            StoredObject.objects.filter(pk=rev.stored_object_id).update(
                purge_after=now + effective_days("document_rejected_quarantine_days")
            )
        rev.refresh_from_db()
        _audit(uow, "scan_result", rev, before=before, reason=finding)
    return status


def scan_pending(
    scanner: Scanner | None = None, *, limit: int = 50, request_id: uuid.UUID | None = None
) -> dict[str, int]:
    """Housekeeping job function: scan QUARANTINED revisions (oldest first)."""
    use = scanner if scanner is not None else configured_scanner()
    counts: dict[str, int] = {}
    for rid in (
        DocumentRevision.objects.filter(scan_status=S.QUARANTINED)
        .order_by("uploaded_at")
        .values_list("pk", flat=True)[:limit]
    ):
        status = scan_revision(rid, use, request_id=request_id)
        counts[status] = counts.get(status, 0) + 1
    return counts


def submit_revision(
    caller: Caller, revision_id: uuid.UUID, *, request_id: uuid.UUID | None = None
) -> DocumentRevision:
    """WORKING -> IN_REVIEW (scan CLEAN), raising the approval request (DEC-032)."""
    action = "platform.document.update"
    require_permission(caller, action)
    with unit_of_work(caller.context(request_id)) as uow:
        rev = _lock_rev(revision_id)
        require_record(caller, action, document_scope(rev.document))
        if rev.scan_status != S.CLEAN:
            raise FileNotReleased("only a CLEAN revision can be submitted for review")
        REVISION_MACHINE.assert_transition(rev.status, R.IN_REVIEW)
        before = _rev_view(rev)
        req = approvals.raise_request(
            uow,
            action=APPROVE,
            resource_type=RESOURCE,
            resource_id=str(rev.pk),
            resource_revision=rev.revision_no,
            requested_by=caller.user_id,
        )
        DocumentRevision.objects.filter(pk=rev.pk).update(
            status=R.IN_REVIEW, submitted_by_id=caller.user_id, submitted_at=db_now(), approval_request=req
        )
        rev.refresh_from_db()
        _audit(uow, "submit", rev, before=before)
    return rev


def approve_revision(
    caller: Caller, revision_id: uuid.UUID, *, note: str = "", request_id: uuid.UUID | None = None
) -> DocumentRevision:
    rev = DocumentRevision.objects.filter(pk=revision_id).first()
    if rev is None or rev.approval_request_id is None:
        raise NotFound()
    approvals.approve(
        caller,
        rev.approval_request_id,
        note=note,
        expected_revision=rev.revision_no,
        request_ctx_id=request_id,
    )
    rev.refresh_from_db()
    return rev


def reject_revision(
    caller: Caller, revision_id: uuid.UUID, *, reason: str, request_id: uuid.UUID | None = None
) -> DocumentRevision:
    rev = DocumentRevision.objects.filter(pk=revision_id).first()
    if rev is None or rev.approval_request_id is None:
        raise NotFound()
    approvals.reject(
        caller,
        rev.approval_request_id,
        note=reason,
        expected_revision=rev.revision_no,
        request_ctx_id=request_id,
    )
    rev.refresh_from_db()
    return rev


# approval handler for document revisions (decided through workflow.approvals with platform.document.approve)
def _on_approved(uow: UnitOfWork, req: ApprovalRequest, decided_by: uuid.UUID | None) -> None:
    rev = _lock_rev(uuid.UUID(req.resource_id))
    if rev.uploaded_by_id == decided_by:
        raise SelfApprovalForbidden()
    REVISION_MACHINE.assert_transition(rev.status, R.APPROVED)
    doc = _lock_doc(rev.document_id)
    before = _rev_view(rev)
    now = db_now()
    for old in (
        DocumentRevision.objects.select_for_update()
        .filter(document=doc, status=R.APPROVED)
        .exclude(pk=rev.pk)
    ):
        old_before = _rev_view(old)
        DocumentRevision.objects.filter(pk=old.pk).update(status=R.SUPERSEDED)
        old.refresh_from_db()
        _audit(uow, "supersede", old, before=old_before)
    DocumentRevision.objects.filter(pk=rev.pk).update(
        status=R.APPROVED, decided_by_id=decided_by, decided_at=now
    )
    Document.objects.filter(pk=doc.pk).update(current_approved_revision_id=rev.pk, updated_by_id=decided_by)
    rev.refresh_from_db()
    _audit(uow, "approve", rev, before=before)
    # approvals never carry over: other pending requests of older revisions of this document are superseded
    for other in DocumentRevision.objects.filter(document=doc, status=R.IN_REVIEW).exclude(pk=rev.pk):
        approvals.close_pending_for(
            uow, RESOURCE, str(other.pk), ApprovalStatus.SUPERSEDED, note="newer revision approved"
        )


def _on_closed(uow: UnitOfWork, req: ApprovalRequest, by: uuid.UUID | None) -> None:
    rev = DocumentRevision.objects.select_for_update().filter(pk=uuid.UUID(req.resource_id)).first()
    if rev is None or rev.status != R.IN_REVIEW:
        return
    before = _rev_view(rev)
    reason = (
        req.decision_note
        if req.status == ApprovalStatus.REJECTED
        else f"approval request {req.status.lower()}"
    )
    if req.status == ApprovalStatus.REJECTED:
        DocumentRevision.objects.filter(pk=rev.pk).update(
            status=R.REJECTED, decided_by_id=by, decided_at=db_now(), reject_reason=reason[:500]
        )
    else:  # withdrawn / expired / superseded: no IN_REVIEW -> WORKING edge exists; the revision stays
        return
    rev.refresh_from_db()
    _audit(uow, "reject", rev, before=before, reason=reason)


def _makers(req: ApprovalRequest) -> set[uuid.UUID]:
    rev = DocumentRevision.objects.filter(pk=uuid.UUID(req.resource_id)).first()
    return {rev.uploaded_by_id} if rev is not None else set()


approvals.register_resource_handler(RESOURCE, approvals.ResourceHandler(_on_approved, _on_closed, _makers))


def download(caller: Caller, revision_id: uuid.UUID) -> DownloadFile:
    action = "platform.document.download"
    require_permission(caller, action)
    rev = DocumentRevision.objects.select_related("document", "stored_object").filter(pk=revision_id).first()
    if rev is None:
        raise NotFound()
    require_record(caller, action, revision_scope(rev))
    if rev.scan_status != S.CLEAN or rev.stored_object.bytes_purged_at is not None:
        raise FileNotReleased()
    data = storage.read(rev.stored_object.storage_key, key_ref=rev.stored_object.key_ref)
    return DownloadFile(
        data=data,
        filename=rev.original_name,
        sha256=rev.sha256,
        headers=download_headers(rev.original_name, len(data)),
    )


def purge_rejected(
    *, limit: int = 200, request_id: uuid.UUID | None = None, now: datetime | None = None
) -> int:
    """Housekeeping job function (DEC-053): delete the bytes of rejected uploads after the quarantine period;
    metadata and SHA-256 stay (``bytes_purged_at`` is set once). ``now`` is injectable for tests only."""
    now = now or db_now()
    keys = list(
        StoredObject.objects.filter(
            purge_after__isnull=False, purge_after__lte=now, bytes_purged_at__isnull=True
        )
        .filter(Q(revision__scan_status=S.REJECTED))
        .values_list("storage_key", flat=True)[:limit]
    )
    n = 0
    for key in keys:
        with unit_of_work_or_nothing(_system_ctx(request_id)) as uow:
            obj = (
                StoredObject.objects.select_for_update(skip_locked=True)
                .filter(pk=key, bytes_purged_at__isnull=True)
                .first()
            )
            if obj is None:
                raise NothingToDo()
            StoredObject.objects.filter(pk=key).update(bytes_purged_at=now)
            uow.audit(
                action="platform.document.object.purge",
                resource_type="platform.stored_object",
                resource_id=key[:64],
                after={"sha256": obj.sha256, "size_bytes": obj.size_bytes},
                reason="rejected upload: quarantine period over (DEC-053)",
            )
            uow.emit(
                event_type="platform.document.object.purged",
                aggregate_type="platform.stored_object",
                aggregate_id=key[:64],
                aggregate_version=1,
                payload={"sha256": obj.sha256},
            )
            # REV-0115: bytes are deleted only after the marker is committed (idempotent delete); a failed
            # commit leaves bytes and no marker, and the next run purges again.
            transaction.on_commit(functools.partial(storage.delete, key))
            n += 1
    return n


def update_document(
    caller: Caller,
    document_id: uuid.UUID,
    *,
    expected_version: int,
    title_fa: str | None = None,
    legacy_location_ref: str | None = None,
    clear_legacy_location_ref: bool = False,
    request_id: uuid.UUID | None = None,
) -> Document:
    """``updateDocument`` (01.4): metadata only (title, legacy location text, C-29); type, sensitivity and
    revisions never change here. Same record scope as ``getDocument`` (404 outside it)."""
    from platform_core.engine.errors import VersionConflict

    action = "platform.document.update"
    require_permission(caller, action)
    with unit_of_work(caller.context(request_id)) as uow:
        doc = _lock_doc(document_id)
        require_record(caller, action, document_scope(doc))
        if doc.row_version != expected_version:
            raise VersionConflict()
        values: dict[str, object] = {}
        if title_fa is not None:
            if not title_fa.strip():
                raise ValidationFailed(errors=[FieldError("title_fa", "REQUIRED")])
            values["title_fa"] = title_fa.strip()[:200]
        if clear_legacy_location_ref:
            values["legacy_location_ref"] = ""
        elif legacy_location_ref is not None:
            values["legacy_location_ref"] = legacy_location_ref.strip()[:500]
        if not values:
            raise ValidationFailed("nothing to change", errors=[FieldError("body", "NO_CHANGE")])
        with db_rules():
            Document.objects.filter(pk=doc.pk).update(updated_by_id=caller.user_id, **values)
        doc.refresh_from_db()
        uow.audit(
            action="platform.document.update",
            resource_type="platform.document",
            resource_id=str(doc.pk),
            resource_version=doc.row_version,
            after={"changed": sorted(values)},
        )
        uow.emit(
            event_type="platform.document.updated",
            aggregate_type="platform.document",
            aggregate_id=str(doc.pk),
            aggregate_version=doc.row_version,
            payload={"id": str(doc.pk)},
        )
    return doc


def record_download(caller: Caller, rev: DocumentRevision, *, request_id: uuid.UUID | None = None) -> None:
    """Every download is audited (openapi ``downloadDocumentRevision``); no outbox event (a read)."""
    with unit_of_work(caller.context(request_id), require_event=False) as uow:
        uow.audit(
            action="platform.document.download",
            resource_type="platform.document_revision",
            resource_id=str(rev.pk),
            resource_version=rev.row_version,
            scope={"document_id": str(rev.document_id)},
            after={"sha256": rev.sha256, "size_bytes": rev.size_bytes},
        )
