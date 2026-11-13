"""PHASE_02 / 02.3 race and idempotency tests of the engine use cases (committed rows, real concurrency on
separate PostgreSQL connections; ID-02 / ID-04 at use-case level). Synthetic data only.

* duplicate confirms of one order: one effect (the others are refused, no extra serial, no gap)
* concurrent confirms of different orders: no duplicate, no gap
* the same approved change request applied concurrently: applied once
* two change requests on the same base applied concurrently: one wins, the other is STALE_BASE_VERSION
* concurrent product / style creation: distinct, contiguous numbers (row lock on the counting row)
* concurrent code issues for one style: one code
* confirm through the idempotent command layer: a replay returns the stored result without a second effect
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from platform_core.commercial import changes, orders
from platform_core.commercial.models import CustomerOrder, OrderChangeRequest
from platform_core.engine import commands
from platform_core.engine.errors import (
    AleekhanError,
    IdempotencyKeyReused,
    StateTransitionNotAllowed,
    VersionConflict,
)
from platform_core.models import OutboxEvent
from platform_core.product_identity import codes, master
from platform_core.product_identity.models import ProductCode, Serial, SerialCounter

from . import phase02_engine as e
from . import phase02_factories as f
from .engine_fixtures import ensure_catalogue
from .threads import run_concurrently

N = 6


@pytest.fixture
def phase02_tx(audit_cleanup: None) -> None:
    ensure_catalogue()


pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("phase02_tx")]


def _next() -> int:
    return SerialCounter.objects.get(namespace_key="factory_serial").next_value


def _split(results: list[Any]) -> tuple[list[Any], list[BaseException]]:
    ok = [r for r in results if not isinstance(r, BaseException)]
    bad = [r for r in results if isinstance(r, BaseException)]
    return ok, bad


def test_duplicate_confirms_of_one_order_have_a_single_effect_race() -> None:
    p = e.people()
    o = e.validated_order(p.co, lines=2)
    planners = [p.po, p.po2, *[e.holder("planning_officer") for _ in range(N - 2)]]
    first = _next()
    results = run_concurrently(
        lambda i: orders.confirm_order(planners[i].caller, o.pk, expected_version=o.row_version), N
    )
    ok, bad = _split(results)
    assert len(ok) == 1 and ok[0].status == "CONFIRMED"
    assert all(isinstance(x, (VersionConflict, StateTransitionNotAllowed)) for x in bad), bad
    assert Serial.objects.count() == 2 and _next() == first + 2  # no extra number, no gap
    assert OutboxEvent.objects.filter(event_type="commercial.order.confirmed").count() == 1


def test_concurrent_confirms_of_different_orders_no_duplicate_no_gap_race() -> None:
    p = e.people()
    n = 12
    made = [e.validated_order(p.co, lines=1 + i % 2) for i in range(n)]
    planners = [e.holder("planning_officer") for _ in range(n)]
    first = _next()
    results = run_concurrently(
        lambda i: orders.confirm_order(planners[i].caller, made[i].pk, expected_version=made[i].row_version),
        n,
    )
    ok, bad = _split(results)
    assert bad == [] and len(ok) == n
    total = sum(1 + i % 2 for i in range(n))
    values = sorted(Serial.objects.values_list("serial_value", flat=True))
    assert values == list(range(first, first + total))


def test_one_change_request_applied_concurrently_is_applied_once_race() -> None:
    p = e.people()
    o = e.confirmed_order(p.co, p.po, lines=2)
    ln = e.live_lines(o)[0]
    o.refresh_from_db()
    cr = changes.create_change_request(
        p.co.caller,
        o.pk,
        kind="QTY_CHANGE",
        items=[{"line_id": str(ln.pk), "quantity": 77}],
        reason="synthetic race",
        expected_version=o.row_version,
        submit=True,
    )
    cr = changes.decide_change_request(p.cm.caller, cr.pk, approve=True, expected_version=cr.row_version)
    appliers = [p.po, p.po2, *[e.holder("planning_officer") for _ in range(N - 2)]]
    results = run_concurrently(
        lambda i: changes.apply_change_request(appliers[i].caller, cr.pk, expected_version=cr.row_version), N
    )
    ok, bad = _split(results)
    assert len(ok) == 1 and all(isinstance(x, (VersionConflict, StateTransitionNotAllowed)) for x in bad), bad
    o.refresh_from_db()
    assert o.current_version == 2
    assert (
        OutboxEvent.objects.filter(event_type="commercial.order.changed", aggregate_id=str(o.pk)).count() == 1
    )


def test_two_requests_on_the_same_base_one_wins_race() -> None:
    p = e.people()
    o = e.confirmed_order(p.co, p.po, lines=2)
    a, b = e.live_lines(o)
    crs = []
    for ln, qty in ((a, 21), (b, 22)):
        o.refresh_from_db()
        cr = changes.create_change_request(
            p.co.caller,
            o.pk,
            kind="QTY_CHANGE",
            items=[{"line_id": str(ln.pk), "quantity": qty}],
            reason="synthetic race",
            expected_version=o.row_version,
            submit=True,
        )
        crs.append(
            changes.decide_change_request(p.cm.caller, cr.pk, approve=True, expected_version=cr.row_version)
        )
    who = [p.po, p.po2]
    results = run_concurrently(
        lambda i: changes.apply_change_request(who[i].caller, crs[i].pk, expected_version=crs[i].row_version),
        2,
    )
    ok, bad = _split(results)
    assert len(ok) == 1 and len(bad) == 1
    assert isinstance(bad[0], AleekhanError) and bad[0].errors[0].code == "STALE_BASE_VERSION"
    assert sorted(OrderChangeRequest.objects.values_list("status", flat=True)) == ["APPLIED", "APPROVED"]
    assert CustomerOrder.objects.get(pk=o.pk).current_version == 2


def test_concurrent_product_and_style_creation_gets_distinct_contiguous_numbers_race() -> None:
    p = e.people()
    t = f.product_type()
    c = f.category(t, "01")
    stewards = [p.pds, *[e.holder("product_data_steward") for _ in range(N - 1)]]
    results = run_concurrently(
        lambda i: master.create_product(stewards[i].caller, product_type_id=t.pk, name_fa=f"م {i} {f.SYN}"), N
    )
    ok, bad = _split(results)
    assert bad == [] and sorted(x.product_no for x in ok) == [f"{n:04d}" for n in range(1, N + 1)]
    prod = ok[0]
    results = run_concurrently(
        lambda i: master.create_style(
            stewards[i].caller, product_id=prod.pk, category_id=c.pk, name_fa=f"س {i}"
        ),
        N,
    )
    ok, bad = _split(results)
    assert bad == [] and sorted(x.style_no for x in ok) == [f"{n:04d}" for n in range(1, N + 1)]


def test_concurrent_code_issues_for_one_style_give_one_code_race() -> None:
    p = e.people()
    r = codes.create_rule_revision(p.pds.caller, product_type_codes=["91"], source_workbook_sha256="b" * 64)
    cases = [
        {
            "inputs": {
                "type_code": "91",
                "category_code": "07",
                "product_no": f"{9000 + i:04d}",
                "style_no": "0001",
            },
            "expected_code": f"029107{9000 + i:04d}0001",
            "source_sheet": "SyntheticSheet",
            "source_cell_ref": f"A{i}",
        }
        for i in range(20)
    ]
    codes.add_golden_cases(p.pds.caller, r.pk, cases=cases)
    r.refresh_from_db()
    r = codes.submit_rule_revision(p.pds.caller, r.pk, expected_version=r.row_version)
    r = codes.approve_rule_revision(p.cra.caller, r.pk, expected_version=r.row_version)
    codes.activate_rule_revision(p.cra.caller, r.pk, expected_version=r.row_version)
    t = f.product_type("91")
    s = f.style(f.product(t, "9001"), f.category(t, "07"), "0001")
    stewards = [p.pds, *[e.holder("product_data_steward") for _ in range(N - 1)]]
    results = run_concurrently(
        lambda i: codes.issue_product_code(stewards[i].caller, s.pk, idempotency_key=uuid.uuid4()), N
    )
    ok, bad = _split(results)
    assert len(ok) == 1 and ProductCode.objects.filter(style=s).count() == 1
    assert all(isinstance(x, AleekhanError) and x.errors[0].code == "CODE_ALREADY_ISSUED" for x in bad), bad


def test_confirm_replay_through_the_command_layer_has_a_single_effect_race() -> None:
    p = e.people()
    o = e.validated_order(p.co, lines=2)
    first = _next()
    key = uuid.uuid4()

    def run() -> dict[str, Any]:
        done = orders.confirm_order(p.po.caller, o.pk, expected_version=o.row_version)
        return {"id": str(done.pk), "status": done.status, "version": done.current_version}

    ctx = p.po.caller.context()
    payload = {"order_id": str(o.pk), "expected_version": o.row_version}
    results = run_concurrently(
        lambda _i: commands.execute(
            ctx, key=key, command="commercial.order.confirm", payload=payload, fn=run
        ),
        3,
    )
    ok, bad = _split(results)
    # one executes; the others replay the stored result or meet the in-flight claim (409, retry later)
    assert ok and all(r[0] == {"id": str(o.pk), "status": "CONFIRMED", "version": 1} for r in ok)
    assert [r[1] for r in ok].count(False) <= 1
    assert all(getattr(x, "code", None) == "IDEMPOTENCY_IN_PROGRESS" for x in bad), bad
    again, replayed = commands.execute(
        ctx, key=key, command="commercial.order.confirm", payload=payload, fn=run
    )
    assert replayed and again["status"] == "CONFIRMED"
    assert Serial.objects.count() == 2 and _next() == first + 2
    with pytest.raises(IdempotencyKeyReused):
        commands.execute(ctx, key=key, command="commercial.order.confirm", payload={"order_id": "x"}, fn=run)
