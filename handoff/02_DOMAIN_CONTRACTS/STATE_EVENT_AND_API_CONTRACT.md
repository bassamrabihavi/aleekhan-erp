# State Machines, API Contract Families & Domain Events

## State Machines (proposed; must be approved per owner)
- `CustomerPO`: DRAFT → VALIDATED → CONFIRMED → RELEASED_TO_PLAN → PARTIAL_FULFILLED → FULFILLED → CLOSED; change via AMENDMENT, cancellation with authorization. `PAUSED`/`ON_HOLD` side-states.
- `TechnicalPackage`: DRAFT → UNDER_REVIEW → APPROVED → RELEASED → SUPERSEDED; `REJECTED` returns to new revision, not mutate approved.
- `DieCandidate`: EXTRACTED → TRIAGED → LINKED_TO_TRACKER → CODE_PENDING → ERP_MATCHED → ENGINEERING_APPROVED → TOOL_READY; physical tool receipt tracked by warehouse.
- `Reservation`: REQUESTED → RESERVED/SHORTAGE → ISSUED/PARTIALLY_ISSUED → CLOSED/RELEASED; no negative or dual use.
- `ProductionBatch`: PLANNED → MATERIAL_READY → CUTTING → WORK_IN_PROGRESS → QC_PENDING → QC_RELEASED/REWORK/HOLD → FG_RECEIVED.
- `NCR`: OPEN → CONTAINED → INVESTIGATED → ACTION_APPROVED → VERIFIED → CLOSED; closure must have evidence.
- `Shipment`: DRAFT → DOCUMENT_MATCHED → PICKED → DISPATCHED → CUSTOMER_RECEIVED / RETURN_PENDING → RECONCILED.
- `TimeStandard`: DRAFT → REVIEWED → APPROVED → ACTIVE → SUPERSEDED; active revision immutable.

## REST/OpenAPI boundary examples (endpoints to design/confirm in Gate-0)
`/api/v1/customers`, `/products`, `/styles`, `/product-codes/validate`, `/serials`, `/customer-orders`, `/revisions`, `/engineering/dxf-imports`, `/engineering/die-candidates`, `/engineering/dies`, `/engineering/cliches`, `/engineering/bom-revisions`, `/engineering/opc-revisions`, `/engineering/time-studies`, `/planning/demands`, `/planning/scenarios`, `/warehouse/inventory-snapshots`, `/warehouse/reservations`, `/warehouse/shortages`, `/production/batches`, `/production/activities`, `/quality/inspections`, `/quality/ncr`, `/fg/receipts`, `/dispatch/shipments`, `/imports/jobs`, `/admin/jobs`, `/audits`, `/reports`.

**API rules:** resources include owner scope and revision/ETag; write operations require authorized role+record scope, idempotency key and optimistic concurrency; errors as stable structured codes; pagination, filtering, audit correlation; OpenAPI generated and schema-diff tested; server enforces invariants independent of UI.

## Event catalog (Outbox)
`CustomerOrderConfirmed`, `SerialAllocated`, `CustomerOrderChanged`, `TechnicalPackageReleased`, `TimeStandardApproved`, `DieCandidateExtracted`, `DieTrackerLinked`, `MaterialReservationCreated`, `WarehouseGAPRaised`, `SupplierETAChanged`, `MaterialIssued`, `ProductionBatchStarted`, `OperationAccepted`, `ProductionScrapRecorded`, `QualityHoldApplied`, `QCGradeAssigned`, `FGReceiptConfirmed`, `ShipmentDispatched`, `ShipmentReconciled`, `ResourceDowntimeRecorded`, `ImportBatchValidated`, `DataConflictRaised`, `SecurityAlertRaised`.

Events require: event_id uuid, aggregate_type/id, aggregate_version, occurrence_utc, actor, correlation_id/causation_id, schema_version, payload with necessary identifiers only; no salary/password/customer personal addresses in generic event payloads. Handlers idempotent; out-of-order handled via version+queue; fail/DLQ visible to Admin.

## Authorization in workflow
- Customer art approval by Commercial on confirmed artwork revision, not by Engineering independently.
- Tool fabrication supplier ETA by Supply; Warehouse/انبارک physical receipt; Engineering technical fit.
- Incoming material QA Hold by QA; Release requires QA, not Warehouse alone.
- QC Product grade by QC; cannot be overridden by planner.
- Payroll update by HR with designated approval, technical admin cannot bypass.
