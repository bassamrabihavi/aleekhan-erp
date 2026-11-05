"""Effective parameter values for the engine (PHASE_01 / 01.3): no policy number is hard-coded in code.

:func:`effective` reads the value effective *now* through the SQL function ``platform_param_value`` (the same
function the DB guards use, so application and triggers always agree). A parameter without an effective value
is a configuration error (``EngineContractError`` -> 500), never a silent default.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import DatabaseError, connections, transaction

from platform_core.engine.errors import EngineContractError


def effective(key: str, *, using: str = "default") -> str:
    try:
        # savepoint: a missing parameter must not abort the caller's transaction
        with transaction.atomic(using=using), connections[using].cursor() as cur:
            cur.execute("SELECT public.platform_param_value(%s)", [key])
            row = cur.fetchone()
    except DatabaseError as exc:  # parameter_missing (check_violation) -> configuration error
        raise EngineContractError(f"parameter {key!r} has no effective value") from exc
    assert row is not None
    return str(row[0])


def effective_int(key: str, *, using: str = "default") -> int:
    return int(effective(key, using=using))


def effective_bool(key: str, *, using: str = "default") -> bool:
    value = effective(key, using=using)
    if value not in ("true", "false"):
        raise EngineContractError(f"parameter {key!r} is not a boolean")
    return value == "true"


def effective_minutes(key: str, *, using: str = "default") -> timedelta:
    return timedelta(minutes=effective_int(key, using=using))


def effective_hours(key: str, *, using: str = "default") -> timedelta:
    return timedelta(hours=effective_int(key, using=using))


def effective_days(key: str, *, using: str = "default") -> timedelta:
    return timedelta(days=effective_int(key, using=using))


def effective_at(key: str, at: datetime, *, using: str = "default") -> str:
    """Value effective at instant ``at`` (``platform_param_value_at``, migration 0012; REV-0113)."""
    try:
        with transaction.atomic(using=using), connections[using].cursor() as cur:
            cur.execute("SELECT public.platform_param_value_at(%s, %s)", [key, at])
            row = cur.fetchone()
    except DatabaseError as exc:
        raise EngineContractError(f"parameter {key!r} has no effective value") from exc
    assert row is not None
    return str(row[0])
