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
