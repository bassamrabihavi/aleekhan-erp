# Changelog

All changes are recorded per phase and step. Format: step -> what changed -> commits (full SHA from `git log`).
Implementation commit = the commit the step was reviewed on (`control/PROJECT_STATUS.json` `steps.<id>.commit`).
Review verdicts are in `reports/phase-00/step-N/REVIEW.md`. No version number is released yet (no Gate accepted).

## PHASE_00 - Baseline & Architecture Lock (Gate-0 pending employer acceptance)

### Setup and kickoff
- Control kit, handoff v1.0 copy without `09_PRIVATE`, repo setup script, PHASE_00 start and handoff checksum
  intake (`reports/phase-00/KICKOFF_INTAKE.md`).
- Commits: `2ad2885f6f4db1f27767937c930b01f625c5aa5d`, `1cecd8119f958636b31a3b11d9a6219de1dc6c42`,
  `ebcbee55953b4b2e2be82051b8da98e35a28446a`; tooling (read-only employer analyst subagent)
  `2f9aff6bba66211237cfd37bfdccf480fb6099d2`.

### 00.1 Discovery & Contract
- Added: discovery docs (`docs/discovery/CONFLICTS.md`, `DATA_TABLE.md`, `STATE_TRANSITIONS.md`,
  `MOCK_UI_BINDING.md`, `RISKS.md`), OpenAPI draft (`docs/api/openapi-draft.yaml`), EOL-aware handoff verifier
  (`tools/verify_handoff.py`), decision packets DEC-044 / DEC-045; `status.py add-decision`.
- DEC-044 option B: original CRLF bytes of 13 handoff CSVs restored (employer-authorised exception).
- Implementation `57f4500e87bb936c1b8a622faaee5bb4a657e1d6`; report `cdc3e76e6a93465d639f9ab22796baa52ad755a5`;
  status `3a992ab6cf996cfdbbbd24c4983ac7bba061fa03`; decisions `f97040fab4b0ef86bb6a6f47b0bbeacb9feed63f`,
  `d35b3d8ae97bb528dd5e0630d5a065f2eae50bea`; review PASS `fd85969541ee2f25e167688652f1d82d59285f5c`.

### 00.2 Database
- Added: Django 5.2 project `backend/aleekhan`, app `platform_core`; migrations `0001_initial`,
  `0002_db_triggers`, `0003_seed_schema_meta` (audit append-only, outbox, idempotency, schema meta); `Code14Field`
  (format only); migration round-trip script `backend/scripts/db_roundtrip.sh`; `docs/db/README.md`.
- Fixed: REV-0003 (Windows drive paths in `verify_handoff.py`), REV-0004 (unused noqa).
- Implementation `7cf1f10066aec4c7cda8e6794eab43e748af644e`; report + DEC-045 option A
  `f694ff906025622ab5d0ee9791b5ea63510aed08`; status `a7428fdb16a23782d0cccfc55d98df9a60391ebe`; review PASS
  `013f6053dc87554aa3adfdc8fc9e32e17bba9941`.

### 00.3 Domain Engine
- Added: error catalogue (`docs/engine/ERROR_CODES.md`), unit of work (audit + outbox in one transaction),
  idempotency protocol, optimistic concurrency, outbox dispatcher, rule gate (`RULE_NOT_APPROVED`); Python 3.12.
- Fixed: REV-0005 (Python 3.12 target), REV-0006 (ruff lint scope; `control/` excluded explicitly), REV-0007 (platform-table exemption doc).
- Implementation `a6efb53cff09aefdacb50ef48e092ec0041ced6f`; report `9d3b6c6757403dfa859e4d00c0b1c344c8eb6226`;
  status `b31f1d5df1d938980689172f78e0de9f9dd8203c`; review PASS `588a57ffecdb6377d569894c11b35c63165ed762`.

### 00.4 Backend/API
- Added: DRF `/api/v1` platform endpoints (health live/ready, version, access-gate check), RFC 9457 problem
  errors, request id, throttling, cursor pagination, ETag, deny-by-default permissions, OpenAPI contract tests
  (`docs/api/API_RUNTIME.md`).
- Fixed: REV-0001 (OpenAPI security declaration), REV-0008..REV-0012.
- Implementation `bd332cbb85cf6269533c63c33a0e85f8489b90bd`; report `8f53ce580454b419b4531b677ce45ebbb5bd262d`;
  status `c32db1324fd886c5c371262d6ad3bc3836526456`; review PASS `e7b008f515bf29c731f989e9232119bd28129e27`.

### 00.5 UI
- Added: React/TypeScript smoke UI "system status" page on the real `/api/v1` endpoints, RTL design tokens
  (`docs/ui/DESIGN_TOKENS.md`), loading/error/empty/stale states, keyboard/a11y, Playwright E2E and screenshots
  1440/1180/768/390 (`reports/phase-00/step-5/screenshots/`).
- Implementation `fbd4218e8330226d3677583a054a42e9d1f20fff`; evidence `08086d87f079a7abcf8b97ac13bd6c666fbd4592`;
  status `485662685891decdfad1491f1f25b71868a90e2c`; review PASS `efb32ef5d60ba3c2bfef773d5e41ee5333d64de2`;
  employer UAT T-001 PASS `bb627c731563de0be8ec160c03e197e657e7aacd`.
- Brand: employer-supplied logo with provenance `2b2648f85f38f5cb982f1edcb7ddc0d322618a3b`; palette choice
  `83090340cba357ac80217519d5f0db65278f37bb`.

### 00.6 Integration
- Added: migrations `0004_integration`, `0005_integration_triggers`, `0006_seed_integration_sources`; read-only
  source registry, import batch + staging state machine (sha256 provenance, idempotent receive), outbox
  retries/backoff, consumer inbox + compensation, freshness, conflict queue (`docs/integration/README.md`);
  logo + logo-green palette in the UI.
- Fixed: REV-0501, REV-0503, REV-0504 (UI).
- Implementation `d7b444a8f2e907b8bb6c730faf15a5b455dc5e9e`; evidence `033dceac5293fb0326459c72de42ec0e825bdf13`;
  status `f186209e0f3e5959652fe57ad15ab0e4896e70fd`; review PASS `a5aae58cc4592c0d4ff4bf34ffc243543f643a43`;
  employer UAT T-002 PASS `7a20c8f9181cde0e7ea9dc3caffd2ff99ceb0b24`.

### 00.7 Security & Ops
- Added: GitHub Actions workflow `.github/workflows/ci.yml` + local runner `tools/ci_local.sh` (13 stages),
  secret scan (`tools/secret_scan.py`, tree + history), dependency scans (pip-audit, npm audit), SBOMs,
  deny-by-default route parity tests, Persian redaction, monotonic freshness, least-privilege DB roles
  (`ops/db/`), backup/restore drill (`ops/backup/drill.sh`), outbox monitoring (`outbox_status`), perf smoke,
  `docs/ops/*`, `docs/security/PHASE_00_SECURITY_CHECKLIST.md`, `docs/security/THREAT_MODEL_DELTA_00.6_00.7.md`.
- Fixed: REV-0601, REV-0602, REV-0603, REV-0015, REV-0016; REV-0502 mitigated for new logs.
- Decision: DEC-046 (repository stays public; DEC-041 data rule unchanged) resolved REV-0701.
- Implementation `5f3f5c3aca572a8d0575d8cd98444e78cc82a8e7`, fix `d6b6de96784d8d4d715e5978a2552c3531798faa`;
  evidence `128abdf25be4394d653328f8d2bda511934d1799`; status `b5397b6b5e00f9d5567de8e1b318b65e1b29041a`;
  review BLOCKED `b312dc8e9f62680d869bda3f8c0d00c344b51fe9`; DEC-046 `513153b4641d956d8f7ae3c4b15d5bb718625732`;
  re-review PASS `a45973c407208b66cc3ea4ced11f45a214f3eb31`.

### 00.8 Report & Review
- Commit `3c0ea1c03e0582d4a5e0d3e5e0fa76e151a659ed`; orchestrator CI 13/13 PASS (`reports/phase-00/step-8/logs/ci/summary.md`).
- Fixed REV-0702 [P2]: `tools/secret_scan.py` treats a value as a placeholder only when the WHOLE value is a
  placeholder form (`fullmatch`); regression tests in `tools/tests/test_secret_scan.py`.
- Fixed REV-0703 [P3]: threat model and security checklist updated for the public repository (DEC-046): T-67
  re-assessed, T-75..T-78 added, checklist 2.1 / 3.13.
- Fixed REV-0704 [P3]: GitHub Actions pinned to full commit SHAs with version comments
  (`reports/phase-00/step-8/logs/rev0704_action_shas.log`).
- Added: `CHANGELOG.md`, `docs/db/ERD.md` (all platform tables, migrations 0001-0006),
  `reports/phase-00/TRACE_MAP.md`, `reports/phase-00/PHASE_REPORT.md` + `PHASE_REPORT.json`, `docs/adr/ADR-001.md` (PROPOSED, for signature); CONFLICTS C-02/C-14/C-15 refreshed.
- No migration, no API or UI change in 00.8.

## PHASE_01 - Platform & Identity (started by the employer 2026-11-04)

### 01.1 Discovery & Contract
- Added: PHASE_01 sections in `docs/discovery/CONFLICTS.md` (C-26..C-46), `DATA_TABLE.md`, `STATE_TRANSITIONS.md`
  (section 4), `MOCK_UI_BINDING.md` (section 6: pages 36/39/40/42/46 + org tree), `RISKS.md` (R-21..R-35);
  `docs/security/PERMISSION_MATRIX_DRAFT.md` (PROPOSED v0.1); decision packets DEC-032, DEC-048..DEC-054 and
  addendum rows DEC-048..DEC-054.
- Changed: OpenAPI `0.4.0-draft` -> `0.5.0-draft` (additive: 97 planned operations, not served);
  `CONTRACT_VERSION`; contract tests compare route parity with implemented paths only; new
  `test_api_contract_planned.py`.
- No migration, no business code, no real data.
- Implementation: 89e5f0d.

### 01.2 Database
- Added: migrations `0007_phase01_platform_schema` (33 platform tables + 5 audit columns),
  `0008_phase01_db_guards` (btree_gist, 5 exclusion constraints, row-version / append-only / terminal-state /
  invariant triggers, parameter lookup functions), `0009_phase01_constraint_names` (conventional FK/unique/index
  names, exactly reversible), `0010_seed_phase01_catalogue` (permission matrix v1.0: 43 permissions, 11 roles,
  111 grants; unit types; upload allow-list; protected job types; 32 DEC-provenanced parameters). Model modules
  `platform_core/{identity,org,workflow,documents,params,jobs}`; `schema_common.py`.
- Decisions reflected: DEC-003, DEC-032, DEC-048..DEC-054 (APPROVED 2026-11-04). Permission matrix promoted to
  APPROVED v1.0 (`docs/security/PERMISSION_MATRIX_DRAFT.md`).
- Changed: OpenAPI `0.5.0-draft` -> `0.5.1-draft` (`CONTRACT_VERSION`): `x-aleekhan-decided-by` for approved
  decisions, enums aligned with the schema; `ops/db/grants.sql` + `roles_check.sh` (PHASE_01 privileges);
  `backend/scripts/db_roundtrip.sh` (extension check, partial rollback to 0006); `docs/db/ERD.md` sections 4-6,
  `DATA_TABLE.md`, `STATE_TRANSITIONS.md` (DECIDED markers, open questions Q-0101..Q-0106), `CONFLICTS.md`.
- Fixed: REV-0101 (MFA step-up on `rejectDocumentRevision` + regression test), REV-0103 (host name redaction in
  `tools/redact_paths.py`, junit xml redacted in place by `tools/ci_local.sh`, unit tests), REV-0104 (Notification
  retention labelled TECHNICAL DEFAULT in `DATA_TABLE.md`).
- Employer answers 2026-11-05 seeded as DEC-051 parameters: Q-0101 `session_limit_exceeded_action`,
  Q-0102 `session_operator_absolute_hours`, Q-0105 `password_history_reuse_depth`.
- Fixed (orchestrator verification): deadlock between concurrent role/position assignment inserts during the
  GiST exclusion check - per-user advisory transaction lock in the guard triggers.
- Rework after review REWORK (REV-0105..0107; migrations 0007/0008/0010 amended in place, nothing deployed):
  role lifecycle DRAFT->ACTIVE->RETIRED enforced in the DB (closes the re-DRAFT bypass); OWNER_POLICY values
  only by an owner_admin holder with reason (Q-0103); org changes never back-dated (60 s tolerance);
  upload limit 26 214 400 bytes (Q-0104); `platform_position.primary_capacity` with per-position locking
  (Q-0106). Employer answers 2026-11-05.
- No API endpoint, engine rule or UI added; no user, org or network data seeded.
- Implementation: PENDING.

### 01.3 Domain Engine
- Added (services only, no HTTP views): `platform_core/authz/policy.py` (RBAC over role assignments: GLOBAL /
  ORG_UNIT / ORG_UNIT_SUBTREE, own / own-unit, sensitivity caps, TECHNICAL != business approval, MFA step-up,
  field redaction, `RbacPolicy` adapter for 01.4), identity (`passwords`, `totp` RFC 6238, `crypto` AES-256-GCM,
  `network` zones, `sessions`, `auth` login/MFA/step-up/lockout/password change, `mfa` enrolment/recovery
  codes/admin reset, `users`, `roles`), `org/service.py`, workflow (`approvals` maker-checker, `tasks`,
  `instances` cancellation), documents (`filetypes` allow-list/magic/macro check, `scanner` ClamAV adapter + test
  double, `storage` encrypted, `service` quarantine/review/download/purge), `params` (`values`, `service`), jobs
  (`service`, `retention`), engine (`audit_chain`, `dbrules`, `commands`), `manage.py bootstrap_owner`.
- Changed: unit of work takes the audit chain lock first and fills `session_id`, `network_zone` and the hash
  chain; error catalogue + golden + OpenAPI `0.5.2-draft` (`INVALID_CREDENTIALS`, `NETWORK_POLICY_DENIED`,
  `PASSWORD_CHANGE_REQUIRED`, `SELF_APPROVAL_FORBIDDEN`, `PASSWORD_POLICY_VIOLATION`, `FILE_TYPE_NOT_ALLOWED`,
  `FILE_NOT_RELEASED`, `JOB_PROTECTED`); settings for CIDR lists, data keys, document storage, clamd.
- Migration `0011_phase01_engine`: REV-0109 (no back-dating of person-to-position assignments), session end
  reason `CONCURRENT_LIMIT` (Q-0101), housekeeping job types.
- New runtime dependency: `cryptography==50.0.2` (+ `cffi==2.0.0`, `pycparser==2.23`).
- Production API unchanged: `ACCESS_POLICY` stays deny-all until 01.4 wires authentication.
- Implementation: PENDING.
- Rework 1 (REV-0111..0115): operator document access limited to the current approved revision of documents
  linked to own tasks (object + list scoping); `scope_q` fixed for GLOBAL grants and sensitivity caps (fail
  closed); migration `0012_phase01_engine_rework` (`platform_param_value_at`, superseded future values never
  apply; login outcome `MFA_ENROLMENT_REQUIRED`); purge deletes bytes after commit.
- DEC-055 option B (employer 2026-11-05): owner bootstrap self-approval of the first holder of each
  business-approval role (`approvals.bootstrap_self_approve`), migration `0013_dec055_bootstrap_self_approval`
  (flag column, CHECKs, per-role-locked trigger, role-assignment guard).

### 01.4 Backend/API
- Added: HTTP endpoints for every PHASE_01 operation (`backend/platform_core/api/phase01/`: auth, me,
  admin-identity, org, workflow, audit, jobs, documents, parameters) over the 01.3 services; session-cookie
  authentication with CSRF (`api/session_auth.py`); login throttles per IP / per username
  (`ALEEKHAN_RATE_LOGIN_IP`, `ALEEKHAN_RATE_LOGIN_USER`, technical defaults); request-body validation mirrored
  from the OpenAPI schemas; keyset pagination with per-record scope check for task / approval inboxes.
- Changed: production `ACCESS_POLICY` = `RbacPolicy` (approved matrix v1.0) instead of `DenyAllPolicy`
  (deny by default kept: unknown action -> 403, out of scope -> 404); `ScopedPermission` enforces the MFA
  step-up of the permission; public operations = probes + `getLoginContext` / `login` (C-26).
- Contract `0.6.0-draft` (= `CONTRACT_VERSION`): planned markers removed (route parity covers all 88 paths);
  new `stepUpMfa` and `bootstrapSelfApproveRequest` (DEC-055); `UserCreated` (one-time password shown once,
  never stored for idempotent replay); `requestJobCancel` text aligned with STATE_TRANSITIONS 4.7 (QUEUED ->
  CANCELLED); nullable actor references for system/console rows; see `info.description` 0.6.0.
- Engine additions for contract operations without a 01.3 service: `users.update_user`, `roles.update_role`,
  `org.update_unit`, `update_position` (title / unit head), `documents.update_document` / `record_download`
  (audited download), `params.define_parameter` / `create_dynamic_field` / `update_dynamic_field`, task notes and
  `due_at`, `approvals.can_decide` / `makers_of`; `StoredResponse.secret_free_body`.
- Fixed: `mfa.reset_factors` wrote no outbox event for a user without factors/sessions (500); REV-0118 (test
  assertion that was always true for the download branch).
- No migration.

### 01.5 UI
- Added (frontend): PHASE_01 shell bound to the real API - login ceremony (password -> MFA code -> forced
  password change -> TOTP enrolment with 10 recovery codes shown once), session-ended handling (401 -> login
  with notice), logout, role-aware navigation from `GET /me/permissions` (cosmetic; server re-checks), MFA
  step-up dialog on `401 MFA_REQUIRED` (one retry with a new Idempotency-Key), hash router; pages 46 (users with
  server-generated one-time password shown once, lock/unlock, reset password/MFA, sessions, effective
  permissions; roles; role assignments with explicit self-assignment and DEC-032 pending notice), org tree
  (WAI-ARIA tree, keyboard, create unit / unit-head position / holder from now on only), 39 (approval inbox,
  approve / reject / withdraw with reason, DEC-055 bootstrap approval; task inbox start / complete / block /
  unblock), 40 (documents, quarantine upload with parent check, download only CLEAN, submit / approve / reject),
  42 (parameters by classification, OWNER_POLICY one step, RULE_NOT_APPROVED shown with its DEC id), 36 (health
  counters, audit integrity, job definitions, safe cancel; protected jobs not cancellable); my sessions.
  Loading / error (code + request id) / forbidden / empty / stale states on every query; RTL; responsive
  1440/1180/768/390. Vitest unit tests (`src/phase01.test.tsx`) and Playwright E2E against the real backend
  (`e2e/phase01.spec.ts`, console-bootstrapped synthetic owner in `e2e/global-setup.ts`).
- DEC-056 (APPROVED 2026-11-06): permission matrix v1.1 - `owner_admin` holds `platform.workflow.approval.read`
  and `platform.workflow.approval.decide`; engine + DB guard exception for exactly that pair; maker != checker
  unchanged; owner decisions audited with `scope.via_role`. Migration `0014_dec056_owner_approval_rights`
  (reversible; also fixes `requires_second_approval` at grant time and exempts the console bootstrap of the
  owner from the DEC-032 second approval).
- Fixed: REV-0120 (upload parent check under the document row lock), REV-0121 (withdraw reason stored in the
  closing note and audit), REV-0122 (publish note -> audit reason), REV-0123 (CSRF token rotated on login and
  MFA verify).
- Contract `0.6.1-draft`: optional `ParameterValueRevision.row_version` (If-Match of `publishParameterValue`).
- Dev: Vite proxy keeps the browser Host (`changeOrigin: false`) so the CSRF Origin check matches; `/` is the
  login / dashboard, the PHASE_00 smoke page moved to `#/status`.

### 01.6 Integration
- Added: event catalogue `backend/platform_core/engine/events.py` (52 platform event types of PHASE_00 + PHASE_01:
  producer module, aggregate type, versions, payload JSON Schema, sensitivity S1; golden
  `tests/golden/event_catalogue.golden.json`; `docs/integration/EVENT_CATALOGUE.md`). `UnitOfWork.emit` enforces
  it (unknown type / wrong aggregate / non-current version / payload mismatch -> `EngineContractError`, write rolled
  back) and stamps provenance (`producer`, `build_commit`, `schema_migration`).
- Consumer pipeline: catalogue admission in `RegistryPublisher` (accepts N and N-1 with upcast; older / invalid ->
  dead letter at once via `PublishError(permanent=True)`; newer -> backoff), per-aggregate delivery order in
  `claim_batch` (`OutboxPolicy.per_aggregate_order`), integration freshness (`ops.monitoring.integration_health`:
  lag, stale flag, blocked aggregates, held events, open conflicts, open compensations) in `outbox_status`,
  `GET /admin/health` (`integration`, contract `0.6.2-draft`, additive) and page 36.
- Migrations: `0015_dec056_matrix_v12` (DEC-056 extension 2026-11-10: owner_admin `document.approve` +
  `config.parameter.publish`, DB guard exception widened to exactly three pairs; reversible),
  `0016_outbox_provenance_and_order` (three provenance columns + format CHECKs + partial index; reversible).
- DEC-056 extension (matrix v1.2, REV-0125): the owner decides document revisions and BUSINESS_RULE publish
  directly; TECHNICAL values still need a config approver; never his own request / upload / proposal. HTTP + E2E
  coverage of the owner deciding another person's request (REV-0128); UAT steps added.
- Fixed: REV-0126 (page 46 subtitle reflects DEC-056).


### 01.7 Security & Ops
- Security & ops evidence: `docs/security/PHASE_01_SECURITY_CHECKLIST.md` (status per item with evidence;
  signature rows open), secret scan (tree + history), dependency scan (pip-audit / npm audit), logs in
  `reports/phase-01/step-7/logs/`.
- Privacy / permission tests `tests/test_phase01_step7_privacy.py`: every role x every PHASE_01 operation the
  matrix does not grant -> 403; every MFA-flagged operation -> 401 `MFA_REQUIRED` without a fresh step-up;
  document sensitivity caps (EMP S1, MGR/MGT S2) -> 404 above the cap; no never-exposed field or value in any GET
  response; no plaintext password / one-time password / TOTP secret / OTP / recovery code / session token in any
  row of any `platform_*` table or any log record after a full ceremony.
- Perf (`pytest -m perf`, `tests/test_perf_phase01.py`): inboxes at the 1000-row per-record check limit, audit
  chain lock throughput with 1 / 4 / 8 writers, outbox dispatch lag with 1 / 4 dispatchers (TECHNICAL DEFAULT
  budgets). Fix found by it: `authz.policy.request_cache` (grants / scope facts read once per list request).
- Ops: housekeeping job monitoring (`ops.monitoring.housekeeping_health`, `manage.py job_status`,
  `manage.py run_housekeeping`, page 36 block, `GET /admin/health` `jobs.housekeeping`, contract
  `0.6.3-draft`, additive); orphan upload cleanup job `document_orphan_cleanup` (audited, idempotent, 24 h
  grace); upload size limit before parsing (`api/upload_limit.py`, REV-0124) + proxy limits
  (`docs/ops/DEPLOYMENT_LIMITS.md`); backup drill covers PHASE_01 tables, migrations 0011-0018 and the audit
  chain; rollback rehearsal to 0010 (`ops/backup/rollback_rehearsal.sh`, docs/ops/ROLLBACK.md section 3a).
- Migrations: `0017_dec056_matrix_v13` (owner_admin `document.read` + `document.download`, not business
  approval, guard unchanged; reversible), `0018_outbox_discard_and_orphan_job` (delivery state DISCARDED +
  `discarded_at` + CHECK + ordering index without settled rows; orphan cleanup job type; reversible).
- DEC-056 extension 2 (matrix v1.3): the owner opens and downloads the documents he decides (service, HTTP, E2E,
  UAT step 3.11).
- Fixed: REV-0129 (owner-only discard of dead letters, console, audited, reason required), REV-0130
  (`blocked_aggregates` = aggregates with events waiting behind a dead letter), REV-0131 (page 36 in Farsi), the
  Parameters page hides the publish button for the owner on TECHNICAL values.

### 01.8 Report & Review (this step; commit SHA added by the orchestrator when committed)
- Phase report set: `reports/phase-01/PHASE_REPORT.md` + `.json`, `reports/phase-01/TRACE_MAP.md`,
  `reports/phase-01/step-8/REPORT.md` + `.json`; full local CI evidence on the final tree in
  `reports/phase-01/step-8/logs/ci/`; all PHASE_01 screenshots regenerated from the final tree at
  1440/1180/768/390 in `reports/phase-01/step-8/screenshots/` (REV-0127, REV-0135).
- Fixed REV-0132 [P2]: direct unit tests of `authz.policy.request_cache`
  (`tests/test_authz_request_cache.py`: nothing cached outside the block, memo gone after the block and after an
  exception, nested blocks, two users in one block, a revoked / new grant seen by the next request).
- REV-0133 (employer decision 2026-11-10): `manage.py outbox_dead_letter replay` is allowed for an ACTIVE
  `owner_admin` or `it_ops` holder; `discard` stays `owner_admin` only; both need a reason and are audited
  (`ops/dead_letters.ALLOWED_ROLES`; `--user`, `--owner` kept as alias); tests for both roles and refusal of
  others; docs (integration README, JOB_MONITORING, STATE_TRANSITIONS, security checklist 4.5).
- REV-0134: `tools/ci_local.sh` logs start with the stage's exact commands and end with `# exit code: N`;
  `summary.md` has an exit-code column, the worktree state and the git tree id of every code directory as
  tested. The contract stage validates `docs/api/openapi-draft.yaml`; the perf stage runs the PHASE_01 perf
  suite too; the ops stage runs the rollback rehearsal; `makemigrations --check` uses `aleekhan.settings_test`;
  E2E artefact folders can be redirected (`CI_E2E_*`). `docs/ops/CI.md` updated.
- `docs/db/ERD.md`: migration rows 0014-0018.

## PHASE_02 - Order & Product Identity (started by the employer 2026-11-11)

### 02.1 Discovery & Contract (commit SHA added by the orchestrator when committed)
- Discovery: `docs/discovery/CONFLICTS.md` C-47..C-76; `DATA_TABLE.md` PHASE_02 logical model (identity +
  commercial tables, source provenance block, invariants INV-02-01..09); `STATE_TRANSITIONS.md` section 5 (order,
  line, code rule revision, serial, change request, product code registry; blocked guards name their decision);
  `MOCK_UI_BINDING.md` section 7 (pages 1, 2, 4, 29, 33); `RISKS.md` R-36..R-47.
- Decision packets (Persian, for the orchestrator to move to `control/decisions/`): DEC-005, DEC-006, DEC-027 and
  new DEC-057 (PHASE_02 permission matrix, P0), DEC-058 (customer/order master data, P1), DEC-059 (order changes
  after confirmation, P0), DEC-060 (real-looking customer names in `handoff/`, P1) in `control/decisions/`.
- Contract `docs/api/openapi-draft.yaml` 0.7.0-draft: 63 PLANNED operations on 48 paths (`/identity/...`,
  `/commercial/...`, step 02.4, not routed), 14 blocked by DEC-005/006/057/059; four planned error codes;
  `side_effect_free_operations`; additive (all previous paths/components unchanged). `CONTRACT_VERSION` follows.
- Tests: new `test_api_contract_planned_phase02.py`; `test_api_contract_planned.py` allows planned PHASE_02 paths
  only; the permission-seed test compares implemented operations only.
- No migration, no business code, no real data; no private source read (not available on this machine).

### 02.2 Database (commit SHA added by the orchestrator when committed)
- Migrations `0019_phase02_identity_commercial_schema` (21 tables `identity_*` / `commercial_*`),
  `0020_phase02_db_guards` (triggers, 6 deferred constraint triggers, FK/index names), `0021_phase02_seed_catalogue`
  (units, order types, external reference types, serial counter at 63001), `0022_dec057_matrix_v20` (DEC-057 matrix
  v2.0: 22 permissions, 5 BUSINESS roles, owner exception six pairs). All reversible; round trip + schema diff.
- Engine primitive `platform_core/product_identity/serials.py` (gapless allocation under the counter row lock, snapshot
  v1, audit, outbox `identity.serial.allocated`, idempotent by allocation key); event catalogue + golden updated;
  `authz.policy.OWNER_BA_ACTIONS` = six pairs.
- REV-0201: Identity owns serial + snapshot, the line holds the UNIQUE FK (ERD 7.1); REV-0202: blocked-by markers
  must exist in the decision register; REV-0203: untagged change-request rules marked PROPOSED and not enforced.
- Tests: `test_phase02_schema.py`, `test_phase02_serial_allocation.py` (ID-01/02/03/04 against PostgreSQL),
  updated PHASE_01 matrix/table tests; `ops/db/grants.sql` + `roles_check.sh` PHASE_02 privileges;
  `docs/security/PERMISSION_MATRIX_DRAFT.md` v2.0 (section 7); `docs/db/ERD.md` section 7.
- No real type, category, code, customer or serial in the repository (synthetic test data only).


### 02.3 Domain Engine (commit SHA added by the orchestrator when committed)
- Engine (no HTTP): `product_identity/coderule.py` (DEC-005 code rule as pure functions, `RULE_SPEC_V1`),
  `product_identity/codes.py` (code rule revision lifecycle with >= 20 golden cases per family, maker != checker,
  fresh MFA; side-effect-free preview; issue RESERVED / ERP_PENDING only under an ACTIVE revision, else
  `RULE_NOT_APPROVED`; ERP match by the import), `product_identity/master.py` (customers, brands, products with
  max + 1 / buckle + width numbers, styles with count + 1 numbers, style revisions), `commercial/orders.py` (draft,
  validate, confirm with one serial per line in the same unit of work, release; PII masking + read audit; PO
  duplicate warning), `commercial/changes.py` (7 change kinds, decide / planning approval / apply, new order
  version + serial snapshots), `product_identity/refusals.py` (stable `errors[].code` reasons, golden),
  `product_identity/usecase.py` (shared helpers, technical number sequences).
- REV-0220: `allocate_serial` refuses the same key with another payload (`IDEMPOTENCY_KEY_REUSED` /
  `IDEMPOTENCY_PAYLOAD_MISMATCH`); `add_snapshot`, `cancel_serial` added.
- Migrations `0023_phase02_engine` (cancel from ON_HOLD when the stored state is CONFIRMED - DEC-059 amendment,
  REV-0222; `ck_commercial_cr_planner_not_decider`; number sequences) and `0024_dec057_dec059_matrix_v21` (matrix
  v2.1: owner PHASE_02 reads, `commercial.change.planning_approve` for planning_officer). Both reversible.
- Events: 36 new catalogued types (`identity.*`, `commercial.*`); golden + `docs/integration/EVENT_CATALOGUE.md`.
- Tests: `test_phase02_coderule.py` (unit + hypothesis), `test_phase02_golden_harness.py` (real data via
  `ALEEKHAN_GOLDEN_FILE` outside the repo, skipped without it; synthetic self-test), `test_phase02_engine_identity.py`,
  `test_phase02_engine_orders.py`, `test_phase02_engine_changes.py`, `test_phase02_engine_race.py`; PHASE_01/02
  matrix tests moved to v2.1; `roles_check.sh` sequence checks.
- Docs: STATE_TRANSITIONS 5.10, DATA_TABLE "02.3 result" (number format PROPOSED), ERD 7.5, PERMISSION_MATRIX v2.1,
  ERROR_CODES "PHASE_02 refusal reasons". OpenAPI unchanged (02.4).
- DEC-005 amendment 2026-11-13 (style `0000` legacy only): `coderule.validate_legacy_code` /
  `parse_code(..., legacy=True)` accept it with exact segments; `build_code` / issue refuse it
  (`STYLE_0000_LEGACY_ONLY`); golden harness and DB golden check count such cases in their family as legacy-only
  (build refused + legacy parse exact) and report them separately; migration 0023 extended
  (`ck_identity_style_no_fmt` allows 0000 for IMP/LEG only; `ck_identity_product_code_sys_no_style_0000`).

### 02.4 Backend/API (commit SHA added by the orchestrator when committed)
- API: all 66 PHASE_02 operations served (`backend/platform_core/api/phase02/`: `bodies.py`, `serializers.py`,
  `identity_views.py`, `commercial_views.py`, `urls.py`) over the 02.3 use cases - session cookie, permission per
  action (DEC-057 matrix v2.1), GLOBAL record scope (404), fresh MFA on issue / code-rule decisions / confirm /
  decide / planning decision, rate limits, ETag + If-Match, cursor pagination, request id, Idempotency-Key on every
  mutation (except the two side-effect free POSTs), refusal reasons in `errors[].code`.
- Contract `0.8.0-draft` (`docs/api/openapi-draft.yaml`): planned markers removed, `x-aleekhan-blocked-by`
  (DEC-005/006/057/059) replaced by `x-aleekhan-decided-by`; added `updateCustomerBrand`,
  `addCodeRuleGoldenCases`, `decidePlanningChangeRequest`; `SerialNumber` pattern `^[1-9][0-9]*$`;
  `TechnicalNumber`; PHASE_02 schemas aligned with the engine (enums without PAUSED / SERIAL_ALLOCATED, type /
  category levels, `Style.category_id`, masked `customer_representative_name`, historical match fields, change
  request items); `phase02_refusal_reasons`; planned error codes dropped (reasons instead). `/version` reports
  0.8.0-draft. API_RUNTIME section 14.
- Employer amendments of 2026-11-14: numbers `CU-`/`SO-`/`CR-` + Jalali year (Asia/Tehran) + 6+ digits, restart
  every year (`product_identity/jalali.py`, `platform_number_counter`); style collision -> first free number
  after count + 1, audited (REV-0232; `coderule.first_free_style_no`, `STYLE_NO_COLLISION` removed); planning
  may approve or reject a due-date change (`changes.planning_decide_change_request`, reject closes REJECTED);
  held order: only resume or cancel (decided, unchanged).
- Golden (REV-0230 / REV-0231): harness counts `c77_checked` / `c77_disagree` (any disagreement fails),
  `belt_checked` per belt family (>= 20, belt families inferred or declared with `ALEEKHAN_GOLDEN_BELT_FAMILIES`),
  `legacy_disputed` reported only; `codes.golden_report` refuses belt-type cases without both segments
  (`BELT_SEGMENTS_REQUIRED`) and a C-77 disagreement.
- Engine: external references (`product_identity/external.py`), `remove_line` / `activate_rule_revision`
  reasons, snapshot image `order_version` = the version it represents; refusal reasons `EXTERNAL_REF_EXISTS`,
  `SERIAL_ALLOCATED_AT_CONFIRM`, `RULE_REVISION_NOT_ACTIVE`; events `commercial.change_request.planning_rejected`,
  `identity.external_ref.created` / `.ended`.
- Migration `0025_phase02_api_numbers` (reversible): number counter + forward-only guard (replaces the 0023
  sequences), planning-reject columns + CHECKs + one more change-request lifecycle edge. `grants.sql` /
  `roles_check.sh` updated.
- Tests: `test_api_phase02_contract.py` (replaces `test_api_contract_planned_phase02.py`), `test_api_phase02_flows.py`,
  `test_phase02_jalali.py`, harness / engine additions.
