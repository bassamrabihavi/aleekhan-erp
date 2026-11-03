"""Platform domain engine (PHASE_00 / 00.3): errors, rule gate, state machines, transactional writes,
idempotency, optimistic concurrency and outbox dispatch. No business rules live here.

Modules:
* ``errors``       stable error-code catalogue + typed exceptions (docs/engine/ERROR_CODES.md)
* ``rules``        ``require_approved_rule(decision_id)`` -> RULE_NOT_APPROVED
* ``state``        declarative ``StateMachine`` -> STATE_TRANSITION_NOT_ALLOWED
* ``context``      ``Actor``, ``RequestContext``, ``db_now``
* ``uow``          ``unit_of_work``: write + audit + outbox in one transaction
* ``redaction``    sensitive-key redaction / rejection
* ``concurrency``  ETag / If-Match / compare-and-set on ``row_version`` -> VERSION_CONFLICT
* ``idempotency``  begin / complete / replay / expiry on ``platform_idempotency_record``
* ``outbox``       delivery state machine, backoff, SKIP LOCKED claim, publisher protocol
* ``testing``      test doubles only (refused outside dev/test)
"""
