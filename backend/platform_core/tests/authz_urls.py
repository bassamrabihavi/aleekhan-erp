"""TEST-ONLY URLconf (00.7): the *production* routes, generated from ``aleekhan.urls``, with one change -
each view also accepts the synthetic header principal of ``api_harness.HeaderTestAuthentication``.

Nothing else is overridden (no ``access_policy``, no permission class), so requests carry an authenticated
principal but are judged by the production permission classes and the production policy
(``permissions.ACCESS_POLICY``). Used by ``test_authz_route_parity.py`` to prove deny-by-default on every
route: anonymous -> 401, authenticated without permission -> 403. Never routed in production.
"""

from __future__ import annotations

from typing import Any

from django.urls import URLPattern, URLResolver, get_resolver, path

from .api_harness import HeaderTestAuthentication


def production_routes() -> list[tuple[str, Any]]:
    """``(route, view_class)`` for every production URL pattern (recursively through ``include``)."""

    def walk(patterns: list[URLPattern | URLResolver], prefix: str) -> list[tuple[str, Any]]:
        out: list[tuple[str, Any]] = []
        for p in patterns:
            if isinstance(p, URLResolver):
                out += walk(list(p.url_patterns), prefix + str(p.pattern))
            else:
                view_cls = getattr(p.callback, "view_class", None) or getattr(p.callback, "cls", None)
                out.append((prefix + str(p.pattern), view_cls))
        return out

    return walk(list(get_resolver("aleekhan.urls").url_patterns), "")


def _with_header_principal(view_cls: Any) -> Any:
    return type(
        f"Authz{view_cls.__name__}", (view_cls,), {"authentication_classes": [HeaderTestAuthentication]}
    )


urlpatterns: list[URLPattern] = [
    path(route, _with_header_principal(view_cls).as_view()) for route, view_cls in production_routes()
]
