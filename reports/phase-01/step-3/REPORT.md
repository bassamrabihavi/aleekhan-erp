# REPORT — PHASE_01 / 01.3 Domain Engine

```
PROJECT: Aleekhan
PHASE: PHASE_01
STEP: 01.3
COMMIT SHA: 6fc3eea
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-05
IMPLEMENTER: Claude Code (aleekhan-implementer); report written and verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 01.2 PASS (reports/phase-01/step-2/REVIEW.md)
```

## 1. Purpose & acceptance
Step 01.3 builds the domain engine: services only, with no HTTP views. `api.permissions.ACCESS_POLICY` stays `DenyAllPolicy` until 01.4, and a test asserts this.

It implements the following employer decisions:
- DEC-003, DEC-032, DEC-048 to DEC-054.
- Q-0101 to Q-0106.
- REV-0109 (no back-dating of position assignments).

Acceptance groundwork:
- **SEC-01:** record-scope policy (`authz/policy.py`, `scope_q`). A golden file covers all 473 matrix cells.
- **SEC-03:** the upload pipeline:
  - allow-list and magic-byte check;
  - XLSX must be macro-free;
  - zip-bomb guard;
  - quarantine, ClamAV adapter, encrypted storage;
  - download as attachment only;
  - purge after 30 days.

## 2. Actual changes
**Authorization** (`authz/policy.py`)
- Role/scope policy. Scopes: GLOBAL, ORG_UNIT, ORG_UNIT_SUBTREE, own records, own unit.
- Caps on document sensitivity.
- TECHNICAL roles are excluded from business approval.
- MFA step-up window comes from a parameter.
- Field redaction, and an `RbacPolicy` adapter for 01.4.

**Identity** (`identity/`)
- Passwords (DEC-051): PBKDF2; one-time password valid 72 h with a forced change; the last 5 passwords are refused.
- TOTP per RFC 6238, with a replay guard and golden test vectors.
- AES-256-GCM encryption of secrets at rest.
- Network zones from the configured CIDR list. VPN and unknown addresses count as outside.
- Sessions:
  - users idle 2 h, absolute 12 h;
  - operators idle 8 h, absolute 12 h;
  - at most 3 sessions; on a 4th login the oldest is ended (`CONCURRENT_LIMIT`).
- Login, MFA verify with token rotation, and step-up.
- Lockout: 5 failures in 15 min → locked for 15 min.
- MFA enrolment, 10 single-use recovery codes, and admin MFA reset.
- User administration, role lifecycle and role assignments.

**Other modules**
- `org/service.py`: units, positions and position assignments.
- `workflow/`:
  - approvals: maker ≠ checker, one decision per request, 30-day expiry;
  - tasks;
  - workflow cancellation with compensation.
- `documents/`: the SEC-03 pipeline above, plus a clearly named test-double scanner.
- `params/`:
  - effective parameter values;
  - OWNER_POLICY parameters are published by the owner alone;
  - BUSINESS_RULE parameters are refused with `RULE_NOT_APPROVED`.
- `jobs/`:
  - safe cancel; protected jobs are refused with `JOB_PROTECTED`; force kill is refused (DEC-024);
  - login events are kept 24 months; audit events are never deleted.

**Engine**
- New: `audit_chain.py` (hash chain), `dbrules.py`, `commands.py`, and `manage.py bootstrap_owner [--recover]` (DEC-054 option C).
- Changed: the unit of work now takes the audit-chain lock first, and fills session_id, network_zone and the chain hash.

**Error codes**
- 8 new codes: INVALID_CREDENTIALS, NETWORK_POLICY_DENIED, PASSWORD_CHANGE_REQUIRED, SELF_APPROVAL_FORBIDDEN, PASSWORD_POLICY_VIOLATION, FILE_TYPE_NOT_ALLOWED, FILE_NOT_RELEASED, JOB_PROTECTED.
- `planned_error_codes` is now empty.

**Migration `0011_phase01_engine`** (reversible)
- REV-0109 trigger:
  - a position assignment cannot start more than 60 s in the past;
  - it cannot be ended with a past date;
  - an ended assignment never changes.
- Session end reason `CONCURRENT_LIMIT`.
- 7 housekeeping job types (not protected).
- The reverse migration is refused while data depends on these additions.

**Dependency**
- `cryptography==50.0.2`, with `cffi==2.0.0` and `pycparser==2.23`.
- All three are older than 14 days.
- Wheels checked against the PyPI SHA-256 digests; lock regenerated.

**Docs**
- `docs/engine/PHASE01_ENGINE.md`: engine readings E-1 to E-10.
- `ERROR_CODES.md`, engine README, `ERD.md`, `STATE_TRANSITIONS.md` §4.13, `CHANGELOG.md`.
- OpenAPI 0.5.2-draft.

**Config**
- `backend/.env.example`: new settings variables, placeholders only.
- `ruff.toml`: one per-file ignore for migration 0011.
- `ops/db/roles_check.sh`: a new check that the app role can verify the audit chain.

## 3. Data integrity
Every write goes through the unit of work, which records the change, the audit event and the outbox message together.

The audit hash chain is serialized by one lock. The app role can verify the chain but cannot rewrite it (roles check 50/50).

The DB guards from 01.2 still hold. The REV-0109 trigger is added.

## 4. Security evidence
- Production access policy is still DenyAll (tested).
- Secrets at rest use AES-256-GCM; recovery codes and passwords are stored as hashes.
- Secret scan: 0 findings, both tree and history.
- Logs: path and hostname redaction done; a grep for the account name, hostname and home path finds 0 hits.
- pip-audit over OSV: no known vulnerabilities. The PyPI-service run timed out (network).

## 5. Test evidence
Orchestrator re-runs on work-windows (PG 17.9); logs in `logs/orch/`.

| Command | Outcome | Log |
|---|---|---|
| ruff check + format --check | PASS | `logs/orch/ruff.log` |
| mypy strict | PASS, 151 files | `logs/orch/mypy.log` |
| `pytest -m "not perf"` full | **851 passed, 1 skipped** (real ClamAV not configured), 1 deselected (perf) | `logs/orch/pytest.log`, `pytest.xml` |
| race tests (`-k "concurrent or race or parallel"`) ×3 | 20 passed each run | `logs/orch/concurrency_x3.log` |
| `db_roundtrip.sh` | ROUNDTRIP OK | `logs/orch/db_roundtrip.log`, `migration/` |
| `roles_check.sh` | passed=50, failed=0 | `logs/orch/roles_check.log`, `roles/` |

Orchestrator fix before commit: the pre-commit guard flagged 6 inline synthetic test passwords; they were moved to named `SYN_PW_*` constants in `engine_fixtures.py` (no guard bypass); full suite re-run 851 passed.

Implementer runs, in `logs/`:
- race/concurrency suite ×5: 36/36 each run;
- makemigrations --check: clean;
- tools unittest and verify_handoff: pass;
- secret scan: 0;
- OpenAPI validation: valid;
- offline SBOM written.

## 6. Demo (employer)
Nothing to click yet; the API comes in 01.4 and the pages in 01.5.

## 7. Issues / decisions
1. **Blocking gap for Gate-1 (needs an employer decision): the first holder of a business-approval role can never be confirmed.**
   - Nobody yet holds the decide permission, and DEC-032 forbids self-approval.
   - A proposal will be prepared as a decision packet, for example a console confirmation in the DEC-054 style.
2. **Engine readings E-1 to E-10** (`docs/engine/PHASE01_ENGINE.md`), for the reviewer and the employer to confirm. Examples:
   - MFA is required at login for any role that holds an MFA or business-approval permission.
   - A user who needs MFA but has not enrolled gets a session inside the factory with MFA actions refused, and is refused outside.
   - "Last 5 passwords" includes the current one.
3. **Contract conflict:** the OpenAPI text for `requestJobCancel` says a queued job goes to CANCEL_REQUESTED. STATE_TRANSITIONS §4.7 says CANCELLED, and the engine follows §4.7.
4. **Not implemented, by design:**
   - a path back for a revision whose approval expires or is withdrawn;
   - the manual-resolution task when a workflow fails;
   - the yearly audit archive;
   - the break-glass account (before production);
   - signed releases.
5. **Performance:** the single audit-chain lock serializes write transactions. The perf check is in 01.7.

## 8. Rollback
- DB: `manage.py migrate platform_core 0010`.
- Code: `git revert <commit>`.

## 9. Review request
Request PASS. Reviewer attention:
- the audit-chain lock in the unit of work;
- the cryptography usage;
- the authz golden file;
- the upload pipeline;
- readings E-1 to E-10;
- the first-approver gap.

## 10. Next step
01.4 API: endpoints over these services, the switch from DenyAll to `RbacPolicy`, and the SEC-01 API tests.
