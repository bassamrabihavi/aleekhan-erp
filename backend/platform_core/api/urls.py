"""Routes under ``/api/v1`` (openapi-draft ``servers``). PHASE_00: platform probes + access gate only."""

from __future__ import annotations

from django.urls import URLPattern, path

from . import views

urlpatterns: list[URLPattern] = [
    path("health/live", views.LivenessView.as_view(), name="health-live"),
    path("health/ready", views.ReadinessView.as_view(), name="health-ready"),
    path("version", views.VersionView.as_view(), name="version"),
    path("access-gate/check", views.AccessGateCheckView.as_view(), name="access-gate-check"),
]
