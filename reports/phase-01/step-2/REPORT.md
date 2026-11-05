# REPORT — PHASE_01 / 01.2 Database

```
PROJECT: Aleekhan
PHASE: PHASE_01
STEP: 01.2
COMMIT SHA: see status file / REPORT.json (filled after commit)
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-05
IMPLEMENTER: Claude Code (aleekhan-implementer); report written and verified by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; 01.1 PASS (reports/phase-01/step-1/REVIEW.md)
```

## 1. Purpose & acceptance
Step text: "01.2 — Database: نسخه Migration، PK/FK/unique/check/index، audit, outbox، rollback و seed غیرحساس؛ تست migrate-up/down و schema diff."

The schema implements the employer decisions approved on 2026-11-04/05:
- DEC-003, DEC-032, DEC-048, DEC-049, DEC-050, DEC-051, DEC-052, DEC-053, DEC-054.
- The employer answers Q-0101, Q-0102 and Q-0105.

Acceptance groundwork:
- **SEC-01:** record-scope columns and FKs (tests at API level come in 01.4).
- **SEC-03:** upload allow-list CHECK; every new revision starts quarantined; scan verdict final; content immutable.

## 2. Actual changes
**Migrations (app `platform_core`)**
- `0007_phase01_platform_schema`: 33 new tables (identity, org, workflow, documents, params, jobs). It also adds 5 audit-chain columns to `platform_audit_event`, with DB defaults.
- `0008_phase01_db_guards` (reversible RunSQL):
  - `btree_gist` and 5 exclusion constraints.
  - Row-version triggers.
  - Append-only, terminal-state, immutable and invariant triggers.
  - Per-user advisory lock in the position- and role-assignment guards (deadlock fix, see §5).
- `0009_phase01_constraint_names`: conventional `fk_/uq_/ix_` names; exact reverse.
- `0010_seed_phase01_catalogue`, non-sensitive seed:
  - 43 permissions, 11 roles (matrix v1.0) and 111 grants.
  - Unit types COMPANY/DEPARTMENT/SECTION/LINE.
  - Upload allow-list pdf/png/jpg/jpeg/dxf/xlsx.
  - 3 protected job types.
  - 32 parameters, each with its DEC provenance.
  - Not seeded: users, org data, CIDR ranges, secrets.

**Code**
- Models in `platform_core/{identity,org,workflow,documents,params,jobs}/models.py` and `schema_common.py`.
- `CONTRACT_VERSION` = 0.5.1-draft.

**Tests**
- New: `test_phase01_identity/roles/org/workflow_docs/params_jobs/schema/concurrency.py`, plus `phase01_factories.py`.
- Updated contract tests, including the REV-0101 regression check.

**Ops**
- `ops/db/grants.sql`, `roles_check.sh`: 22 new checks.
- `backend/scripts/db_roundtrip.sh`: extension-left check; partial rollback to 0006.
- `tools/redact_paths.py`: REV-0103 hostname redaction, `--in-place`; 3 tests.
- `tools/ci_local.sh`: redacts junit files.

**Docs**
- `docs/api/openapi-draft.yaml` 0.5.1-draft:
  - The 18 formerly blocked operations now carry `x-aleekhan-decided-by`.
  - REV-0101: MFA added to `rejectDocumentRevision`.
  - Enum changes: account_kind PERSON/OPERATOR; assignment kind PRIMARY/ACTING; new classification OWNER_POLICY.
- `docs/security/PERMISSION_MATRIX_DRAFT.md`: APPROVED v1.0 (DEC-049).
- `docs/db/ERD.md` §4–6.
- `docs/discovery/DATA_TABLE.md` (REV-0104 label), `STATE_TRANSITIONS.md` (§4.12 questions), `CONFLICTS.md`.
- `docs/ops/DB_ROLES.md`, `docs/api/API_RUNTIME.md`, `CHANGELOG.md`.

## 3. Data integrity (enforced in PostgreSQL)
| Decision | Rules enforced |
|---|---|
| DEC-003 | A TECHNICAL role can never hold a business-approval permission. |
| DEC-032 | Maker≠checker on approval requests and document revisions. BUSINESS_RULE publisher ≠ proposer. A business-approval role assignment stays PENDING until a third person approves. Approval requests have a mandatory expiry. Login events can be deleted only after 24 months. |
| DEC-048 | No cycles, depth ≤ the `org_tree_max_depth` parameter (6). One PRIMARY position per person at a time (exclusion). ACTING needs an end date. Effective-dated, non-backdatable history. |
| DEC-050 | TOTP replay guard. Recovery codes stored as hashes, single use. |
| DEC-051 | Policy values are parameters. Password history kept as hashes. The one-time password expires and forces a change. |
| DEC-052 | Operator accounts are INTERNAL_ONLY. |
| DEC-053 | Allow-list CHECK and size parameter. |
| DEC-054 | At most one break-glass account; its usage log is append-only. |

Other rules:
- Protected job types cannot be cancelled.
- Synthetic rows must carry «محیط آزمایشی — داده ساختگی».

## 4. Security evidence
- **App role:** DML only. It cannot update or delete append-only tables, nor disable triggers (roles check 49/0).
- **Seed data:** no secrets or real data.
- **Secret scan:** 0 findings over the tree and history.
- **Logs:** no home path, account name or hostname (grep 0 hits).

## 5. Test evidence
Orchestrator re-runs on work-windows, PG 17.9; logs in `logs/orch/`.

| Command | Outcome | Log |
|---|---|---|
| ruff check + format --check | PASS | `logs/orch/ruff.log` |
| mypy strict | PASS, 112 files | `logs/orch/mypy.log` |
| `pytest -m "not perf"` full | **692 passed**, 1 deselected (perf) | `logs/orch/pytest.log`, `pytest.xml` |
| concurrency tests ×5 | 5 passed each run | `logs/orch/concurrency_x5.log` |
| `db_roundtrip.sh` (up → zero → up, partial rollback to 0006) | ROUNDTRIP OK, schema diff EMPTY (5815 lines) | `logs/orch/db_roundtrip.log`, `migration/` |
| `roles_check.sh` | passed=49, failed=0 | `logs/orch/roles_check.log`, `roles/` |

The implementer's own runs are in `logs/`: 692 passed, concurrency ×12, makemigrations --check clean, tools unittest 42 OK, verify_handoff OK=300 / KNOWN_DEFECT=1, secret scan 0, OpenAPI valid.

**Verification history:** the first orchestrator full run gave 691 passed and 1 failed (`test_concurrent_primary_position_assignment_only_one_wins`).
- It was flaky. A deadlock occurred while PostgreSQL checked the exclusion constraint. The invariant held, but the losing caller would have got a 500 instead of a 409.
- Fix: a per-user `pg_advisory_xact_lock` in the assignment guards. The same fix was applied to role assignment.
- Re-run after the fix: 692/692, and concurrency stable over 12 + 5 runs.

## 6. Demo (employer)
Nothing to click yet (DB only). Pages come in 01.5.

## 7. Issues / decisions
- **Still open, employer questions:**
  - Q-0103: does publishing an OWNER_POLICY parameter need a second person?
  - Q-0104: does 25 MB mean 25,000,000 or 26,214,400 bytes? 25,000,000 is seeded, the stricter reading.
  - Q-0106: can one position have several PRIMARY holders?
- **Permission sensitivity:** left blank, because the matrix gives no per-action class.
- **OWNER_POLICY classification:** added, which is a contract change. Reviewer to confirm.
- **Actor ids:** PHASE_00 audit/outbox actor_id has no FK to user, on purpose.
- **Password hasher:** chosen in 01.3. Argon2 would need a new pinned dependency.
- **Notification table:** deferred to 01.4/01.5.
- **DEC-027 (UI design system):** still open, for 01.5.

## 8. Rollback
- DB: `manage.py migrate platform_core 0006` (tested in the roundtrip).
- Code: `git revert <commit>`.

## 9. Review request
Request PASS. Reviewer attention:
- The deadlock fix.
- The OWNER_POLICY enum addition.
- The DB-level enforcement of DEC-032 (pending business-approval assignments).

## 10. Next step
01.3 Domain Engine:
- Password, lockout and session logic, including END_OLDEST_SESSION.
- TOTP and recovery codes.
- Approval workflow with maker≠checker and expiry.
- Upload quarantine pipeline.
- Audit hash chain.
- Error codes.
