"""Base class for every API view.

DRF runs ``check_permissions`` *before* ``check_throttles``, so requests rejected with 401/403 would never be
rate limited (an anonymous client could hammer a protected endpoint, and later the login endpoint, without
limit). :class:`AleekhanAPIView` throttles first, then checks permissions. A contract test asserts that every
production view derives from it.
"""

from __future__ import annotations

from typing import Any

from rest_framework.request import Request
from rest_framework.views import APIView


class AleekhanAPIView(APIView):
    _throttles_checked = False

    def check_throttles(self, request: Request) -> None:
        if self._throttles_checked:
            return
        self._throttles_checked = True
        super().check_throttles(request)

    def check_permissions(self, request: Request) -> None:
        self.check_throttles(request)  # rate limit applies to rejected requests too
        super().check_permissions(request)

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        self._throttles_checked = False
        super().initial(request, *args, **kwargs)
