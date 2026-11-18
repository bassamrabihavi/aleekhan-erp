"""``manage.py runserver_e2e`` - Django's dev server for the local E2E / fidelity runs only (PHASE_02 / 02.8).

Why: the E2E suite (Playwright via the Vite proxy) opens many connections at once. Django's dev
``WSGIServer`` listens with a backlog of only ``request_queue_size = 10``; on Windows a full backlog answers
new connections with a reset, which the Vite proxy reports as ``ECONNREFUSED`` and the UI (correctly) shows
as a failed refresh / stale data. This command is ``runserver`` unchanged except for a larger listen
backlog, so the real stale / error handling of the UI stays untouched and only the test server stops
dropping connections.

Refuses to run unless ``ALEEKHAN_ENV`` is ``dev`` or ``test`` (never staging / prod).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import CommandError
from django.core.management.commands.runserver import Command as RunserverCommand
from django.core.servers import basehttp

#: Listen backlog for the E2E dev server (Django's default is 10).
E2E_BACKLOG = 256


class _E2EWSGIServer(basehttp.WSGIServer):
    request_queue_size = E2E_BACKLOG


class Command(RunserverCommand):
    help = "runserver for the local E2E runs (larger listen backlog; dev / test only)."
    server_cls = _E2EWSGIServer

    def handle(self, *args: Any, **options: Any) -> None:
        if getattr(settings, "ALEEKHAN_ENV", None) not in {"dev", "test"}:
            raise CommandError("runserver_e2e is only for ALEEKHAN_ENV=dev or test")
        super().handle(*args, **options)
