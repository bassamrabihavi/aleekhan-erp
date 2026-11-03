"""HTTP/API layer of the platform (PHASE_00 / 00.4). Contract: ``docs/api/openapi-draft.yaml``.

Modules:
* ``request_id``   X-Request-ID middleware + access log + context variable
* ``logging``      JSON log formatter and request-id log filter (no secrets / PII)
* ``problems``     DRF exception handler and Django 400/403/404/500 handlers -> RFC 9457 problem+json
* ``permissions``  deny-by-default permission, public allowlist, scoped (action + record) permission
* ``throttling``   per-IP / per-principal rate limits -> 429 RATE_LIMITED with Retry-After
* ``pagination``   cursor pagination (default 25, max 100, opaque ``next_cursor``)
* ``concurrency``  ETag / If-Match helpers on top of ``engine.concurrency``
* ``idempotent``   ``Idempotency-Key`` -> ``engine.idempotency.run_idempotent`` -> DRF Response
* ``views``/``urls`` phase-0 endpoints: /health/live, /health/ready, /version, /access-gate/check
"""
