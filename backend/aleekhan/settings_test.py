"""Explicit test settings (REV-0011): used by pytest and mypy (pyproject.toml).

``aleekhan.settings`` refuses to start without ``ALEEKHAN_ENV``. Test runs name their environment here,
explicitly: this module pins ``ALEEKHAN_ENV=test`` and refuses to run if the shell says otherwise (e.g. a
stray ``ALEEKHAN_ENV=prod``), so a test run can never pick up deployed behaviour by accident.
"""

from __future__ import annotations

import os

from django.core.exceptions import ImproperlyConfigured

_shell_env = os.environ.get("ALEEKHAN_ENV", "").strip().lower()
if _shell_env not in {"", "test"}:
    raise ImproperlyConfigured("aleekhan.settings_test requires ALEEKHAN_ENV=test (or unset)")
os.environ["ALEEKHAN_ENV"] = "test"

from .settings import *  # noqa: E402,F403
