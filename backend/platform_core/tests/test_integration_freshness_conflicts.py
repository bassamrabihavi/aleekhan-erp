"""00.6 freshness classification and conflict queue service (synthetic sources and keys only)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, transaction
from hypothesis import given
from hypothesis import strategies as st

from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import (
    EngineContractError,
    NotFound,
    StateTransitionNotAllowed,
    ValidationFailed,
    VersionConflict,
)
from platform_core.engine.redaction import REDACTED
from platform_core.integration import conflicts as cf
from platform_core.integration import imports as im
from platform_core.integration.freshness import Freshness, age_seconds, classify, freshness_of
from platform_core.integration.models import ConflictItem, ConflictStatus, IntegrationSource
from platform_core.models import AuditEvent, OutboxEvent

from . import factories
from .threads import run_concurrently

NOW = datetime(2026, 11, 4, 8, 0, tzinfo=UTC)
DAY = timedelta(hours=24)
USER = uuid.UUID("00000000-0000-4000-8000-0000000000c1")


def _user() -> RequestContext:
    return RequestContext(Actor.user(USER), request_id=uuid.uuid4())


# ------------------------------------------------------------------------------------------- freshness
@pytest.mark.parametrize(
    ("last", "expected"),
    [
        (None, Freshness.NEVER),
        (NOW, Freshness.FRESH),
        (NOW - DAY, Freshness.FRESH),  # boundary: exactly the threshold is still fresh
        (NOW - DAY - timedelta(microseconds=1), Freshness.STALE),
        (NOW + timedelta(minutes=5), Freshness.FRESH),  # clock skew: future counts as age 0
    ],
)
def test_classify(last: datetime | None, expected: Freshness) -> None:
    assert classify(last, DAY, NOW) == expected


def test_classify_rejects_non_positive_threshold() -> None:
    with pytest.raises(ValueError):
        classify(NOW, timedelta(0), NOW)


@given(
    age=st.integers(min_value=-(10**6), max_value=10**8), threshold=st.integers(min_value=1, max_value=10**7)
)
def test_classify_is_monotone_in_age(age: int, threshold: int) -> None:
    last = NOW - timedelta(seconds=age)
    got = classify(last, timedelta(seconds=threshold), NOW)
    assert got == (Freshness.STALE if age > threshold else Freshness.FRESH)
    assert age_seconds(last, NOW) == max(0, age)


@pytest.mark.django_db
def test_freshness_follows_validated_batches() -> None:
    src = factories.integration_source(staleness_threshold=timedelta(hours=1))
    assert freshness_of(src, NOW).freshness == Freshness.NEVER
    ctx = RequestContext(Actor.system())
    batch = im.receive_file(ctx, source_code=src.code, content=b"SYNTHETIC-1", original_name="s.xlsx").batch
    im.stage_rows(ctx, batch.id, [im.StagingInput(1, {"a": "1"})])
    im.validate_batch(ctx, batch.id)
    src.refresh_from_db()
    assert src.last_success_at is not None
    assert freshness_of(src, src.last_success_at + timedelta(minutes=59)).freshness == Freshness.FRESH
    assert freshness_of(src, src.last_success_at + timedelta(minutes=61)).freshness == Freshness.STALE


@pytest.mark.django_db
def test_seeded_thresholds_are_marked_technical_default() -> None:
    seeded = IntegrationSource.objects.filter(
        code__in=["rahkaran_excel", "legacy_planning_xlsm", "legacy_wh_xlsm"]
    )
    assert seeded.count() == 3
    assert {s.threshold_basis for s in seeded} == {"TECHNICAL_DEFAULT"}
    assert {s.direction for s in seeded} == {"READ_ONLY"}
    assert IntegrationSource.objects.get(code="rahkaran_excel").staleness_threshold == DAY


# ------------------------------------------------------------------------------------------- raise
@pytest.mark.django_db
def test_raise_is_idempotent_while_open_and_redacts_details() -> None:
    src = factories.integration_source()
    ctx = RequestContext(Actor.system(), request_id=uuid.uuid4())
    res = cf.raise_conflict(
        ctx,
        source_code=src.code,
        kind="duplicate_code",
        key="SYN!00000000000001",
        details={"sheet": "SYN", "cell": "B7", "api_token": "<synthetic-not-a-secret>"},
    )
    assert res.created and res.item.status == ConflictStatus.OPEN
    assert res.item.details == {"sheet": "SYN", "cell": "B7", "api_token": REDACTED}
    assert (
        OutboxEvent.objects.get(request_id=ctx.request_id).event_type
        == "platform.integration.conflict_raised"
    )
    again = cf.raise_conflict(
        RequestContext(Actor.system()), source_code=src.code, kind="duplicate_code", key="SYN!00000000000001"
    )
    assert not again.created and again.item.conflict_id == res.item.conflict_id
    assert ConflictItem.objects.filter(source=src).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"kind": "Bad Kind"}, "kind"),
        ({"key": ""}, "key"),
        ({"key": "x" * 201}, "key"),
        ({"key": "a\x00b"}, "key"),
        ({"details": {"blob": "x" * 9000}}, "details"),
    ],
)
def test_raise_validation(kwargs: dict[str, object], field: str) -> None:
    src = factories.integration_source()
    args: dict[str, object] = {"source_code": src.code, "kind": "synthetic_kind", "key": "k1"}
    args.update(kwargs)
    with pytest.raises(ValidationFailed) as exc:
        cf.raise_conflict(RequestContext(Actor.system()), **args)  # type: ignore[arg-type]
    assert exc.value.errors[0].field == field


@pytest.mark.django_db
def test_raise_with_batch_of_another_source_is_404() -> None:
    a, b = factories.integration_source(), factories.integration_source()
    batch = im.receive_file(
        RequestContext(Actor.system()), source_code=a.code, content=b"SYN", original_name="x"
    ).batch
    with pytest.raises(NotFound):
        cf.raise_conflict(
            RequestContext(Actor.system()), source_code=b.code, kind="syn_kind", key="k", batch_id=batch.id
        )


# ------------------------------------------------------------------------------------------- resolve
@pytest.mark.django_db
def test_resolve_and_dismiss_are_audited_terminal_and_reopenable_as_new_item() -> None:
    src = factories.integration_source()
    item = cf.raise_conflict(
        RequestContext(Actor.system()), source_code=src.code, kind="syn_kind", key="k"
    ).item
    with pytest.raises(EngineContractError):
        cf.resolve_conflict(
            RequestContext(Actor.system()),
            ConflictItem.objects.all(),
            item.conflict_id,
            expected_version=item.row_version,
            outcome="RESOLVED",
            note="x",
        )
    with pytest.raises(VersionConflict):
        cf.resolve_conflict(
            _user(),
            ConflictItem.objects.all(),
            item.conflict_id,
            expected_version=item.row_version + 1,
            outcome="RESOLVED",
            note="x",
        )
    with pytest.raises(NotFound):
        cf.resolve_conflict(
            _user(),
            ConflictItem.objects.none(),
            item.conflict_id,
            expected_version=item.row_version,
            outcome="RESOLVED",
            note="x",
        )
    ctx = _user()
    done = cf.resolve_conflict(
        ctx,
        ConflictItem.objects.all(),
        item.conflict_id,
        expected_version=item.row_version,
        outcome="RESOLVED",
        note="synthetic: kept tracker value",
    )
    assert (done.status, done.resolved_by, done.resolution_note) == (
        "RESOLVED",
        USER,
        "synthetic: kept tracker value",
    )
    assert done.row_version == item.row_version + 1
    audit = AuditEvent.objects.get(request_id=ctx.request_id)
    assert (audit.action, audit.before, audit.after) == (
        "platform.integration.conflict.resolve",
        {"status": "OPEN"},
        {"status": "RESOLVED"},
    )
    assert (
        OutboxEvent.objects.get(request_id=ctx.request_id).event_type
        == "platform.integration.conflict_resolved"
    )
    with pytest.raises(StateTransitionNotAllowed):
        cf.resolve_conflict(
            _user(),
            ConflictItem.objects.all(),
            item.conflict_id,
            expected_version=done.row_version,
            outcome="DISMISSED",
            note="again",
        )
    reopened = cf.raise_conflict(
        RequestContext(Actor.system()), source_code=src.code, kind="syn_kind", key="k"
    )
    assert reopened.created and reopened.item.conflict_id != item.conflict_id


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("outcome", "note", "field"),
    [
        ("OPEN", "x", "outcome"),
        ("APPLY", "x", "outcome"),
        ("RESOLVED", " ", "note"),
        ("DISMISSED", "x" * 501, "note"),
    ],
)
def test_resolve_validation(outcome: str, note: str, field: str) -> None:
    src = factories.integration_source()
    item = cf.raise_conflict(
        RequestContext(Actor.system()), source_code=src.code, kind="syn_kind", key="k"
    ).item
    with pytest.raises(ValidationFailed) as exc:
        cf.resolve_conflict(
            _user(),
            ConflictItem.objects.all(),
            item.conflict_id,
            expected_version=item.row_version,
            outcome=outcome,
            note=note,
        )
    assert exc.value.errors[0].field == field


@pytest.mark.django_db
def test_conflict_resolution_consistency_is_enforced_by_db() -> None:
    src = factories.integration_source()
    item = cf.raise_conflict(
        RequestContext(Actor.system()), source_code=src.code, kind="syn_kind", key="k"
    ).item
    with pytest.raises(IntegrityError) as exc, transaction.atomic():
        ConflictItem.objects.filter(pk=item.pk).update(status="RESOLVED")
    assert "ck_conflict_item_resolution_consistent" in str(exc.value)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_concurrent_raisers_converge_on_one_open_item() -> None:
    src = factories.integration_source()

    def raiser(i: int) -> tuple[uuid.UUID, bool]:
        r = cf.raise_conflict(
            RequestContext(Actor.system()), source_code=src.code, kind="syn_kind", key="same-key"
        )
        return r.item.conflict_id, r.created

    results = run_concurrently(raiser, 6)
    assert all(isinstance(r, tuple) for r in results), results
    assert len({r[0] for r in results}) == 1 and sum(r[1] for r in results) == 1
    assert ConflictItem.objects.filter(source=src, status="OPEN").count() == 1
