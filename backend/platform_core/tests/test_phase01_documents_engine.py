"""Documents and the upload quarantine pipeline (DEC-053, SEC-03) at service level: allow-list, magic bytes,
macro-free XLSX, size limit, encryption at rest, scanner (test double + ClamAV contract test), review with
maker-checker, download-only headers, purge of rejected bytes, nothing executed."""

from __future__ import annotations

import io
import os
import socket
import subprocess
import zipfile
from datetime import timedelta

import pytest

from platform_core.authz.policy import Caller
from platform_core.documents import filetypes, scanner, service, storage
from platform_core.documents.models import DocumentRevision, StoredObject
from platform_core.engine.context import db_now
from platform_core.engine.errors import (
    AccessDenied,
    DependencyUnavailable,
    FileNotReleased,
    FileTypeNotAllowed,
    MfaRequired,
    NotFound,
    PayloadTooLarge,
    SelfApprovalForbidden,
)
from platform_core.identity.models import User

from .engine_fixtures import caller, give_role, person

# The standard anti-malware test string (not malware; https://www.eicar.org), split so this file itself is not
# flagged by scanners that inspect the repository.
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
PDF = b"%PDF-1.7\n% synthetic test document\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _xlsx(*, macro: bool = False, content_type_macro: bool = False) -> bytes:
    buf = io.BytesIO()
    ct = (
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
        if content_type_macro
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    )
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            f'<Types><Override PartName="/xl/workbook.xml" ContentType="{ct}"/></Types>',
        )
        zf.writestr("xl/workbook.xml", "<workbook/>")
        if macro:
            zf.writestr("xl/vbaProject.bin", b"\x00synthetic")
    return buf.getvalue()


@pytest.fixture
def store(settings, tmp_path) -> None:
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = str(tmp_path)


@pytest.fixture
def no_exec(monkeypatch) -> None:
    """Nothing in the pipeline may start a process (SEC-03: files are never executed)."""

    def refuse(*a: object, **k: object) -> None:
        raise AssertionError("a process was started")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(os, "system", refuse)
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", refuse)


def _people() -> tuple[Caller, Caller, Caller]:
    ctl, apr, emp = person(), person(), person()
    give_role(ctl, "document_controller")
    give_role(apr, "document_approver")
    give_role(emp, "employee")
    return caller(ctl), caller(apr), caller(emp)


# --------------------------------------------------------------------------------------- content checks
@pytest.mark.parametrize(
    ("check", "data", "ok"),
    [
        ("PDF", PDF, True),
        ("PDF", PNG, False),
        ("PNG", PNG, True),
        ("JPEG", b"\xff\xd8\xff\xe0" + b"\x00" * 16, True),
        ("JPEG", PDF, False),
        ("DXF", b"  0\r\nSECTION\r\n  2\r\nHEADER\r\n", True),
        ("DXF", b"AutoCAD Binary DXF\r\n\x1a\x00rest", True),
        ("DXF", b"MZ\x90\x00 executable", False),
        ("OOXML_NO_MACRO", _xlsx(), True),
        ("OOXML_NO_MACRO", _xlsx(macro=True), False),
        ("OOXML_NO_MACRO", _xlsx(content_type_macro=True), False),
        ("OOXML_NO_MACRO", b"PK\x03\x04 not a zip", False),
        ("UNKNOWN", PDF, False),
    ],
)
def test_content_checks(check: str, data: bytes, ok: bool) -> None:
    if ok:
        filetypes.check_content(check, data)
    else:
        with pytest.raises(FileTypeNotAllowed):
            filetypes.check_content(check, data)


def test_zip_bomb_guard() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", b"\x00" * (20 * 1024 * 1024))  # compresses ~1000:1
    with pytest.raises(FileTypeNotAllowed) as exc:
        filetypes.check_content("OOXML_NO_MACRO", buf.getvalue())
    assert exc.value.errors[0].code == "CONTAINER_TOO_COMPLEX"


def test_filename_sanitising() -> None:
    assert filetypes.sanitise_filename("..\\..\\windows\\evil.pdf") == "evil.pdf"
    assert filetypes.sanitise_filename("dir/sub/plan\x00.dxf") == "plan.dxf"
    with pytest.raises(FileTypeNotAllowed):
        filetypes.sanitise_filename("../")


# ---------------------------------------------------------------------------------------- upload
@pytest.mark.django_db
def test_upload_refusals_store_nothing(store, no_exec) -> None:
    ctl, _apr, emp = _people()
    doc = service.create_document(ctl, document_type="syn_drawing", title_fa="نقشه ساختگی", sensitivity="S1")
    with pytest.raises(AccessDenied):
        service.upload_revision(emp, doc.pk, filename="a.pdf", data=PDF)
    for name, data, code in (
        ("macro.xlsm", _xlsx(macro=True), "TYPE_NOT_ALLOWED"),
        ("tool.exe", b"MZ", "TYPE_NOT_ALLOWED"),
        ("fake.pdf", PNG, "MAGIC_MISMATCH"),
        ("macro.xlsx", _xlsx(macro=True), "MACRO_CONTENT"),
    ):
        with pytest.raises(FileTypeNotAllowed) as exc:
            service.upload_revision(ctl, doc.pk, filename=name, data=data)
        assert exc.value.errors[0].code == code, name
    big = b"%PDF-" + b"0" * 26_214_400
    with pytest.raises(PayloadTooLarge):
        service.upload_revision(ctl, doc.pk, filename="big.pdf", data=big)
    assert not StoredObject.objects.exists() and not DocumentRevision.objects.exists()


@pytest.mark.django_db
def test_clean_flow_encrypted_at_rest_review_and_download(store, no_exec, tmp_path) -> None:
    ctl, apr, emp = _people()
    doc = service.create_document(ctl, document_type="syn_drawing", title_fa="نقشه ساختگی", sensitivity="S1")
    rev = service.upload_revision(ctl, doc.pk, filename="plan sheet.pdf", data=PDF)
    assert (rev.status, rev.scan_status) == ("WORKING", "QUARANTINED")
    raw = (tmp_path / rev.stored_object_id[:2] / rev.stored_object_id).read_bytes()
    assert PDF not in raw and raw.startswith(b"AKE1")  # encrypted at rest
    with pytest.raises(FileNotReleased):
        service.download(emp, rev.pk)
    with pytest.raises(FileNotReleased):
        service.submit_revision(ctl, rev.pk)
    assert service.scan_revision(rev.pk, None) == "QUARANTINED"  # no scanner configured -> stays quarantined
    fake = scanner.FakeScannerForTests()
    assert service.scan_revision(rev.pk, fake) == "CLEAN"
    rev = service.submit_revision(ctl, rev.pk)
    assert rev.status == "IN_REVIEW" and rev.approval_request_id
    with pytest.raises(MfaRequired):
        service.approve_revision(caller(person_with("document_approver"), mfa=False), rev.pk)
    rev = service.approve_revision(apr, rev.pk, note="ok")
    assert rev.status == "APPROVED"
    doc.refresh_from_db()
    assert doc.current_approved_revision_id == rev.pk
    out = service.download(emp, rev.pk)
    assert out.data == PDF and out.headers["Content-Disposition"].startswith("attachment;")
    assert (
        out.headers["Content-Type"] == "application/octet-stream"
        and out.headers["X-Content-Type-Options"] == "nosniff"
    )
    rev2 = service.upload_revision(ctl, doc.pk, filename="plan sheet v2.pdf", data=PDF + b"%v2\n")
    service.scan_revision(rev2.pk, fake)
    service.submit_revision(ctl, rev2.pk)
    service.approve_revision(apr, rev2.pk)
    assert DocumentRevision.objects.get(pk=rev.pk).status == "SUPERSEDED"


def person_with(role: str) -> User:
    u = person()
    give_role(u, role)
    return u


@pytest.mark.django_db
def test_uploader_never_approves_and_s2_hidden_from_employees(store, no_exec) -> None:
    _ctl, apr, emp = _people()
    both = person()
    give_role(both, "document_controller")
    give_role(both, "document_approver")
    c = caller(both)
    doc = service.create_document(
        c, document_type="syn_drawing", title_fa="نقشه محرمانه ساختگی", sensitivity="S2"
    )
    rev = service.upload_revision(c, doc.pk, filename="secret.pdf", data=PDF)
    service.scan_revision(rev.pk, scanner.FakeScannerForTests())
    service.submit_revision(c, rev.pk)
    with pytest.raises(SelfApprovalForbidden):
        service.approve_revision(c, rev.pk)
    service.approve_revision(apr, rev.pk)
    with pytest.raises(NotFound):  # EMP sees S1 only (matrix v1.0)
        service.download(emp, rev.pk)


@pytest.mark.django_db
def test_eicar_is_quarantined_rejected_and_purged_after_30_days(store, no_exec) -> None:
    ctl, _apr, _emp = _people()
    doc = service.create_document(
        ctl, document_type="syn_drawing", title_fa="سند آزمون ساختگی", sensitivity="S1"
    )
    rev = service.upload_revision(ctl, doc.pk, filename="eicar.pdf", data=PDF + EICAR)
    assert rev.scan_status == "QUARANTINED"
    assert service.scan_revision(rev.pk, scanner.FakeScannerForTests()) == "REJECTED"
    rev.refresh_from_db()
    assert (rev.status, rev.scan_finding) == ("REJECTED", "Eicar-Test-Signature")
    obj = StoredObject.objects.get(pk=rev.stored_object_id)
    assert obj.purge_after is not None and rev.scanned_at is not None
    assert obj.purge_after - rev.scanned_at == timedelta(days=30)
    assert service.purge_rejected() == 0  # not before the quarantine period
    assert service.purge_rejected(now=db_now() + timedelta(days=31)) == 1
    obj.refresh_from_db()
    assert obj.bytes_purged_at is not None and obj.sha256 == rev.sha256  # metadata + hash kept
    with pytest.raises(DependencyUnavailable):
        storage.read(obj.storage_key, key_ref=obj.key_ref)


@pytest.mark.django_db
def test_scanner_unavailable_keeps_the_file_quarantined(store) -> None:
    ctl, _apr, _emp = _people()
    doc = service.create_document(ctl, document_type="syn_drawing", title_fa="سند ساختگی", sensitivity="S1")
    rev = service.upload_revision(ctl, doc.pk, filename="a.pdf", data=PDF)
    assert service.scan_revision(rev.pk, scanner.FakeScannerForTests(unavailable=True)) == "QUARANTINED"


def test_fake_scanner_is_a_test_double_only(settings) -> None:
    settings.ALEEKHAN_ENV = "prod"
    with pytest.raises(Exception, match="test double"):
        scanner.FakeScannerForTests()


def test_storage_refuses_without_configuration(settings) -> None:
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = ""
    with pytest.raises(DependencyUnavailable):
        storage.write(storage.new_storage_key(), PDF)


# ------------------------------------------------------------------------------ ClamAV contract test
def _clamd_reachable(settings) -> bool:
    host = getattr(settings, "ALEEKHAN_CLAMD_HOST", "")
    if not host:
        return False
    try:
        with socket.create_connection((host, settings.ALEEKHAN_CLAMD_PORT), timeout=2):
            return True
    except OSError:
        return False


def test_real_clamav_adapter_detects_eicar(settings) -> None:
    """Contract test of the production adapter against a real clamd (DEC-053 AV-A). Skipped when no clamd is
    configured/reachable (ClamAV is not installed on developer machines; it runs in the isolated
    container)."""
    if not _clamd_reachable(settings):
        pytest.skip(
            "clamd not configured/reachable (ALEEKHAN_CLAMD_HOST); real-scanner contract test skipped"
        )
    real = scanner.configured_scanner()
    assert real is not None
    assert real.scan(EICAR).clean is False
    assert real.scan(PDF).clean is True


@pytest.mark.parametrize(
    ("reply", "clean", "finding"),
    [
        (b"stream: OK", True, ""),
        (b"stream: Eicar-Test-Signature FOUND", False, "Eicar-Test-Signature"),
        (b"INSTREAM size limit exceeded. ERROR", False, "SCANNER_SIZE_LIMIT"),
    ],
)
def test_clamd_reply_parsing(monkeypatch, reply: bytes, clean: bool, finding: str) -> None:
    """Protocol parsing of the production adapter (socket replaced by a stub; the real daemon is the skipped
    contract test above)."""

    class StubSocket:
        def __enter__(self) -> StubSocket:
            return self

        def __exit__(self, *a: object) -> None:
            return None

        def sendall(self, data: bytes) -> None:
            return None

    s = scanner.ClamdScanner(host="127.0.0.1", port=1)
    monkeypatch.setattr(s, "version", lambda: "ClamAV synthetic")
    monkeypatch.setattr(s, "_connect", lambda: StubSocket())
    monkeypatch.setattr(scanner.ClamdScanner, "_read_reply", staticmethod(lambda sock: reply))
    v = s.scan(EICAR)
    assert (v.clean, v.finding) == (clean, finding)


def test_unreachable_clamd_is_dependency_unavailable() -> None:
    with pytest.raises(DependencyUnavailable):
        scanner.ClamdScanner(host="127.0.0.1", port=1, timeout=0.5).scan(PDF)
