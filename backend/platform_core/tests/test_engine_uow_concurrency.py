"""Transactional write helper (write + audit + outbox, all-or-nothing) and optimistic concurrency."""

from __future__ import annotations

import uuid

import pytest
from django.db import transaction
from hypothesis import given
from hypothesis import strategies as st

from platform_core.engine.concurrency import (
    MAX_ROW_VERSION,
    lock_versioned,
    make_etag,
    parse_if_match,
    update_versioned,
)
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import (
    EngineContractError,
    NotFound,
    PreconditionRequired,
    ValidationFailed,
    VersionConflict,
)
from platform_core.engine.redaction import REDACTED
from platform_core.engine.uow import unit_of_work
from platform_core.models import ActorType, AuditEvent, IdempotencyRecord, OutboxEvent

from .factories import idempotency_record, outbox_event
from .threads import run_concurrently

USER = uuid.UUID("00000000-0000-4000-8000-000000000001")  # synthetic


def _ctx() -> RequestContext:
    return RequestContext(Actor.user(USER), request_id=uuid.uuid4())


def _business_write(marker: uuid.UUID) -> None:
    """Stand-in for an owning module's write (PHASE_00 has no business tables): any platform row."""
    idempotency_record(key=marker)


def _written(marker: uuid.UUID) -> bool:
    return IdempotencyRecord.objects.filter(key=marker).exists()


def _write(uow_ctx: RequestContext, marker: uuid.UUID, *, fail_after: bool = False) -> None:
    with unit_of_work(uow_ctx) as uow:
        _business_write(marker)
        uow.audit(action="platform.synthetic.update", resource_type="platform.synthetic", resource_id="1")
        uow.emit(
            event_type="platform.synthetic.updated",
            aggregate_type="platform.synthetic",
            aggregate_id="1",
            aggregate_version=1,
            payload={"id": "1"},
        )
        if fail_after:
            raise RuntimeError("synthetic failure after audit and outbox")


# ------------------------------------------------------------------------------------------- unit of work
@pytest.mark.django_db
def test_write_audit_outbox_commit_together_with_context() -> None:
    ctx, marker = _ctx(), uuid.uuid4()
    _write(ctx, marker)
    assert _written(marker)
    audit = AuditEvent.objects.get(request_id=ctx.request_id)
    event = OutboxEvent.objects.get(request_id=ctx.request_id)
    assert (audit.actor_type, audit.actor_id, audit.correlation_id) == (ActorType.USER, USER, ctx.request_id)
    assert (event.actor_id, event.correlation_id, event.delivery_status) == (USER, ctx.request_id, "PENDING")


@pytest.mark.django_db(transaction=True)
def test_rollback_leaves_no_write_no_audit_no_outbox() -> None:
    ctx, marker = _ctx(), uuid.uuid4()
    with pytest.raises(RuntimeError):
        _write(ctx, marker, fail_after=True)
    assert not _written(marker)
    assert not AuditEvent.objects.filter(request_id=ctx.request_id).exists()
    assert not OutboxEvent.objects.filter(request_id=ctx.request_id).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("missing", ["audit", "event"])
def test_write_without_audit_or_event_is_rejected_and_rolled_back(missing: str) -> None:
    ctx, marker = _ctx(), uuid.uuid4()
    with pytest.raises(EngineContractError), unit_of_work(ctx) as uow:
        _business_write(marker)
        if missing != "audit":
            uow.audit(action="platform.synthetic.update", resource_type="platform.synthetic")
        if missing != "event":
            uow.emit(
                event_type="platform.synthetic.updated",
                aggregate_type="platform.synthetic",
                aggregate_id="1",
                aggregate_version=1,
            )
    assert not _written(marker)
    assert AuditEvent.objects.count() == 0
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db
def test_require_event_false_allows_audit_only() -> None:
    with unit_of_work(_ctx(), require_event=False) as uow:
        uow.audit(action="platform.synthetic.update", resource_type="platform.synthetic")
    assert AuditEvent.objects.count() == 1


@pytest.mark.django_db
def test_audit_snapshots_redacted_and_sensitive_payload_rejected() -> None:
    with unit_of_work(_ctx(), require_event=False) as uow:
        a = uow.audit(
            action="platform.synthetic.update",
            resource_type="platform.synthetic",
            before={"name": "x", "password": "synthetic-pw"},
            after={"name": "y", "nested": {"salary": 1}},
        )
    stored = AuditEvent.objects.get(pk=a.pk)
    assert stored.before == {"name": "x", "password": REDACTED}
    assert stored.after == {"name": "y", "nested": {"salary": REDACTED}}
    with pytest.raises(EngineContractError, match="sensitive"), unit_of_work(_ctx()) as uow:
        uow.audit(action="platform.synthetic.update", resource_type="platform.synthetic")
        uow.emit(
            event_type="platform.synthetic.updated",
            aggregate_type="platform.synthetic",
            aggregate_id="1",
            aggregate_version=1,
            payload={"items": [{"token": "x"}]},
        )


def test_user_actor_requires_id() -> None:
    with pytest.raises(EngineContractError):
        Actor(ActorType.USER)
    assert Actor.system().actor_id is None


# ------------------------------------------------------------------------------------------- ETag / If-Match
@given(v=st.integers(min_value=1, max_value=MAX_ROW_VERSION))
def test_etag_roundtrip_property(v: int) -> None:
    assert parse_if_match(make_etag(v)) == v
    assert parse_if_match(f"  {make_etag(v)} ") == v


@pytest.mark.parametrize("header", [None, "", "   "])
def test_missing_if_match_is_428(header: str | None) -> None:
    with pytest.raises(PreconditionRequired) as exc:
        parse_if_match(header)
    assert exc.value.http_status == 428


@pytest.mark.parametrize("header", ["*", "3", '"0"', '"03"', '"1", "2"', '"abc"', '"99999999999999999999"'])
def test_malformed_if_match_is_400(header: str) -> None:
    with pytest.raises(ValidationFailed) as exc:
        parse_if_match(header)
    assert exc.value.errors[0].field == "If-Match"


def test_weak_etag_is_412() -> None:
    with pytest.raises(VersionConflict):
        parse_if_match('W/"3"')


@pytest.mark.parametrize("bad", [0, -1, MAX_ROW_VERSION + 1])
def test_make_etag_range(bad: int) -> None:
    with pytest.raises(ValueError):
        make_etag(bad)


# ------------------------------------------------------------------------------------------- compare-and-set
@pytest.mark.django_db
def test_update_versioned_success_conflict_and_not_found() -> None:
    row = outbox_event()
    qs = OutboxEvent.objects.all()
    assert update_versioned(qs, row.pk, 1, last_error="a") == 2
    row.refresh_from_db()
    assert (row.row_version, row.last_error) == (2, "a")
    with pytest.raises(VersionConflict):
        update_versioned(qs, row.pk, 1, last_error="stale")
    with pytest.raises(NotFound):
        update_versioned(qs, row.pk + 10_000, 2, last_error="x")
    # out-of-scope record behaves like a missing one (BOLA: 404, not 403)
    with pytest.raises(NotFound):
        update_versioned(qs.filter(aggregate_id="other-scope"), row.pk, 2, last_error="x")
    with pytest.raises(EngineContractError):
        update_versioned(qs, row.pk, 2, row_version=99)
    with pytest.raises(EngineContractError):
        update_versioned(qs, row.pk, 2)


@pytest.mark.django_db
def test_lock_versioned() -> None:
    row = outbox_event()
    with transaction.atomic():
        assert lock_versioned(OutboxEvent.objects.all(), row.pk, 1).pk == row.pk
        with pytest.raises(VersionConflict):
            lock_versioned(OutboxEvent.objects.all(), row.pk, 7)
        with pytest.raises(NotFound):
            lock_versioned(OutboxEvent.objects.all(), row.pk + 10_000, 1)


@pytest.mark.django_db(transaction=True)
def test_lock_versioned_requires_a_transaction() -> None:
    row = outbox_event()
    with pytest.raises(EngineContractError):
        lock_versioned(OutboxEvent.objects.all(), row.pk, 1)


@pytest.mark.django_db(transaction=True)
def test_concurrent_updates_same_version_exactly_one_wins() -> None:
    row = outbox_event()
    n = 8

    def attempt(i: int) -> int:
        with transaction.atomic():
            return update_versioned(OutboxEvent.objects.all(), row.pk, 1, last_error=f"writer-{i}")

    results = run_concurrently(attempt, n)
    wins = [r for r in results if r == 2]
    conflicts = [r for r in results if isinstance(r, VersionConflict)]
    assert len(wins) == 1, results
    assert len(conflicts) == n - 1, results
    row.refresh_from_db()
    assert row.row_version == 2
