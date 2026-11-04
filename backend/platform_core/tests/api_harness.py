"""TEST-ONLY URLconf and views. Never routed in production (``aleekhan/urls.py`` does not include it; a test
asserts that no production route resolves to this module).

Purpose: prove the reusable API utilities (scoped permission + 404 for out-of-scope records, cursor
pagination, ETag/If-Match, Idempotency-Key replay, problem mapping) against real HTTP requests while PHASE_00
has no business endpoints and no authentication backend.

* :class:`HeaderTestAuthentication` - a SYNTHETIC principal from ``X-Test-Principal: <uuid>`` and
  ``X-Test-Scope: a,b`` headers. It exists only here; production has no authentication class at all
  (``DEFAULT_AUTHENTICATION_CLASSES = []``) until PHASE_01.
* :class:`SyntheticScopePolicy` - allows two synthetic actions and scopes outbox rows by ``aggregate_id``.
* Synthetic resource = ``platform_outbox_event`` rows created by the tests (the only versioned table in
  PHASE_00); ``aggregate_id`` plays the role of the record scope.
* 00.6: :class:`IntegrationHarnessPolicy` grants only the actions listed in ``X-Test-Actions: a,b`` and scopes
  integration sources / conflict items by source code (``X-Test-Scope``), so the explicit-permission and
  out-of-scope (404) behaviour of the production integration views is exercised over HTTP.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from django.db import models
from django.urls import URLPattern, URLResolver, include, path
from rest_framework import serializers
from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.api import integration_views as iv
from platform_core.api.base import AleekhanAPIView
from platform_core.api.concurrency import expected_version, with_row_etag
from platform_core.api.idempotent import idempotent_response
from platform_core.api.pagination import AleekhanCursorPagination
from platform_core.api.permissions import Principal, ScopedPermission, scoped_queryset
from platform_core.api.views import AccessGateCheckView
from platform_core.engine.concurrency import make_etag, update_versioned
from platform_core.engine.errors import EngineContractError, FieldError, NotFound, ValidationFailed
from platform_core.engine.idempotency import StoredResponse
from platform_core.engine.rules import require_approved_rule
from platform_core.engine.uow import UnitOfWork
from platform_core.models import OutboxEvent

READ = "platform.synthetic.read"
UPDATE = "platform.synthetic.update"


@dataclass(frozen=True)
class SyntheticPrincipal:
    actor_id: uuid.UUID
    scope: frozenset[str] = field(default_factory=frozenset)
    actions: frozenset[str] = field(default_factory=frozenset)
    is_authenticated: bool = True

    @property
    def pk(self) -> uuid.UUID:
        return self.actor_id


class HeaderTestAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[SyntheticPrincipal, None] | None:
        raw = request.headers.get("X-Test-Principal")
        if not raw:
            return None
        scope = frozenset(s for s in request.headers.get("X-Test-Scope", "").split(",") if s)
        actions = frozenset(s for s in request.headers.get("X-Test-Actions", "").split(",") if s)
        return SyntheticPrincipal(uuid.UUID(raw), scope, actions), None


class SyntheticScopePolicy:
    def allows_action(self, principal: Principal, action: str) -> bool:
        return action in {READ, UPDATE}

    def _scope(self, principal: Principal) -> frozenset[str]:
        return getattr(principal, "scope", frozenset())

    def allows_record(self, principal: Principal, action: str, obj: Any) -> bool:
        return getattr(obj, "aggregate_id", None) in self._scope(principal)

    def scope_queryset[M: models.Model](
        self, principal: Principal, action: str, queryset: models.QuerySet[M]
    ) -> models.QuerySet[M]:
        return queryset.filter(aggregate_id__in=sorted(self._scope(principal)))


class IntegrationHarnessPolicy:
    """Grants exactly the actions in ``X-Test-Actions``; record scope = source codes in ``X-Test-Scope``."""

    def _scope(self, principal: Principal) -> frozenset[str]:
        return getattr(principal, "scope", frozenset())

    def allows_action(self, principal: Principal, action: str) -> bool:
        return action in getattr(principal, "actions", frozenset())

    def allows_record(self, principal: Principal, action: str, obj: Any) -> bool:
        code = getattr(obj, "code", None) or getattr(getattr(obj, "source", None), "code", None)
        return code in self._scope(principal)

    def scope_queryset[M: models.Model](
        self, principal: Principal, action: str, queryset: models.QuerySet[M]
    ) -> models.QuerySet[M]:
        scope = sorted(self._scope(principal))
        if queryset.model.__name__ == "IntegrationSource":
            return queryset.filter(code__in=scope)
        return queryset.filter(source__code__in=scope)


class HarnessFreshnessView(iv.IntegrationFreshnessView):
    authentication_classes = [HeaderTestAuthentication]
    access_policy = IntegrationHarnessPolicy()


class HarnessConflictListView(iv.ConflictListView):
    authentication_classes = [HeaderTestAuthentication]
    access_policy = IntegrationHarnessPolicy()


class HarnessConflictDetailView(iv.ConflictDetailView):
    authentication_classes = [HeaderTestAuthentication]
    access_policy = IntegrationHarnessPolicy()


class HarnessConflictResolveView(iv.ConflictResolveView):
    authentication_classes = [HeaderTestAuthentication]
    access_policy = IntegrationHarnessPolicy()


class OutboxRowSerializer(serializers.ModelSerializer[OutboxEvent]):
    class Meta:
        model = OutboxEvent
        fields = ["id", "aggregate_id", "row_version", "last_error"]


class _HarnessView(AleekhanAPIView):
    authentication_classes = [HeaderTestAuthentication]
    permission_classes = [ScopedPermission]
    access_policy = SyntheticScopePolicy()


class SyntheticListView(_HarnessView):
    required_action = READ

    def get(self, request: Request) -> Response:
        qs = scoped_queryset(request, self, OutboxEvent.objects.all())
        paginator = AleekhanCursorPagination()
        page = paginator.paginate_queryset(qs, request, self)
        assert page is not None
        return paginator.get_paginated_response(OutboxRowSerializer(page, many=True).data)


class SyntheticDetailView(_HarnessView):
    required_action = READ

    def get_object(self, pk: int) -> OutboxEvent:
        # unscoped lookup + object permission: proves has_object_permission -> 404 for out-of-scope rows
        obj = OutboxEvent.objects.filter(pk=pk).first()
        if obj is None:
            raise NotFound()
        self.check_object_permissions(self.request, obj)
        return obj

    def get(self, request: Request, pk: int) -> Response:
        obj = self.get_object(pk)
        return with_row_etag(Response(OutboxRowSerializer(obj).data), obj.row_version)


class SyntheticUpdateView(_HarnessView):
    """PATCH with If-Match + Idempotency-Key -> update_versioned on the scoped queryset, audit + outbox."""

    required_action = UPDATE

    def patch(self, request: Request, pk: int) -> Response:
        expected = expected_version(request)
        qs = scoped_queryset(request, self, OutboxEvent.objects.all())
        data = request.data if isinstance(request.data, dict) else {}

        def handler(uow: UnitOfWork) -> StoredResponse:
            note = data.get("last_error")
            if not isinstance(note, str) or len(note) > 200:
                raise ValidationFailed(errors=[FieldError(field="last_error", code="INVALID")])
            new_version = update_versioned(qs, pk, expected, last_error=note)
            uow.audit(
                action="platform.synthetic.update",
                resource_type="platform.synthetic",
                resource_id=str(pk),
                resource_version=new_version,
            )
            uow.emit(
                event_type="platform.synthetic.updated",
                aggregate_type="platform.synthetic",
                aggregate_id=f"harness-{pk}",
                aggregate_version=new_version,
                payload={"id": pk},
            )
            return StoredResponse(
                200, {"id": pk, "row_version": new_version}, {"ETag": make_etag(new_version)}
            )

        return idempotent_response(request, endpoint=f"/api/v1/_test/synthetic/{pk}", handler=handler)


class DefaultPermissionView(AleekhanAPIView):
    """No permission declared -> the global default DenyByDefault applies."""

    authentication_classes = [HeaderTestAuthentication]

    def get(self, request: Request) -> Response:  # pragma: no cover - must never be reached
        return Response({"reached": True})


class ErrorView(AleekhanAPIView):
    """Raises a chosen exception to test the global exception handler."""

    authentication_classes: list[type[BaseAuthentication]] = []
    permission_classes = []

    def get(self, request: Request, kind: str) -> Response:
        if kind == "contract":
            raise EngineContractError("SYNTHETIC-SECRET-contract-detail")
        if kind == "runtime":
            raise RuntimeError("SYNTHETIC-SECRET password=hunter2 SELECT * FROM x")
        if kind == "rule":
            require_approved_rule("DEC-005", rule="synthetic.code.issue")
        if kind == "drf-validation":
            raise serializers.ValidationError({"qty": ["must be positive"], "nested": {"x": ["bad"]}})
        return Response({"kind": kind})


class HarnessAccessGateView(AccessGateCheckView):
    authentication_classes = [HeaderTestAuthentication]


test_patterns: list[URLPattern] = [
    path("synthetic", SyntheticListView.as_view()),
    path("synthetic/<int:pk>", SyntheticDetailView.as_view()),
    path("synthetic/<int:pk>/update", SyntheticUpdateView.as_view()),
    path("default-permission", DefaultPermissionView.as_view()),
    path("errors/<str:kind>", ErrorView.as_view()),
    path("access-gate/check", HarnessAccessGateView.as_view()),
    path("integration/freshness", HarnessFreshnessView.as_view()),
    path("integration/conflicts", HarnessConflictListView.as_view()),
    path("integration/conflicts/<uuid:conflict_id>", HarnessConflictDetailView.as_view()),
    path("integration/conflicts/<uuid:conflict_id>/resolve", HarnessConflictResolveView.as_view()),
]

urlpatterns: list[URLPattern | URLResolver] = [
    path("api/v1/", include("platform_core.api.urls")),
    path("api/v1/_test/", include(test_patterns)),
]

handler400 = "platform_core.api.problems.bad_request"
handler403 = "platform_core.api.problems.permission_denied"
handler404 = "platform_core.api.problems.page_not_found"
handler500 = "platform_core.api.problems.server_error"
