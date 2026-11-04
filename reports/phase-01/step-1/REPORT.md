# REPORT — PHASE_01 / 01.1 Discovery & Contract

```
PROJECT: Aleekhan
PHASE: PHASE_01
STEP: 01.1
COMMIT SHA: 89e5f0d (step content); report hygiene follow-up commit after review
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-04
IMPLEMENTER: Claude Code (aleekhan-implementer); report written and verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; PHASE_00 accepted (tag phase-00-accepted)
```

## 1. Purpose & acceptance
Step text: "01.1 — Discovery & Contract: تعارض‌ها، جدول داده، state transitions، OpenAPI draft، mock/UI binding و خطرات را ثبت کن؛ برای P0 تصمیم بگیر، هنوز داده واقعی mutate نکن."

Acceptance cases with minimum_phase 1 (GLOBAL_ACCEPTANCE_CASES.csv):
- **SEC-01** (unauthorized object id → BOLA/IDOR blocked, P0): every planned `{id}` path follows the "out of scope = 404 NOT_FOUND" convention (API_RUNTIME §2). Tests come in 01.4.
- **SEC-03** (unsafe upload → quarantined, no execution, P0): upload contract plus STATE_TRANSITIONS §4.6 (quarantine machine). The tool choice is blocked on DEC-053.
- SEC-02 (force kill) belongs to PHASE_11 and is absent from the contract; jobs get safe cancel only, with permission and reason.

Employer requirements in scope:
- DEC-003: users only inside the system; admin ≠ business approval.
- DEC-043: org tree, page 46 + tree view; details in DEC-048.
- DEC-047: permission matrix approval, DEC-049.

Pages 36, 39, 40, 42, 46 (all DRAFT).

## 2. Actual changes (documents and contracts; no migrations, no business code, no real data)
**Discovery documents**
- `docs/discovery/CONFLICTS.md`: C-26 to C-46.
- `docs/discovery/DATA_TABLE.md`: PHASE_01 section with 27 entities. Each has key fields, constraints, provenance, sensitivity S0–S3 and retention.
- `docs/discovery/STATE_TRANSITIONS.md` §4. Machines: user, session, work task, approval, workflow cancellation, document quarantine, job run (safe cancel only), role/assignment, parameter, org. Every unapproved guard is BLOCKED with its DEC id.
- `docs/discovery/MOCK_UI_BINDING.md` §6: shared shell, pages 36/39/40/42/46, the org tree, and a catalog→operation map.
- `docs/discovery/RISKS.md`: R-21 to R-35.

**API contract**
- `docs/api/openapi-draft.yaml` → **0.5.0-draft**: 97 planned operations on 78 paths. Each path is marked `x-aleekhan-status: planned`, `x-aleekhan-step: '01.4'`.
  - The 8 implemented paths are unchanged.
  - Changes to existing components: the `sessionCookie` description, and an optional `WWW-Authenticate` header (REV-0013, C-42).
- `docs/api/API_RUNTIME.md` §8.

**Security**
- `docs/security/PERMISSION_MATRIX_DRAFT.md`: PROPOSED v0.1, 11 roles × 43 permissions. Deny by default; technical roles hold no business approval; no self-approval.

**Code and tests (contract plumbing only)**
- `backend/platform_core/api/views.py`: `CONTRACT_VERSION = "0.5.0-draft"`. Runtime behaviour of the 8 endpoints is unchanged.
- `backend/platform_core/tests/openapi_contract.py` and `test_api_contract.py`:
  - Route parity now compares URL routes with *implemented* paths and asserts that no planned path is routed.
  - The implemented public set still equals `PUBLIC_OPERATIONS`.
- New `test_api_contract_planned.py` (8 tests): rules for planned operations.
  - Session security, `x-aleekhan-permission`, Idempotency-Key unless exempt, If-Match on PATCH, 409 on blocked operations.
  - Unique operation ids; planned error codes not yet in `ErrorCode`.
  - The planned public set is pinned to `{getLoginContext, login}`.

**Decisions**
- New packets in Persian: `control/decisions/DEC-032_PACKET.md`, `DEC-048_PACKET.md` … `DEC-054_PACKET.md`.
- `DECISIONS_ADDENDUM.csv`: rows DEC-048 to DEC-054 (OPEN).

**Changelog:** `CHANGELOG.md` entry.

## 3. Data integrity
No schema or data was touched. Write rules (transactional, idempotent, audit + outbox, If-Match) are carried in the contract conventions for 01.2–01.4.

## 4. Security evidence
- **Production URLconf:** unchanged, and `DenyAllPolicy` is still in force.
- **New public operations (C-26):** exactly two, both pre-login: `GET /auth/login` (CSRF cookie only) and `POST /auth/login`. A test pins them. **Needs reviewer acceptance.**
- **Idempotency-Key exemptions (C-27):** six credential operations are exempt, because passwords and one-time secrets must not be stored in idempotency records: login, verifyMfa, logout, changeMyPassword, startMfaEnrolment, confirmMfaEnrolment.
- **Contract scope:** no force-kill, no break-glass endpoint, no business resources.
- **Secret scan:** 0 findings over the tree and history.

## 5. Test evidence
Re-run by the orchestrator on work-windows; logs in `logs/orch/`.

| Command | Outcome | Log |
|---|---|---|
| `ruff check` + `ruff format --check` (backend) | PASS | `logs/orch/ruff.log` |
| `mypy .` strict | PASS, 87 files | `logs/orch/mypy.log` |
| `pytest -m "not perf"` full suite (PG 17.9) | **583 passed, 1 deselected** (perf) | `logs/orch/pytest.log`, `pytest.xml` |

Implementer runs:

| Command | Outcome | Log |
|---|---|---|
| contract/openapi subset | 52 passed | `logs/pytest_contract.log` |
| full suite | 583 passed, 1 deselected | `logs/pytest_full_not_perf.log` |
| OpenAPI validation | VALID 3.1.0; 8 implemented + 78 planned paths; 18 operations blocked by decisions | `logs/openapi_validate.log` |
| `verify_handoff.py` | OK=300, KNOWN_DEFECT=1 (DEC-044), failures=0 | `logs/verify_handoff.log` |
| `secret_scan.py` / `--history` | 0 / 0 | `logs/secret_scan*.log` |
| REPORT.json schema | valid | `logs/report_schema.log` |

Not applicable to this step: migrations up/down, golden data, Playwright, frontend build.

## 6. Demo (employer)
There is nothing to click yet. `/api/v1/version` now reports `contract_version` 0.5.0-draft.

The employer's work in this step is the decision packets, answered one at a time.

## 7. Issues / decisions

| ID | Priority | Question |
|---|---|---|
| DEC-032 | P1 (Gate-1) | Maker-checker scope; owner as only approver; approval expiry; audit/login retention |
| DEC-048 | P0 | Org tree details (unit types/levels, acting holders, reports-to between positions or persons, approval routing along the tree, who edits it) |
| DEC-049 | P0 | Approve permission matrix v0.1 |
| DEC-050 | P0 | MFA method and recovery |
| DEC-051 | P0 | Password policy, lockout, session lifetime, concurrent sessions, MFA re-check window |
| DEC-052 | P0 | "Inside factory" network definition; personal vs shared operator accounts |
| DEC-053 | P0 | Upload types/size, antivirus tool, storage, quarantine (SEC-03) |
| DEC-054 | P1 | Emergency access / sole-admin recovery |

Other items:
- **Proposals for the reviewer:** C-30 (separate WorkTask and ApprovalRequest machines), C-33/C-34 (split of pages 42/36 between PHASE_01 and PHASE_11), C-46 (no document check-out in PHASE_01).
- **Planned error codes:** INVALID_CREDENTIALS, SELF_APPROVAL_FORBIDDEN, … are listed in `x-aleekhan-conventions` only. They enter `ErrorCode` and the golden catalogue in 01.3/01.4.
- **C-41:** security checklist row 2.3 still says OPEN although REV-0014 is closed. To fix in 01.7.
- **R-32:** the contract is about 7,700 lines (yaml.dump). 01.4 may split it.

## 8. Rollback
`git revert <commit>`. This restores 0.4.0-draft, the old contract tests and `CONTRACT_VERSION` together. No data or schema is involved.

## 9. Review request
Request PASS. Reviewer attention:
- C-26: the two public pre-login operations.
- C-27: the Idempotency-Key exemptions.
- The changed route-parity test.

## 10. Next step (proposal)
- The employer answers the packets one at a time, starting with DEC-048 (org tree) and DEC-049 (matrix).
- 01.2 Database can start in parallel for the parts no decision blocks. The schema can hold every option.
