"""PHASE_02 / 02.8 Gate follow-up (employer decisions 2026-11-17) against PostgreSQL. Synthetic data only.

* REV-0290 (DEC-059 amendment): at most one SUBMITTED / APPROVED change request per order (engine refusal
  ``OPEN_CHANGE_REQUEST_EXISTS`` + DB backstop ``uq_commercial_cr_one_open_per_order``); 30-day expiry
  (``expires_at`` at submit, ``CHANGE_REQUEST_EXPIRED`` before the sweep, housekeeping job
  ``change_request_expiry_sweep`` -> EXPIRED, audit + outbox; a new submit expires an overdue request first).
  The concurrent-submit race is in ``test_phase02_engine_race.py``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.db.models.functions import Now

from platform_core.commercial import changes
from platform_core.commercial.models import CustomerOrder, OrderChangeRequest
from platform_core.devtools import phase02_engine as e
from platform_core.devtools.phase01_factories import db_refuses
from platform_core.engine.errors import AleekhanError, StateTransitionNotAllowed
from platform_core.jobs import service as jobs
from platform_core.jobs.models import JobDefinition
from platform_core.models import AuditEvent, OutboxEvent

from .phase02_engine import deferred_checks  # noqa: F401 - fixture

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("deferred_checks")]
OPEN = "OPEN_CHANGE_REQUEST_EXISTS"
EXPIRED = "CHANGE_REQUEST_EXPIRED"


def _reason(exc: AleekhanError) -> str:
    return exc.errors[0].code


@pytest.fixture
def p() -> e.People:
    return e.people()


def _cr(who: e.Who, o: CustomerOrder, kind: str = "HOLD", *, submit: bool = True, **kw: Any) -> Any:
    o.refresh_from_db()
    return changes.create_change_request(
        who.caller,
        o.pk,
        kind=kind,
        items=kw.pop("items", []),
        reason="synthetic change",
        expected_version=o.row_version,
        submit=submit,
        **kw,
    )


def _age(cr: Any) -> Any:
    """Move an open request 31 days into the past (its 30-day expiry is then 1 day ago)."""
    OrderChangeRequest.objects.filter(pk=cr.pk).update(
        submitted_at=Now() - timedelta(days=31), expires_at=Now() - timedelta(days=1)
    )
    cr.refresh_from_db()
    return cr


# ------------------------------------------------------------------------------------- one open request
def test_submit_writes_expires_at_30_days_after_submit(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    cr = _cr(p.co, o)
    assert cr.status == "SUBMITTED" and cr.expires_at is not None and cr.submitted_at is not None
    assert cr.expires_at - cr.submitted_at == timedelta(days=30)
    draft = _cr(p.co2, o, submit=False)
    assert draft.status == "DRAFT" and draft.expires_at is None  # a DRAFT has no expiry and does not count


def test_second_open_request_of_an_order_is_refused_until_the_first_is_closed(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    first = _cr(p.co, o)
    with pytest.raises(StateTransitionNotAllowed) as exc:
        _cr(p.co2, o)  # create + submit
    assert _reason(exc.value) == OPEN
    draft = _cr(p.co2, o, submit=False)  # a DRAFT is allowed
    with pytest.raises(StateTransitionNotAllowed) as exc2:
        changes.submit_change_request(p.co2.caller, draft.pk, expected_version=draft.row_version)
    assert _reason(exc2.value) == OPEN
    first = changes.decide_change_request(
        p.cm.caller, first.pk, approve=True, expected_version=first.row_version
    )
    with pytest.raises(StateTransitionNotAllowed) as exc3:  # APPROVED is still open
        changes.submit_change_request(p.co2.caller, draft.pk, expected_version=draft.row_version)
    assert _reason(exc3.value) == OPEN
    changes.apply_change_request(p.po.caller, first.pk, expected_version=first.row_version)
    # applied -> the order moved to version 2 (ON_HOLD): the old draft is stale, a new request is accepted
    resume = _cr(p.co2, o, "RESUME")
    assert resume.status == "SUBMITTED"


@pytest.mark.parametrize("close", ["withdraw", "reject"])
def test_withdrawn_or_rejected_request_frees_the_order(p: e.People, close: str) -> None:
    o = e.confirmed_order(p.co, p.po)
    first = _cr(p.co, o)
    draft = _cr(p.co2, o, submit=False)
    if close == "withdraw":
        changes.withdraw_change_request(
            p.co.caller, first.pk, expected_version=first.row_version, reason="synthetic withdraw"
        )
    else:
        changes.decide_change_request(
            p.cm.caller, first.pk, approve=False, expected_version=first.row_version, note="synthetic reject"
        )
    out = changes.submit_change_request(p.co2.caller, draft.pk, expected_version=draft.row_version)
    assert out.status == "SUBMITTED" and out.expires_at is not None


def test_other_orders_are_independent(p: e.People) -> None:
    a = e.confirmed_order(p.co, p.po)
    b = e.confirmed_order(p.co, p.po)
    _cr(p.co, a)
    assert _cr(p.co, b).status == "SUBMITTED"


def test_db_backstop_refuses_a_second_open_request(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    first = _cr(p.co, o)
    draft = _cr(p.co2, o, submit=False)
    with db_refuses("uq_commercial_cr_one_open_per_order"):
        OrderChangeRequest.objects.filter(pk=draft.pk).update(
            status="SUBMITTED", submitted_at=Now(), expires_at=Now() + timedelta(days=30)
        )
    with db_refuses("ck_commercial_cr_open_has_expiry"):
        OrderChangeRequest.objects.filter(pk=first.pk).update(expires_at=None)
    with db_refuses("ck_commercial_cr_expiry_after_submit"):
        OrderChangeRequest.objects.filter(pk=first.pk).update(expires_at=Now() - timedelta(days=1))


# ------------------------------------------------------------------------------------------------ expiry
def test_overdue_request_cannot_be_decided_or_applied(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    submitted = _age(_cr(p.co, o))
    with pytest.raises(StateTransitionNotAllowed) as exc:
        changes.decide_change_request(
            p.cm.caller, submitted.pk, approve=True, expected_version=submitted.row_version
        )
    assert _reason(exc.value) == EXPIRED

    o2 = e.confirmed_order(p.co, p.po)
    cr = _cr(p.co, o2)
    cr = changes.decide_change_request(p.cm.caller, cr.pk, approve=True, expected_version=cr.row_version)
    cr = _age(cr)
    with pytest.raises(StateTransitionNotAllowed) as exc2:
        changes.apply_change_request(p.po.caller, cr.pk, expected_version=cr.row_version)
    assert _reason(exc2.value) == EXPIRED


def test_overdue_due_date_request_cannot_get_the_planning_decision(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    cr = _age(_cr(p.co, o, "DUE_DATE_CHANGE", items=[{"line_id": None, "requested_due_date": "2030-03-01"}]))
    with pytest.raises(StateTransitionNotAllowed) as exc:
        changes.planning_decide_change_request(
            p.po2.caller, cr.pk, approve=True, expected_version=cr.row_version
        )
    assert _reason(exc.value) == EXPIRED


def test_expiry_sweep_job_expires_overdue_requests_only_with_audit_and_event(p: e.People) -> None:
    assert JobDefinition.objects.filter(job_type="change_request_expiry_sweep").exists()  # migration 0029
    assert "change_request_expiry_sweep" in jobs.HOUSEKEEPING_TYPES
    o1, o2, o3 = (e.confirmed_order(p.co, p.po) for _ in range(3))
    overdue = _age(_cr(p.co, o1))
    approved = _cr(p.co, o2)
    approved = _age(
        changes.decide_change_request(
            p.cm.caller, approved.pk, approve=True, expected_version=approved.row_version
        )
    )
    fresh = _cr(p.co, o3)
    run = jobs.run_job("change_request_expiry_sweep")
    assert run.state == "SUCCEEDED"
    for cr, want in ((overdue, "EXPIRED"), (approved, "EXPIRED"), (fresh, "SUBMITTED")):
        cr.refresh_from_db()
        assert cr.status == want
    audits = AuditEvent.objects.filter(action="commercial.change_request.expire")
    assert sorted(a.resource_id for a in audits) == sorted([str(overdue.pk), str(approved.pk)])
    assert all(a.actor_type == "SYSTEM" for a in audits)
    events = OutboxEvent.objects.filter(event_type="commercial.change_request.expired")
    assert sorted(ev.aggregate_id for ev in events) == sorted([str(overdue.pk), str(approved.pk)])
    assert all(ev.payload["status"] == "EXPIRED" for ev in events)
    assert changes.expire_due() == 0  # idempotent: nothing left
    # an expired request no longer blocks the order
    assert _cr(p.co2, o1).status == "SUBMITTED"


def test_new_submit_expires_an_overdue_open_request_first(p: e.People) -> None:
    o = e.confirmed_order(p.co, p.po)
    old = _age(_cr(p.co, o))
    new = _cr(p.co2, o)
    old.refresh_from_db()
    assert (old.status, new.status) == ("EXPIRED", "SUBMITTED")
    assert AuditEvent.objects.filter(
        action="commercial.change_request.expire", resource_id=str(old.pk)
    ).exists()
    with pytest.raises(StateTransitionNotAllowed):  # EXPIRED is terminal
        changes.withdraw_change_request(
            p.co.caller, old.pk, expected_version=old.row_version, reason="too late"
        )
