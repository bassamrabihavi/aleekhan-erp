VERDICT: PASS
PHASE/STEP: PHASE_01 / 01.1 Discovery & Contract   COMMIT: 89e5f0db89fa482778a8647e91c7af44c496696a
REVIEWER: aleekhan-reviewer (independent, read-only), machine work-windows, 2026-11-04
INPUTS: `git show 89e5f0d`, reports/phase-01/step-1/REPORT.md + REPORT.json, handoff/03_PHASE_PLAN/PHASE_01.md, REVIEW_CHECKLIST R01-R14, handoff/05_SECURITY/*

## Reproduced by the reviewer
| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` (backend) | All checks passed / 87 files already formatted |
| `mypy .` | Success: no issues found in 87 source files |
| `pytest test_api_contract.py test_api_contract_planned.py` | 24 passed, 2 errors. The 2 errors are DB-backed health tests: the reviewer shell has no PG credentials |
| `pytest -m "not perf"` full suite | 310 passed, 273 errors. All errors come from the DB connection, because the reviewer shell has no PG credentials. Logic is not the cause. The DB part is NOT reproduced by the reviewer. Evidence for it: orchestrator `logs/orch/pytest.xml` (tests=583 failures=0 errors=0 skipped=0, timestamp 18:41, before the commit at 18:42) |
| openapi-spec-validator on `docs/api/openapi-draft.yaml` | VALID |
| Semantic diff of OpenAPI 0.4.0 vs 0.5.0 (own script, yaml-parsed) | All 8 implemented path items are identical. Only 2 components changed: the `sessionCookie` description and an optional `WWW-Authenticate` header on `AuthenticationRequired`. No path was removed. Top-level `security` is unchanged |
| Planned-operation inventory (own script) | 97 ops / 78 paths. Exactly 2 public ops: `getLoginContext`, `login`. Every `{id}` path declares 404. `/audits*` has only GET. No force-kill and no break-glass operation |
| `tools/verify_handoff.py` | OK=300, KNOWN_DEFECT=1 (DEC-044), failures=0 |
| `tools/secret_scan.py --history` | findings=0 -> PASS |

## CHECKS
- R01 ✔ Scope. The diff holds docs, the contract, contract tests and the `CONTRACT_VERSION` constant (views.py:32). There are no migrations, no business code and no data. `out_of_scope_phase_01` sits at openapi-draft.yaml:7820. Force kill is excluded (openapi-draft.yaml:3693, C-31). Check-out is excluded (C-46).
- R02 ✔ Every unapproved rule is marked **BLOCKED (DEC-xxx)** (STATE_TRANSITIONS §4.1-4.11), and 18 ops carry `x-aleekhan-blocked-by` with a 409. The packets label recommendations "فقط پیشنهاد". CONFLICTS also states: "No P0 business rule was decided in this step". One minor exception: REV-0104.
- R03 n/a No migration in this step (01.2). DATA_TABLE.md gives a constraint/retention design for 01.2.
- R04 n/a No write path. The contract carries `write_requirements` (Idempotency-Key, If-Match, audit + outbox in the same transaction), and `test_planned_mutations_require_idempotency_key_unless_exempt` enforces it.
- R05 n/a The engine comes in 01.3. The state machines are drafted, and their blocked guards answer 409 RULE_NOT_APPROVED.
- R06 ✔ OpenAPI diff checked semantically (above). The new tests (test_api_contract_planned.py, 8 tests) pin permission, session, Idempotency-Key, If-Match/412, 409 on blocked ops and unique operationIds. Route parity asserts that no planned path is routed (test_api_contract.py:93-96). Reproduced: 24 passed.
- R07 n/a No UI in this step. MOCK_UI_BINDING §6 is documentation only, and C-43 rejects fabricated KPIs.
- R08 ✔ Public ops are pinned to 2 in two places (test_api_contract.py:43 and `planned_public_operations`). The `login` password is `writeOnly` and never echoed or logged. Exempting the 6 credential ceremonies from Idempotency-Key is justified: it avoids storing secret-bearing hashes. Audit has no mutation API. All 6 cancel/disable/assignment ops require a reason. Secret scan: 0 findings. SEC-01 is covered by the 404-on-out-of-scope convention on every `{id}` path, and SEC-03 by the quarantine machine (§4.6, blocked on DEC-053). A minor privacy note is REV-0103.
- R09 ✔ Only `backend/platform_core` and docs are touched. No other module tables exist or are referenced for writes.
- R10 n/a No integration in this step.
- R11 n/a No ops change.
- R12 ✔ (partial) Lint, type and contract tests were reproduced. The DB-backed suite could not be reproduced here (no PG credentials in the reviewer shell). It is evidenced by the committed junit xml (583/0/0/0). This step changes no DB code.
- R13 ✔ Updated: CHANGELOG.md:94-105, API_RUNTIME.md §8, CONFLICTS C-26..C-46, RISKS R-21..R-35, DATA_TABLE, STATE_TRANSITIONS §4, PERMISSION_MATRIX_DRAFT, DECISIONS_ADDENDUM rows DEC-048..054.
- R14 n/a Left to the employer at Gate time.

## ISSUES
- REV-0101 [P2] docs/api/openapi-draft.yaml:4187 vs docs/security/PERMISSION_MATRIX_DRAFT.md:88. `rejectDocumentRevision` has no `x-aleekhan-mfa-step-up`, but the matrix row `platform.document.approve` (approve AND reject) is flagged MFA. The analogous `rejectRequest` (openapi-draft.yaml:3167) does carry MFA. Repro: parse the yaml and compare the `x-aleekhan-mfa-step-up` of `approveDocumentRevision` and `rejectDocumentRevision`. Expected fix: add the MFA step-up to `rejectDocumentRevision`, or footnote the matrix if the difference is deliberate. Regression test required: operations that share one `x-aleekhan-permission` must share the MFA flag (or a listed exception).
- REV-0102 [P3] reports/phase-01/step-1/REPORT.md:7, REPORT.json `commit_sha: "PENDING"`, CHANGELOG.md:105. The report does not carry the commit hash, although the phase outputs require "git commit hash". Expected fix: fill in 89e5f0d in the next status/report commit. No regression test needed.
- REV-0103 [P3] reports/phase-01/step-1/logs/orch/pytest.xml. The junit file records the workstation hostname in a public repo (DEC-046). Expected fix: strip or normalise `hostname` when saving junit logs (for example with a log-sanitising step). Regression test optional: secret_scan rule or report check.
- REV-0104 [P3] docs/discovery/DATA_TABLE.md:161. The Notification retention "TECH: 180 days" is a retention period presented as a technical default, while retention policy is otherwise deferred to DEC-032 (C-39). Expected fix: mark it as a proposal under DEC-032, or have ops/the employer confirm it in 01.2. No test needed.

Notes (not defects of this commit):
- The uncommitted working tree already records DEC-048 as APPROVED (DECISION_LOG.csv). The 0.5.0 contract still lists DEC-048 in `x-aleekhan-blocked-by` (createOrgUnit, createPosition, createPositionAssignment) and in STATE_TRANSITIONS §4.4/§4.10. A reviewed commit in 01.2/01.3 must update these markers to match the approved answer. In phase 1, routing is role + unit scope only (option A).
- Reviewer accepts the technical proposals C-26 (2 public pre-login ops), C-27 (6 Idempotency-Key exemptions with compensating controls), C-30 (WorkTask vs ApprovalRequest split) and the changed route-parity test. C-33/C-34/C-46 phase splits are acceptable as proposals, but they change scope, so the employer should confirm them with DEC-049.
- P0 decisions DEC-049..DEC-053 are open. This step's mandate is to raise them as packets, which it did, so they do not block 01.1. They do block the guarded operations in 01.3/01.4 and Gate-1.

## EMPLOYER ATTENTION
- ماتریس دسترسی (DEC-049) هنوز تأیید نشده است. تا تأیید آن هیچ نقشی فعال نمی‌شود.
- این تصمیم‌ها برای ادامه کار لازم‌اند و به ترتیب پرسیده می‌شوند:
  - روش ورود دومرحله‌ای (DEC-050)
  - سیاست رمز عبور و جلسه (DEC-051)
  - تعریف شبکه داخل کارخانه (DEC-052)
  - بارگذاری فایل و ضدبدافزار (DEC-053)
- تقسیم صفحه ۳۶ و ۴۲ بین فاز ۱ و فاز ۱۱ (C-33، C-34) و حذف check-out سند از فاز ۱ (C-46) پیشنهادهای فنی‌اند. چون محدوده را تغییر می‌دهند، تأیید شما لازم است.
- در این گام چیزی برای آزمون (UAT) وجود ندارد.
