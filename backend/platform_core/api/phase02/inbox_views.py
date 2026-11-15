"""``GET /me/decision-inbox`` (02.5, contract 0.8.3-draft, employer decision 2026-11-15).

The PHASE_02 decisions that wait for the CALLER, so they appear in the PHASE_01 approval inbox (page 39) next
to the platform approval requests, each linking to its own page:

* ``ORDER_CONFIRM`` - a VALIDATED order (``commercial.order.confirm``); never the order's creator (DEC-057).
* ``CHANGE_DECIDE`` - a SUBMITTED change request (``commercial.change.decide``); never its requester nor the
  planning approver of the same request (DEC-059 amendment 2026-11-12).
* ``CHANGE_PLANNING_DECISION`` - a due-date change request still waiting for planning (SUBMITTED or
  APPROVED, no planning approval / rejection yet) (``commercial.change.planning_approve``); never its
  requester nor the manager who decided it.
* ``CODE_RULE_APPROVE`` - a code rule revision IN_REVIEW (``identity.code_rule.approve``); never its maker.

Read-only and session-only (like ``/me/permissions``): the feed itself needs no single permission, every block
is filtered by the caller's own GLOBAL grant of the deciding permission (a caller without it sees nothing of
that kind). It lists what the caller MAY decide; the decision itself is still the owning operation, which
re-checks permission, fresh MFA, maker-checker, state and version. Nothing is written here and no personal
data (customer names, representative names) is returned - only ids, numbers and times.
"""

from __future__ import annotations

from typing import Any, Final

from django.db.models import Q
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.authz import policy as P
from platform_core.commercial.models import (
    ChangeKind,
    ChangeStatus,
    CustomerOrder,
    OrderChangeRequest,
    OrderStatus,
)
from platform_core.engine.context import db_now
from platform_core.product_identity.models import CodeRuleRevision, CodeRuleStatus

from ..phase01.common import NO_STORE, SessionView, sid, utc_req
from .common import GLOBAL

PER_KIND: Final = 100
ORDER_CONFIRM: Final = "commercial.order.confirm"
CHANGE_DECIDE: Final = "commercial.change.decide"
CHANGE_PLANNING: Final = "commercial.change.planning_approve"
RULE_APPROVE: Final = "identity.code_rule.approve"


def _item(
    kind: str,
    entity_type: str,
    pk: Any,
    number: str | None,
    revision_no: int | None,
    by: Any,
    at: Any,
    rv: int,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "entity_type": entity_type,
        "entity_id": str(pk),
        "number": number,
        "revision_no": revision_no,
        "requested_by": sid(by),
        "requested_at": utc_req(at),
        "row_version": rv,
    }


class MyDecisionInboxView(SessionView):
    def get(self, request: Request) -> Response:
        caller = self.caller()
        me = caller.user_id
        items: list[dict[str, Any]] = []
        truncated = False

        def take(rows: list[Any]) -> list[Any]:
            nonlocal truncated
            if len(rows) > PER_KIND:
                truncated = True
            return rows[:PER_KIND]

        if P.can(caller, ORDER_CONFIRM, GLOBAL):
            orders = CustomerOrder.objects.filter(status=OrderStatus.VALIDATED).exclude(created_by_id=me)
            for o in take(list(orders.order_by("-updated_at", "id")[: PER_KIND + 1])):
                items.append(
                    _item(
                        "ORDER_CONFIRM",
                        "customer_order",
                        o.pk,
                        o.order_no,
                        None,
                        o.created_by_id,
                        o.updated_at,
                        o.row_version,
                    )
                )
        if P.can(caller, CHANGE_DECIDE, GLOBAL):
            decide = (
                OrderChangeRequest.objects.filter(status=ChangeStatus.SUBMITTED)
                .exclude(requested_by_id=me)
                .exclude(planning_approved_by_id=me)
            )
            for cr in take(list(decide.order_by("-submitted_at", "id")[: PER_KIND + 1])):
                items.append(
                    _item(
                        "CHANGE_DECIDE",
                        "change_request",
                        cr.pk,
                        cr.request_no,
                        None,
                        cr.requested_by_id,
                        cr.submitted_at or cr.created_at,
                        cr.row_version,
                    )
                )
        if P.can(caller, CHANGE_PLANNING, GLOBAL):
            planning = (
                OrderChangeRequest.objects.filter(
                    kind=ChangeKind.DUE_DATE_CHANGE,
                    status__in=(ChangeStatus.SUBMITTED, ChangeStatus.APPROVED),
                    planning_approved_by__isnull=True,
                    planning_rejected_by__isnull=True,
                )
                .exclude(requested_by_id=me)
                .exclude(Q(decided_by_id=me))
            )
            for cr in take(list(planning.order_by("-submitted_at", "id")[: PER_KIND + 1])):
                items.append(
                    _item(
                        "CHANGE_PLANNING_DECISION",
                        "change_request",
                        cr.pk,
                        cr.request_no,
                        None,
                        cr.requested_by_id,
                        cr.submitted_at or cr.created_at,
                        cr.row_version,
                    )
                )
        if P.can(caller, RULE_APPROVE, GLOBAL):
            rules = CodeRuleRevision.objects.filter(status=CodeRuleStatus.IN_REVIEW).exclude(created_by_id=me)
            for r in take(list(rules.order_by("-updated_at", "id")[: PER_KIND + 1])):
                items.append(
                    _item(
                        "CODE_RULE_APPROVE",
                        "code_rule_revision",
                        r.pk,
                        None,
                        r.revision_no,
                        r.created_by_id,
                        r.updated_at,
                        r.row_version,
                    )
                )
        items.sort(key=lambda x: (x["requested_at"], x["entity_id"]), reverse=True)
        body = {"as_of": utc_req(db_now()), "items": items, "truncated": truncated}
        return Response(body, headers=NO_STORE)
