"""``manage.py runserver_e2e`` (02.8 / REV-0295): differs from runserver only by its listen backlog."""

from __future__ import annotations

import pytest
from django.core.management import CommandError
from django.core.management.commands.runserver import Command as RunserverCommand
from django.core.servers import basehttp
from django.test import override_settings

from platform_core.management.commands import runserver_e2e


def test_server_class_has_a_larger_backlog_and_is_otherwise_djangos() -> None:
    cls = runserver_e2e.Command.server_cls
    assert issubclass(cls, basehttp.WSGIServer)
    assert cls.request_queue_size == runserver_e2e.E2E_BACKLOG >= 128
    assert basehttp.WSGIServer.request_queue_size == 10  # Django's own server is untouched
    assert issubclass(runserver_e2e.Command, RunserverCommand)


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_refuses_outside_dev_and_test(env: str) -> None:
    with (
        override_settings(ALEEKHAN_ENV=env),
        pytest.raises(CommandError, match="only for ALEEKHAN_ENV=dev or test"),
    ):
        runserver_e2e.Command().handle(
            addrport="127.0.0.1:0", use_ipv6=False, use_threading=True, use_reloader=False, skip_checks=True
        )
