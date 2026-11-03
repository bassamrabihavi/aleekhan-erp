# Security baseline — mandatory all phases

**Baseline:** OWASP ASVS 5.0.0 for web/API review (https://asvs.owasp.org/), CWE Top 25, threat modeling and test-driven authorization. Controls listed below are *required requirements*; **not a claim of certification**.

## 1. Identity, Authentication, Authorization
- MFA mandatory for system administrators, HR/payroll, finance, commercial customer approvals, QC release/override, warehouse inventory adjustment, release/production deployment, high-impact job kill. Consider company SSO (Gate-0 decision). Rate limiting, session expiration, password policies and brute-force protections.
- Deny by default and per-record scope (department/customer/line/warehouse/site) + per-action + per-field. Permission checks enforced on backend and query serialization, not UI hide only. Explicit maker-checker separation for salary, grade, source override, price revisions and asset receipt.
- Emergency access is time-boxed, justification-required, independently audited and revocable; technical admin NEVER implicitly approves business workflow.

## 2. Confidentiality & Data
- Secret storage via managed secret store/environment; no passwords/private keys in Git, log, screenshot, report, sample ZIP or AI prompts; rotation policy.
- HTTPS/TLS on internal network, DB and workers on private segment, encrypted backups and sensitive object storage; restrict ingress/egress to approved endpoints.
- PII: customer phone/address, employees, wages, price, bank-like data via classification with retention; blind snapshots for testing; no full PII in logs/AI.
- **Factory raw sources are private:** legacy XLSM and `.py` may execute unwanted code or reveal internal info; default quarantine; no automatic macros. No cloud AI upload without employer consent. Files scanned for malware and formula injection before import/export.
- Signed/hashed files and revision history; SHA-256 file hash; field-level audit for sensitive changes; logs append-only under restricted roles, with periodic integrity check.

## 3. Application/API
- Prevent SQL injection, XSS, template injection, unsafe object deserialization, CSRF, SSRF, path traversal, insecure file upload, CSV formula injection and IDOR/BOLA.
- Content security policy; escaping UI; model data sanitize; external reference URLs allowlist; file parser sandbox (CPU/memory/time budgets, no network, read-only mount, ZIP bomb limits).
- OpenAPI-contract fuzz tests; pagination/max-size, rate limits, explicit error codes, idempotency on mutating actions, optimistic concurrency and DB constraints.
- Supply-chain SCA/SBOM, signed build artifacts and pinned versions; dependency scan and patch process. Container non-root, restricted filesystem/NET, image scan.
- On AI assistance: no automatic business write, no unrestricted SQL execution, document retrieval permission filter, prompt injection tests, citation to source, human approval for material decisions.

## 4. Data integrity, reliability & operations
- Snapshot vs official docs vs reservation clear separation; ledger atomic + audit + outbox, no double stock allocation; backup consistency, restore proof, job checkpoint/cancel safe states; forced kill prohibited for critical transactions until safe recovery path implemented.
- Production/staging/test isolation with synthetic or anonymized samples; least privileged service accounts; audit retention rule and backup RPO/RTO formally approved before production.
- Recording compensation actions when a cross-system process fails; duplicate webhook/import handling; visibility of stale data timestamps.

## 5. Security Gate evidences
Per phase attach: Threat changes, RBAC/ABAC tests (at least allow/deny across distinct users), SAST/SCA results, secret-scan, data-flow and sensitive-field review, API fuzz/IDOR tests, migration/backup/rollback evidence, sample logs redacted, fixed severity table; **Critical/P0 fail => BLOCKED**. For high-impact features, request focused manual penetration test prior to Pilot.
