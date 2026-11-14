# Data table — core entities by owning module (PHASE_00 / 00.1)

Status: DRAFT logical model. Source: `handoff/02_DOMAIN_CONTRACTS/DOMAIN_ENTITY_CATALOG.md` (PROPOSED), `ARCHITECTURE_OVERVIEW_FA.md`, `SOURCE_MAPPING_AND_IMPORT.md`, `STATE_EVENT_AND_API_CONTRACT.md`, `time_capacity_v1/04_DOMAIN_MODEL_API_EVENTS_FA.md`, `UI_PAGE_PHASE_MAP.csv`/`PHASE_INDEX.csv`. Physical DDL is decided per phase in step xx.2; nothing here is a migration.

## Conventions (all entities)
- PK: internal UUID (non-guessable, PHASE_00 proposal; `bigint` surrogate allowed internally only if never exposed). Business codes are never PKs.
- 14-digit Rahkaran codes: `varchar(14)` + `CHECK (code ~ '^[0-9]{14}$')` + explicit namespace column/table (`product_code` and `die_code` are separate namespaces, no shared sequence). Leading zeros preserved; never numeric type. *Format* validation from PHASE_02; *issuing* new codes BLOCKED until DEC-005 (product) / DEC-008 (die).
- `cliche_code`: free alphanumeric `varchar` (e.g. DOR51); NOT a 14-digit code.
- `serial_number`: separate identity; format BLOCKED by DEC-006.
- Quantities and money: `numeric(p,s)` + UOM; never float. UOM conversion only via approved table (DEC-017).
- Time: `timestamptz` in UTC; Jalali only in UI (Asia/Tehran). Jalali strings never the source of truth.
- Every owned table: `created_at/by`, `updated_at/by`, `row_version` (ETag), soft-delete or reversal events instead of hard delete for ledger-like data; writes produce `AuditEvent` + `OutboxEvent` in the same transaction.
- Provenance: imported rows carry `source_file_id` + `raw_record_id` (+ `transform_rule_version`).

Sensitivity classes (proposed, to be confirmed in 00.7 threat model):
`S0` public-internal (no harm) · `S1` internal operational · `S2` confidential business (prices, customer identity, supplier terms, codes/designs) · `S3` restricted personal/financial (salary, PII contact, performance per person) · `SEC` secrets/credentials (never in DB plain, never in logs).

Provenance: `SYS` created in platform · `IMP` imported from Excel/ERP snapshot (read-only external evidence) · `DXF` derived by parser · `EXT` external reference only.

## Platform (Admin/Platform) — PHASE_00 skeleton, PHASE_01 full
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes / invariants |
|---|---|---|---|---|---|
| User | id, username (unique, citext), display_name, is_active, mfa_enrolled, network_policy (internal_only/any) | SYS (created only by owner/admin, DEC-003) | S3 (credentials hashes = SEC) | 01 | no AD/LDAP/SSO; admin ≠ business approval |
| OrgUnit / Position / ReportsTo | id, parent_id, name, position_id, user_id, valid_from/to | SYS | S1 | 01 | DEC-043; tree acyclic (check in engine); effect on approvals settled in 01.1 |
| Role, Permission, Scope, RoleAssignment | role code, action id, scope (department/customer/line/warehouse/site), assigned_by, reason | SYS | S1 | 01 | deny-by-default; self-assignment by owner audited (CLAUDE.md DEC-003 note) |
| ApprovalTask | id, resource_type/id, resource_revision, action, maker_id, checker_id, state | SYS | S1–S3 by resource | 01 | maker ≠ checker for material actions (DEC-032 PROPOSED) |
| AuditEvent | id, occurred_at (UTC), actor_id, request_id, action, resource, scope, reason, before/after (redacted) | SYS | S2 (append-only) | **00** skeleton | immutable; integrity check; retention DEC-032 |
| OutboxEvent | event_id uuid, aggregate_type/id, aggregate_version, occurred_at, actor, correlation_id, causation_id, schema_version, payload, delivery_status | SYS | S1 (no salary/password/PII in payload) | **00** skeleton | unique(event_id); consumers idempotent; DLQ visible |
| IdempotencyRecord | key uuid, actor_id, endpoint, request_hash, response, created_at, expires_at | SYS | S1 | **00** skeleton | unique(actor_id, key) |
| ImportBatch / SourceFile / RawRecord / DataConflict | SourceFile(id, original_name, sha256, size, actor, received_utc, source_type, parse_status, claimed_origin); RawRecord(workbook, sheet, row, cell_ref, raw_value, cell_type, formula_text, cached_value, normalized_value, transform_rule_version, error_code) | IMP | S2 (S3 if sheet holds salary/contact — those are not read, DEC-028) | 01 (framework) / 06, 12 (use) | binary original immutable (object storage + SHA-256); staging separate from official |
| Job | id, type, state, checkpoint, cancel_requested_by, protected (no force kill) | SYS | S1 | 01 / 11 | DEC-024 |
| Document | id, uri, sha256, revision, approved_revision immutable | SYS/IMP | S2 | 01 / 12 | |
| DynamicFieldDefinition | system_key, type, validity | SYS | S1 | 01 / 11 | typed, versioned |
| Notification | id, user_id, channel, payload ref | SYS | S1 | 01 | |

## Identity / Product Registry — PHASE_02
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes |
|---|---|---|---|---|---|
| Customer | id, name, external_ids (namespaced) | SYS/IMP | S2 (contact = S3) | 02 | customer contact not read from legacy (DEC-028) |
| ProductFamily | code BAG/SHOE/BELT/POCKET | SYS | S1 | 02 | |
| Product, Style, Revision | id, family, size, color, released_version | SYS/IMP | S2 | 02 | |
| ProductCode | code varchar(14) + namespace `product_code` | IMP (Planning NOrder/Codding/Sorce) | S2 | 02 | validate format only; issue BLOCKED DEC-005 |
| Serial | id, serial_number (format BLOCKED DEC-006), customer_po_line_id (unique), product/style/revision snapshot | SYS | S2 | 02 | race-safe transactional sequence, idempotent (ID-02/04); no MAX()+1 |
| SerialSnapshot | serial_id, version, snapshot json, created_at | SYS | S2 | 02 | non-destructive |
| ExternalIdentity | system, namespace, external_id, internal_id | IMP | S2 | 02 | not assumed unique across systems |

## Commercial — PHASE_02 (pricing PHASE_10)
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes |
|---|---|---|---|---|---|
| Inquiry, QuoteVersion | id, customer, version | SYS | S2 (price) | 02 / 10 | |
| CustomerPO, CustomerPOLine | po_id, external_po_number (not globally unique), line_no, product/style, qty+UOM, promised_date | SYS | S2 | 02 | header→many lines; line↔serial (DEC-006) |
| OrderChange | id, po_line, change, impact | SYS | S2 | 02 / 05 | amendments, never in-place history rewrite |
| CustomerArtworkApproval | artwork revision, approver (Commercial) | SYS | S2 | 03 | approval by Commercial only |

## Engineering — PHASE_03
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes |
|---|---|---|---|---|---|
| DXFArtifact, PatternRevision | id, sha256, revision, parser_version | DXF/IMP | S2 | 03 | revision selection rule DEC-029 |
| DieCandidate | id, dxf_id, entity handles, raw/normalized text, bbox, confidence, warnings | DXF | S2 | 03 | parser never issues codes (ENG-02) |
| DieRegistry, DieRevision | die_code varchar(14) namespace `die_code`, description (from tracker), revision | IMP (tracker) | S2 | 03 | code via tracker only; DEC-007/008 |
| Cliche, ClicheApproval | cliche_code (alphanumeric), brand, size, revision | IMP | S2 | 03 | conflicting dims → manual (ENG-04, DEC-009) |
| Jig, SkivingPlan, ProductTechnicalPackage | revision refs | SYS | S2 | 03 | release immutable (ENG-03) |

## BOM / OPC / Time — PHASE_04
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes |
|---|---|---|---|---|---|
| BOMRevision, BOMItem, MaterialRole, ConsumptionRule, WasteRule | rows unbounded; unit, color, print, finish, grade | SYS/IMP | S2 | 04 | DEC-031 |
| OPCRoute, OperationDefinition, OperationDependency | acyclic (OPC-01) | SYS | S2 | 04 | shoe route DEC-010 |
| TimeStudyPlan, RawObservation, StandardTimeRevision | person-min / machine-min / wait separately (TIME-02) | SYS | S2 (per-person = S3) | 04 | approval DEC-011; immutable observations |

## Planning — PHASE_05
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes |
|---|---|---|---|---|---|
| Program (Season/Month/Week), Demand, Forecast, Commit | dedup forecast→commit (PLAN-01) | SYS | S2 | 05 | |
| CapacityScenario, ScheduleRevision, ResourceAllocation, FastTrackQueue | scenario snapshot, approvals | SYS | S2 | 05 | solver output not a promise; DEC-012/013/014/034 |

## Warehouse / Supply — PHASE_06
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes |
|---|---|---|---|---|---|
| MaterialMaster, UOMConversion | material code (namespaced), conversions | IMP/SYS | S2 | 06 | DEC-017 |
| SourceInventorySnapshot | as_of, effective_at, freshness, source_reliability, qty | IMP (ListData) | S2 | 06 | read-only evidence; ≠ available (DEC-015/016) |
| Lot, Location, Hold, Reservation, Issue, Receipt, Return, ShortageGAP, StockLedger | ledger: type, qty numeric, UOM, lot, location, hold, owner serial/batch, external_ref, txn id, reason | SYS | S2 | 06 | no negative, no double reservation (WH-02/03) |
| PurchaseRequisition, Supplier, PO, ETAHistory, DieFabricationRequest | | SYS | S2 (supplier terms) | 06 | Supply never posts receipt (WH-04); DEC-033 |

## Production — PHASE_07
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes |
|---|---|---|---|---|---|
| WorkOrder, WorkBatch, Bundle, StationActivity, QuantityLedger | event_id unique, qty in/out | SYS | S1 (per-operator = S3) | 07 | out ≤ in (WIP-01); offline DEC-018 |
| OperatorShift, Downtime, Scrap, Rework | | SYS | S1/S3 | 07 | no double credit (WIP-03) |

## Quality — PHASE_08
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes |
|---|---|---|---|---|---|
| IncomingInspection, QualitySpecVersion, Defect, NCR, CAPA, ProductInspection, QCGrade, DeviationPermit | required_grade ≠ actual_grade | SYS | S2 | 08 | grade table DEC-019 |

## FG / Dispatch — PHASE_09
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes |
|---|---|---|---|---|---|
| FGReceipt, FGCount, Pick, Delivery, DeliveryLine, ProofOfDelivery, ReturnAuthorization | partial deliveries | SYS | S2 | 09 | serial close rule DEC-020 (FG-01) |

## HR / Assets / Cost — PHASE_10 (assets 05/07)
| Entity | Key fields | Provenance | Sensitivity | Phase | Notes |
|---|---|---|---|---|---|
| Employee, SkillCertification, Assignment, Leave | | SYS | S3 | 10 (skills used 05) | |
| PayrollConfidential | field-level access, maker-checker | SYS | S3 | 10 | DEC-022; never in events/logs/AI |
| Machine, Maintenance, Calibration | | SYS | S1 | 05 / 07 | page 51 |
| CostRateRevision, StandardCost, ActualCost, MetricDefinition | versioned | SYS | S2/S3 | 10 | DEC-021 |

## PHASE_00 physical scope (for step 00.2)
Only platform skeleton tables are candidates in PHASE_00: `AuditEvent`, `OutboxEvent`, `IdempotencyRecord` (+ Django built-ins). No business entity and no real data are created in PHASE_00 (PHASE_00.md "NO business writes").

# PHASE_01 / 01.1 — Platform & Identity entities (detail for step 01.2)

Status: DRAFT logical model, refines the "Platform" table above. Sources: `PHASE_01.md` (domain: User, Role,
Scope, Permission, MFA, Audit, Outbox, Job, Task, Document, DynamicField draft, encrypted file refs),
`DOMAIN_ENTITY_CATALOG.md` Platform row, catalog `DATA_MODEL.md` §36/39/40/42/46 (DRAFT), DEC-003/042/043,
`docs/api/openapi-draft.yaml` 0.5.0 schemas. Physical DDL, indexes and migration ids are decided in 01.2; no
migration is created in 01.1.

Conventions added for PHASE_01 (all entities below):
- PK `uuid` (exposed) unless noted; `row_version` integer ≥ 1 (ETag); `created_at/by`, `updated_at/by`; every
  write = state + `AuditEvent` + `OutboxEvent` in one transaction (00.3 unit of work).
- No hard delete of identity, role, assignment, org or document rows: status/validity end instead (history
  needed for "who could do what, when"). Effective-dated rows use `valid_from`/`valid_to` (UTC, half-open
  `[from, to)`) with an exclusion/overlap check per key.
- Provenance column `provenance` ∈ `SYS` (created in the platform) / `SEED_SYNTHETIC` (dev/test/staging seed,
  never in production). PHASE_01 has no `IMP` platform data.
- Retention column: **KEEP** = no deletion while the system lives (history); **DEC-032** = retention decided
  by DEC-032 (APPROVED 2026-11-04: business and access audit never deleted, yearly archive; login events 2
  years; other DEC-032 rows below = KEEP); **TECH** = technical default stated, ops-confirmable,
  not a business rule.

| Entity | Key fields | Constraints / invariants | Prov. | Sens. | Retention |
|---|---|---|---|---|---|
| User | user_id, username (citext, unique), display_name, status (CREATED/ACTIVE/LOCKED/DISABLED), account_kind (PERSON/OPERATOR_TERMINAL/SERVICE), network_policy (INTERNAL_ONLY/ANY_WITH_MFA_OUTSIDE), mfa_enrolled, last_login_at, failed_login_count, locked_until | username regex `^[a-z0-9][a-z0-9._-]{2,63}$`; created only through `createUser` by a holder of `platform.identity.user.create` (DEC-003) or the bootstrap management command for the first owner; no self-registration, no directory sync; OPERATOR ⇒ INTERNAL_ONLY (CHECK); account kinds PERSON / OPERATOR only - personal operator accounts, no shared terminal or service accounts (DEC-052 APPROVED) | SYS | S1 (name) | KEEP (disabled, never deleted) |
| Credential (password hash) | user_id (PK/FK 1:1), hasher id, hash, set_at, must_change, one_time_expires_at | Django password-hasher encoding `<algorithm>$...` (CHECK; hasher choice in 01.3 - Argon2 needs a new pinned dependency); hash never leaves the DB, never in audit/outbox/logs; policy DEC-051 APPROVED (parameters `password_*`) | SYS | SEC | replaced on change; previous hashes kept append-only in `platform_password_history` (DEC-051 rotation; the last 5 are refused - `password_history_reuse_depth`, employer answer Q-0105 2026-11-05) |
| MfaFactor | factor_id, user_id FK, method (TOTP only, DEC-050 APPROVED), secret (encrypted at rest with a key from env/secret store, not the DB), confirmed_at, last_used_step (replay guard), status | at most one ACTIVE factor per method per user (partial unique); secret write-only; reset only by `resetUserMfa` (audited, MFA step-up) | SYS | SEC | removed factor kept as revoked metadata (no secret) |
| RecoveryCode | user_id FK, code_hash, used_at | hashed like passwords; shown once (DEC-050) | SYS | SEC | deleted when regenerated (hash only) |
| Session | session_key (Django, secret, never exposed), session_handle (public random id), user_id FK, state (MFA_PENDING/ACTIVE/EXPIRED/REVOKED/LOGGED_OUT), created_at, last_seen_at, expires_at (absolute), idle_expires_at, mfa_verified_at, network_zone (INTERNAL/EXTERNAL/UNKNOWN), client_ip (from trusted proxy), user_agent_hash | server-side store = table `platform_session`, cookie value stored as SHA-256 only (01.2); id rotated at login and MFA; timeouts DEC-051 APPROVED (parameters `session_*`); revoke-all on disable/password change | SYS | S1 (IP = personal data, S1) | TECH: session rows 90 days after end; security events go to AuditEvent (DEC-032) |
| LoginAttempt / SecurityEvent | id, occurred_at, username_attempted (normalised, may not exist), user_id (nullable), outcome (OK/INVALID_CREDENTIALS/LOCKED/NETWORK_POLICY_DENIED/MFA_FAILED), client_ip, network_zone, request_id | append-only; feeds lockout + page 36/46 counters; never stores the submitted password | SYS | S1 | DEC-032 |
| Permission (action catalogue) | action (PK text, e.g. `platform.identity.user.create`), module, description_fa, sensitivity S0–S3, mfa_step_up, business_approval | defined in code + seeded by migration (reviewed commit); not editable through the API; pattern as OpenAPI `action` | SYS | S0 | KEEP |
| Role | role_id, code (SystemKey, unique), name_fa, kind (TECHNICAL/BUSINESS), status (DRAFT/ACTIVE/RETIRED), matrix_version | CHECK: a TECHNICAL role contains no permission with business_approval=true (DEC-003 "admin ≠ business approval"); activation only if the permission set matches the approved matrix (DEC-049) | SYS | S0 | KEEP |
| RolePermission | role_id FK, action FK | unique(role_id, action); changes only while role DRAFT, or as a new matrix version (01.2 detail) | SYS | S0 | KEEP (history via audit) |
| RoleAssignment | assignment_id, user_id FK, role_id FK, scope_kind (GLOBAL/ORG_UNIT/ORG_UNIT_SUBTREE; SITE/WAREHOUSE/LINE/CUSTOMER reserved), scope_ref_id, valid_from, valid_to, status (PENDING_APPROVAL/ACTIVE/EXPIRED/REVOKED), granted_by, self_assignment (generated: granted_by = user_id), reason, approval_id (nullable) | no overlapping ACTIVE assignment for same (user, role, scope); reason mandatory; self_assignment always audited (DEC-003); need of a second approver: DEC-032; scope_ref_id FK to OrgUnit when scope_kind ORG_UNIT* | SYS | S1 | KEEP |
| OrgUnit | unit_id, code (SystemKey unique), name_fa, unit_type, parent_unit_id (self FK, nullable for roots), valid_from, valid_to, status | acyclic + depth ≤ `org_tree_max_depth` = 6 (DB trigger under an advisory lock, 01.2); unit types COMPANY/DEPARTMENT/SECTION/LINE seeded, admin may add (DEC-048 APPROVED); deactivate only when no active position | SYS | S1 | KEEP (effective-dated) |
| Position | position_id, unit_id FK, code, title_fa, reports_to_position_id (self FK), is_unit_head, status | reports-to graph acyclic; at most one is_unit_head per unit (partial unique, 01.2); reports-to at **position** level (person changes keep the line) | SYS | S1 | KEEP |
| PositionAssignment | position_assignment_id, position_id FK, user_id FK, kind (PRIMARY/ADDITIONAL/ACTING), valid_from, valid_to | one PRIMARY per user at any instant (exclusion constraint) + ACTING with an end date; no ADDITIONAL (DEC-048 APPROVED); **grants no permission by itself** (roles separate) | SYS | S1 | KEEP |
| WorkTask | task_id, subject, related_entity (type/id/revision), assignee (USER/ORG_UNIT/POSITION + id), status (STATE_TRANSITIONS §4.3), due_at, blocked_reason, blocked_by_ref, created_by, completed_by, closed_by | closer ≠ completer (verify step); reassign needs reason + scope check; SLA pause rules not in PHASE_01 (catalog invariant needs approved rule) | SYS | S1–S3 by related entity (field-level) | DEC-032 |
| ApprovalRequest | approval_id, action (permission id), resource (type/id), resource_revision, status (§4.4), requested_by, route (resolved approvers), decided_by, decided_at, decision_note, expires_at, workflow_instance_id | unique OPEN request per (resource, revision, action); decided_by ≠ requested_by (DB CHECK + engine); one-time decision; approval invalid if the resource revision changed; routing = role + unit scope only (DEC-048); actions requiring approval: document revision, BUSINESS_RULE publish, BA-role assignment; expiry 30 days (DEC-032) | SYS | S1–S3 by resource | DEC-032 |
| WorkflowDefinition | definition_id, key, version, status (DRAFT/ACTIVE/RETIRED), steps (json, schema-validated), decision_id | shipped as versioned data in reviewed migrations (not edited at runtime in PHASE_01); unique(key, version); one ACTIVE per key | SYS | S0 | KEEP |
| WorkflowInstance | instance_id, definition_id FK (pinned version), subject (type/id), status (§4.5), started_at, ended_at, current_step, history (separate table rows) | instance keeps the definition version it started with; cancel → compensation steps per definition | SYS | S1 | DEC-032 |
| AuditEvent (PHASE_00 table, extended) | + `session_handle`, `network_zone`, `self_assignment` flag in payload, hash-chain columns `prev_hash`, `event_hash` (proposal) | append-only (00.2 triggers); integrity check job writes `AuditIntegrityRun` (status OK/BROKEN, checked count); redaction per field permission at read time | SYS | S2 | DEC-032 (until then KEEP) |
| AuditIntegrityRun | run_id, started_at, finished_at, status, events_checked, first_broken_event_id | append-only | SYS | S1 | KEEP |
| JobDefinition | job_type (SystemKey PK), name_fa, cancellable, protected | seeded by migration; `protected=true` for migrations/restore/backup (SECURITY_BASELINE §4); full protected list DEC-024 | SYS | S0 | KEEP |
| JobRun | job_id, job_type FK, state (§4.7), queued_at, started_at, finished_at, progress (nullable, only if the job reports it), last_checkpoint_at, cancel_requested_by, cancel_reason, error_code, idempotency/task key (unique) | cancel only for cancellable & not protected; reason ≥ 3 chars; one terminal state; Celery task id unique (DEC-001 Celery) | SYS | S1 | TECH: 180 days, then summary rows only (ops to confirm) |
| Document | document_id, document_type (SystemKey), title_fa, owner_entity (type/id), sensitivity S1–S3, current_approved_revision_id, legacy_location_ref (text evidence, C-29) | approved revision immutable; download needs `platform.document.download` + record scope + scan CLEAN | SYS | S1–S3 (per document) | KEEP |
| DocumentRevision | revision_id, document_id FK, revision_no (unique per document), parent_revision_id, status (§4.6), scan_status (QUARANTINED/SCANNING/CLEAN/REJECTED), scan_finding, sha256 (`^[0-9a-f]{64}$`), size_bytes, media_type (server-detected), original_name (sanitised basename), storage_key (random, never a client path), encryption_key_ref | sha256 computed server-side while streaming; storage_key unique; never executed or rendered inline; PDF/PNG/JPG/DXF/XLSX, ≤ 25 MB = 26 214 400 bytes (Q-0104), ClamAV (DEC-053 APPROVED) | SYS | S1–S3 | KEEP (rejected file bytes: 30 days quarantine then purge, metadata + hash kept — DEC-053 APPROVED) |
| StoredObject (encrypted file ref) | storage_key, bucket/volume, size, sha256, encryption (algorithm, key_ref), created_at | private storage, not web-served; key material outside the DB (env/secret store) | SYS | SEC (key ref) / S1–S3 (content) | follows its revision |
| ParameterDefinition | parameter_key (SystemKey PK, immutable), label_fa, datatype, owner_module, classification (TECHNICAL/BUSINESS_RULE), decision_id | BUSINESS_RULE ⇒ decision_id required; values of a BUSINESS_RULE parameter cannot be published while its decision is not APPROVED (RULE_NOT_APPROVED) | SYS | S0–S2 | KEEP |
| ParameterValueRevision | value_revision_id, parameter_key FK, value (canonical string + datatype; decimals as strings), status (DRAFT/PENDING_APPROVAL/PUBLISHED/SUPERSEDED/REJECTED), effective_from, proposed_by, published_by, approval_id | one PUBLISHED revision effective at any instant per key; history never rewritten; publisher ≠ proposer for BUSINESS_RULE (DEC-032 APPROVED; trigger) | SYS | S0–S2 | KEEP |
| DynamicFieldDefinition | field_key (SystemKey, immutable), entity_scope, label_fa, datatype, security_class S0–S3, help_fa, status (DRAFT only in PHASE_01) | label change never changes the key; no form/layout binding until PHASE_11 (C-33) | SYS | S0–S1 | KEEP |
| Notification (in-app) | notification_id, user_id FK, kind, ref (type/id), created_at, read_at | in-app only in PHASE_01 (no SMS/email channel decided); payload ids only, no sensitive text | SYS | S1 | TECHNICAL DEFAULT: 180 days (REV-0104: not a business rule and not part of DEC-032; ops/employer to confirm before production; table not created in 01.2) |

Sensitive-field handling (field-level redaction, PHASE_01 engine): Credential/MfaFactor/RecoveryCode/session_key
are never serialised; `client_ip` and `user_agent_hash` visible only with `platform.identity.session.read`;
audit `changes` values for S2/S3 fields are redacted for callers without the field permission
(`redacted_fields[]` lists the field names, never the values).

## PHASE_01 physical scope (for step 01.2)
Candidates: all rows of the table above except `Notification` (optional, may move to 01.4/01.5 if the inbox
needs it). No business entity of later phases; no real people or org data in seeds (synthetic only, labelled).

### 01.2 result (migrations 0007-0010, docs/db/ERD.md section 6)
- Created: 33 tables (every row above except `Notification`, plus the additional tables below) and 5 columns on
  `platform_audit_event`
  (`session_id`, `network_zone`, `chain_seq`, `prev_hash`, `event_hash`; filled by the 01.3 engine).
  `Notification` is not created (no inbox endpoint before 01.4/01.5).
- Additional tables from the decisions: `platform_password_history` (DEC-051), `platform_break_glass_usage`
  (DEC-054), `platform_org_unit_type` (DEC-048), `platform_org_unit_history` / `platform_position_history`
  (DEC-048 item 7, effective-dated, written by trigger), `platform_upload_type` (DEC-053 allow-list).
- Not created on purpose: a network/CIDR table (DEC-052: the list lives only in server config, never in Git or
  the DB), any AD/LDAP/SSO column (DEC-003), a delegation/out-of-office table (STATE_TRANSITIONS 4.11).
- Numbers of DEC-032/048..054 are versioned parameter values with decision provenance
  (`platform_parameter_value`, classification `OWNER_POLICY`), not constants.
- Open questions raised by 01.2: STATE_TRANSITIONS.md section 4.12. Answered by the employer on 2026-11-05
  and seeded as DEC-051 parameters: Q-0101 (4th login ends the oldest session), Q-0102 (operator absolute
  session 12 h), Q-0105 (last 5 passwords refused), Q-0103 (OWNER_POLICY values: owner_admin alone, reason,
  MFA, audit), Q-0104 (25 MB = 26 214 400 bytes), Q-0106 (position `primary_capacity`, default 1, heads 1).
  Rework (REV-0105/0107): role lifecycle enforced in the DB; org changes never back-dated (60 s tolerance).

# PHASE_02 / 02.1 additions — Order & Product Identity (logical model for 02.2)

Status: DRAFT logical model (2026-11-11). Nothing here is a migration. Physical DDL is decided in 02.2.
Sources: `PHASE_02.md` (Customer, Product/Style, CodeRuleRevision, PO Header/Line, Serial, Historical Snapshot,
External Ref), `DOMAIN_ENTITY_CATALOG.md` (Identity, Commercial), `ARCHITECTURE_OVERVIEW_FA.md`,
`SOURCE_MAPPING_AND_IMPORT.md`, catalog `29_36…/DATA_MODEL.md` and `05_06…/DATA_MODEL.md` (DRAFT), and the conflicts
C-47…C-76. The rows of the PHASE_00 table above ("Identity / Product Registry — PHASE_02", "Commercial — PHASE_02")
are superseded by this section.

## 1. Conventions specific to PHASE_02 (in addition to the conventions at the top of this file)
- **Module ownership.** `identity_*` tables belong to the Identity module; `commercial_*` tables to the Commercial
  module. Neither module writes the other's tables. Cross-module effects travel as outbox events
  (ARCHITECTURE_OVERVIEW "never mutate other modules' authoritative data via direct table writes").
- **14-digit codes.** `varchar(14)` + `CHECK (code ~ '^[0-9]{14}$')` (the existing `Code14Field`,
  `platform_core/code14.py`), always with a `code_namespace` column, `CHECK (code_namespace IN ('product_code','die_code'))`.
  Never `numeric`, `bigint` or `char(14)` with padding. No Persian/Arabic-Indic digit normalisation inside the DB
  (normalisation is an import transform with the raw value kept). The **segments** of a product code are not
  modelled as columns: their number, order and width are DEC-005.
- **Serial number.** Its own namespace; `varchar`. Width, pattern and allocation are BLOCKED (DEC-006). 02.2 creates
  the column as `varchar(32)` with `CHECK (serial_number <> '' AND serial_number = btrim(serial_number))` and **no
  pattern**. The pattern CHECK is added by the migration that implements the approved DEC-006 rule.
- **Business dates** (`order_date`, `requested_due_date`): `date`. Event times: `timestamptz` UTC. Jalali only in the UI.
- **Quantities**: `integer > 0` with `uom` ∈ {PIECE, PAIR} in PHASE_02 (C-67). No float, no conversion.
- **Every owned table**: `id uuid` PK, `created_at/created_by`, `updated_at/updated_by`, `row_version bigint >= 1`
  (ETag), audit + outbox in the same transaction (UnitOfWork, 00.3). Ledger-like and versioned tables are
  append-only (DB trigger, like `platform_audit_event`).
- **Sensitivity**: customer identity, product codes, styles and order quantities are S2. Prices are absent from
  PHASE_02 (PHASE_10). Customer contact persons are not stored (DEC-028; C-54).

### 1.1 Source provenance block (columns on every table that can hold imported or legacy-derived data)
| Column | Type / constraint | Meaning |
|---|---|---|
| `provenance_kind` | `varchar(8)`, CHECK in (`SYS`, `IMP`, `LEG`, `EXT`) | SYS = created in the platform; IMP = applied from an import batch; LEG = read-only legacy evidence (historical); EXT = reference only |
| `import_batch_id` | uuid FK → `platform_import_batch(id)` ON DELETE PROTECT, nullable | the batch the value came from |
| `staging_row_id` | bigint FK → `platform_import_staging_row(id)` ON DELETE PROTECT, nullable | the raw row (workbook, sheet, row, payload hash) |
| `source_sheet` | `varchar(100)`, default '' | sheet name as in the source (e.g. `NOrder`) |
| `source_cell_ref` | `varchar(32)`, default '' | A1 reference of the cell that produced the value |
| `source_raw_value` | `text`, nullable | raw cell text exactly as read (never trimmed or normalised) |
| `source_formula` | `text`, nullable | formula text if the cell had one (formula ≠ evaluated truth, SOURCE_MAPPING §4) |
| `transform_rule_version` | `varchar(64)`, default '' | version id of the transform that normalised the raw value |
| CHECK | `provenance_kind IN ('IMP','LEG') ⇒ import_batch_id IS NOT NULL AND staging_row_id IS NOT NULL` | an imported value always points to its raw row |
| CHECK | `provenance_kind = 'SYS' ⇒ import_batch_id IS NULL` | no fake provenance |

The workbook hash is reached through `import_batch.file_sha256`. It is not copied, so one hash is the single truth.

## 2. Identity module
| Entity (table) | Key fields | Keys and constraints | Provenance | Sensitivity | Blocked parts |
|---|---|---|---|---|---|
| Customer (`identity_customer`) | id, `customer_no` (internal, system-generated text), `display_name_fa`, `legal_name_fa` (nullable), `status` (ACTIVE / INACTIVE), `default_required_quality_ref` (text, C-68) | UNIQUE(`customer_no`); UNIQUE(lower(normalised `display_name_fa`)) **as a warning index only** (non-unique index + engine duplicate check; never an auto-merge); CHECK status; no contact columns | block 1.1 | S2 | none |
| CustomerBrand (`identity_customer_brand`) | id, customer_id FK, `brand_name_fa`, `status` | UNIQUE(customer_id, normalised `brand_name_fa`); FK ON DELETE PROTECT | block 1.1 | S2 | whether brands exist as a separate level: DEC-058 q.1 (the table is harmless if unused) |
| ProductClass (`identity_product_class`) | id, `parent_id` (self FK, nullable), `level_key` (SystemKey of the classification level), `label_fa`, `segment_value` (`varchar(8)`, **nullable**), `rule_revision_id` FK (nullable), `status` (DRAFT / ACTIVE / RETIRED) | acyclic (engine + trigger); UNIQUE(parent_id, label_fa); UNIQUE(rule_revision_id, level_key, segment_value) WHERE segment_value IS NOT NULL; CHECK `segment_value ~ '^[0-9]+$'` | block 1.1 (IMP from `Sorce` after DEC-005) | S1 | the levels (type/category/…), their order and `segment_value` widths: DEC-005 E-1…E-3. Nothing is seeded (C-58). |
| Product (`identity_product`) | id, `product_class_id` FK, `product_no` (`varchar(8)`, digits, nullable), `name_fa`, `uom` (PIECE / PAIR), `status` (DRAFT / ACTIVE / RETIRED) | CHECK `product_no ~ '^[0-9]+$'`; uniqueness scope of `product_no`: DEC-005 E-4 (02.2 adds only a non-unique index); FK PROTECT | block 1.1 | S2 | product number width and scope: DEC-005 |
| Style (`identity_style`) | id, product_id FK, `style_no` (`varchar(8)`, digits, nullable), `name_fa`, `current_revision_id` FK (nullable), `status` | UNIQUE(product_id, style_no) WHERE style_no IS NOT NULL (C-57); CHECK digits | block 1.1 | S2 | style number width: DEC-005 |
| StyleRevision (`identity_style_revision`) | id, style_id FK, `revision_no` (int ≥ 1), `attributes` (jsonb: colour, main material **as text references**, hardware colour, notes), `status` (DRAFT / ACTIVE / SUPERSEDED), `technical_package_revision_id` (uuid, nullable, PHASE_03/04, C-59) | UNIQUE(style_id, revision_no); one ACTIVE per style (partial unique index); ACTIVE and SUPERSEDED rows immutable (trigger) | block 1.1 | S2 | material/colour master lists are PHASE_04/06; text only here |
| CodeRuleRevision (`identity_code_rule_revision`) | id, `code_namespace` (= product_code), `revision_no`, `scope` (jsonb: which classes the rule covers), `rule_spec` (jsonb, schema-validated, **content defined only after DEC-005**), `source_workbook_sha256`, `evidence_ref` (document id of the extraction report, PHASE_01 documents), `golden_case_count`, `status` (DRAFT / IN_REVIEW / APPROVED / ACTIVE / RETIRED / REJECTED), `decision_id` (`^DEC-[0-9]{3}$`), `approved_by`, `approved_at` | UNIQUE(code_namespace, revision_no); CHECK `source_workbook_sha256 ~ '^[0-9a-f]{64}$'`; ACTIVE ⇒ approved_by ≠ created_by (maker-checker, DEC-032 pattern) and `golden_case_count >= 20` (Gate text) and `decision_id` APPROVED; ACTIVE/RETIRED immutable | SYS (rule) + evidence hash | S2 | **entire activation BLOCKED by DEC-005**; the `rule_spec` JSON schema is written after the extraction |
| CodeRuleGoldenCase (`identity_code_rule_golden_case`) | id, rule_revision_id FK, `inputs` (jsonb), `expected_code` (Code14), `source_sheet`, `source_cell_ref`, `source_workbook_sha256`, `verified_by`, `verified_at` | UNIQUE(rule_revision_id, source_sheet, source_cell_ref); expected_code CHECK regex | LEG (server DB only) | S2 | real cases live **only** in the server DB and in the private directory, never in Git (DEC-028, DEC-046; R-38). Repository tests use synthetic cases. |
| ProductCode (`identity_product_code`) — registry | id, `code` (Code14), `code_namespace` (product_code), `style_id` FK (nullable until matched), `rule_revision_id` FK (nullable: imported legacy codes have none), `status` (RESERVED / ACTIVE / RETIRED / DISPUTED), `erp_status` (ERP_PENDING / ERP_MATCHED / ERP_MISSING), `erp_seen_batch_id` FK import batch (nullable), `issued_by`, `issued_at` | **UNIQUE(code_namespace, code)**; CHECK regex; ACTIVE ⇒ `erp_status = ERP_MATCHED` (C-75); `style_id` unique WHERE status IN (RESERVED, ACTIVE) only if DEC-005 confirms one code per style (open: E-6) | block 1.1 (IMP from the Rahkaran item list or LEG from Planning; SYS only through an APPROVED rule) | S2 | issuing (SYS rows) BLOCKED by DEC-005; ERP matching uses the Rahkaran import of PHASE_06 (`erp_status` stays ERP_PENDING until then) |
| SerialNamespace (`identity_serial_namespace`) | id, `namespace_key` (SystemKey), `pattern` (text regex, nullable), `next_value` (bigint), `reserved_below` (bigint, legacy collision guard), `decision_id`, `status` (DRAFT / ACTIVE) | UNIQUE(namespace_key); ACTIVE ⇒ pattern NOT NULL and decision APPROVED; `next_value` only moved by the allocation function under `SELECT … FOR UPDATE` (or a DB sequence per namespace, chosen in 02.2) | SYS | S1 | **BLOCKED by DEC-006** (no ACTIVE row can exist) |
| Serial (`identity_serial`) | id, `serial_namespace_id` FK, `serial_number` (varchar 32), `order_line_id` FK → `commercial_customer_order_line`, `customer_id`, `style_id`, `style_revision_id`, `product_code_id` (nullable), `status` (STATE_TRANSITIONS §5.4), `allocation_idempotency_key` (uuid), `allocated_by`, `allocated_at` | **UNIQUE(serial_namespace_id, serial_number)**; **UNIQUE(order_line_id)** (ID-03, C-47); UNIQUE(allocation_idempotency_key) (ID-04); number never re-used, even after CANCELLED (no delete; trigger); FK PROTECT | SYS (LEG serials live in HistoricalOrderRecord, not here) | S2 | allocation BLOCKED by DEC-006 |
| SerialSnapshot (`identity_serial_snapshot`) | id, serial_id FK, `version` (int ≥ 1), `snapshot` (jsonb: customer, brand, PO no, line no, product code, style + revision attributes, quantity + uom, dates, required quality reference), `reason` (ALLOCATED / CHANGE_APPLIED / TECH_PACKAGE_LINKED), `change_request_id` (nullable), `created_at`, `created_by` | UNIQUE(serial_id, version); append-only (trigger); version 1 written in the allocation transaction (ID-02, C-64) | SYS | S2 | none (needs a serial, so in practice after DEC-006) |
| ExternalRef (`identity_external_ref`) | id, `target_type` (customer / product / style / customer_order / order_line / serial), `target_id`, `system` (RAHKARAN / CUSTOMER / LEGACY_PLANNING / OTHER), `namespace` (SystemKey, e.g. `rahkaran_project_code`, `customer_style_code`, `customer_serial`, `contract_no`), `value` (`varchar(64)`, raw text kept exactly), `valid_from`, `valid_to` | UNIQUE(system, namespace, value, target_type, target_id); index (system, namespace, value); **no** global uniqueness of `value` (C-56); values never parsed into numbers | block 1.1 | S2 | the namespace list: DEC-058 q.4 (rows can be created with SystemKeys; new namespaces by data steward) |
| HistoricalOrderRecord (`identity_historical_order_record`) | id, `import_batch_id`, `staging_row_id`, `legacy_order_ref` (text), `legacy_serial_ref` (text), `legacy_product_code_raw` (text, **not** Code14-checked), `normalised_product_code` (Code14, nullable), `payload` (jsonb: the mapped legacy columns, raw), `match_status` (UNMATCHED / SUGGESTED / CONFIRMED / REJECTED), `matched_serial_id` (nullable), `matched_by` | UNIQUE(staging_row_id); never updated except `match_*` columns (trigger); never an official order | LEG | S2 | bulk import BLOCKED by DEC-025/035 (PHASE_12); PHASE_02 uses it for the golden extraction only |

## 3. Commercial module
| Entity (table) | Key fields | Keys and constraints | Provenance | Sensitivity | Blocked parts |
|---|---|---|---|---|---|
| CustomerOrder (`commercial_customer_order`) — PO header | id, `order_no` (internal, system-generated text), `customer_id` FK, `brand_id` FK (nullable), `external_po_number` (`varchar(64)`, raw), `order_type` (SystemKey, list DEC-058 q.6), `program_ref` (text, nullable; PHASE_05 owns programs), `order_date` (date), `requested_due_date` (date, nullable), `status` (STATE_TRANSITIONS §5.1), `hold_reason` (nullable), `current_version` (int), `cancel_reason` (nullable) | UNIQUE(order_no); index (customer_id, external_po_number) **non-unique** (C-55); CHECK status; CHECK `requested_due_date >= order_date`; CHECK `status IN (ON_HOLD, PAUSED) ⇔ hold_reason IS NOT NULL`; FK PROTECT | block 1.1 | S2 | confirmation authority DEC-057; cancellation after CONFIRMED DEC-059 |
| CustomerOrderLine (`commercial_customer_order_line`) | id, order_id FK, `line_no` (int ≥ 1), `style_id` FK, `style_revision_id` FK, `product_code_id` FK (nullable until known), `quantity` (int > 0), `uom`, `requested_due_date` (nullable), `status` (STATE_TRANSITIONS §5.2), `serial_id` (nullable, mirrors `identity_serial.order_line_id`), `cancel_reason` | UNIQUE(order_id, line_no); line_no never re-used inside an order; one Product/Style per line (single `style_id`, README_FA); CHECK quantity > 0; CHECK uom; CONFIRMED lines immutable except via change request (trigger checks `current_version`) | block 1.1 | S2 | whether a line may be CONFIRMED without a serial: DEC-006 q.2 |
| CustomerOrderVersion (`commercial_customer_order_version`) | id, order_id FK, `version` (int ≥ 1), `image` (jsonb: header + all lines), `reason` (CONFIRMED / CHANGE_APPLIED / CANCELLED), `change_request_id` (nullable), `created_at`, `created_by` | UNIQUE(order_id, version); append-only (trigger); `commercial_customer_order.current_version` = max(version) (engine + check in the same transaction) | SYS | S2 | none |
| OrderChangeRequest (`commercial_order_change_request`) | id, `request_no`, order_id FK, `base_order_version` (int), `kind` (QTY_CHANGE / DUE_DATE_CHANGE / ADD_LINE / CANCEL_LINE / CANCEL_ORDER / HOLD / RESUME), `items` (jsonb, schema per kind: line id, old value, new value), `reason` (≥ 3 chars), `status` (STATE_TRANSITIONS §5.5), `impact` (jsonb, PHASE_02 part only: affected lines/serials/snapshots), `approval_id` FK → `platform_approval_request` (nullable), `requested_by`, `decided_by`, `applied_version` (nullable) | UNIQUE(request_no); CHECK status; at most one SUBMITTED/APPROVED request per order at a time (partial unique index) so two changes never race on one version; APPLIED ⇒ `applied_version = base_order_version + 1`; decided_by ≠ requested_by (DEC-032 pattern) | SYS | S2 | allowed kinds per state and the approver: **DEC-059 / DEC-057** |

## 4. Platform tables reused (no new platform table in PHASE_02)
`platform_import_batch` / `platform_import_staging_row` (provenance), `platform_approval_request` (maker-checker of
CodeRuleRevision and change requests), `platform_audit_event`, `platform_outbox_event`, `platform_idempotency_record`
(ID-04), `platform_document` (extraction reports as evidence), `platform_conflict_item` (import conflicts, e.g. a
Rahkaran code that differs from the Planning code).

## 5. Invariants that 02.2/02.3 must prove with tests
| ID | Invariant | Evidence planned |
|---|---|---|
| INV-02-01 | A 14-digit code is stored and returned as the same 14-character string (leading zeros kept); integers and Persian digits are refused | ID-01; DB CHECK + API schema `Code14` + property test |
| INV-02-02 | No two serials share (namespace, number); a line has at most one serial | ID-02, ID-03; UNIQUE constraints + 100 concurrent allocations (Gate) |
| INV-02-03 | The same Idempotency-Key + body gives one serial and the same response | ID-04; `platform_idempotency_record` + UNIQUE(`allocation_idempotency_key`) |
| INV-02-04 | Exactly one SerialSnapshot v1 per committed line, written in the allocation transaction | ID-02; rollback test (failure after snapshot ⇒ no serial, no snapshot, no outbox) |
| INV-02-05 | A serial number is never re-used, and a serial row is never deleted | trigger test |
| INV-02-06 | CONFIRMED order data changes only through an APPLIED change request, which writes a new CustomerOrderVersion | trigger + engine test |
| INV-02-07 | A code is issued only under an ACTIVE CodeRuleRevision; otherwise 409 RULE_NOT_APPROVED (DEC-005) | engine test (runs today: blocked path) |
| INV-02-08 | Similarity never merges two styles/customers | API contract: no merge operation |
| INV-02-09 | Imported values keep raw + normalised + provenance; IMP/LEG rows always point to a staging row | DB CHECK (block 1.1) |

### 02.2 result (migrations 0019-0022, docs/db/ERD.md section 7)
- Built to the decisions APPROVED on 2026-11-12 (DEC-005/006/057/058/059); where they differ from the 02.1 draft
  above, the decision wins:
  - Classification: one table `identity_product_class` with two levels (`product_type`, `category`), 2-digit
    segments; `identity_product.product_no` and `identity_style.style_no` 4 digits (DEC-005). Units are a seeded
    table `identity_unit_of_measure` (PIECE/PAIR, DEC-058) referenced by the product type and checked on every line.
  - Serial: `identity_serial_counter` (single row `factory_serial`, start 63001, legacy < 63000) replaces the
    planned `SerialNamespace`; pattern `^[1-9][0-9]*$` (DEC-006). Legacy serials are text on
    `identity_historical_order_record` (`legacy_serial_text`, plain value, duplicate flag) - never in `identity_serial`.
  - REV-0201: no mirror column; the line holds `serial_id` (UNIQUE FK); Identity owns serial + snapshot (ERD 7.1).
  - Order states without `PAUSED` (DEC-059: single ON_HOLD with `status_before_hold`); line states without
    `SERIAL_ALLOCATED` (DEC-006 L-A: a confirmed line always has its serial). The 0.7.0-draft contract enums still
    list both; the 02.4 contract update removes them.
  - The customer representative name is on the order only (`customer_representative_name`, PII, DEC-058); no
    contact column exists anywhere.
- Not created: `Inquiry/QuoteVersion` (PHASE_10), `CustomerArtworkApproval` (PHASE_03).
- REV-0203 (untagged rules of the 02.1 draft): "one SUBMITTED/APPROVED change request per order" and "change request
  expires after 30 days" are **not** enforced (OPEN, not decided; the base-version check already makes two changes
  on one version impossible); "uom of the family" is now DEC-058 (enforced by trigger).

### 02.3 result (domain engine, migrations 0023-0024)
- **Technical numbers — PROPOSED, waiting for the employer's confirmation** (gapless not required; unique and
  race-safe):

  | Record | Format | Example (synthetic) | Source |
  |---|---|---|---|
  | Customer `customer_no` | `CU-` + at least 6 digits | `CU-000042` | sequence `identity_customer_no_seq` |
  | Order `order_no` | `SO-` + at least 6 digits | `SO-000137` | sequence `commercial_order_no_seq` |
  | Change request `request_no` | `CR-` + at least 6 digits | `CR-000009` | sequence `commercial_change_request_no_seq` |

  One PostgreSQL sequence per kind (migration 0023): concurrent writers never get the same number; the UNIQUE
  constraints of the tables stay the final guard. A rolled-back write consumes a number (gaps allowed). The width
  grows past 6 digits instead of wrapping. These numbers are **not** the factory serial (DEC-006), which never
  uses a sequence. Alternatives the employer may prefer: a Jalali-year prefix (`SO-1405-000137`, resets yearly)
  or a per-customer order counter; neither is implemented.
- Code rule (DEC-005): `CodeRuleRevision.rule_spec` = `product_identity.coderule.RULE_SPEC_V1` (prefix `02`,
  segments 2/2/4/4, product number max + 1 per type or buckle + width, style count + 1 per product and category);
  `scope` = `{"product_types": [...]}`; submit requires >= 20 golden cases per type of the scope, every one
  reproduced; approval marks the cases verified by the approver.
- Change requests: `items` schema per kind (`commercial.changes.normalise_items`): QTY_CHANGE
  `{line_id, quantity}`, DUE_DATE_CHANGE `{line_id | null (header), requested_due_date}`, ADD_LINE
  `{style_id, style_revision_id, product_code_id | null, quantity, requested_due_date | null}`, CANCEL_LINE
  `{line_id}`, CANCEL_ORDER / HOLD / RESUME `[]`. `impact` = lines and serials touched (other modules
  `NOT_AVAILABLE_IN_PHASE_02`).
- Version images (`commercial_customer_order_version.image`) and serial snapshots carry identifiers, quantities,
  dates, codes and serial numbers, but **never** the representative name (only `has_customer_representative`).
- **Style 0000 (DEC-005 amendment 2026-11-13): legacy only.** The 14 real codes with style segment `0000` (all
  product type 02, golden run on the Planning baseline) are history: imported (IMP / LEG) styles and codes may carry
  `0000` and be registered / matched; the system never builds, issues or numbers it (new styles start at `0001`;
  `STYLE_0000_LEGACY_ONLY`). Engine: `coderule.validate_legacy_code` / `parse_code(..., legacy=True)`; DB:
  `ck_identity_style_no_fmt` (0000 only for IMP/LEG), `ck_identity_product_code_sys_no_style_0000`. Golden cases with
  style 0000 count in their family and pass only if the build path refuses them and the legacy parse is exact.
- DB: `ck_commercial_cr_planner_not_decider` (DEC-059 amendment 2026-11-12) and the ON_HOLD -> CANCELLED edge of
  `commercial_order_guard()` (stored state CONFIRMED only).

### 02.4 result (Backend/API, migration 0025) - employer amendments of 2026-11-14
- **Technical numbers - DECIDED (DEC-058 amendment 2026-11-14)**, replacing the PROPOSED 02.3 format:

  | Record | Format | Example (synthetic) |
  |---|---|---|
  | Customer `customer_no` | `CU-<Jalali year>-` + at least 6 digits | `CU-1405-000042` |
  | Order `order_no` | `SO-<Jalali year>-` + at least 6 digits | `SO-1405-000137` |
  | Change request `request_no` | `CR-<Jalali year>-` + at least 6 digits | `CR-1405-000009` |

  The year is the Jalali year of the creating transaction's database clock in Asia/Tehran
  (`product_identity/jalali.py`, verified against Nowruz dates: 1404/12/29 = 2026-03-20, 1405/01/01 = 2026-03-21).
  Numbering restarts at 1 every Jalali year. Counter: `platform_number_counter` (PK kind + jalali_year), one
  atomic `INSERT ... ON CONFLICT DO UPDATE SET last_value = last_value + 1` per number under the row lock (two
  writers never get the same number; the tables' UNIQUE constraints stay the final guard). Gaps are allowed. A guard
  trigger lets a row start at 1 and move forward by exactly 1 only; no reset, delete or truncate (runtime role
  checked by `roles_check.sh`). The 0023 sequences are dropped (reverse re-creates them after the largest plain
  number already used).
- **Style collision (DEC-005 amendment, REV-0232):** `count + 1` taken -> the first free number after it
  (`coderule.first_free_style_no`), the audit row carries `scope.style_no_collision` and a reason; never refused,
  never a duplicate (product row lock + UNIQUE). Gaps below are never back-filled.
- **Planning reject (DEC-059 amendment):** `commercial_order_change_request.planning_rejected_by` /
  `planning_rejected_at` (pair CHECK; due-date only; closes REJECTED; never the requester nor the deciding
  manager; excludes a planning approval).
- **External references:** written by `product_identity/external.py` (create / end; raw value kept exactly, never
  parsed; duplicate per system + type + value + target refused `EXTERNAL_REF_EXISTS`).
