"""Source registry access + guards (PHASE_00 / 00.6).

* :func:`get_source` -> 404 ``NOT_FOUND`` for an unknown code.
* :func:`require_enabled` -> 409 ``SOURCE_DISABLED``.
* :func:`require_writable` -> always 409 ``SOURCE_READ_ONLY`` in PHASE_00: every source is READ_ONLY (DB CHECK
  ``ck_integration_source_read_only``). Any future connector code path that would write to an external system
  (export, write-back to Rahkaran) must call it first; there is no such path today (ADR-001: Rahkaran
  write-back needs its own ADR and approval).
"""

from __future__ import annotations

from platform_core.engine.errors import NotFound, SourceDisabled, SourceReadOnly

from .models import IntegrationSource, SourceDirection


def get_source(code: str, *, using: str = "default", for_update: bool = False) -> IntegrationSource:
    qs = IntegrationSource.objects.using(using)
    if for_update:
        qs = qs.select_for_update()
    source = qs.filter(code=code).first()
    if source is None:
        raise NotFound()  # never echo the caller's input
    return source


def require_enabled(source: IntegrationSource) -> None:
    if not source.is_enabled:
        raise SourceDisabled(f"source {source.code} is disabled")


def require_writable(source: IntegrationSource) -> None:
    """Guard for any write to the external system behind ``source``. Always refuses in PHASE_00."""
    if source.direction == SourceDirection.READ_ONLY:
        raise SourceReadOnly(f"source {source.code} is read-only")
    raise SourceReadOnly(f"source {source.code}: write direction {source.direction!r} is not supported")
