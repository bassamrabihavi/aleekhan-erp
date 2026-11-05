"""Retention (DEC-032 R-A APPROVED) and audit integrity job functions.

* Business and access audit (``platform_audit_event``) is **never deleted** (``retention_business_audit =
  KEEP_FOREVER_YEARLY_ARCHIVE``); the table is append-only (DB triggers + grants). :func:`purge_audit_events`
  exists only to make that explicit: it always refuses. The yearly archive needs an approved archive target
  (not decided) and is not implemented.
* Login events (``platform_login_attempt``) are kept ``retention_login_events_months`` (24); the purge deletes
  only older rows - the DB trigger refuses any row inside the retention period anyway.
* :func:`run_audit_integrity` verifies the audit hash chain and records an append-only integrity run.
"""

from __future__ import annotations

from datetime import datetime

from django.db import connection

from platform_core.engine.audit_chain import verify_chain
from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.engine.errors import AccessDenied
from platform_core.engine.uow import NothingToDo, unit_of_work_or_nothing
from platform_core.identity.models import LoginAttempt
from platform_core.params.values import effective, effective_int


def login_retention_cutoff(now: datetime | None = None) -> datetime:
    months = effective_int("retention_login_events_months")
    with connection.cursor() as cur:
        cur.execute("SELECT %s::timestamptz - make_interval(months => %s)", [now or db_now(), months])
        row = cur.fetchone()
    assert row is not None
    value: datetime = row[0]
    return value


def purge_login_events(*, limit: int = 5000) -> int:
    """Delete login events older than the retention period (oldest first, in batches)."""
    cutoff = login_retention_cutoff()
    ids = list(
        LoginAttempt.objects.filter(occurred_at__lt=cutoff)
        .order_by("occurred_at")
        .values_list("pk", flat=True)[:limit]
    )
    if not ids:
        return 0
    deleted = 0
    with unit_of_work_or_nothing(RequestContext(Actor.system()), require_event=False) as uow:
        deleted, _ = LoginAttempt.objects.filter(pk__in=ids, occurred_at__lt=cutoff).delete()
        if not deleted:
            raise NothingToDo()
        uow.audit(
            action="platform.audit.retention.purge_login_events",
            resource_type="platform.login_attempt",
            after={"deleted": deleted, "cutoff": cutoff.isoformat()},
            reason="DEC-032: login events kept retention_login_events_months",
        )
    return deleted


def purge_audit_events() -> None:
    """Business/access audit is never deleted (DEC-032 R-A)."""
    raise AccessDenied(f"audit events are kept forever ({effective('retention_business_audit')})")


def run_audit_integrity() -> int:
    """Job function: one verification (result in platform_audit_integrity_run); 0 = nothing more to do."""
    verify_chain()
    return 0
