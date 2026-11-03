"""Idempotency protocol: begin / complete / replay / reuse / in-progress / lease / expiry / races."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from platform_core.engine import idempotency as idem
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import (
    AuthenticationRequired,
    ClientError,
    EngineContractError,
    FieldError,
    IdempotencyInProgress,
    IdempotencyKeyRequired,
    IdempotencyKeyReused,
    MfaRequired,
    NotFound,
    RateLimited,
    RuleNotApproved,
    ValidationFailed,
    VersionConflict,
)
from platform_core.engine.uow import UnitOfWork
from platform_core.models import AuditEvent, IdempotencyRecord, IdempotencyState, OutboxEvent

from .threads import run_concurrently

ENDPOINT = "/api/v1/synthetic/things"


# ------------------------------------------------------------------------------------------- pure parts
json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=8),
    lambda inner: st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=5), inner, max_size=3),
    max_leaves=15,
)


@given(body=st.dictionaries(st.text(max_size=6), json_values, max_size=5))
def test_request_hash_is_deterministic_and_key_order_independent(body: dict[str, Any]) -> None:
    reordered = dict(reversed(list(body.items())))
    h = idem.request_hash("POST", ENDPOINT, body)
    assert h == idem.request_hash("post", ENDPOINT, reordered)
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


@given(a=json_values, b=json_values)
def test_request_hash_distinguishes_bodies(a: Any, b: Any) -> None:
    same = idem.canonical_request("POST", ENDPOINT, a) == idem.canonical_request("POST", ENDPOINT, b)
    assert (idem.request_hash("POST", ENDPOINT, a) == idem.request_hash("POST", ENDPOINT, b)) == same


def test_request_hash_binds_method_and_endpoint_and_rejects_nan() -> None:
    body = {"q": 1}
    assert idem.request_hash("POST", ENDPOINT, body) != idem.request_hash("PUT", ENDPOINT, body)
    assert idem.request_hash("POST", ENDPOINT, body) != idem.request_hash("POST", ENDPOINT + "/x", body)
    with pytest.raises(ValueError):
        idem.request_hash("POST", ENDPOINT, {"x": float("nan")})


def test_parse_idempotency_key() -> None:
    k = uuid.uuid4()
    assert idem.parse_idempotency_key(f" {k} ") == k
    with pytest.raises(IdempotencyKeyRequired):
        idem.parse_idempotency_key(None)
    with pytest.raises(IdempotencyKeyRequired):
        idem.parse_idempotency_key("")
    with pytest.raises(ValidationFailed):
        idem.parse_idempotency_key("not-a-uuid")


# ------------------------------------------------------------------------------------------- begin/complete
def _begin(actor: uuid.UUID, key: uuid.UUID, body: Any = None, **kw: Any) -> idem.BeginResult:
    body = {"n": 1} if body is None else body
    return idem.begin(
        actor_id=actor,
        key=key,
        method="POST",
        endpoint=ENDPOINT,
        req_hash=idem.request_hash("POST", ENDPOINT, body),
        **kw,
    )


@pytest.mark.django_db
def test_first_begin_claims_then_complete_then_replay() -> None:
    actor, key = uuid.uuid4(), uuid.uuid4()
    first = _begin(actor, key)
    assert first.claim is not None and first.replay is None
    idem.complete(first.claim, idem.StoredResponse(201, {"id": "x"}, {"Location": "/x"}))
    again = _begin(actor, key)
    assert again.claim is None
    assert again.replay == idem.StoredResponse(201, {"id": "x"}, {"Location": "/x"})
    rec = IdempotencyRecord.objects.get(actor_id=actor, key=key)
    assert rec.state == IdempotencyState.COMPLETED
    assert rec.expires_at - rec.created_at == idem.IDEMPOTENCY_TTL


@pytest.mark.django_db
def test_same_key_different_request_is_reused_error() -> None:
    actor, key = uuid.uuid4(), uuid.uuid4()
    claim = _begin(actor, key).claim
    assert claim is not None
    with pytest.raises(IdempotencyKeyReused) as exc:
        _begin(actor, key, body={"n": 2})
    assert exc.value.http_status == 422
    idem.complete(claim, idem.StoredResponse(200))
    with pytest.raises(IdempotencyKeyReused):
        _begin(actor, key, body={"n": 2})
    # the key is per actor: another actor may use the same key value
    assert _begin(uuid.uuid4(), key, body={"n": 2}).claim is not None


@pytest.mark.django_db
def test_in_progress_duplicate_is_409_until_lease_expires() -> None:
    actor, key = uuid.uuid4(), uuid.uuid4()
    first = _begin(actor, key).claim
    assert first is not None
    with pytest.raises(IdempotencyInProgress) as exc:
        _begin(actor, key)
    assert exc.value.http_status == 409
    # holder "crashed": a 1 microsecond lease has certainly run out by the next statement
    taken = _begin(actor, key, lease=timedelta(microseconds=1))
    assert taken.claim is not None and taken.claim.row_version > first.row_version
    # the old holder can no longer complete or release
    with pytest.raises(IdempotencyInProgress):
        idem.complete(first, idem.StoredResponse(201))
    assert idem.release_for_retry(first) is False
    idem.complete(taken.claim, idem.StoredResponse(201))


@pytest.mark.django_db
def test_failed_retryable_allows_retry_with_same_request_only() -> None:
    actor, key = uuid.uuid4(), uuid.uuid4()
    claim = _begin(actor, key).claim
    assert claim is not None
    assert idem.release_for_retry(claim) is True
    with pytest.raises(IdempotencyKeyReused):
        _begin(actor, key, body={"n": 9})
    retry = _begin(actor, key)
    assert retry.claim is not None


@pytest.mark.django_db
def test_expired_record_is_reusable_even_with_a_new_request() -> None:
    actor, key = uuid.uuid4(), uuid.uuid4()
    claim = _begin(actor, key).claim
    assert claim is not None
    idem.complete(claim, idem.StoredResponse(201, {"old": True}))
    rec = IdempotencyRecord.objects.get(pk=claim.record_id)
    IdempotencyRecord.objects.filter(pk=rec.pk).update(expires_at=rec.created_at + timedelta(microseconds=1))
    fresh = _begin(actor, key, body={"n": 2})
    assert fresh.claim is not None
    rec.refresh_from_db()
    assert rec.state == IdempotencyState.IN_PROGRESS
    assert rec.response_body is None and rec.response_status is None
    assert rec.expires_at > rec.updated_at


@pytest.mark.django_db
def test_purge_expired_deletes_only_expired() -> None:
    actor = uuid.uuid4()
    keep = _begin(actor, uuid.uuid4()).claim
    gone = _begin(actor, uuid.uuid4()).claim
    assert keep is not None and gone is not None
    rec = IdempotencyRecord.objects.get(pk=gone.record_id)
    IdempotencyRecord.objects.filter(pk=rec.pk).update(expires_at=rec.created_at + timedelta(microseconds=1))
    assert idem.purge_expired() == 1
    assert list(IdempotencyRecord.objects.filter(actor_id=actor).values_list("pk", flat=True)) == [
        keep.record_id
    ]


@pytest.mark.django_db
def test_begin_contract_checks() -> None:
    with pytest.raises(EngineContractError):
        idem.begin(
            actor_id=uuid.uuid4(), key=uuid.uuid4(), method="GET", endpoint=ENDPOINT, req_hash="0" * 64
        )
    with pytest.raises(EngineContractError):
        _begin(uuid.uuid4(), uuid.uuid4(), ttl=timedelta(minutes=1), lease=timedelta(minutes=5))


# ------------------------------------------------------------------------------------------- run_idempotent
def _ctx(actor: uuid.UUID) -> RequestContext:
    return RequestContext(Actor.user(actor), request_id=uuid.uuid4())


def _handler(calls: list[int], *, fail: bool = False, delay: float = 0.0) -> Any:
    lock = threading.Lock()

    def handler(uow: UnitOfWork) -> idem.StoredResponse:
        with lock:
            calls.append(1)
        if delay:
            time.sleep(delay)
        uow.audit(action="platform.synthetic.create", resource_type="platform.synthetic", resource_id="s1")
        uow.emit(
            event_type="platform.synthetic.created",
            aggregate_type="platform.synthetic",
            aggregate_id="s1",
            aggregate_version=1,
        )
        if fail:
            raise RuntimeError("synthetic handler failure")
        return idem.StoredResponse(201, {"id": "s1"})

    return handler


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_run_idempotent_executes_once_and_replays() -> None:
    actor, key = uuid.uuid4(), uuid.uuid4()
    calls: list[int] = []
    kw: dict[str, Any] = {"key": key, "method": "POST", "endpoint": ENDPOINT, "body": {"n": 1}}
    first = idem.run_idempotent(_ctx(actor), handler=_handler(calls), **kw)
    second = idem.run_idempotent(_ctx(actor), handler=_handler(calls), **kw)
    assert (first.replayed, second.replayed) == (False, True)
    assert first.response == second.response == idem.StoredResponse(201, {"id": "s1"})
    assert len(calls) == 1
    assert AuditEvent.objects.count() == 1 and OutboxEvent.objects.count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_run_idempotent_failure_rolls_back_and_allows_retry() -> None:
    actor, key = uuid.uuid4(), uuid.uuid4()
    calls: list[int] = []
    kw: dict[str, Any] = {"key": key, "method": "POST", "endpoint": ENDPOINT, "body": {"n": 1}}
    with pytest.raises(RuntimeError):
        idem.run_idempotent(_ctx(actor), handler=_handler(calls, fail=True), **kw)
    assert AuditEvent.objects.count() == 0 and OutboxEvent.objects.count() == 0
    assert IdempotencyRecord.objects.get(actor_id=actor, key=key).state == IdempotencyState.FAILED_RETRYABLE
    ok = idem.run_idempotent(_ctx(actor), handler=_handler(calls), **kw)
    assert ok.replayed is False and len(calls) == 2
    assert AuditEvent.objects.count() == 1 and OutboxEvent.objects.count() == 1


@pytest.mark.django_db
def test_run_idempotent_preconditions() -> None:
    kw: dict[str, Any] = {"method": "POST", "endpoint": ENDPOINT, "body": {}, "handler": _handler([])}
    with pytest.raises(AuthenticationRequired):
        idem.run_idempotent(RequestContext(Actor.system()), key=uuid.uuid4(), **kw)
    with pytest.raises(IdempotencyKeyRequired):
        idem.run_idempotent(_ctx(uuid.uuid4()), key=None, **kw)
    with pytest.raises(EngineContractError):  # pytest-django wraps this test in a transaction
        idem.run_idempotent(_ctx(uuid.uuid4()), key=uuid.uuid4(), **kw)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_concurrent_same_key_executes_handler_exactly_once() -> None:
    """N clients send the same request with the same key at once (PostgreSQL, separate connections)."""
    actor, key = uuid.uuid4(), uuid.uuid4()
    calls: list[int] = []
    n = 8
    handler = _handler(calls, delay=0.3)

    def client(_: int) -> Any:
        return idem.run_idempotent(
            _ctx(actor), key=key, method="POST", endpoint=ENDPOINT, body={"n": 1}, handler=handler
        )

    results = run_concurrently(client, n)
    executed = [r for r in results if isinstance(r, idem.IdempotentResult) and not r.replayed]
    replayed = [r for r in results if isinstance(r, idem.IdempotentResult) and r.replayed]
    in_progress = [r for r in results if isinstance(r, IdempotencyInProgress)]
    assert len(executed) == 1, results
    assert len(executed) + len(replayed) + len(in_progress) == n, results
    assert len(calls) == 1
    assert AuditEvent.objects.count() == 1 and OutboxEvent.objects.count() == 1
    rec = IdempotencyRecord.objects.get(actor_id=actor, key=key)
    assert rec.state == IdempotencyState.COMPLETED and rec.response_status == 201


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_concurrent_same_key_different_bodies_one_wins_rest_rejected() -> None:
    actor, key = uuid.uuid4(), uuid.uuid4()
    calls: list[int] = []
    handler = _handler(calls, delay=0.2)

    def client(i: int) -> Any:
        return idem.run_idempotent(
            _ctx(actor), key=key, method="POST", endpoint=ENDPOINT, body={"n": i}, handler=handler
        )

    results = run_concurrently(client, 6)
    assert sum(isinstance(r, idem.IdempotentResult) for r in results) == 1, results
    assert sum(isinstance(r, IdempotencyKeyReused) for r in results) == 5, results
    assert len(calls) == 1


# ------------------------------------------------------------------------------------------- REV-0012
def _raising_handler(calls: list[int], exc: Exception) -> Any:
    def handler(uow: UnitOfWork) -> idem.StoredResponse:
        calls.append(1)
        # the write happened inside the unit of work and must be rolled back
        uow.audit(action="platform.synthetic.create", resource_type="platform.synthetic", resource_id="s1")
        uow.emit(
            event_type="platform.synthetic.created",
            aggregate_type="platform.synthetic",
            aggregate_id="s1",
            aggregate_version=1,
        )
        raise exc

    return handler


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
@pytest.mark.parametrize(
    "exc",
    [
        ValidationFailed("synthetic", errors=[FieldError("qty", "OUT_OF_RANGE")]),
        RuleNotApproved("DEC-005"),
        VersionConflict(),
        NotFound(),
    ],
    ids=lambda e: type(e).__name__,
)
def test_run_idempotent_client_error_is_stored_and_replayed(exc: Exception) -> None:
    """Deterministic 4xx: rolled back, stored as COMPLETED with the problem body, replayed (no re-run)."""
    actor, key = uuid.uuid4(), uuid.uuid4()
    calls: list[int] = []
    first_ctx = _ctx(actor)
    kw: dict[str, Any] = {"key": key, "method": "POST", "endpoint": ENDPOINT, "body": {"n": 1}}
    with pytest.raises(type(exc)):
        idem.run_idempotent(first_ctx, handler=_raising_handler(calls, exc), **kw)
    assert AuditEvent.objects.count() == 0 and OutboxEvent.objects.count() == 0
    rec = IdempotencyRecord.objects.get(actor_id=actor, key=key)
    assert rec.state == IdempotencyState.COMPLETED
    assert isinstance(exc, ClientError)
    assert rec.response_status == exc.http_status
    assert rec.response_body == exc.to_problem(first_ctx.request_id)  # type: ignore[arg-type]
    assert rec.response_headers == {"Content-Type": "application/problem+json"}

    again = idem.run_idempotent(_ctx(actor), handler=_handler(calls), **kw)
    assert again.replayed is True
    assert again.response.status == exc.http_status
    assert again.response.body["code"] == exc.code.value
    assert again.response.body["request_id"] == str(first_ctx.request_id)  # original request id
    assert len(calls) == 1  # the (succeeding) second handler never ran
    assert AuditEvent.objects.count() == 0 and OutboxEvent.objects.count() == 0
    # a different request with the same key is still rejected
    with pytest.raises(IdempotencyKeyReused):
        idem.run_idempotent(_ctx(actor), handler=_handler(calls), **{**kw, "body": {"n": 2}})


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
@pytest.mark.parametrize(
    "exc",
    [IdempotencyInProgress(), RateLimited(), AuthenticationRequired(), MfaRequired()],
    ids=lambda e: type(e).__name__,
)
def test_run_idempotent_transient_client_error_is_retryable(exc: Exception) -> None:
    actor, key = uuid.uuid4(), uuid.uuid4()
    calls: list[int] = []
    kw: dict[str, Any] = {"key": key, "method": "POST", "endpoint": ENDPOINT, "body": {"n": 1}}
    with pytest.raises(type(exc)):
        idem.run_idempotent(_ctx(actor), handler=_raising_handler(calls, exc), **kw)
    assert IdempotencyRecord.objects.get(actor_id=actor, key=key).state == IdempotencyState.FAILED_RETRYABLE
    ok = idem.run_idempotent(_ctx(actor), handler=_handler(calls), **kw)
    assert ok.replayed is False and len(calls) == 2


def test_replayable_classification_covers_every_client_error() -> None:
    from platform_core.engine import errors as E

    transient = {E.ErrorCode.IDEMPOTENCY_IN_PROGRESS, E.ErrorCode.RATE_LIMITED}
    transient |= {E.ErrorCode.AUTHENTICATION_REQUIRED, E.ErrorCode.MFA_REQUIRED}
    for code, cls in E.EXCEPTION_FOR_CODE.items():
        if not issubclass(cls, E.ClientError):
            continue
        inst = E.RuleNotApproved("DEC-001") if cls is E.RuleNotApproved else cls()
        assert idem.is_replayable_client_error(inst) is (code not in transient), code
