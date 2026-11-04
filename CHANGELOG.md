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
- Implementation: PENDING (orchestrator fills the SHA after commit).
