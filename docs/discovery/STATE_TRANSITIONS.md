# State transitions — PHASE_00 / 00.1

Status: DRAFT. Business state machines below are copied from `handoff/02_DOMAIN_CONTRACTS/STATE_EVENT_AND_API_CONTRACT.md` (all **PROPOSED**, "must be approved per owner"). They are documentation for later phases; none is implemented in PHASE_00. Guards that depend on an OPEN decision are marked **BLOCKED (DEC-xxx)**: the engine must refuse the transition with `RULE_NOT_APPROVED` + `decision_id` until the decision is approved.

General rules (all machines): server-side only; each transition = one DB transaction (state + audit + outbox event); `If-Match` row version; idempotency key on the command; illegal transition → `409 STATE_TRANSITION_NOT_ALLOWED`; terminal/approved states immutable (changes create a new revision).

## 1. Platform machines (PHASE_00/01, proposed by this step)

### 1.1 OutboxEvent delivery (PHASE_00 skeleton)
`PENDING → DISPATCHED → ACKED`; `PENDING|DISPATCHED → FAILED` (attempt++, backoff) `→ PENDING`; `FAILED → DEAD_LETTER` after max attempts (visible to Admin); `DEAD_LETTER → PENDING` only by authorised admin replay (audited). Consumers dedupe by `event_id`.
Implemented in 00.3 (`platform_core/engine/outbox.py`, golden `tests/golden/outbox_delivery_machine.golden.json`). Composite moves are validated edge by edge and written in one UPDATE: a due retry is claimed as `FAILED → PENDING → DISPATCHED`; a final failure is `DISPATCHED → FAILED → DEAD_LETTER`. Attempts are counted at claim time; a `DISPATCHED` row older than the lease is recovered as a failed attempt. See `docs/engine/README.md` §5.

### 1.2 IdempotencyRecord (PHASE_00 skeleton)
`IN_PROGRESS → COMPLETED` (response stored) | `IN_PROGRESS → FAILED_RETRYABLE` (deleted/expired so retry allowed). Same key + different request hash → 422 `IDEMPOTENCY_KEY_REUSED`. Concurrent duplicate while `IN_PROGRESS` → 409 `IDEMPOTENCY_IN_PROGRESS`. Retention window: proposal 24h, confirm in 00.3.
Implemented in 00.3 (`platform_core/engine/idempotency.py`): retention 24 h and in-progress lease 5 min are technical parameters (defaults, not business rules; ops confirmation in 00.7). `FAILED_RETRYABLE` and expired records are re-claimed in place (`→ IN_PROGRESS`); an `IN_PROGRESS` record past its lease (holder crashed) is taken over. See `docs/engine/README.md` §2.

### 1.3 Job (PHASE_01/11)
`QUEUED → RUNNING → SUCCEEDED | FAILED`; `RUNNING → CANCEL_REQUESTED → CANCELLED` (at checkpoint, safe); force-kill of protected jobs **BLOCKED (DEC-024)** (SEC-02).

### 1.4 ApprovalTask (PHASE_01)
`OPEN → APPROVED | REJECTED | EXPIRED | WITHDRAWN`; maker cannot approve own material change (split-of-duty, ROLE_PERMISSION_MATRIX); approval bound to resource revision, one-time. Exact maker-checker list **BLOCKED (DEC-032, PROPOSED)**; routing via org hierarchy per DEC-043 (detail in 01.1).

### 1.5 User account (PHASE_01)
`INVITED/CREATED (by owner/admin) → ACTIVE ↔ LOCKED (brute force) → DISABLED`; no self-registration; no external directory (DEC-003). MFA enrolment required before ACTIVE for MFA roles and outside access (DEC-003/DEC-042).

### 1.6 Import batch (PHASE_01 framework, PHASE_06/12 use)
`RECEIVED → QUARANTINED (scan) → PARSED → VALIDATED → PENDING_REVIEW → APPROVED | REJECTED`; `APPROVED → COMPENSATED` (rollback-with-compensation). Row statuses: `PENDING_REVIEW, ERROR, MATCHED, REJECTED, APPROVED` (ARCHITECTURE_OVERVIEW §کیفیت داده). Snapshot freshness/reimport policy **BLOCKED (DEC-016)**.
Implemented as a platform framework in 00.6 (`platform_core/integration/imports.py`, golden `tests/golden/import_batch_machine.golden.json`): `RECEIVED → STAGED → VALIDATED → APPLIED → COMPENSATED`, `RECEIVED|STAGED|VALIDATED → REJECTED`, `VALIDATED → SUPERSEDED`. Mapping to the proposal above: PARSED = STAGED; PENDING_REVIEW = VALIDATED (awaiting review); APPROVED = APPLIED. `QUARANTINED` (file scan) is not implemented: there is no file upload/storage path in PHASE_00 (SEC-03 is PHASE_01; scan tooling 00.7). APPLIED / SUPERSEDED / COMPENSATED are gated per source by `policy_decision_id` (DEC-016 Rahkaran, DEC-025 legacy workbooks) → always `RULE_NOT_APPROVED` in PHASE_00. Row status `NEW` added for "staged, not yet validated". Conflict queue: `OPEN → RESOLVED | DISMISSED` (docs/integration/README.md §6).

## 2. Business machines (from contract, PROPOSED)

| Machine | Transitions (as contracted) | Phase | Blocked guards |
|---|---|---|---|
| CustomerPO | DRAFT → VALIDATED → CONFIRMED → RELEASED_TO_PLAN → PARTIAL_FULFILLED → FULFILLED → CLOSED; side states PAUSED / ON_HOLD; change via AMENDMENT; cancellation with authorization | 02/09 | serial allocation at CONFIRMED: **BLOCKED (DEC-006)**; product code issue: **BLOCKED (DEC-005)**; FULFILLED→CLOSED: **BLOCKED (DEC-020)** |
| Serial (derived, not in contract text) | proposal: ALLOCATED → IN_PRODUCTION → PARTIALLY_DELIVERED → DELIVERED → CLOSED | 02/09 | entire machine **BLOCKED (DEC-006, DEC-020)** — to be proposed to the owner in 02.1, not invented here |
| TechnicalPackage | DRAFT → UNDER_REVIEW → APPROVED → RELEASED → SUPERSEDED; REJECTED → new revision (never mutate approved) | 03/04 | post-release change needs ECR/ECO |
| DieCandidate | EXTRACTED → TRIAGED → LINKED_TO_TRACKER → CODE_PENDING → ERP_MATCHED → ENGINEERING_APPROVED → TOOL_READY | 03 | LINKED_TO_TRACKER **BLOCKED (DEC-007)**; CODE_PENDING→ERP_MATCHED **BLOCKED (DEC-008)**; DXF revision choice **(DEC-029 PROPOSED)**; physical receipt owned by Warehouse |
| TimeStandard | DRAFT → REVIEWED → APPROVED → ACTIVE → SUPERSEDED; active immutable | 04 | APPROVED **BLOCKED (DEC-011, TC-DEC-03/04/05)**; shoe **(DEC-010)** |
| Reservation | REQUESTED → RESERVED / SHORTAGE → ISSUED / PARTIALLY_ISSUED → CLOSED / RELEASED; no negative or dual use | 06 | availability semantics **BLOCKED (DEC-015)**; UOM **(DEC-017)**; snapshot validity **(DEC-016)** |
| ProductionBatch | PLANNED → MATERIAL_READY → CUTTING → WORK_IN_PROGRESS → QC_PENDING → QC_RELEASED / REWORK / HOLD → FG_RECEIVED | 07/08 | SWU credit on rework **BLOCKED (DEC-012, TC-DEC-08)**; offline replay **(DEC-018)** |
| NCR | OPEN → CONTAINED → INVESTIGATED → ACTION_APPROVED → VERIFIED → CLOSED; closure needs evidence | 08 | — |
| QC grade (guard) | required vs actual grade compare | 08 | **BLOCKED (DEC-019)** |
| Shipment | DRAFT → DOCUMENT_MATCHED → PICKED → DISPATCHED → CUSTOMER_RECEIVED / RETURN_PENDING → RECONCILED | 09 | hold/unapproved grade cannot ship (QC-02); customer receipt rule **(DEC-020)** |

Unspecified in the contract (must be asked of the owner in the phase's xx.1, not assumed): reverse transitions (e.g. RELEASED_TO_PLAN → CONFIRMED), exits from PAUSED/ON_HOLD, Reservation SHORTAGE → RESERVED on receipt, Shipment RETURN_PENDING outcomes.

## 3. Project control (phase/step) — governance, not product
Enforced by `control/tools/status.py` `STEP_TRANSITIONS` (not part of the product): `TODO → IN_PROGRESS | BLOCKED`; `IN_PROGRESS → IN_REVIEW | BLOCKED`; `IN_REVIEW → PASS | REWORK | BLOCKED`; `REWORK → IN_PROGRESS | BLOCKED`; `BLOCKED → IN_PROGRESS | TODO`; `PASS → REWORK` (only via a recorded REV issue). 3 rework cycles → BLOCKED/escalate (CLAUDE.md). Phase states `NOT_STARTED, ACTIVE, GATE_PENDING, ACCEPTED, BLOCKED`; ACCEPTED only with employer signature (DEC-036). Open P0 decisions block phase start.
