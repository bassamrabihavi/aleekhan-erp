"""Audit hash chain (PHASE_01 / 01.3): append, verification + integrity run, tamper detection, session/zone
columns, savepoint rollback, concurrency (contiguous sequence), property test over payloads."""

from __future__ import annotations

import itertools
import uuid

import pytest
from django.db import connection, transaction
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from platform_core.engine import audit_chain as ac
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.uow import unit_of_work
from platform_core.jobs.models import AuditIntegrityRun
from platform_core.models import AuditEvent

from .threads import run_concurrently


def _write(n: int = 1, **audit: object) -> list[AuditEvent]:
    ctx = RequestContext(
        Actor.user(uuid.uuid4()), request_id=uuid.uuid4(), session_id=uuid.uuid4(), network_zone="INTERNAL"
    )
    out = []
    with unit_of_work(ctx, require_event=False) as uow:
        for i in range(n):
            out.append(
                uow.audit(
                    action="platform.synthetic.update",
                    resource_type="platform.synthetic",
                    resource_id=str(i),
                    **audit,  # type: ignore[arg-type]
                )
            )
    return out


def _as_owner(sql: str, params: list[str] | None = None) -> None:
    """TEST-ONLY tampering as the throw-away test DB owner (simulates an attacker with owner rights)."""
    with connection.cursor() as cur:
        cur.execute("ALTER TABLE platform_audit_event DISABLE TRIGGER trg_audit_event_append_only")
        try:
            cur.execute(sql, params or [])
        finally:
            cur.execute("ALTER TABLE platform_audit_event ENABLE TRIGGER trg_audit_event_append_only")


@pytest.mark.django_db
def test_chain_is_written_and_verifies() -> None:
    events = _write(3, before={"a": 1}, after={"a": 2, "nested": {"x": [1, 2]}}, scope={"unit": "u"})
    seqs = [int(e.chain_seq or 0) for e in events]
    assert seqs == list(range(seqs[0], seqs[0] + 3))
    stored = list(AuditEvent.objects.filter(pk__in=[e.pk for e in events]).order_by("chain_seq"))
    assert stored[0].session_id == events[0].session_id and stored[0].network_zone == "INTERNAL"
    for prev, cur in itertools.pairwise(stored):
        assert cur.prev_hash == prev.event_hash
    run = ac.verify_chain()
    assert run.status == "OK" and run.events_checked >= 3 and run.checked_up_to_seq == stored[-1].chain_seq
    assert AuditIntegrityRun.objects.filter(pk=run.pk).exists()


@pytest.mark.django_db
def test_changed_field_is_detected() -> None:
    events = _write(3)
    _as_owner("UPDATE platform_audit_event SET reason = 'tampered' WHERE id = %s", [str(events[1].pk)])
    run = ac.verify_chain()
    assert run.status == "BROKEN" and run.first_broken_event_id == events[1].pk


@pytest.mark.django_db
def test_deleted_row_is_detected_as_gap() -> None:
    events = _write(3)
    _as_owner("DELETE FROM platform_audit_event WHERE id = %s", [str(events[1].pk)])
    run = ac.verify_chain()
    assert run.status == "BROKEN" and run.first_broken_event_id == events[2].pk


@pytest.mark.django_db
def test_raw_insert_bypassing_the_engine_is_detected() -> None:
    _write(1)
    bypass = uuid.uuid4()
    with connection.cursor() as cur:
        cur.execute(
            "INSERT INTO platform_audit_event (id, occurred_at, actor_type, action, outcome, resource_type, "
            "resource_id, scope, reason) VALUES (%s, now() + interval '1 second', 'SYSTEM', "
            "'platform.synthetic.raw', 'SUCCESS', 'platform.synthetic', 'raw', '{}', '')",
            [str(bypass)],
        )
    assert ac.verify_chain().first_broken_event_id == bypass


@pytest.mark.django_db
def test_savepoint_rollback_leaves_no_gap() -> None:
    ctx = RequestContext(Actor.system())
    with unit_of_work(ctx, require_event=False) as uow:
        uow.audit(action="platform.synthetic.outer", resource_type="platform.synthetic")
        try:
            with transaction.atomic(), unit_of_work(ctx, require_event=False) as inner:
                inner.audit(action="platform.synthetic.inner", resource_type="platform.synthetic")
                raise RuntimeError("synthetic")
        except RuntimeError:
            pass
        uow.audit(action="platform.synthetic.after", resource_type="platform.synthetic")
    assert not AuditEvent.objects.filter(action="platform.synthetic.inner").exists()
    assert ac.verify_chain().status == "OK"


@pytest.mark.django_db
def test_verify_on_empty_or_legacy_only_table_is_ok() -> None:
    assert ac.check_chain().first_broken is None


json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(-(2**60), 2**60)
    | st.text(max_size=20)
    | st.floats(allow_nan=False, allow_infinity=False, width=64),
    lambda children: (
        st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=8), children, max_size=3)
    ),
    max_leaves=10,
)


@pytest.mark.django_db
@settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    after=st.dictionaries(
        st.text(min_size=1, max_size=8).filter(lambda k: "\x00" not in k), json_values, max_size=4
    )
)
def test_any_json_payload_round_trips_through_the_chain(after: dict[str, object]) -> None:
    def clean(v: object) -> bool:
        return "\x00" not in str(v)

    if not clean(after):
        return
    _write(1, after=after)
    assert ac.check_chain().first_broken is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_writers_build_one_contiguous_chain(audit_cleanup: None) -> None:
    n = 6

    def work(i: int) -> None:
        _write(3)

    results = run_concurrently(work, n)
    assert all(not isinstance(r, BaseException) for r in results), results
    seqs = list(
        AuditEvent.objects.exclude(chain_seq=None).order_by("chain_seq").values_list("chain_seq", flat=True)
    )
    assert seqs == list(range(1, 3 * n + 1))
    assert ac.check_chain().first_broken is None and ac.check_chain().checked == 3 * n
