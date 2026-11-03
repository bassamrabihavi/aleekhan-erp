"""Idempotency protocol on ``platform_idempotency_record`` (STATE_TRANSITIONS 1.2, openapi-draft conventions).

Per (actor_id, Idempotency-Key)::

    begin()  - no row                          -> insert IN_PROGRESS, caller proceeds (claim)
             - row expired (expires_at <= now)  -> reset to IN_PROGRESS with the new request, proceed
             - request hash differs             -> 422 IDEMPOTENCY_KEY_REUSED
             - COMPLETED                        -> replay the stored response (no second execution)
             - IN_PROGRESS, lease still running -> 409 IDEMPOTENCY_IN_PROGRESS
             - IN_PROGRESS, lease expired       -> take over (holder crashed), proceed
             - FAILED_RETRYABLE                 -> reset to IN_PROGRESS, proceed
    complete() - IN_PROGRESS -> COMPLETED with the response; compare-and-set on row_version, so a holder
                 whose lease was taken over cannot complete (its business transaction rolls back)
    release_for_retry() - IN_PROGRESS -> FAILED_RETRYABLE (the write failed and was rolled back)

Race safety: the claim is a plain INSERT guarded by ``uq_idempotency_record_actor_key``; a concurrent
duplicate either blocks on the unique index until the first inserter commits, or finds the committed row and
locks it with ``SELECT ... FOR UPDATE``. :func:`run_idempotent` commits the claim on its own and calls
:func:`complete` inside the same transaction as the business write, audit and outbox, so a request is
executed at most once and its stored response always matches a committed write.

Time comes from the database clock (:func:`db_now`). Retention ``IDEMPOTENCY_TTL`` = 24 h and lease
``IN_PROGRESS_LEASE`` = 5 min are technical defaults (STATE_TRANSITIONS 1.2 proposal), passed as parameters;
they are not business rules.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import DateTimeField, DurationField, ExpressionWrapper, Value
from django.db.models.expressions import CombinedExpression
from django.db.models.functions import Now

from platform_core.models import HttpMethod, IdempotencyRecord, IdempotencyState

from .context import RequestContext, db_now
from .errors import (
    AuthenticationRequired,
    EngineContractError,
    FieldError,
    IdempotencyInProgress,
    IdempotencyKeyRequired,
    IdempotencyKeyReused,
    ValidationFailed,
)
from .uow import UnitOfWork, unit_of_work

IDEMPOTENCY_TTL = timedelta(hours=24)
IN_PROGRESS_LEASE = timedelta(minutes=5)
UNIQUE_CONSTRAINT = "uq_idempotency_record_actor_key"


def parse_idempotency_key(header: str | None) -> uuid.UUID:
    if header is None or not header.strip():
        raise IdempotencyKeyRequired("Idempotency-Key header is required for mutating requests")
    try:
        return uuid.UUID(header.strip())
    except ValueError:
        raise ValidationFailed(
            "Idempotency-Key must be a UUID",
            errors=[FieldError(field="Idempotency-Key", code="INVALID_UUID")],
        ) from None


def canonical_request(method: str, endpoint: str, body: Any) -> bytes:
    """Canonical JSON of the request: key order and whitespace do not matter; NaN/Infinity are rejected."""
    doc = {"method": method.upper(), "endpoint": endpoint, "body": body}
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )


def request_hash(method: str, endpoint: str, body: Any) -> str:
    return hashlib.sha256(canonical_request(method, endpoint, body)).hexdigest()


@dataclass(frozen=True)
class StoredResponse:
    status: int
    body: Any = None
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IdempotencyClaim:
    record_id: uuid.UUID
    row_version: int
    actor_id: uuid.UUID
    key: uuid.UUID


@dataclass(frozen=True)
class BeginResult:
    claim: IdempotencyClaim | None = None
    replay: StoredResponse | None = None


def _is_unique_violation(exc: IntegrityError) -> bool:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None) == UNIQUE_CONSTRAINT


def begin(
    *,
    actor_id: uuid.UUID,
    key: uuid.UUID,
    method: str,
    endpoint: str,
    req_hash: str,
    ttl: timedelta = IDEMPOTENCY_TTL,
    lease: timedelta = IN_PROGRESS_LEASE,
    using: str = "default",
) -> BeginResult:
    if method not in HttpMethod.values:
        raise EngineContractError(f"idempotency applies to mutating methods only, got {method!r}")
    if ttl <= lease:
        raise EngineContractError("ttl must be longer than the in-progress lease")
    with transaction.atomic(using=using):
        try:
            with transaction.atomic(using=using):
                rec = IdempotencyRecord.objects.using(using).create(
                    actor_id=actor_id,
                    key=key,
                    method=method,
                    endpoint=endpoint,
                    request_hash=req_hash,
                    expires_at=_db_now_plus(ttl),
                )
            return BeginResult(claim=IdempotencyClaim(rec.id, 1, actor_id, key))
        except IntegrityError as exc:
            if not _is_unique_violation(exc):
                raise
        found = (
            IdempotencyRecord.objects.using(using)
            .select_for_update()
            .filter(actor_id=actor_id, key=key)
            .first()
        )
        if found is None:  # purged (expired) between our conflict and the lock: the client simply retries
            raise IdempotencyInProgress("idempotency record changed concurrently; retry")
        rec = found
        now = db_now(using)
        expired = rec.expires_at <= now
        if not expired:
            if rec.request_hash != req_hash or rec.method != method or rec.endpoint != endpoint:
                raise IdempotencyKeyReused()
            if rec.state == IdempotencyState.COMPLETED:
                assert rec.response_status is not None  # ck_idempotency_record_completed_has_status
                return BeginResult(
                    replay=StoredResponse(
                        status=rec.response_status,
                        body=rec.response_body,
                        headers=dict(rec.response_headers or {}),
                    )
                )
            if rec.state == IdempotencyState.IN_PROGRESS and rec.updated_at + lease > now:
                raise IdempotencyInProgress()
        # expired, FAILED_RETRYABLE, or IN_PROGRESS whose holder lost its lease -> new claim
        IdempotencyRecord.objects.using(using).filter(pk=rec.pk, row_version=rec.row_version).update(
            state=IdempotencyState.IN_PROGRESS,
            method=method,
            endpoint=endpoint,
            request_hash=req_hash,
            response_status=None,
            response_headers={},
            response_body=None,
            expires_at=_db_now_plus(ttl),
        )
        return BeginResult(claim=IdempotencyClaim(rec.id, rec.row_version + 1, actor_id, key))


def _db_now_plus(delta: timedelta) -> ExpressionWrapper[CombinedExpression]:
    """``statement_timestamp() + delta`` evaluated in the writing statement itself, so ``expires_at`` uses the
    same instant as ``created_at`` / ``updated_at`` (ck_idempotency_record_expiry_after_create holds for any
    positive ``delta``)."""
    return ExpressionWrapper(Now() + Value(delta, output_field=DurationField()), output_field=DateTimeField())


def complete(claim: IdempotencyClaim, response: StoredResponse, *, using: str = "default") -> None:
    if not 100 <= response.status <= 599:
        raise EngineContractError("response status out of range")
    updated = (
        IdempotencyRecord.objects.using(using)
        .filter(pk=claim.record_id, row_version=claim.row_version, state=IdempotencyState.IN_PROGRESS)
        .update(
            state=IdempotencyState.COMPLETED,
            response_status=response.status,
            response_headers=dict(response.headers),
            response_body=response.body,
        )
    )
    if updated != 1:
        raise IdempotencyInProgress("idempotency claim was lost (lease expired and taken over)")


def release_for_retry(claim: IdempotencyClaim, *, using: str = "default") -> bool:
    """Mark the claim FAILED_RETRYABLE. Returns False if the claim was already lost (no-op)."""
    updated = (
        IdempotencyRecord.objects.using(using)
        .filter(pk=claim.record_id, row_version=claim.row_version, state=IdempotencyState.IN_PROGRESS)
        .update(state=IdempotencyState.FAILED_RETRYABLE)
    )
    return updated == 1


def purge_expired(*, limit: int = 1000, using: str = "default") -> int:
    """Delete up to ``limit`` expired records (housekeeping job; scheduling is wired in 00.6/00.7)."""
    with transaction.atomic(using=using):
        now = db_now(using)
        ids = list(
            IdempotencyRecord.objects.using(using)
            .select_for_update(skip_locked=True)
            .filter(expires_at__lte=now)
            .order_by("expires_at")
            .values_list("pk", flat=True)[:limit]
        )
        deleted, _ = IdempotencyRecord.objects.using(using).filter(pk__in=ids).delete()
    return deleted


@dataclass(frozen=True)
class IdempotentResult:
    response: StoredResponse
    replayed: bool


def run_idempotent(
    ctx: RequestContext,
    *,
    key: uuid.UUID | None,
    method: str,
    endpoint: str,
    body: Any,
    handler: Callable[[UnitOfWork], StoredResponse],
    require_event: bool = True,
    ttl: timedelta = IDEMPOTENCY_TTL,
    lease: timedelta = IN_PROGRESS_LEASE,
    using: str = "default",
) -> IdempotentResult:
    """Execute ``handler`` at most once per (actor, key, request); replay the stored response otherwise.

    The handler runs inside :func:`unit_of_work` (write + audit + outbox) and the idempotency record is
    completed in that same transaction. On any exception the transaction rolls back and the claim is released
    for retry (FAILED_RETRYABLE); the exception propagates.
    """
    actor_id = ctx.actor.actor_id
    if actor_id is None:
        raise AuthenticationRequired("mutating requests require an authenticated actor")
    if key is None:
        raise IdempotencyKeyRequired()
    if transaction.get_connection(using).in_atomic_block:
        raise EngineContractError("run_idempotent must not run inside an outer transaction")
    started = begin(
        actor_id=actor_id,
        key=key,
        method=method,
        endpoint=endpoint,
        req_hash=request_hash(method, endpoint, body),
        ttl=ttl,
        lease=lease,
        using=using,
    )
    if started.replay is not None:
        return IdempotentResult(started.replay, replayed=True)
    claim = started.claim
    assert claim is not None
    try:
        with unit_of_work(ctx, require_event=require_event, using=using) as uow:
            response = handler(uow)
            complete(claim, response, using=using)
    except BaseException:
        # Best effort: if even this fails (e.g. lost DB connection) the lease lets a retry take over later;
        # never mask the original exception.
        with contextlib.suppress(Exception):
            release_for_retry(claim, using=using)
        raise
    return IdempotentResult(response, replayed=False)
