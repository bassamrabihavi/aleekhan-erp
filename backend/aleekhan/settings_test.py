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

# ------------------------------------------------------------------------------------- PHASE_01 / 01.3
# TEST ONLY: a fast PBKDF2 work factor (the production hasher is unchanged, see settings.PASSWORD_HASHERS).
PASSWORD_HASHERS = ["platform_core.tests.hashers.FastPBKDF2ForTests"]
# TEST ONLY synthetic data key, derived at start-up from a public label (not a secret, never used outside
# tests).
import hashlib as _hashlib  # noqa: E402

ALEEKHAN_DATA_KEYS = {"test-key-1": _hashlib.sha256(b"aleekhan synthetic test data key 1").digest()}
ALEEKHAN_DATA_KEY_CURRENT = "test-key-1"
