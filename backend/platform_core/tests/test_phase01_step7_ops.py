"""PHASE_01 / 01.7 Security & Ops: dead-letter discard (REV-0129), blocked aggregates (REV-0130), housekeeping
job monitoring, the orphan-upload cleanup job and the upload size limit before parsing (REV-0124).

Real PostgreSQL, synthetic data only (aggregate ids ``agg-*``, synthetic users, a temporary storage folder).
"""

from __future__ import annotations

import io
import json
import os
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from platform_core.api.upload_limit import MULTIPART_OVERHEAD_BYTES, upload_limit_bytes
from platform_core.documents import scanner, storage
from platform_core.documents import service as docs
from platform_core.engine import outbox as ob
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import AccessDenied, EngineContractError, StateTransitionNotAllowed
from platform_core.jobs import service as jobs
from platform_core.jobs.models import JobDefinition, JobRun
from platform_core.models import AuditEvent, DeliveryStatus, OutboxEvent
from platform_core.ops import dead_letters, monitoring
from platform_core.params.values import effective_int

from . import openapi_contract as oc
from .engine_fixtures import network as set_network
from .engine_fixtures import person, with_role
from .factories import outbox_event
from .phase01_api import API, body, code, get, session_client, with_roles

S = DeliveryStatus
T0 = datetime(2030, 1, 1, tzinfo=UTC)
PDF = b"%PDF-1.7\n% synthetic 01.7 document\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def _poisoned(agg: str) -> tuple[OutboxEvent, OutboxEvent]:
    head = outbox_event(
        aggregate_id=agg, aggregate_version=1, delivery_status=S.DEAD_LETTER, next_attempt_at=T0
    )
    tail = outbox_event(aggregate_id=agg, aggregate_version=2, next_attempt_at=T0)
    return head, tail


def _owner_name() -> str:
    return with_roles("owner_admin").username


# ------------------------------------------------------------------------------------- REV-0129 discard
@pytest.mark.django_db
def test_owner_discard_releases_the_aggregate_and_is_audited_with_reason() -> None:
    head, tail = _poisoned("agg-poison")
    assert ob.claim_batch(ob.OutboxPolicy(), now=T0) == []  # the poison head holds the tail back
    owner = _owner_name()
    status = dead_letters.handle(
        action="discard", username=owner, event_id=head.event_id, reason="رویداد ساختگی خراب (آزمون)"
    )
    assert status == S.DISCARDED
    head.refresh_from_db()
    assert head.delivery_status == S.DISCARDED and head.discarded_at is not None
    audit = AuditEvent.objects.get(action="platform.outbox.discard", resource_id=str(head.event_id))
    assert audit.reason == "رویداد ساختگی خراب (آزمون)" and audit.actor_type == "USER"
    assert audit.before == {"delivery_status": "DEAD_LETTER", "attempts": 0}
    claimed = ob.claim_batch(ob.OutboxPolicy(), now=T0)
    assert [c.pk for c in claimed] == [tail.pk]  # the later event of the same aggregate is delivered
    # terminal: neither replay nor a second discard
    with pytest.raises(StateTransitionNotAllowed):
        dead_letters.handle(action="replay", username=owner, event_id=head.event_id, reason="دوباره")
    with pytest.raises(StateTransitionNotAllowed):
        dead_letters.handle(action="discard", username=owner, event_id=head.event_id, reason="دوباره")


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["it_ops", "security_auditor", "employee", None])
def test_only_the_owner_may_discard_or_replay(role: str | None) -> None:
    head, _tail = _poisoned(f"agg-deny-{role}")
    u = with_roles(role) if role else person()
    for action in ("discard", "replay"):
        with pytest.raises(AccessDenied):
            dead_letters.handle(
                action=action, username=u.username, event_id=head.event_id, reason="تلاش ساختگی"
            )
    head.refresh_from_db()
    assert head.delivery_status == S.DEAD_LETTER
    assert not AuditEvent.objects.filter(resource_id=str(head.event_id)).exists()


@pytest.mark.django_db
def test_discard_needs_a_reason_a_user_and_a_dead_letter() -> None:
    head, tail = _poisoned("agg-reason")
    with pytest.raises(EngineContractError):
        dead_letters.handle(action="discard", username=_owner_name(), event_id=head.event_id, reason="  ")
    with pytest.raises(EngineContractError):
        ob.discard_dead_letter(RequestContext(Actor.system()), head.event_id, reason="سیستم")
    with pytest.raises(StateTransitionNotAllowed):
        dead_letters.handle(
            action="discard", username=_owner_name(), event_id=tail.event_id, reason="نه مرده"
        )
    assert OutboxEvent.objects.filter(delivery_status=S.DISCARDED).count() == 0


@pytest.mark.django_db
def test_disabled_owner_cannot_discard() -> None:
    from platform_core.identity.models import User

    head, _tail = _poisoned("agg-disabled")
    owner = with_roles("owner_admin")
    User.objects.filter(pk=owner.pk).update(status="DISABLED")
    with pytest.raises(AccessDenied):
        dead_letters.handle(
            action="discard", username=owner.username, event_id=head.event_id, reason="ساختگی"
        )


@pytest.mark.django_db
def test_console_command_lists_and_discards(capsys: Any) -> None:
    head, _tail = _poisoned("agg-cli")
    call_command("outbox_dead_letter", "list", "--json")
    rows = json.loads(capsys.readouterr().out)
    assert [r["event_id"] for r in rows] == [str(head.event_id)] and rows[0]["held_behind"] == 1
    assert set(rows[0]) == {
        "event_id",
        "event_type",
        "aggregate_type",
        "occurred_at",
        "attempts",
        "held_behind",
    }
    with pytest.raises(CommandError):
        call_command(
            "outbox_dead_letter", "discard", "--owner", _owner_name(), "--event-id", str(head.event_id)
        )
    it = with_roles("it_ops").username
    with pytest.raises(CommandError, match="ACCESS_DENIED"):
        call_command(
            "outbox_dead_letter",
            "discard",
            "--owner",
            it,
            "--event-id",
            str(head.event_id),
            "--reason",
            "ساختگی",
        )
    call_command(
        "outbox_dead_letter", "discard", "--owner", _owner_name(), "--event-id", str(head.event_id),
        "--reason", "رویداد ساختگی خراب",
    )  # fmt: skip
    assert "DISCARDED" in capsys.readouterr().out
    head.refresh_from_db()
    assert head.delivery_status == S.DISCARDED


@pytest.mark.django_db
def test_discarded_counts_as_settled_in_health() -> None:
    head, tail = _poisoned("agg-health")
    h = monitoring.integration_health(now=T0)
    assert (h.blocked_aggregates, h.held_events) == (1, 1)
    dead_letters.handle(action="discard", username=_owner_name(), event_id=head.event_id, reason="ساختگی")
    h = monitoring.integration_health(now=T0)
    assert (h.blocked_aggregates, h.held_events) == (0, 0)
    snap = monitoring.outbox_snapshot(now=T0)
    assert (
        snap.counts[S.DISCARDED] == 1 and snap.dead_letters == 0 and "DEAD_LETTER_PRESENT" not in snap.reasons
    )
    assert tail.delivery_status == S.PENDING


# ------------------------------------------------------------------------------- REV-0130 blocked count
@pytest.mark.django_db
def test_dead_letter_without_followers_blocks_nothing() -> None:
    outbox_event(aggregate_id="agg-alone", delivery_status=S.DEAD_LETTER)
    h = monitoring.integration_health(now=T0)
    assert (h.blocked_aggregates, h.held_events) == (0, 0)  # = the OpenAPI description
    assert monitoring.outbox_snapshot(now=T0).verdict == "critical"  # still a dead letter to handle
    outbox_event(aggregate_id="agg-alone", aggregate_version=2)
    outbox_event(aggregate_id="agg-alone", aggregate_version=3)
    h = monitoring.integration_health(now=T0)
    assert (h.blocked_aggregates, h.held_events) == (1, 2)


# --------------------------------------------------------------------------- housekeeping job monitoring
@pytest.mark.django_db
def test_never_run_housekeeping_jobs_are_overdue_and_a_success_clears_it() -> None:
    health = {j.job_type: j for j in monitoring.housekeeping_health()}
    assert set(health) == set(jobs.HOUSEKEEPING_TYPES)
    assert all(j.overdue and not j.failing and j.last_state is None for j in health.values())
    assert monitoring.housekeeping_verdict(list(health.values())) == ("warn", ["HOUSEKEEPING_OVERDUE"])
    run = jobs.run_job("audit_integrity_check")
    assert run.state == "SUCCEEDED"
    j = next(x for x in monitoring.housekeeping_health() if x.job_type == "audit_integrity_check")
    assert (j.overdue, j.failing, j.last_state) == (False, False, "SUCCEEDED")
    assert j.last_succeeded_at is not None
    later = j.last_succeeded_at + monitoring.HOUSEKEEPING_MAX_AGE + timedelta(seconds=1)
    j = next(x for x in monitoring.housekeeping_health(now=later) if x.job_type == "audit_integrity_check")
    assert j.overdue is True


@pytest.mark.django_db
def test_failed_housekeeping_run_is_failing_with_its_code(monkeypatch: Any, capsys: Any) -> None:
    def boom() -> int:
        raise RuntimeError("synthetic failure")

    real = jobs._housekeeping
    monkeypatch.setattr(jobs, "_housekeeping", lambda: {**real(), "session_expiry_sweep": boom})
    assert jobs.run_job("session_expiry_sweep").state == "FAILED"
    j = next(x for x in monitoring.housekeeping_health() if x.job_type == "session_expiry_sweep")
    assert j.failing and j.last_error_code == "JOB_FAILED"
    call_command("job_status", "--json")
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "warn" and "HOUSEKEEPING_FAILING" in out["reasons"]
    assert "synthetic failure" not in json.dumps(out)  # codes only, never exception text
    with pytest.raises(CommandError):
        call_command("job_status", "--fail-on", "warn")


@pytest.mark.django_db
def test_run_housekeeping_command_runs_under_the_job_lifecycle(capsys: Any) -> None:
    call_command("run_housekeeping", "approval_expiry_sweep")
    assert "approval_expiry_sweep: SUCCEEDED" in capsys.readouterr().out
    assert JobRun.objects.filter(job_type_id="approval_expiry_sweep", state="SUCCEEDED").count() == 1
    with pytest.raises(CommandError):
        call_command("run_housekeeping", "not_a_job")
    with pytest.raises(CommandError):
        call_command("run_housekeeping")


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache")
def test_health_endpoint_shows_housekeeping_alerts(settings: Any) -> None:
    set_network(settings)
    jobs.run_job("audit_integrity_check")
    c = session_client(with_roles("owner_admin"))
    r = get(c, "/admin/health")
    assert r.status_code == 200, r.content
    oc.validate_response("/admin/health", "get", r)
    j = body(r)["jobs"]
    by_type = {x["job_type"]: x for x in j["housekeeping"]}
    assert set(by_type) == set(jobs.HOUSEKEEPING_TYPES)
    assert by_type["audit_integrity_check"]["overdue"] is False
    assert j["housekeeping_alerts"] == len(jobs.HOUSEKEEPING_TYPES) - 1  # the others never ran


# ------------------------------------------------------------------------------ orphan upload cleanup
@pytest.fixture
def store(settings: Any, tmp_path: Any) -> Any:
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = str(tmp_path)
    return tmp_path


def _age(path: Any, hours: float) -> None:
    t = time.time() - hours * 3600
    os.utime(path, (t, t))


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db")
def test_orphan_cleanup_removes_only_old_bytes_without_a_row(store: Any) -> None:
    _ctl, ctl = with_role("document_controller")
    doc = docs.create_document(ctl, document_type="syn_drawing", title_fa="نقشه ساختگی", sensitivity="S1")
    rev = docs.upload_revision(ctl, doc.pk, filename="sheet.pdf", data=PDF + uuid.uuid4().bytes)
    known_key = rev.stored_object.storage_key
    orphan = storage.new_storage_key()
    storage.write(orphan, b"synthetic orphan bytes")
    young = storage.new_storage_key()
    storage.write(young, b"synthetic young orphan")
    part_key = storage.new_storage_key()
    part = store / part_key[:2] / f"{part_key}.part"
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"synthetic partial write")
    stranger = store / "notes.txt"
    stranger.write_text("synthetic file the cleanup must not touch", encoding="utf-8")
    for key in (known_key, orphan):
        _age(store / key[:2] / key, 48)
    _age(part, 48)
    _age(stranger, 48)

    assert docs.purge_orphans() == 2  # the orphan and the partial write
    assert not (store / orphan[:2] / orphan).exists() and not part.exists()
    assert (store / known_key[:2] / known_key).exists()  # has a row
    assert (store / young[:2] / young).exists()  # inside the grace period
    assert stranger.exists()  # not a storage name
    audits = AuditEvent.objects.filter(action="platform.document.object.orphan_purge")
    assert {a.resource_id: (a.after or {})["kind"] for a in audits} == {
        orphan: "no_row",
        part_key: "partial_write",
    }
    assert docs.purge_orphans() == 0  # idempotent
    assert storage.read(known_key, key_ref=rev.stored_object.key_ref).startswith(b"%PDF-1.7")


@pytest.mark.django_db
def test_orphan_cleanup_job_is_seeded_safe_and_runs(store: Any) -> None:
    d = JobDefinition.objects.get(job_type="document_orphan_cleanup")
    assert (d.cancellable, d.protected) == (True, False)
    assert "document_orphan_cleanup" in jobs.HOUSEKEEPING_TYPES
    orphan = storage.new_storage_key()
    storage.write(orphan, b"synthetic orphan")
    _age(store / orphan[:2] / orphan, 30)
    assert jobs.run_job("document_orphan_cleanup").state == "SUCCEEDED"
    assert AuditEvent.objects.filter(
        action="platform.document.object.orphan_purge", resource_id=orphan
    ).exists()


@pytest.mark.django_db
def test_orphan_cleanup_without_storage_is_a_no_op(settings: Any) -> None:
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = ""
    assert docs.purge_orphans() == 0


# ------------------------------------------------------------------------------ REV-0124 upload limit
def _multipart(declared: int) -> dict[str, Any]:
    boundary = "synthetic-boundary"
    payload = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n%PDF-1.7 synthetic\r\n--{boundary}--\r\n"
    ).encode()
    return {
        "data": payload,
        "content_type": f"multipart/form-data; boundary={boundary}",
        "CONTENT_LENGTH": str(declared),
    }


@pytest.mark.django_db
def test_oversized_upload_is_refused_from_content_length_before_parsing() -> None:
    limit = upload_limit_bytes()
    assert limit == effective_int("document_upload_max_bytes") + MULTIPART_OVERHEAD_BYTES
    url = f"{API}/documents/{uuid.uuid4()}/revisions"
    # declared length far larger than the bytes sent: had anything read the body, the test client's
    # FakePayload would raise - a 413 here proves the body was never parsed (and nothing spooled to disk)
    r = Client().generic("POST", url, **_multipart(limit + 1))
    assert r.status_code == 413 and code(r) == "PAYLOAD_TOO_LARGE", r.content
    assert r["Content-Type"].startswith("application/problem+json") and r["X-Request-ID"]
    c = session_client(with_roles("document_controller"))
    r = c.generic("POST", url, **_multipart(limit + 1), HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert r.status_code == 413 and code(r) == "PAYLOAD_TOO_LARGE"


@pytest.mark.django_db
def test_upload_within_the_limit_passes_to_the_normal_checks() -> None:
    url = f"{API}/documents/{uuid.uuid4()}/revisions"
    m = _multipart(0)
    m["CONTENT_LENGTH"] = str(len(m["data"]))
    r = Client().generic("POST", url, **m)
    assert r.status_code == 401  # anonymous: normal authentication answer, not 413


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache", "store")
def test_real_upload_still_works_through_the_middleware(settings: Any) -> None:
    set_network(settings)
    u, ctl_caller = with_role("document_controller")
    doc = docs.create_document(
        ctl_caller, document_type="syn_drawing", title_fa="نقشه ساختگی", sensitivity="S1"
    )
    c = session_client(u)
    upload = io.BytesIO(PDF + secrets.token_bytes(8))
    upload.name = "sheet.pdf"
    r = c.post(
        f"{API}/documents/{doc.pk}/revisions", {"file": upload}, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())
    )
    assert r.status_code == 202, r.content
    docs.scan_revision(uuid.UUID(body(r)["revision_id"]), scanner.FakeScannerForTests())
