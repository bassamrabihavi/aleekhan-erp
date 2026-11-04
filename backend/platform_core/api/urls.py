"""Routes under ``/api/v1`` (openapi-draft ``servers``). PHASE_00: platform probes, access gate,
integration."""

from __future__ import annotations

from django.urls import URLPattern, path

from . import integration_views, views

urlpatterns: list[URLPattern] = [
    path("health/live", views.LivenessView.as_view(), name="health-live"),
    path("health/ready", views.ReadinessView.as_view(), name="health-ready"),
    path("version", views.VersionView.as_view(), name="version"),
    path("access-gate/check", views.AccessGateCheckView.as_view(), name="access-gate-check"),
    path(
        "integration/freshness",
        integration_views.IntegrationFreshnessView.as_view(),
        name="integration-freshness",
    ),
    path("integration/conflicts", integration_views.ConflictListView.as_view(), name="integration-conflicts"),
    path(
        "integration/conflicts/<uuid:conflict_id>",
        integration_views.ConflictDetailView.as_view(),
        name="integration-conflict",
    ),
    path(
        "integration/conflicts/<uuid:conflict_id>/resolve",
        integration_views.ConflictResolveView.as_view(),
        name="integration-conflict-resolve",
    ),
]
