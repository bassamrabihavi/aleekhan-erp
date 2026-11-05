"""``admin-identity`` endpoints: users, sessions of a user, permission catalogue, roles, role assignments.

Identity records carry no org unit, so their record scope is GLOBAL-only (``RecordScope()``): a grant held
through an ORG_UNIT / ORG_UNIT_SUBTREE assignment never reaches them (list and object answer alike, 404).
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from django.db.models import Q
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.authz import policy as P
from platform_core.authz.policy import Caller, RecordScope
from platform_core.engine.context import db_now
from platform_core.engine.errors import FieldError, NotFound, ValidationFailed
from platform_core.engine.idempotency import StoredResponse
from platform_core.engine.redaction import REDACTED
from platform_core.identity import mfa, roles, sessions, users
from platform_core.identity.models import Credential, Permission, Role, RoleAssignment, Session, User
from platform_core.identity.passwords import generate_one_time_password

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
    query_choice,
    query_uuid,
    stored,
    utc_req,
    write,
)

NO_UNIT: Final = RecordScope()
USER_READ: Final = "platform.identity.user.read"
SESSION_READ: Final = "platform.identity.session.read"
SESSION_REVOKE: Final = "platform.identity.session.revoke"
ROLE_READ: Final = "platform.identity.role.read"
ROLE_MANAGE: Final = "platform.identity.role.manage"
ASSIGN_READ: Final = "platform.identity.assignment.read"
ASSIGN_GRANT: Final = "platform.identity.assignment.grant"


def global_q(caller: Caller, action: str) -> Q:
    return P.scope_q(caller, action, unit_field=None, owner_fields=())


def _global(caller: Caller, action: str) -> Any:
    return lambda _obj: in_scope(caller, action, NO_UNIT)


# ------------------------------------------------------------------------------------------------ users
class UsersView(Phase01View):
    required_action = USER_READ
    write_action = "platform.identity.user.create"

    def get(self, request: Request) -> Response:
        caller = self.caller()
        status = query_choice(request, "status", ("CREATED", "ACTIVE", "LOCKED", "DISABLED"))
        q = request.query_params.get("q")
        if q is not None and not 1 <= len(q) <= 64:
            raise ValidationFailed(errors=[FieldError("q", "OUT_OF_RANGE")])
        qs = User.objects.filter(global_q(caller, USER_READ))
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(display_name__icontains=q))
        return paginate(request, self, qs, S.user)

    def post(self, request: Request) -> Response:
        data = body_of(request, "UserCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            secret = generate_one_time_password()
            u = users.create_user(
                caller,
                username=data["username"],
                display_name=data["display_name"],
                account_kind=data["account_kind"],
                network_policy=data["network_policy"],
                initial_password=secret,
                reason=data["reason"],
                request_id=rid,
            )
            return _with_credential(201, {"user": S.user(u)}, u, secret)

        return write(self, run)


def _with_credential(status: int, body: dict[str, Any], u: User, secret: str) -> StoredResponse:
    cred = Credential.objects.get(user=u)
    assert cred.one_time_expires_at is not None
    credential = {
        "user_id": str(u.pk),
        "one_time_password": secret,
        "expires_at": utc_req(cred.one_time_expires_at),
    }
    full = {**body, "one_time_credential": credential}
    # the idempotency record never stores the one-time password (shown once, DEC-051)
    safe = {**body, "one_time_credential": {**credential, "one_time_password": REDACTED}}
    return StoredResponse(status, full, {"ETag": f'"{u.row_version}"', **NO_STORE}, safe, True)


def _user_or_404(caller: Caller, action: str, user_id: uuid.UUID) -> User:
    u = User.objects.filter(pk=user_id).first()
    if u is None:
        raise NotFound()
    in_scope(caller, action, NO_UNIT)
    return u


class UserView(Phase01View):
    required_action = USER_READ
    write_action = "platform.identity.user.update"

    def get(self, request: Request, user_id: uuid.UUID) -> Response:
        u = _user_or_404(self.caller(), USER_READ, user_id)
        return etag_response(S.user(u), u.row_version)

    def patch(self, request: Request, user_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "UserUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(
                User, user_id, scope=_global(caller, "platform.identity.user.update"), expected=expected
            )
            u = users.update_user(
                caller,
                user_id,
                reason=data["reason"],
                display_name=data.get("display_name"),
                network_policy=data.get("network_policy"),
                request_id=rid,
            )
            return stored(200, S.user(u), etag_version=u.row_version)

        return write(self, run)


def _user_action(action: str, fn: Any, *, result: str = "user") -> type[Phase01View]:
    """POST /admin/users/{user_id}/<verb>: If-Match on the user + ReasonRequest + the identity service."""

    class _View(Phase01View):
        required_action = action

        def post(self, request: Request, user_id: uuid.UUID) -> Response:
            expected = if_match(self)
            data = body_of(request, "ReasonRequest")

            def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
                lock_checked(User, user_id, scope=_global(caller, action), expected=expected)
                if result == "credential":
                    secret = generate_one_time_password()
                    u = users.reset_password(
                        caller, user_id, new_one_time_password=secret, reason=data["reason"], request_id=rid
                    )
                    cred = _with_credential(200, {}, u, secret)
                    body = cred.body["one_time_credential"]
                    safe = cred.secret_free_body["one_time_credential"]
                    return StoredResponse(200, body, {"ETag": f'"{u.row_version}"', **NO_STORE}, safe, True)
                fn(caller, user_id, reason=data["reason"], request_id=rid)
                u = User.objects.get(pk=user_id)
                return stored(200, S.user(u), etag_version=u.row_version)

            return write(self, run)

    _View.__name__ = f"UserAction_{action.rsplit('.', 1)[-1]}"
    return _View


DisableUserView = _user_action("platform.identity.user.disable", users.disable_user)
EnableUserView = _user_action("platform.identity.user.disable", users.enable_user)
UnlockUserView = _user_action("platform.identity.user.unlock", users.unlock_user)
ResetPasswordView = _user_action("platform.identity.user.reset_password", None, result="credential")
ResetMfaView = _user_action("platform.identity.user.reset_mfa", mfa.reset_user_mfa)
RevokeUserSessionsView = _user_action(SESSION_REVOKE, sessions.revoke_sessions_of)


class UserSessionsView(Phase01View):
    required_action = SESSION_READ

    def get(self, request: Request, user_id: uuid.UUID) -> Response:
        _user_or_404(self.caller(), SESSION_READ, user_id)
        qs = Session.objects.filter(user_id=user_id, state__in=sessions.LIVE)
        return paginate(request, self, qs, S.session_info)


class UserEffectivePermissionsView(Phase01View):
    required_action = USER_READ

    def get(self, request: Request, user_id: uuid.UUID) -> Response:
        u = _user_or_404(self.caller(), USER_READ, user_id)
        return Response(S.effective_permissions(u.pk, db_now()), headers=NO_STORE)


# ------------------------------------------------------------------------------------------- catalogue
class PermissionsView(Phase01View):
    required_action = ROLE_READ

    def get(self, request: Request) -> Response:
        qs = Permission.objects.filter(global_q(self.caller(), ROLE_READ))
        return paginate(request, self, qs, S.permission, ordering="action")


class RolesView(Phase01View):
    required_action = ROLE_READ
    write_action = ROLE_MANAGE

    def get(self, request: Request) -> Response:
        qs = Role.objects.filter(global_q(self.caller(), ROLE_READ)).prefetch_related("grants")
        return paginate(request, self, qs, S.role, ordering="code")

    def post(self, request: Request) -> Response:
        data = body_of(request, "RoleCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            in_scope(caller, ROLE_MANAGE, NO_UNIT)
            r = roles.create_role(
                caller,
                code=data["code"],
                name_fa=data["name_fa"],
                kind=data["kind"],
                reason=data["reason"],
                request_id=rid,
            )
            if data["permissions"]:
                r = roles.update_role(
                    caller, r.pk, reason=data["reason"], permissions=data["permissions"], request_id=rid
                )
            return stored(201, S.role(r), etag_version=r.row_version)

        return write(self, run)


class RoleView(Phase01View):
    required_action = ROLE_READ
    write_action = ROLE_MANAGE

    def get(self, request: Request, role_id: uuid.UUID) -> Response:
        caller = self.caller()
        r = Role.objects.filter(pk=role_id).first()
        if r is None:
            raise NotFound()
        in_scope(caller, ROLE_READ, NO_UNIT)
        return etag_response(S.role(r), r.row_version)

    def patch(self, request: Request, role_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "RoleUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(Role, role_id, scope=_global(caller, ROLE_MANAGE), expected=expected)
            r = roles.update_role(
                caller,
                role_id,
                reason=data["reason"],
                name_fa=data.get("name_fa"),
                permissions=data.get("permissions"),
                request_id=rid,
            )
            return stored(200, S.role(r), etag_version=r.row_version)

        return write(self, run)


def _role_action(fn: Any) -> type[Phase01View]:
    class _View(Phase01View):
        required_action = ROLE_MANAGE

        def post(self, request: Request, role_id: uuid.UUID) -> Response:
            expected = if_match(self)
            data = body_of(request, "ReasonRequest")

            def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
                lock_checked(Role, role_id, scope=_global(caller, ROLE_MANAGE), expected=expected)
                r = fn(caller, role_id, reason=data["reason"], request_id=rid)
                return stored(200, S.role(r), etag_version=r.row_version)

            return write(self, run)

    return _View


ActivateRoleView = _role_action(roles.activate_role)
RetireRoleView = _role_action(roles.retire_role)


# ----------------------------------------------------------------------------------------- assignments
class AssignmentsView(Phase01View):
    required_action = ASSIGN_READ
    write_action = ASSIGN_GRANT

    def get(self, request: Request) -> Response:
        qs = RoleAssignment.objects.filter(global_q(self.caller(), ASSIGN_READ))
        user_id = query_uuid(request, "user_id")
        role_id = query_uuid(request, "role_id")
        if user_id:
            qs = qs.filter(user_id=user_id)
        if role_id:
            qs = qs.filter(role_id=role_id)
        return paginate(request, self, qs, S.assignment)

    def post(self, request: Request) -> Response:
        data = body_of(request, "RoleAssignmentCreateRequest")
        if "valid_from" in data:
            raise not_supported("valid_from")  # starts now (01.3 engine); future starts not implemented
        scope = data["scope"]
        if scope.get("kind") not in ("GLOBAL", "ORG_UNIT", "ORG_UNIT_SUBTREE"):
            raise ValidationFailed(errors=[FieldError("scope.kind", "NOT_SUPPORTED")])

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            in_scope(caller, ASSIGN_GRANT, NO_UNIT)
            r = Role.objects.filter(pk=data["role_id"]).first()
            if r is None:
                raise NotFound()
            ra = roles.grant_role(
                caller,
                user_id=data["user_id"],
                role_code=r.code,
                scope_kind=scope["kind"],
                scope_unit_id=scope.get("ref_id"),
                valid_to=data.get("valid_to"),
                reason=data["reason"],
                allow_self=bool(data.get("confirm_self_assignment", False)),
                request_id=rid,
            )
            return stored(201, S.assignment(ra), etag_version=ra.row_version)

        return write(self, run)


class AssignmentView(Phase01View):
    required_action = ASSIGN_READ

    def get(self, request: Request, assignment_id: uuid.UUID) -> Response:
        caller = self.caller()
        ra = RoleAssignment.objects.filter(pk=assignment_id).first()
        if ra is None:
            raise NotFound()
        in_scope(caller, ASSIGN_READ, NO_UNIT)
        return etag_response(S.assignment(ra), ra.row_version)


class RevokeAssignmentView(Phase01View):
    required_action = ASSIGN_GRANT

    def post(self, request: Request, assignment_id: uuid.UUID) -> Response:
        expected = if_match(self)
        data = body_of(request, "ReasonRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            lock_checked(
                RoleAssignment, assignment_id, scope=_global(caller, ASSIGN_GRANT), expected=expected
            )
            ra = roles.revoke_assignment(caller, assignment_id, reason=data["reason"], request_id=rid)
            return stored(200, S.assignment(ra), etag_version=ra.row_version)

        return write(self, run)
