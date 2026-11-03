"""URL configuration. PHASE_00 / 00.2 exposes no endpoints; health/version API arrives in step 00.4."""

from django.urls import URLPattern, URLResolver

urlpatterns: list[URLPattern | URLResolver] = []
