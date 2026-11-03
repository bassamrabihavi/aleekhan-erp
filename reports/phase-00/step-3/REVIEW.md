VERDICT: PASS
PHASE/STEP: PHASE_00 / 00.3 Domain Engine   COMMIT: a6efb53cff09aefdacb50ef48e092ec0041ced6f
REVIEWER: aleekhan-reviewer (independent, read-only), work-windows, 2026-11-03
NOTE: Advisory until DEC-036 is APPROVED; the employer confirms the step.

Re-run by the reviewer (HEAD b31f1d5; `git diff --stat a6efb53 HEAD` = only control/PROJECT_STATUS.json and reports/phase-00/step-3/REPORT.*, so no code differs):
- `ruff check .` -> "All checks passed!" (exit 0); `ruff format --check .` -> "71 files already formatted" (exit 0)
- `mypy .` (backend, strict, py3.12) -> "Success: no issues found in 40 source files"
- `pytest -q` (PostgreSQL 17.9 on 127.0.0.1:5433, Python 3.12.10) -> "175 passed", 0 skipped
- `pytest -k "race or concurren"` x3 -> "30 passed" each time (a wider selection than the report's 5; all stable)
- `manage.py makemigrations --check --dry-run` -> "No changes detected"
- `backend/scripts/db_roundtrip.sh` (up, zero, up, diff) -> "schema diff: EMPTY (386 lines compared)", "ROUNDTRIP OK"
- `unittest discover -s tools/tests` -> "Ran 12 tests ... OK"; `tools/verify_handoff.py` -> "OK=300, KNOWN_DEFECT=1, EXCLUDED=46 | failures=0"
- Secrets grep of reports/phase-00/step-3 for password, PGPASSWORD and DSN credentials -> 0 hits

CHECKS:
- R01 ✔ Scope is engine only, with no business table, API, UI or migration (git show --stat: engine/, tests, docs, config). The carry-over items REV-0005, 0006 and 0007 are closed: pyproject.toml:5,8; ruff.toml:2-6; docs/db/README.md "Audit columns" row.
- R02 ✔ No business rule is invented. engine/rules.py:23 has `APPROVED_RULE_DECISIONS = {}`, guarded by test_engine_rules_state.py:23. The numeric defaults (TTL 24h, lease 5min, 10 attempts, 2s x2 cap 1h) are labelled as technical parameters (idempotency.py:22-24, outbox.py:17-19) and are left for 00.7.
- R03 ✔ There is no schema change: makemigrations finds no changes and the round-trip diff is EMPTY. Compare-and-set runs on row_version (concurrency.py:64, outbox.py:232,257, idempotency.py:168,193). A race test shows 8 writers -> 1 wins / 7 VERSION_CONFLICT (test_engine_uow_concurrency.py:215).
- R04 ✔ Write + audit + outbox run in one atomic block, and an empty audit or outbox rolls the write back (uow.py:112-118; tests :78, :89). The idempotent claim is committed separately, and complete() runs inside the business transaction (idempotency.py:276-279). Race tests on separate connections pass: same key -> handler once (test_engine_idempotency.py:255); different bodies -> 1 ok / 5 KEY_REUSED (:281); 4 dispatchers with SKIP LOCKED -> 60 published once each (test_engine_outbox.py:211).
- R05 ✔ The golden files are error_codes, outbox_delivery_machine and backoff (tests/golden/*). Property tests use hypothesis with derandomize=True (backend/conftest.py:6). The rule gate cannot be bypassed by an env toggle (rules.py:7-9). The state machine enforces rule_gates (state.py:41-43).
- R06 ✔ OpenAPI moves to 0.2.0-draft and adds IDEMPOTENCY_IN_PROGRESS (409) to both the enum and the status map. The catalogue is cross-checked against OpenAPI (test_engine_errors.py:43,63,87). Codes are unchanged (VERSION_CONFLICT, ACCESS_DENIED). Per-action permission is out of scope here; the API layer comes in 00.4, and replay_dead_letter states this (outbox.py:321).
- R07 n/a There is no UI in 00.3.
- R08 ✔ Audit snapshots are redacted and outbox payloads with sensitive keys are rejected (redaction.py; uow.py:68-69,87-89; test :115). last_error stores only a safe code, never str(exc) (outbox.py:168-171; test :155). The test publisher is refused outside dev/test (testing.py:23-25; test :204). No secrets appear in the logs (grep shows 0).
- R09 ✔ Only platform_core tables are written. No other module exists yet.
- R10 n/a There is no integration or source import in 00.3; that is step 00.6.
- R11 ✔ Stale DISPATCHED recovery is in outbox.py:300, DLQ replay is audited at outbox.py:318-345, and housekeeping purge_expired uses SKIP LOCKED (idempotency.py:215). The missing partial index for recover_stale is disclosed in REPORT §7.
- R12 ✔ All of the above was re-run by the reviewer against a real PostgreSQL. The race tests are reproducible (3x stable). No mocked DB is used. The in-memory publisher is labelled as a test double.
- R13 ✔ docs/engine/README.md and docs/engine/ERROR_CODES.md were added. docs/discovery/STATE_TRANSITIONS.md 1.1/1.2, docs/db/README.md and openapi-draft were updated. The new dependencies hypothesis 6.170.4 and sortedcontainers 2.4.0 are pinned in requirements-dev.txt.
- R14 n/a This is left to the employer at Gate time.

ISSUES (none P0/P1; all P3, can be scheduled in 00.4/00.7):
- REV-0008 [P3] backend/platform_core/tests/conftest.py:24 — Problem: audit_cleanup runs `ALTER TABLE ... DISABLE TRIGGER trg_audit_event_append_only` without checking that the connection is the throw-away test DB. Repro: read the fixture; it has no assert on connection.settings_dict["NAME"]. Expected fix: assert the DB name starts with "test_" (or ALEEKHAN_ENV == "test") before the ALTER. In 00.7, use a runtime DB role with no ALTER rights. Regression test: unit test that the fixture refuses a non-test DB name.
- REV-0009 [P3] backend/platform_core/engine/uow.py:64-67 — Problem: only before/after are redacted. `scope`, `reason` and `resource_id` are stored verbatim, so a caller could put sensitive values there. Repro: uow.audit(..., scope={"password": "x"}) stores the value unredacted. Expected fix: apply redact() to scope too, and in 00.4 document that reason must not carry PII. Regression test: extend test_audit_snapshots_redacted_and_sensitive_payload_rejected to cover scope.
- REV-0010 [P3] backend/platform_core/engine/rules.py:23 — Problem: APPROVED_RULE_DECISIONS is a mutable module-level dict, so runtime code (not only tests) could insert an entry and unlock a rule. Expected fix: expose it as types.MappingProxyType, or freeze it, and have tests monkeypatch the lookup function instead. Regression test: assert the registry is immutable.
- REV-0011 [P3] backend/aleekhan/settings.py:26 (pre-existing, interacts with engine/testing.py:23) — Problem: ALEEKHAN_ENV defaults to "dev" when unset, so a production deploy that forgets the variable would accept the InMemoryTestPublisher and DEBUG gating would treat it as dev. Expected fix (00.7): no default outside manage.py dev runs; fail fast if it is unset in deployed settings. Regression test: settings import with the env unset in deploy mode raises ImproperlyConfigured.
- REV-0012 [P3] backend/platform_core/engine/idempotency.py:280-285 — Problem: any handler exception, including a deterministic 4xx such as ValidationFailed or RuleNotApproved, is released as FAILED_RETRYABLE. A retry with the same key therefore re-executes the handler instead of replaying the stored error. This is safe because there is no committed write, but it differs from "same key => same stored response" for error outcomes. Expected fix: decide and document this in 00.4 (store final 4xx responses, or keep retryable and document it). Regression test: matching behaviour test in 00.4.

EMPLOYER ATTENTION:
- این گام فقط موتور فنی است و چیزی برای تست شما ندارد. همه قواعد کسب‌وکار قفل هستند (فهرست قواعد مصوب خالی است).
- اعداد فنی پیش‌فرض (نگهداری کلید تکرار ۲۴ ساعت، مهلت ۵ دقیقه، حداکثر ۱۰ بار تلاش مجدد) پارامتر فنی‌اند، نه قاعده کسب‌وکار. تأیید نهایی‌شان در گام 00.7 با واحد عملیات است.
- تا تصویب DEC-036، این PASS مشورتی است و تأیید گام با شماست.
