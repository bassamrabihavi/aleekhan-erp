"""PHASE_01 / 01.7 carried item: DEC-056 extension 2 (employer 2026-11-10, matrix v1.3, migration 0017).

The owner (``owner_admin``) also reads every document / revision and downloads CLEAN revisions (audited), so
he
can open the file before he decides it. Not a business-approval permission: the DB guard exception stays the
three pairs of 0015. Service level and HTTP level (real session auth, real PostgreSQL). Synthetic data only.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.db import connection

from platform_core.authz import policy as P
from platform_core.documents import scanner
from platform_core.documents import service as docs
from platform_core.engine.errors import AccessDenied, FileNotReleased
from platform_core.identity.models import Permission, Role, RolePermission
from platform_core.models import AuditEvent

from . import openapi_contract as oc
from .engine_fixtures import network as set_network
from .engine_fixtures import with_role
from .phase01_api import API, body, code, get, session_client, with_roles

PDF = b"%PDF-1.7\n% synthetic test document v13\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
OWNER_V13 = {("platform.document.read", "SCOPE", ""), ("platform.document.download", "SCOPE", "")}


@pytest.fixture
def store(settings: Any, tmp_path: Any) -> None:
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = str(tmp_path)


def _revision(ctl: Any, *, sensitivity: str = "S3", clean: bool = True, submit: bool = True) -> Any:
    doc = docs.create_document(
        ctl, document_type="syn_drawing", title_fa="نقشه ساختگی", sensitivity=sensitivity
    )
    rev = docs.upload_revision(ctl, doc.pk, filename="sheet.pdf", data=PDF + uuid.uuid4().bytes)
    if clean:
        docs.scan_revision(rev.pk, scanner.FakeScannerForTests())
        if submit:
            rev = docs.submit_revision(ctl, rev.pk)
    return rev


# ------------------------------------------------------------------------------------------- seed / DB
@pytest.mark.django_db
def test_v13_owner_holds_document_read_and_download_without_a_cap() -> None:
    owner = Role.objects.get(code="owner_admin")
    held = set(
        RolePermission.objects.filter(role=owner).values_list(
            "permission_id", "grant_mode", "max_sensitivity"
        )
    )
    assert OWNER_V13 <= held
    assert (
        owner.matrix_version == "2.1"
    )  # v1.3 here, moved on by DEC-057 (v2.0, 0022) and its amendment (v2.1, 0024)
    # not business-approval permissions -> 0017 did not touch the DB guard exception (0022 widened it to
    # exactly the six pairs of authz.policy.OWNER_BA_ACTIONS, DEC-057)
    assert not Permission.objects.filter(
        action__in=[a for a, _m, _s in OWNER_V13], business_approval=True
    ).exists()
    ba = set(
        RolePermission.objects.filter(role__kind="TECHNICAL", permission__business_approval=True).values_list(
            "role__code", "permission_id"
        )
    )
    assert ba == {("owner_admin", a) for a in P.OWNER_BA_ACTIONS}
    # it_ops / security_auditor still hold no document permission
    assert not RolePermission.objects.filter(
        role__code__in=["it_ops", "security_auditor"], permission__action__startswith="platform.document."
    ).exists()


@pytest.mark.django_db
def test_v13_migration_does_not_replace_the_guard_functions() -> None:
    """0017 adds grants only; the guard bodies are the 0015 text widened by 0022 (DEC-057) - never the
    document read/download grants of v1.3."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p WHERE p.proname IN "
            "('platform_role_permission_guard', 'platform_role_kind_guard', 'platform_permission_ba_guard')"
        )
        bodies = dict(cur.fetchall())
    assert len(bodies) == 3
    for text in bodies.values():
        assert "'platform.document.approve', 'platform.config.parameter.publish'" in text
        assert "platform.document.read" not in text and "platform.document.download" not in text


# ------------------------------------------------------------------------------------------- service
@pytest.mark.django_db
@pytest.mark.usefixtures("store")
def test_owner_reads_and_downloads_a_revision_he_decides() -> None:
    _ctl, ctl = with_role("document_controller")
    rev = _revision(ctl, sensitivity="S3")
    o, owner = with_role("owner_admin")
    got = docs.get_revision(owner, rev.pk)
    assert got.pk == rev.pk
    from platform_core.documents.models import Document, DocumentRevision

    assert Document.objects.filter(docs.document_list_q(owner), pk=rev.document_id).exists()
    assert DocumentRevision.objects.filter(docs.revision_list_q(owner), pk=rev.pk).exists()
    f = docs.download(owner, rev.pk)
    assert f.data.startswith(b"%PDF-1.7") and f.sha256 == rev.sha256
    docs.record_download(owner, rev)
    audit = AuditEvent.objects.get(action="platform.document.download", resource_id=str(rev.pk))
    assert audit.actor_id == o.pk


@pytest.mark.django_db
@pytest.mark.usefixtures("store")
def test_owner_never_downloads_a_revision_that_is_not_clean() -> None:
    _ctl, ctl = with_role("document_controller")
    rev = _revision(ctl, clean=False)
    _o, owner = with_role("owner_admin")
    assert docs.get_revision(owner, rev.pk).scan_status != "CLEAN"  # visible (metadata) ...
    with pytest.raises(FileNotReleased):  # ... but never served while quarantined
        docs.download(owner, rev.pk)


@pytest.mark.django_db
@pytest.mark.usefixtures("store")
def test_it_ops_and_auditor_still_cannot_read_documents() -> None:
    _ctl, ctl = with_role("document_controller")
    rev = _revision(ctl)
    for code_ in ("it_ops", "security_auditor"):
        _u, tech = with_role(code_)
        with pytest.raises(AccessDenied):
            docs.get_revision(tech, rev.pk)
        with pytest.raises(AccessDenied):
            docs.download(tech, rev.pk)


# ------------------------------------------------------------------------------------------- HTTP
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache", "store")
def test_http_owner_opens_lists_and_downloads_the_document_he_decides(settings: Any) -> None:
    set_network(settings)
    _ctl, ctl = with_role("document_controller")
    rev = _revision(ctl, sensitivity="S3")
    owner_user = with_roles("owner_admin")
    owner = session_client(owner_user)
    did, rid = str(rev.document_id), str(rev.pk)
    r = get(owner, f"/documents/{did}")
    assert r.status_code == 200, r.content
    oc.validate_response("/documents/{document_id}", "get", r)
    r = get(owner, "/documents")
    assert r.status_code == 200 and did in {x["document_id"] for x in body(r)["items"]}
    r = get(owner, f"/documents/{did}/revisions")
    assert r.status_code == 200 and rid in {x["revision_id"] for x in body(r)["items"]}
    r = get(owner, f"/documents/{did}/revisions/{rid}")
    assert r.status_code == 200 and body(r)["status"] == "IN_REVIEW", r.content
    r = owner.get(f"{API}/documents/{did}/revisions/{rid}/content")
    assert r.status_code == 200, r.content
    data = r.content
    assert data.startswith(b"%PDF-1.7")
    assert r["Content-Disposition"].startswith("attachment")
    assert AuditEvent.objects.filter(
        action="platform.document.download", resource_id=rid, actor_id=owner_user.pk
    ).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache", "store")
def test_http_owner_download_of_a_quarantined_revision_is_refused(settings: Any) -> None:
    set_network(settings)
    _ctl, ctl = with_role("document_controller")
    rev = _revision(ctl, clean=False)
    owner = session_client(with_roles("owner_admin"))
    r = owner.get(f"{API}/documents/{rev.document_id}/revisions/{rev.pk}/content")
    assert r.status_code == 409 and code(r) == "FILE_NOT_RELEASED", r.content
    assert not AuditEvent.objects.filter(
        action="platform.document.download", resource_id=str(rev.pk)
    ).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache", "store")
def test_http_it_ops_still_gets_403_on_documents(settings: Any) -> None:
    set_network(settings)
    _ctl, ctl = with_role("document_controller")
    rev = _revision(ctl)
    c = session_client(with_roles("it_ops"))
    for path in (f"/documents/{rev.document_id}", f"/documents/{rev.document_id}/revisions/{rev.pk}"):
        r = get(c, path)
        assert r.status_code == 403 and code(r) == "ACCESS_DENIED", (path, r.content)
