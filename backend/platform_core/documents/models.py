"""Documents, revisions and encrypted file references (PHASE_01 / 01.2; SEC-03, DEC-053 APPROVED).

* ``UploadType``     allow-list of file types (DEC-053: PDF, PNG, JPG, DXF, XLSX without macros). A CHECK
  makes macro/executable/script extensions impossible to register at all (``ck_upload_type_never_forbidden``).
* ``StoredObject``   the bytes' location: random storage key on the encrypted server folder (DEC-053 ST-A),
  size,
  server-computed SHA-256, key reference (key material never in the DB). Immutable except the purge marker.
* ``Document`` / ``DocumentRevision``  approval state + scan state (STATE_TRANSITIONS 4.6). Approved revisions
  are immutable; approver != uploader (DEC-032 maker-checker); IN_REVIEW/APPROVED only when scan CLEAN; a
  rejected scan keeps metadata + hash and schedules the byte purge (DEC-053: 30 days quarantine).
  Size limit: trigger against parameter ``document_upload_max_bytes``. Files are download-only (never rendered
  inline) - an API/UI rule of 01.4/01.5, nothing to store here.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint
from django.db.models.functions import Now

from platform_core.schema_common import (
    DECISION_ID_PATTERN,
    ENTITY_TYPE_PATTERN,
    SHA256_PATTERN,
    STORAGE_KEY_PATTERN,
    SYSTEM_KEY_PATTERN,
    Provenance,
    Sensitivity,
    in_values,
    min_length,
)

# DEC-053: "XLSM/DOCM/EXE/اسکریپت هرگز" - extensions that can never be registered as an upload type.
FORBIDDEN_EXTENSIONS = (
    "xlsm",
    "xltm",
    "xlam",
    "xlsb",
    "docm",
    "dotm",
    "pptm",
    "potm",
    "exe",
    "dll",
    "com",
    "scr",
    "msi",
    "bat",
    "cmd",
    "ps1",
    "vbs",
    "vbe",
    "js",
    "jse",
    "wsf",
    "hta",
    "sh",
    "py",
    "jar",
    "html",
    "htm",
    "svg",
)


def _user_fk(*, null: bool = True) -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        "platform_core.User",
        on_delete=models.PROTECT,
        null=null,
        blank=null,
        related_name="+",
        db_index=False,
    )


class UploadType(models.Model):
    extension = models.CharField(max_length=8, primary_key=True)
    media_type = models.CharField(max_length=127)
    label_fa = models.CharField(max_length=100)
    # server-side content check the scanner pipeline must apply (magic bytes / container inspection)
    content_check = models.CharField(max_length=32)
    is_allowed = models.BooleanField(db_default=True)
    decision_id = models.CharField(max_length=7)
    provenance = models.CharField(
        max_length=16, choices=Provenance.choices, db_default=Provenance.MIGRATION_SEED
    )
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "platform_upload_type"
        constraints = [
            CheckConstraint(
                condition=Q(extension__regex=r"^[a-z0-9]{2,8}$"), name="ck_upload_type_extension_fmt"
            ),
            CheckConstraint(
                condition=~in_values("extension", FORBIDDEN_EXTENSIONS), name="ck_upload_type_never_forbidden"
            ),
            CheckConstraint(
                condition=Q(media_type__regex=r"^[a-z]+/[a-z0-9.+-]+$"), name="ck_upload_type_media_type_fmt"
            ),
            CheckConstraint(
                condition=in_values("content_check", ["PDF", "PNG", "JPEG", "DXF", "OOXML_NO_MACRO"]),
                name="ck_upload_type_content_check",
            ),
            CheckConstraint(
                condition=Q(decision_id__regex=DECISION_ID_PATTERN), name="ck_upload_type_decision_fmt"
            ),
            CheckConstraint(
                condition=in_values("provenance", [Provenance.MIGRATION_SEED]),
                name="ck_upload_type_provenance",
            ),
        ]

    def __str__(self) -> str:
        return self.extension


class EncryptionScheme(models.TextChoices):
    ENCRYPTED_VOLUME = "ENCRYPTED_VOLUME", "Encrypted server folder/volume (DEC-053 ST-A)"


class StoredObject(models.Model):
    storage_key = models.CharField(max_length=64, primary_key=True)
    volume = models.CharField(max_length=64)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    encryption_scheme = models.CharField(max_length=20, choices=EncryptionScheme.choices)
    key_ref = models.CharField(max_length=64)
    created_at = models.DateTimeField(db_default=Now())
    purge_after = models.DateTimeField(null=True, blank=True)
    bytes_purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "platform_stored_object"
        constraints = [
            CheckConstraint(
                condition=Q(storage_key__regex=STORAGE_KEY_PATTERN), name="ck_stored_object_storage_key_fmt"
            ),
            CheckConstraint(
                condition=Q(volume__regex=SYSTEM_KEY_PATTERN), name="ck_stored_object_volume_fmt"
            ),
            CheckConstraint(condition=Q(size_bytes__gt=0), name="ck_stored_object_size_pos"),
            CheckConstraint(condition=Q(sha256__regex=SHA256_PATTERN), name="ck_stored_object_sha256_fmt"),
            CheckConstraint(
                condition=in_values("encryption_scheme", EncryptionScheme.values),
                name="ck_stored_object_encryption",
            ),
            CheckConstraint(condition=~Q(key_ref=""), name="ck_stored_object_key_ref_nonempty"),
            CheckConstraint(
                condition=Q(bytes_purged_at__isnull=True) | Q(purge_after__isnull=False),
                name="ck_stored_object_purge_scheduled",
            ),
        ]
        indexes = [
            models.Index(
                fields=["purge_after"],
                name="ix_stored_object_purge_due",
                condition=Q(purge_after__isnull=False, bytes_purged_at__isnull=True),
            ),
            models.Index(fields=["sha256"], name="ix_stored_object_sha256"),
        ]

    def __str__(self) -> str:
        return self.storage_key


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_type = models.CharField(max_length=64)
    title_fa = models.CharField(max_length=200)
    owner_entity_type = models.CharField(max_length=64, blank=True, default="")
    owner_entity_id = models.CharField(max_length=64, blank=True, default="")
    sensitivity = models.CharField(max_length=2, choices=Sensitivity.choices)
    current_approved_revision = models.ForeignKey(
        "platform_core.DocumentRevision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    legacy_location_ref = models.CharField(max_length=500, blank=True, default="")  # text only (C-29)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(db_default=Now())
    created_by = _user_fk(null=False)
    updated_by = _user_fk()
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_document"
        constraints = [
            CheckConstraint(
                condition=Q(document_type__regex=SYSTEM_KEY_PATTERN), name="ck_document_type_fmt"
            ),
            CheckConstraint(condition=~Q(title_fa=""), name="ck_document_title_nonempty"),
            CheckConstraint(
                condition=in_values("sensitivity", ["S1", "S2", "S3"]), name="ck_document_sensitivity"
            ),
            CheckConstraint(
                condition=Q(owner_entity_type="", owner_entity_id="")
                | (Q(owner_entity_type__regex=ENTITY_TYPE_PATTERN) & ~Q(owner_entity_id="")),
                name="ck_document_owner_ref",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_document_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["owner_entity_type", "owner_entity_id"], name="ix_document_owner"),
            models.Index(fields=["document_type"], name="ix_document_type"),
            models.Index(fields=["current_approved_revision"], name="ix_document_current_rev"),
            models.Index(fields=["created_by"], name="ix_document_created_by"),
            models.Index(fields=["updated_by"], name="ix_document_updated_by"),
        ]

    def __str__(self) -> str:
        return f"{self.document_type} {self.id}"


class RevisionStatus(models.TextChoices):
    WORKING = "WORKING", "Working"
    IN_REVIEW = "IN_REVIEW", "In review"
    APPROVED = "APPROVED", "Approved (immutable)"
    REJECTED = "REJECTED", "Rejected"
    SUPERSEDED = "SUPERSEDED", "Superseded by a newer approved revision"


class ScanStatus(models.TextChoices):
    QUARANTINED = "QUARANTINED", "Quarantined (not downloadable)"
    SCANNING = "SCANNING", "Scanning"
    CLEAN = "CLEAN", "Clean"
    REJECTED = "REJECTED", "Rejected by the scanner / type check"


class DocumentRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="revisions", db_index=False)
    revision_no = models.IntegerField()
    parent_revision = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    status = models.CharField(
        max_length=12, choices=RevisionStatus.choices, db_default=RevisionStatus.WORKING
    )
    scan_status = models.CharField(
        max_length=12, choices=ScanStatus.choices, db_default=ScanStatus.QUARANTINED
    )
    scan_finding = models.CharField(max_length=200, blank=True, default="")  # code only, never file content
    scanned_at = models.DateTimeField(null=True, blank=True)
    scanner_version = models.CharField(max_length=64, blank=True, default="")
    stored_object = models.OneToOneField(
        StoredObject, on_delete=models.PROTECT, related_name="revision", db_column="storage_key"
    )
    upload_type = models.ForeignKey(
        UploadType, on_delete=models.PROTECT, related_name="+", db_column="upload_extension", db_index=False
    )
    sha256 = models.CharField(max_length=64)
    size_bytes = models.BigIntegerField()
    media_type_detected = models.CharField(max_length=127, blank=True, default="")
    original_name = models.CharField(max_length=255)
    change_note = models.CharField(max_length=500, blank=True, default="")
    uploaded_by = _user_fk(null=False)
    uploaded_at = models.DateTimeField(db_default=Now())
    submitted_by = _user_fk()
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by = _user_fk()
    decided_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=500, blank=True, default="")
    approval_request = models.ForeignKey(
        "platform_core.ApprovalRequest",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    updated_at = models.DateTimeField(db_default=Now())
    row_version = models.BigIntegerField(db_default=1)

    class Meta:
        db_table = "platform_document_revision"
        constraints = [
            UniqueConstraint(fields=["document", "revision_no"], name="uq_document_revision_no"),
            UniqueConstraint(
                fields=["document"],
                condition=Q(status=RevisionStatus.APPROVED),
                name="uq_document_revision_one_approved",
            ),
            CheckConstraint(condition=Q(revision_no__gte=1), name="ck_document_revision_no_pos"),
            CheckConstraint(
                condition=in_values("status", RevisionStatus.values), name="ck_document_revision_status"
            ),
            CheckConstraint(
                condition=in_values("scan_status", ScanStatus.values), name="ck_document_revision_scan"
            ),
            CheckConstraint(
                condition=Q(sha256__regex=SHA256_PATTERN), name="ck_document_revision_sha256_fmt"
            ),
            CheckConstraint(condition=Q(size_bytes__gt=0), name="ck_document_revision_size_pos"),
            # sanitised basename: no path separators, no control characters, not empty
            CheckConstraint(
                condition=Q(original_name__regex=r"^[^/\\\x01-\x1f\x7f]+$"),
                name="ck_document_revision_name_basename",
            ),
            CheckConstraint(
                condition=~in_values(
                    "status", [RevisionStatus.IN_REVIEW, RevisionStatus.APPROVED, RevisionStatus.SUPERSEDED]
                )
                | Q(scan_status=ScanStatus.CLEAN),
                name="ck_document_revision_review_needs_clean",
            ),
            CheckConstraint(
                condition=~in_values("status", [RevisionStatus.APPROVED, RevisionStatus.SUPERSEDED])
                | Q(decided_by__isnull=False, decided_at__isnull=False),
                name="ck_document_revision_approved_has_decider",
            ),
            # DEC-032: maker != checker (approver/rejecter is never the uploader)
            CheckConstraint(
                condition=Q(decided_by__isnull=True) | ~Q(decided_by=F("uploaded_by")),
                name="ck_document_revision_maker_checker",
            ),
            CheckConstraint(
                condition=~Q(scan_status=ScanStatus.REJECTED) | Q(status=RevisionStatus.REJECTED),
                name="ck_document_revision_scan_reject",
            ),
            CheckConstraint(
                condition=~Q(status=RevisionStatus.REJECTED)
                | Q(scan_status=ScanStatus.REJECTED)
                | (Q(decided_by__isnull=False) & Q(min_length("reject_reason", 3))),
                name="ck_document_revision_reject_reason",
            ),
            CheckConstraint(
                condition=~in_values("scan_status", [ScanStatus.CLEAN, ScanStatus.REJECTED])
                | Q(scanned_at__isnull=False),
                name="ck_document_revision_scanned_at",
            ),
            CheckConstraint(condition=Q(row_version__gte=1), name="ck_document_revision_row_version_pos"),
        ]
        indexes = [
            models.Index(fields=["document", "status"], name="ix_document_revision_doc"),
            models.Index(fields=["scan_status"], name="ix_document_revision_scan"),
            models.Index(fields=["parent_revision"], name="ix_document_revision_parent"),
            models.Index(fields=["upload_type"], name="ix_document_revision_type"),
            models.Index(fields=["uploaded_by"], name="ix_document_revision_uploader"),
            models.Index(fields=["submitted_by"], name="ix_document_revision_submitter"),
            models.Index(fields=["decided_by"], name="ix_document_revision_decider"),
            models.Index(fields=["approval_request"], name="ix_document_revision_approval"),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} r{self.revision_no} [{self.status}/{self.scan_status}]"
