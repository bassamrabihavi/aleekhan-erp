"""``documents`` endpoints (DEC-053 / DEC-032 / SEC-03).

Upload (``multipart/form-data``): size limit ``document_upload_max_bytes`` (413), allow-list + magic bytes +
macro check (415), encrypted at rest, revision WORKING / QUARANTINED (202). Nothing is ever executed, parsed
beyond the content checks or rendered. The idempotency record hashes the file digest and metadata, never the
bytes. Download: only CLEAN and not purged (409 ``FILE_NOT_RELEASED``), always ``Content-Disposition:
attachment`` + ``application/octet-stream`` + ``X-Content-Type-Options: nosniff`` + sandbox CSP; every
download is audited. A revision id under another document's path is 404 (no cross-document access).
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Final

from django.http import HttpResponse
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.authz.policy import Caller
from platform_core.documents import service as docs
from platform_core.documents.models import Document, DocumentRevision
from platform_core.engine.errors import (
    FieldError,
    NotFound,
    PayloadTooLarge,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.engine.idempotency import StoredResponse
from platform_core.params.values import effective_int

from . import serializers as S
from .common import (
    UUID_RE,
    Phase01View,
    body_of,
    etag_response,
    if_match,
    in_scope,
    lock_checked,
    paginate,
    query_pattern,
    stored,
    write,
)

READ: Final = "platform.document.read"
DOWNLOAD: Final = "platform.document.download"
CREATE: Final = "platform.document.create"
UPDATE: Final = "platform.document.update"
UPLOAD: Final = "platform.document.upload"
APPROVE: Final = "platform.document.approve"
UPLOAD_FIELDS: Final = frozenset({"file", "change_note", "parent_revision_id"})
KEY_RE: Final = r"^[a-z][a-z0-9_]{2,63}$"
ENTITY_TYPE_RE: Final = r"^[a-z][a-z0-9_]{0,63}$"


def _doc_or_404(caller: Caller, action: str, document_id: uuid.UUID) -> Document:
    doc = Document.objects.filter(pk=document_id).first()
    if doc is None:
        raise NotFound()
    in_scope(caller, action, docs.document_scope(doc))
    return doc


class DocumentsView(Phase01View):
    required_action = READ
    write_action = CREATE

    def get(self, request: Request) -> Response:
        caller = self.caller()
        qs = Document.objects.filter(docs.document_list_q(caller, READ))
        dtype = query_pattern(request, "document_type", KEY_RE, 64)
        etype = query_pattern(request, "entity_type", ENTITY_TYPE_RE, 64)
        eid = request.query_params.get("entity_id")
        if eid is not None and not 1 <= len(eid) <= 64:
            raise ValidationFailed(errors=[FieldError("entity_id", "OUT_OF_RANGE")])
        if dtype:
            qs = qs.filter(document_type=dtype)
        if etype:
            qs = qs.filter(owner_entity_type=etype)
        if eid:
            qs = qs.filter(owner_entity_id=eid)
        return paginate(request, self, qs, S.document)

    def post(self, request: Request) -> Response:
        data = body_of(request, "DocumentCreateRequest")
        owner = data.get("owner_entity") or {}

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            doc = docs.create_document(
                caller,
                document_type=data["document_type"],
                title_fa=data["title_fa"],
                sensitivity=data["sensitivity"],
                owner_entity_type=owner.get("entity_type", ""),
                owner_entity_id=owner.get("entity_id", ""),
                request_id=rid,
            )
            if data.get("legacy_location_ref"):
                doc = docs.update_document(
                    caller,
                    doc.pk,
                    expected_version=doc.row_version,
                    legacy_location_ref=data["legacy_location_ref"],
                    request_id=rid,
                )
            return stored(201, S.document(doc), etag_version=doc.row_version)

        return write(self, run)


class DocumentView(Phase01View):
    required_action = READ
    write_action = UPDATE

    def get(self, request: Request, document_id: uuid.UUID) -> Response:
        doc = _doc_or_404(self.caller(), READ, document_id)
        return etag_response(S.document(doc), doc.row_version)

    def patch(self, request: Request, document_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "DocumentUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(
                Document,
                document_id,
                scope=lambda d: in_scope(caller, UPDATE, docs.document_scope(d)),
                expected=expected,
            )
            doc = docs.update_document(
                caller,
                document_id,
                expected_version=expected,
                title_fa=data.get("title_fa"),
                legacy_location_ref=data.get("legacy_location_ref"),
                clear_legacy_location_ref="legacy_location_ref" in data
                and data["legacy_location_ref"] is None,
                request_id=rid,
            )
            return stored(200, S.document(doc), etag_version=doc.row_version)

        return write(self, run)


class RevisionsView(Phase01View):
    """GET ``listDocumentRevisions`` / POST ``uploadDocumentRevision`` (multipart, 202 QUARANTINED)."""

    required_action = READ
    write_action = UPLOAD
    parser_classes = [MultiPartParser]

    def get(self, request: Request, document_id: uuid.UUID) -> Response:
        caller = self.caller()
        _doc_or_404(caller, READ, document_id)
        qs = DocumentRevision.objects.select_related("document").filter(
            docs.revision_list_q(caller, READ), document_id=document_id
        )
        return paginate(request, self, qs, S.revision)

    def post(self, request: Request, document_id: uuid.UUID) -> Response:
        caller = self.caller()
        _doc_or_404(caller, UPLOAD, document_id)  # scope before any byte is read (404 outside scope)
        form: Any = request.data
        unknown = sorted((set(form.keys()) | set(request.FILES.keys())) - UPLOAD_FIELDS)
        if unknown:
            raise ValidationFailed(errors=[FieldError(str(k)[:64], "UNKNOWN_FIELD") for k in unknown])
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationFailed(errors=[FieldError("file", "REQUIRED")])
        if upload.size is None or upload.size > effective_int("document_upload_max_bytes"):
            raise PayloadTooLarge("the file exceeds document_upload_max_bytes (DEC-053)")
        note = form.get("change_note", "")
        if not isinstance(note, str) or len(note) > 500:
            raise ValidationFailed(errors=[FieldError("change_note", "TOO_LONG")])
        parent_raw = form.get("parent_revision_id")
        if parent_raw is not None and (not isinstance(parent_raw, str) or not UUID_RE.fullmatch(parent_raw)):
            raise ValidationFailed(errors=[FieldError("parent_revision_id", "INVALID_UUID")])
        data = upload.read()
        filename = str(upload.name or "upload")
        digest = hashlib.sha256(data).hexdigest()

        def run(c: Caller, rid: uuid.UUID) -> StoredResponse:
            if parent_raw is not None:
                last = (
                    DocumentRevision.objects.filter(document_id=document_id).order_by("-revision_no").first()
                )
                if last is None or str(last.pk) != parent_raw.lower():
                    raise StateTransitionNotAllowed("parent_revision_id is not the latest revision")
            rev = docs.upload_revision(
                c, document_id, filename=filename, data=data, change_note=note, request_id=rid
            )
            return stored(202, S.revision(rev), etag_version=rev.row_version)

        hashed = {"filename": filename, "sha256": digest, "size": len(data), "change_note": note,
                  "parent_revision_id": parent_raw}  # fmt: skip
        return write(self, run, body=hashed, hashed_body=True)


def _rev_in_doc(document_id: uuid.UUID, revision_id: uuid.UUID) -> DocumentRevision:
    rev = (
        DocumentRevision.objects.select_related("document")
        .filter(pk=revision_id, document_id=document_id)
        .first()
    )
    if rev is None:
        raise NotFound()  # missing, or a revision of another document
    return rev


class RevisionView(Phase01View):
    required_action = READ

    def get(self, request: Request, document_id: uuid.UUID, revision_id: uuid.UUID) -> Response:
        _rev_in_doc(document_id, revision_id)
        rev = docs.get_revision(self.caller(), revision_id)
        return etag_response(S.revision(rev), rev.row_version)


class RevisionContentView(Phase01View):
    required_action = DOWNLOAD

    def get(self, request: Request, document_id: uuid.UUID, revision_id: uuid.UUID) -> HttpResponse:
        caller = self.caller()
        rev = _rev_in_doc(document_id, revision_id)
        file = docs.download(caller, revision_id)
        docs.record_download(caller, rev, request_id=self.rid())
        response = HttpResponse(file.data, content_type="application/octet-stream")
        for key, value in file.headers.items():
            response[key] = value
        response["ETag"] = f'"{rev.row_version}"'
        return response


def _rev_scope(caller: Caller, action: str, document_id: uuid.UUID) -> Any:
    def check(rev: DocumentRevision) -> None:
        if rev.document_id != document_id:
            raise NotFound()
        in_scope(caller, action, docs.document_scope(rev.document))

    return check


def _revision_action(action: str, schema: str, call: Any) -> type[Phase01View]:
    class _View(Phase01View):
        required_action = action

        def post(self, request: Request, document_id: uuid.UUID, revision_id: uuid.UUID) -> Response:
            expected = if_match(self)
            data = body_of(request, schema)

            def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
                lock_checked(
                    DocumentRevision,
                    revision_id,
                    scope=_rev_scope(caller, action, document_id),
                    expected=expected,
                )
                rev = call(caller, revision_id, data, rid)
                rev.refresh_from_db()
                return stored(200, S.revision(rev), etag_version=rev.row_version)

            return write(self, run)

    return _View


SubmitRevisionView = _revision_action(
    UPDATE, "OptionalNoteRequest", lambda c, i, d, r: docs.submit_revision(c, i, request_id=r)
)
ApproveRevisionView = _revision_action(
    APPROVE,
    "OptionalNoteRequest",
    lambda c, i, d, r: docs.approve_revision(c, i, note=str(d.get("note") or ""), request_id=r),
)
RejectRevisionView = _revision_action(
    APPROVE, "ReasonRequest", lambda c, i, d, r: docs.reject_revision(c, i, reason=d["reason"], request_id=r)
)
