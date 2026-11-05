"""``org`` endpoints: tree, units, positions, position assignments (DEC-043 / DEC-048).

Record scope = the unit of the record (unit itself, position's unit, assignment's position's unit): an
ORG_UNIT / ORG_UNIT_SUBTREE grant covers its units only; out of scope -> 404, lists filtered with ``scope_q``
on the same unit field (list == object check). Holding a position grants nothing (DEC-048).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Final

from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.authz import policy as P
from platform_core.authz.policy import Caller, RecordScope
from platform_core.engine.context import db_now
from platform_core.engine.errors import FieldError, NotFound, ValidationFailed
from platform_core.engine.idempotency import StoredResponse
from platform_core.org import service as org
from platform_core.org.models import OrgUnit, Position, PositionAssignment

from . import serializers as S
from .common import (
    NO_STORE,
    Phase01View,
    body_of,
    etag_response,
    if_match,
    in_scope,
    lock_checked,
    not_supported,
    paginate,
    parse_ts,
    query_uuid,
    stored,
    utc_req,
    visible,
    write,
)

READ: Final = "platform.org.read"
MANAGE: Final = "platform.org.manage"
NOW_TOLERANCE: Final = timedelta(minutes=5)  # TECH: client clock skew accepted for "effective now"
MAX_DEPTH: Final = 12
MAX_ROOTS: Final = 50
MAX_CHILDREN: Final = 200
MAX_POSITIONS: Final = 200
MAX_HOLDERS: Final = 20


def unit_scope(unit_id: uuid.UUID | None) -> RecordScope:
    return RecordScope(units=frozenset({unit_id}) if unit_id else frozenset())


def _unit_q(caller: Caller, action: str, field: str) -> Any:
    return P.scope_q(caller, action, unit_field=field, owner_fields=())


# ------------------------------------------------------------------------------------------------ tree
class OrgTreeView(Phase01View):
    required_action = READ

    def get(self, request: Request) -> Response:
        caller = self.caller()
        now = db_now()
        raw_as_of = request.query_params.get("as_of")
        if raw_as_of is not None and abs(parse_ts(raw_as_of, "as_of") - now) > NOW_TOLERANCE:
            raise not_supported("as_of")  # history views (OrgUnitHistory) are not exposed in 01.4
        raw_depth = request.query_params.get("depth")
        depth = MAX_DEPTH
        if raw_depth is not None:
            if not raw_depth.isdigit() or not 1 <= int(raw_depth) <= MAX_DEPTH:
                raise ValidationFailed(errors=[FieldError("depth", "OUT_OF_RANGE")])
            depth = int(raw_depth)
        root_id = query_uuid(request, "root_unit_id")
        units = {u.pk: u for u in OrgUnit.objects.filter(_unit_q(caller, READ, "id"), status="ACTIVE")}
        children: dict[uuid.UUID | None, list[OrgUnit]] = {}
        for u in units.values():
            children.setdefault(u.parent_id, []).append(u)
        positions: dict[uuid.UUID, list[Position]] = {}
        for p in Position.objects.filter(unit_id__in=list(units), status="ACTIVE").order_by("code"):
            positions.setdefault(p.unit_id, []).append(p)
        holders: dict[uuid.UUID, list[dict[str, Any]]] = {}
        live = (
            PositionAssignment.objects.filter(position__unit_id__in=list(units), valid_from__lte=now)
            .exclude(valid_to__lte=now)
            .select_related("user")
            .order_by("kind", "valid_from")
        )
        for a in live:
            holders.setdefault(a.position_id, []).append(
                {"user_id": str(a.user_id), "display_name": a.user.display_name[:200], "kind": a.kind}
            )

        def node(u: OrgUnit, level: int) -> dict[str, Any]:
            kids = sorted(children.get(u.pk, []), key=lambda x: x.code)
            pos = positions.get(u.pk, [])
            truncated = (
                len(kids) > MAX_CHILDREN or len(pos) > MAX_POSITIONS or (level >= depth and bool(kids))
            )
            out: dict[str, Any] = {
                "unit": S.org_unit(u),
                "positions": [
                    {"position": S.position(p), "holders": holders.get(p.pk, [])[:MAX_HOLDERS]}
                    for p in pos[:MAX_POSITIONS]
                ],
                "children": [node(k, level + 1) for k in kids[:MAX_CHILDREN]] if level < depth else [],
            }
            if truncated:
                out["truncated"] = True
            return out

        if root_id is not None:
            if root_id not in units:
                raise NotFound()  # missing, inactive or outside the caller's scope
            roots = [units[root_id]]
        else:  # visible units whose parent is not visible (top of each visible subtree)
            roots = sorted((u for u in units.values() if u.parent_id not in units), key=lambda x: x.code)
        body = {"as_of": utc_req(now), "roots": [node(r, 1) for r in roots[:MAX_ROOTS]]}
        return Response(body, headers=NO_STORE)


# ----------------------------------------------------------------------------------------------- units
def _unit_in_scope(caller: Caller, action: str) -> Any:
    return lambda u: in_scope(caller, action, unit_scope(u.pk))


def _now_or_400(value: Any, field: str) -> None:
    if value is not None and abs(value - db_now()) > NOW_TOLERANCE:
        raise not_supported(field)  # 01.3 engine: org changes take effect now, never back-dated (REV-0109)


class UnitsView(Phase01View):
    required_action = READ
    write_action = MANAGE

    def get(self, request: Request) -> Response:
        qs = OrgUnit.objects.filter(_unit_q(self.caller(), READ, "id"))
        parent = query_uuid(request, "parent_unit_id")
        if parent is not None:
            qs = qs.filter(parent_id=parent)
        return paginate(request, self, qs, S.org_unit)

    def post(self, request: Request) -> Response:
        data = body_of(request, "OrgUnitCreateRequest")
        _now_or_400(data.get("valid_from"), "valid_from")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            parent = data["parent_unit_id"]
            if parent is not None:
                get = OrgUnit.objects.filter(pk=parent).first()
                if get is None or not visible(caller, MANAGE, unit_scope(parent)):
                    raise NotFound()
            else:
                in_scope(caller, MANAGE, unit_scope(None))  # a new root needs a GLOBAL grant
            u = org.create_unit(
                caller,
                code=data["code"],
                name_fa=data["name_fa"],
                unit_type=data["unit_type"],
                parent_id=parent,
                reason=data["reason"],
                request_id=rid,
            )
            return stored(201, S.org_unit(u), etag_version=u.row_version)

        return write(self, run)


class UnitView(Phase01View):
    required_action = READ
    write_action = MANAGE

    def get(self, request: Request, unit_id: uuid.UUID) -> Response:
        caller = self.caller()
        u = OrgUnit.objects.filter(pk=unit_id).first()
        if u is None:
            raise NotFound()
        in_scope(caller, READ, unit_scope(u.pk))
        return etag_response(S.org_unit(u), u.row_version)

    def patch(self, request: Request, unit_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "OrgUnitUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(OrgUnit, unit_id, scope=_unit_in_scope(caller, MANAGE), expected=expected)
            u = org.update_unit(
                caller,
                unit_id,
                expected_version=expected,
                reason=data["reason"],
                name_fa=data.get("name_fa"),
                request_id=rid,
            )
            return stored(200, S.org_unit(u), etag_version=u.row_version)

        return write(self, run)


class MoveUnitView(Phase01View):
    required_action = MANAGE

    def post(self, request: Request, unit_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "OrgUnitMoveRequest")
        _now_or_400(data["effective_from"], "effective_from")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(OrgUnit, unit_id, scope=_unit_in_scope(caller, MANAGE), expected=expected)
            target = data["new_parent_unit_id"]
            if not OrgUnit.objects.filter(pk=target).exists() or not visible(
                caller, MANAGE, unit_scope(target)
            ):
                raise NotFound()
            u = org.move_unit(
                caller,
                unit_id,
                new_parent_id=target,
                expected_version=expected,
                reason=data["reason"],
                request_id=rid,
            )
            return stored(200, S.org_unit(u), etag_version=u.row_version)

        return write(self, run)


class DeactivateUnitView(Phase01View):
    required_action = MANAGE

    def post(self, request: Request, unit_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "ReasonRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(OrgUnit, unit_id, scope=_unit_in_scope(caller, MANAGE), expected=expected)
            u = org.deactivate_unit(
                caller, unit_id, expected_version=expected, reason=data["reason"], request_id=rid
            )
            return stored(200, S.org_unit(u), etag_version=u.row_version)

        return write(self, run)


# ------------------------------------------------------------------------------------------- positions
def _position_in_scope(caller: Caller, action: str) -> Any:
    return lambda p: in_scope(caller, action, unit_scope(p.unit_id))


class PositionsView(Phase01View):
    required_action = READ
    write_action = MANAGE

    def get(self, request: Request) -> Response:
        qs = Position.objects.filter(_unit_q(self.caller(), READ, "unit_id"))
        unit = query_uuid(request, "unit_id")
        if unit is not None:
            qs = qs.filter(unit_id=unit)
        return paginate(request, self, qs, S.position)

    def post(self, request: Request) -> Response:
        data = body_of(request, "PositionCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            unit = data["unit_id"]
            if not OrgUnit.objects.filter(pk=unit).exists():
                raise NotFound()
            in_scope(caller, MANAGE, unit_scope(unit))
            p = org.create_position(
                caller,
                unit_id=unit,
                code=data["code"],
                title_fa=data["title_fa"],
                reports_to_id=data.get("reports_to_position_id"),
                is_unit_head=bool(data.get("is_unit_head", False)),
                primary_capacity=int(data.get("primary_capacity", 1)),
                reason=data["reason"],
                request_id=rid,
            )
            return stored(201, S.position(p), etag_version=p.row_version)

        return write(self, run)


class PositionView(Phase01View):
    required_action = READ
    write_action = MANAGE

    def get(self, request: Request, position_id: uuid.UUID) -> Response:
        caller = self.caller()
        p = Position.objects.filter(pk=position_id).first()
        if p is None:
            raise NotFound()
        in_scope(caller, READ, unit_scope(p.unit_id))
        return etag_response(S.position(p), p.row_version)

    def patch(self, request: Request, position_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "PositionUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(Position, position_id, scope=_position_in_scope(caller, MANAGE), expected=expected)
            kwargs: dict[str, Any] = {}
            if "reports_to_position_id" in data:
                kwargs["reports_to_id"] = data["reports_to_position_id"]
            p = org.update_position(
                caller,
                position_id,
                expected_version=expected,
                reason=data["reason"],
                primary_capacity=data.get("primary_capacity"),
                title_fa=data.get("title_fa"),
                is_unit_head=data.get("is_unit_head"),
                request_id=rid,
                **kwargs,
            )
            return stored(200, S.position(p), etag_version=p.row_version)

        return write(self, run)


# -------------------------------------------------------------------------------- position assignments
class PositionAssignmentsView(Phase01View):
    required_action = READ
    write_action = MANAGE

    def get(self, request: Request) -> Response:
        qs = PositionAssignment.objects.filter(_unit_q(self.caller(), READ, "position__unit_id"))
        user = query_uuid(request, "user_id")
        position = query_uuid(request, "position_id")
        if user is not None:
            qs = qs.filter(user_id=user)
        if position is not None:
            qs = qs.filter(position_id=position)
        return paginate(request, self, qs, S.position_assignment)

    def post(self, request: Request) -> Response:
        data = body_of(request, "PositionAssignmentCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            p = Position.objects.filter(pk=data["position_id"]).first()
            if p is None:
                raise NotFound()
            in_scope(caller, MANAGE, unit_scope(p.unit_id))
            a = org.assign_position(
                caller,
                position_id=p.pk,
                user_id=data["user_id"],
                kind=data["kind"],
                reason=data["reason"],
                valid_from=data["valid_from"],
                valid_to=data.get("valid_to"),
                request_id=rid,
            )
            return stored(201, S.position_assignment(a), etag_version=a.row_version)

        return write(self, run)


class EndPositionAssignmentView(Phase01View):
    required_action = MANAGE

    def post(self, request: Request, position_assignment_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "ReasonRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            def scope(a: PositionAssignment) -> None:
                in_scope(caller, MANAGE, unit_scope(a.position.unit_id))

            lock_checked(PositionAssignment, position_assignment_id, scope=scope, expected=expected)
            a = org.end_position_assignment(
                caller,
                position_assignment_id,
                expected_version=expected,
                reason=data["reason"],
                request_id=rid,
            )
            return stored(200, S.position_assignment(a), etag_version=a.row_version)

        return write(self, run)
