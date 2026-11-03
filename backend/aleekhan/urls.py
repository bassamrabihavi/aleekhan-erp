"""URL configuration. Every API endpoint lives under the versioned base path ``/api/v1`` (openapi-draft).

There is no admin site, no browsable API and no test route here; test-only views live in
``platform_core/tests/api_harness.py`` and are mounted only by tests (``pytest.mark.urls``).
"""

from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("api/v1/", include("platform_core.api.urls")),
]

# Non-DRF failures (unknown URL, bad Host header, middleware errors) -> problem+json with request id.
handler400 = "platform_core.api.problems.bad_request"
handler403 = "platform_core.api.problems.permission_denied"
handler404 = "platform_core.api.problems.page_not_found"
handler500 = "platform_core.api.problems.server_error"
