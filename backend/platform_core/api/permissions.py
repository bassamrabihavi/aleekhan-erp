"""Authorization skeleton: deny by default, explicit public allowlist, scoped (action + record) permission.

PHASE_00 has no users, roles or login (PHASE_01; DEC-003: users are created only inside the system by the
owner/admin, never AD/LDAP/SSO). Therefore:

* :class:`DenyByDefault` is the DRF default: a view that does not choose a permission is closed
  (401 without a principal, 403 ``ACCESS_DENIED`` with one).
* :class:`PublicEndpoint` is allowed only on the allowlisted platform probes (health/version); a test walks
  the production URLconf and fails if any other view uses it.
* :class:`ScopedPermission` checks the view's ``required_action`` against the :data:`ACCESS_POLICY` and, per
  record, the record scope. A record outside the caller's scope is reported as 404 ``NOT_FOUND`` (not 403)
  to prevent enumeration (BOLA/IDOR, SEC-01). The PHASE_00 policy :class:`DenyAllPolicy` denies everything;
  PHASE_01 replaces it (reviewed commit) with the role/scope policy from the approved permission matrix.
  There is intentionally no setting or environment variable that can swap the policy.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

from django.db import models
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from platform_core.engine.errors import AccessDenied, AuthenticationRequired, EngineContractError, NotFound

if TYPE_CHECKING:  # DRF imports these modules from its settings; avoid an import cycle
    from rest_framework.views import APIView


@runtime_checkable
class Principal(Protocol):
    """The authenticated caller. PHASE_01 provides the real implementation (local user)."""

    @property
    def is_authenticated(self) -> bool: ...

    @property
    def actor_id(self) -> uuid.UUID: ...


def principal_of(request: Request) -> Principal | None:
    """The authenticated principal, or ``None`` (always ``None`` in PHASE_00 production code)."""
    user = getattr(request, "user", None)
    if user is None or getattr(user, "is_authenticated", False) is not True:
        return None
    if not isinstance(user, Principal) or not isinstance(user.actor_id, uuid.UUID):
        return None
    return user


def require_principal(request: Request) -> Principal:
    principal = principal_of(request)
    if principal is None:
        raise AuthenticationRequired()
    return principal


class AccessPolicy(Protocol):
    def allows_action(self, principal: Principal, action: str) -> bool: ...

    def allows_record(self, principal: Principal, action: str, obj: Any) -> bool: ...

    def scope_queryset[M: models.Model](
        self, principal: Principal, action: str, queryset: models.QuerySet[M]
    ) -> models.QuerySet[M]: ...


class DenyAllPolicy:
    """PHASE_00 policy: no action is allowed, no record is in scope (permission matrix still PROPOSED)."""

    def allows_action(self, principal: Principal, action: str) -> bool:
        return False

    def allows_record(self, principal: Principal, action: str, obj: Any) -> bool:
        return False

    def scope_queryset[M: models.Model](
        self, principal: Principal, action: str, queryset: models.QuerySet[M]
    ) -> models.QuerySet[M]:
        return queryset.none()


ACCESS_POLICY: Final[AccessPolicy] = DenyAllPolicy()


def policy_for(view: APIView) -> AccessPolicy:
    policy = getattr(view, "access_policy", None)
    return policy if policy is not None else ACCESS_POLICY


def required_action(view: APIView) -> str:
    action = getattr(view, "required_action", None)
    if not isinstance(action, str) or not action:
        raise EngineContractError(f"{type(view).__name__} uses ScopedPermission without required_action")
    return action


class DenyByDefault(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        require_principal(request)
        raise AccessDenied()


class PublicEndpoint(BasePermission):
    """Unauthenticated access. Allowed only for the platform probes listed in ``PUBLIC_OPERATIONS``."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return True


# openapi-draft operations with ``security: []`` (contract test keeps code and spec in sync).
PUBLIC_OPERATIONS: Final[frozenset[str]] = frozenset({"getLiveness", "getReadiness", "getVersion"})


class AuthenticatedPrincipal(BasePermission):
    """Only requires a principal (401 otherwise). Used by the access-gate stub, which never grants."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        require_principal(request)
        return True


class ScopedPermission(BasePermission):
    """Action permission + record scope. Views set ``required_action`` (e.g. ``module.entity.read``)."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        principal = require_principal(request)
        if not policy_for(view).allows_action(principal, required_action(view)):
            raise AccessDenied()
        return True

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        principal = require_principal(request)
        if not policy_for(view).allows_record(principal, required_action(view), obj):
            raise NotFound()  # out of scope == does not exist (BOLA/IDOR)
        return True


def scoped_queryset[M: models.Model](
    request: Request, view: APIView, queryset: models.QuerySet[M]
) -> models.QuerySet[M]:
    """Restrict a queryset to the caller's record scope (use for lists and for object lookup)."""
    principal = require_principal(request)
    return policy_for(view).scope_queryset(principal, required_action(view), queryset)
