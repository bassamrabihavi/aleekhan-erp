# Platform domain engine — PHASE_00 / 00.3

Code: `backend/platform_core/engine/`. Platform mechanics only; **no business rule** lives here. Anything that
depends on an owner decision goes through `require_approved_rule(DEC-###)` and is blocked (`RULE_NOT_APPROVED`).
Error codes: [ERROR_CODES.md](ERROR_CODES.md).

## 1. Transactional write (`uow.unit_of_work`)

```python
with unit_of_work(RequestContext(Actor.user(uid), request_id=rid)) as uow:
    ...  # owning module's write
    uow.audit(
        action="module.entity.verb",
        resource_type="module.entity",
        resource_id=str(pk),
        resource_version=v,
        before={...},
        after={...},
    )
    uow.emit(
        event_type="module.entity.verbed",
        aggregate_type="module.entity",
        aggregate_id=str(pk),
        aggregate_version=v,
        payload={"id": str(pk)},
    )
```

- One `transaction.atomic()`: write + audit + outbox commit together or not at all.
- At least one audit row is required; at least one outbox event unless `require_event=False`. A violation
  raises `EngineContractError` inside the transaction (the write is rolled back).
- Actor, `request_id` and `correlation_id` (defaults to `request_id`) are copied to audit and outbox rows.
- Audit `before`/`after` and `scope` are redacted (`[REDACTED]` for keys like password/secret/token/salary/
  payroll; see `redaction.py`; `scope` since 00.4, REV-0009); an outbox payload with such a key is rejected.
  Full field classification: 00.7 / later phases.
- `reason` (free text) and `resource_id` (identifier) cannot be redacted by key. Rule: `reason` is a short
  operator justification without personal data or secrets; `resource_id` is a surrogate id or a 14-digit code,
  never a name, phone number or other personal value. Enforced by code review (REV-0009).
- Known limit: audit of *denied/failed* attempts must survive the rollback of the failed write; that writer
  (separate transaction) belongs with the API error handler in 00.4.

## 2. Idempotency (`idempotency`)

`run_idempotent(ctx, key=, method=, endpoint=, body=, handler=)`:

1. Requires an authenticated actor (`AUTHENTICATION_REQUIRED`) and a key (`IDEMPOTENCY_KEY_REQUIRED`); must be
   called outside an outer transaction.
2. `begin` commits a claim (`IN_PROGRESS`) on its own, guarded by `uq_idempotency_record_actor_key`:
   - same key + same request hash + `COMPLETED` → stored response replayed, handler not run;
   - same key + different hash (method, endpoint or canonical body) → 422 `IDEMPOTENCY_KEY_REUSED`;
   - same key + same hash + `IN_PROGRESS` within the lease → 409 `IDEMPOTENCY_IN_PROGRESS`;
   - `IN_PROGRESS` past the lease (holder crashed), `FAILED_RETRYABLE`, or expired → new claim.
3. The handler runs inside `unit_of_work`; `complete` stores the response **in the same transaction** with a
   compare-and-set on `row_version` (a holder that lost its lease cannot complete → its write rolls back).
4. On any exception the business transaction rolls back and the exception is re-raised. Then (REV-0012,
   decided in 00.4):
   - **deterministic client error** (any 4xx except 409 `IDEMPOTENCY_IN_PROGRESS`, 429 `RATE_LIMITED`,
     401 `AUTHENTICATION_REQUIRED` / `MFA_REQUIRED`): the problem response is stored and the record becomes
     `COMPLETED`. A retry with the same key and the same request **replays the same problem** (same status,
     same body including the original `request_id`, header `Idempotent-Replayed: true`) without running the
     handler. To try again after fixing the cause, the client sends a new key.
   - **anything else** (5xx, transient 4xx, programming errors): claim → `FAILED_RETRYABLE`; a retry with the
     same key and the same request executes again.
   Rationale: "same key ⇒ same stored response" holds for every final outcome, and a retried request can never
   flip from an error to a success behind the client's back. Tests: `test_engine_idempotency.py`
   (`test_run_idempotent_client_error_is_stored_and_replayed`, `..._transient_client_error_is_retryable`) and
   `test_api_utilities.py` (HTTP level).

Request hash = SHA-256 of canonical JSON `{"method","endpoint","body"}` (sorted keys, no whitespace,
UTF-8, NaN/Infinity rejected). All times are the DB clock (`statement_timestamp()`).

Defaults (technical, parameters — not business rules; to be confirmed with ops in 00.7):
`IDEMPOTENCY_TTL` = 24 h (STATE_TRANSITIONS 1.2 proposal), `IN_PROGRESS_LEASE` = 5 min. Housekeeping:
`purge_expired(limit=)` (scheduling is 00.6/00.7).

API glue: `platform_core.api.idempotent.idempotent_response(request, endpoint=, handler=)` (principal,
`Idempotency-Key`, request id → `RequestContext`).

## 3. Optimistic concurrency (`concurrency`)

`make_etag(v)` → `"v"` (strong). `parse_if_match(h)`: missing → 428 `PRECONDITION_REQUIRED`; `*`, list or
malformed → 400 `VALIDATION_FAILED`; weak → 412 `VERSION_CONFLICT`. `update_versioned(qs, pk, expected, **values)`
= `UPDATE ... WHERE pk AND row_version = expected` → new version (`expected + 1`, bumped by the DB trigger),
404 if absent / outside the scoped queryset, 412 if stale. `lock_versioned` = `SELECT ... FOR UPDATE` + check.

## 4. State machines (`state`, `outbox.OUTBOX_DELIVERY_MACHINE`)

`StateMachine(name, states, transitions, rule_gates)`; `assert_transition(src, dst)` → 409
`STATE_TRANSITION_NOT_ALLOWED` if not listed, 409 `RULE_NOT_APPROVED` if the edge is gated by an unapproved
decision. Only the platform outbox machine is defined in PHASE_00.

## 5. Outbox dispatcher (`outbox`)

- `claim_batch`: `SELECT ... WHERE delivery_status IN (PENDING, FAILED) AND next_attempt_at <= now ORDER BY
  next_attempt_at, id LIMIT n FOR UPDATE SKIP LOCKED` → `DISPATCHED`, `attempts + 1` (uses
  `ix_outbox_event_dispatch`). Parallel dispatchers never claim the same row.
- Publish outside the claim transaction via an `OutboxPublisher` (`publish(envelope)`; raise on failure).
- Success → `ACKED`. Failure → `FAILED`, `next_attempt_at = now + backoff(attempt)`; at `max_attempts`
  → `DEAD_LETTER`. Late ACK/FAIL by a dispatcher whose row was recovered is ignored (compare-and-set).
- `recover_stale`: `DISPATCHED` older than the lease → counted as a failed attempt (`LEASE_EXPIRED`).
- `replay_dead_letter(ctx, event_id, reason=)`: `DEAD_LETTER → PENDING`, attempts reset, audited
  (`platform.outbox.replay`); USER actor and non-empty reason required; RBAC check is the API's job (PHASE_01).
- Delivery is at-least-once; consumers dedupe by `event_id`. `last_error` stores only a safe code
  (`PublishError.safe_code` or the exception class name), never exception text.
- Backoff: `min(cap, base * factor^(attempt-1))` in integer microseconds, optional deterministic jitter from
  `sha256(event_id:attempt)`. Default policy (technical, tune in 00.6): base 2 s, factor 2, cap 1 h,
  max 10 attempts, lease 5 min, batch 100 — golden in `tests/golden/backoff.golden.json`.
- No broker is wired in PHASE_00. `engine.testing.InMemoryTestPublisher` is a **test double** and refuses to
  start outside `ALEEKHAN_ENV` dev/test.
- 00.6 additions (docs/integration/README.md §3–4): `engine.consumers` (handler registry, inbox dedupe
  `platform_inbox_event`, `RegistryPublisher`, compensation records on DEAD_LETTER, `sweep_dead_letters`);
  injectable jitter source (`OutboxPolicy.jitter_source`) and clock (`now=` on `claim_batch`, `mark_failed`,
  `dispatch_once`, `recover_stale`); `on_dead_letter` hook; `INTEGRATION_POLICY` technical default
  (golden `tests/golden/integration_backoff.golden.json`). Celery/Redis worker wiring is still not done
  (no worker process in PHASE_00; see docs/integration/README.md §8).

## 6. Tests

`backend/platform_core/tests/test_engine_*.py`: unit, property-based (hypothesis, derandomized profile in
`backend/conftest.py`), golden snapshots (`tests/golden/*.json`) and race tests on PostgreSQL (threads with
separate connections: idempotency same-key ×8, different-body ×6, compare-and-set ×8, 4 dispatchers × 60 events).
