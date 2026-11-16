"""PHASE_02 engine test fixture. The synthetic people / order builders live in
``platform_core.devtools.phase02_engine`` (02.8, REV-0275: shared with the ops drill)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.db import connection


@pytest.fixture
def deferred_checks() -> Iterator[None]:
    """Fire the deferred commit-time DB checks of 0020 (gapless counter, serial <-> line pairing, snapshot v1,
    order version row, applied CR has its version) at the end of a test that never commits."""
    yield
    with connection.cursor() as cur:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
