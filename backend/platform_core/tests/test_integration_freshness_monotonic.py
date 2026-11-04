"""REV-0601 (00.7): source freshness provenance never moves backwards.

SYNTHETIC sources/files/rows only (tiny in-test byte strings), no real factory data.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from platform_core.engine.context import Actor, RequestContext
from platform_core.integration import imports as im
from platform_core.integration.models import ImportBatch, IntegrationSource
from platform_core.models import AuditEvent

from . import factories
from .threads import run_concurrently

T = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


def _ctx() -> RequestContext:
    return RequestContext(Actor.system(), request_id=uuid.uuid4())


def _staged(src: IntegrationSource, tag: str, as_of: datetime | None) -> ImportBatch:
    content = f"SYNTHETIC workbook bytes {tag}".encode()
    batch = im.receive_file(
        _ctx(), source_code=src.code, content=content, original_name=f"syn-{tag}.xlsx", source_as_of=as_of
    ).batch
    return im.stage_rows(_ctx(), batch.id, [im.StagingInput(1, {"col_a": f"v-{tag}"}, "SYN")])


def _validate(batch: ImportBatch) -> ImportBatch:
    return im.validate_batch(_ctx(), batch.id)


def _state(src: IntegrationSource) -> tuple[uuid.UUID | None, datetime | None, datetime | None]:
    src.refresh_from_db()
    return src.last_success_batch_id, src.last_as_of, src.last_success_at


# ------------------------------------------------------------------------------------------- pure rule
@pytest.mark.parametrize(
    ("current", "has_current", "candidate", "expected"),
    [
        (None, False, None, True),  # first success, undated
        (None, False, T, True),  # first success, dated
        (T, True, T + timedelta(days=1), True),  # newer snapshot
        (T, True, T, True),  # same snapshot date, later import
        (T, True, T - timedelta(days=30), False),  # older snapshot never wins
        (T, True, None, False),  # undated never replaces a dated provenance
        (None, True, T, True),  # dated replaces undated
        (None, True, None, True),  # both undated: import order
    ],
)
def test_supersedes_freshness_rule(
    current: datetime | None, has_current: bool, candidate: datetime | None, expected: bool
) -> None:
    assert im.supersedes_freshness(current, has_current, candidate) is expected


# ------------------------------------------------------------------------------------------- service
@pytest.mark.django_db
@pytest.mark.parametrize("older_as_of", [T - timedelta(days=30), None], ids=["older", "undated"])
def test_older_or_undated_batch_does_not_regress_freshness(older_as_of: datetime | None) -> None:
    src = factories.integration_source()
    newer = _validate(_staged(src, "newer", T))
    before = _state(src)
    assert before[:2] == (newer.id, T)

    older = _validate(_staged(src, "older", older_as_of))
    assert older.status == "VALIDATED"  # the batch itself is still validated
    assert _state(src) == before  # last_success_batch, last_as_of and last_success_at unchanged
    audit = AuditEvent.objects.get(action="platform.integration.batch.validate", resource_id=str(older.id))
    assert audit.after is not None and audit.after["freshness_advanced"] is False
    audit_newer = AuditEvent.objects.get(
        action="platform.integration.batch.validate", resource_id=str(newer.id)
    )
    assert audit_newer.after is not None and audit_newer.after["freshness_advanced"] is True


@pytest.mark.django_db
def test_newer_batch_advances_freshness() -> None:
    src = factories.integration_source()
    first = _validate(_staged(src, "a", T))
    second = _validate(_staged(src, "b", T + timedelta(hours=1)))
    batch_id, as_of, success_at = _state(src)
    assert (batch_id, as_of) == (second.id, T + timedelta(hours=1))
    assert success_at is not None and first.validated_at is not None and success_at >= first.validated_at


@pytest.mark.django_db
def test_dated_batch_replaces_undated_provenance() -> None:
    src = factories.integration_source()
    _validate(_staged(src, "undated", None))
    dated = _validate(_staged(src, "dated", T))
    assert _state(src)[:2] == (dated.id, T)


# ------------------------------------------------------------------------------------------- race
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_concurrent_validations_keep_the_newest_snapshot() -> None:
    """6 batches with different snapshot dates are validated at the same instant on separate connections.

    Whatever the commit order, the source must end on the newest snapshot (row lock + monotonic rule).
    """
    src = factories.integration_source()
    offsets = [3, 0, 5, 1, 4, 2]
    batches = [_staged(src, f"r{i}", T + timedelta(days=d)) for i, d in enumerate(offsets)]

    results = run_concurrently(lambda i: _validate(batches[i]).id, len(batches))
    assert all(isinstance(r, uuid.UUID) for r in results), results
    newest = batches[offsets.index(max(offsets))]
    assert _state(src)[:2] == (newest.id, T + timedelta(days=max(offsets)))
