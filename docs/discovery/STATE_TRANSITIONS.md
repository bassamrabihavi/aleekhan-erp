# State transitions — PHASE_00 / 00.1

Status: DRAFT. Business state machines below are copied from `handoff/02_DOMAIN_CONTRACTS/STATE_EVENT_AND_API_CONTRACT.md` (all **PROPOSED**, "must be approved per owner"). They are documentation for later phases; none is implemented in PHASE_00. Guards that depend on an OPEN decision are marked **BLOCKED (DEC-xxx)**: the engine must refuse the transition with `RULE_NOT_APPROVED` + `decision_id` until the decision is approved.

General rules (all machines): server-side only; each transition = one DB transaction (state + audit + outbox event); `If-Match` row version; idempotency key on the command; illegal transition → `409 STATE_TRANSITION_NOT_ALLOWED`; terminal/approved states immutable (changes create a new revision).

## 1. Platform machines (PHASE_00/01, proposed by this step)

### 1.1 OutboxEvent delivery (PHASE_00 skeleton)
`PENDING → DISPATCHED → ACKED`; `PENDING|DISPATCHED → FAILED` (attempt++, backoff) `→ PENDING`; `FAILED → DEAD_LETTER` after max attempts (visible to Admin); `DEAD_LETTER → PENDING` only by authorised admin replay (audited); `DEAD_LETTER → DISCARDED` (terminal, PHASE_01 / 01.7, REV-0129) only by the owner (`owner_admin`) from the server console with a reason (audited `platform.outbox.discard`) — a discarded event is never delivered and no longer holds later events of its aggregate back. Replay runs from the server console (`manage.py outbox_dead_letter replay`) by an ACTIVE `owner_admin` or `it_ops` holder with a reason (employer decision 2026-11-10, REV-0133; audited `platform.outbox.replay`); discard stays owner-only. Consumers dedupe by `event_id`.
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

## 4. PHASE_01 platform machines (01.1, PROPOSED — implemented in 01.3; decisions updated in 01.2)

01.2 update (2026-11-04): the employer APPROVED DEC-032 and DEC-048..DEC-054. Guards that were **BLOCKED** by
them are now marked **DECIDED (DEC-xxx)** with the approved value; the numbers live in versioned parameters
(`platform_parameter_value`, migration 0010) and the DB guards of migration 0008 (docs/db/ERD.md section 6).
Still open and therefore still blocked: force kill (DEC-024, PHASE_11), the items of section 4.11, and the
01.2 open questions listed in section 4.12.

Status: DRAFT/PROPOSED. Refines §1.3 (Job), §1.4 (ApprovalTask → split into §4.3 WorkTask and §4.4
ApprovalRequest, CONFLICTS C-30; `OPEN` of §1.4 is `PENDING` here) and §1.5 (User → §4.1). The general rules at
the top of this file apply to every machine (one transaction = state + audit + outbox; If-Match; idempotency
key except the authentication ceremonies of `x-aleekhan-conventions.idempotency_exempt`; illegal move →
409 `STATE_TRANSITION_NOT_ALLOWED`). A guard that depends on an unapproved rule is **BLOCKED (DEC-xxx)**: the
engine refuses with 409 `RULE_NOT_APPROVED` + `decision_id` and changes nothing. "TECH" marks a technical
default (no business meaning, ops-confirmable). Every transition records actor, reason (where listed),
request_id and session handle in the audit event.

### 4.1 User account
| From | To | Trigger / actor | Guards |
|---|---|---|---|
| — | CREATED | `createUser` (holder of `platform.identity.user.create`, MFA step-up) or the console bootstrap command for the first owner (audited as system bootstrap) | username unique; reason; initial one-time credential **DECIDED (DEC-051)**: set by the admin, valid 72 h (`password_initial_validity_hours`), forced change at first login |
| CREATED | ACTIVE | first successful login + password changed | password policy **DECIDED (DEC-051)**: min 8, upper-case + digit + symbol, rotation 90 days (history of hashes in `platform_password_history`); MFA enrolment if MFA is required for the user (role list DEC-049, outside access DEC-042) — factor **DECIDED (DEC-050)**: TOTP + 10 recovery codes |
| ACTIVE | LOCKED | system, after N failed logins / MFA codes in a window | thresholds **DECIDED (DEC-051)**: 5 failures in 15 min -> automatic lock 15 min + event on pages 36/46 (`lockout_*` parameters) |
| LOCKED | ACTIVE | `unlockUser` (reason, MFA step-up) or automatic expiry of `locked_until` | auto-expiry **DECIDED (DEC-051)**: `locked_until` = lock + 15 min; `it_ops` may also unlock (DEC-049) |
| CREATED, ACTIVE, LOCKED | DISABLED | `disableUser` (reason, MFA step-up) | revokes all sessions in the same transaction; refused if the target is the last ACTIVE holder of `platform.identity.user.disable` (lock-out protection, TECH) |
| DISABLED | ACTIVE | `enableUser` (reason, MFA step-up) | sessions stay revoked; `must_change` set if the credential is older than policy (DEC-051) |

No delete, no self-registration, no directory sync (DEC-003). `resetUserPassword` / `resetUserMfa` do not change
the state; they revoke sessions and set `must_change` / remove the factor (DECIDED DEC-051 / DEC-050: admin MFA reset needs reason + admin MFA + audit).

### 4.2 Session
| From | To | Trigger | Guards / notes |
|---|---|---|---|
| — | ACTIVE | `login` when MFA does not apply | network policy: OPERATOR / INTERNAL_ONLY accounts from EXTERNAL or UNKNOWN zone → 403 `NETWORK_POLICY_DENIED`, no session (DEC-042; zone **DECIDED (DEC-052)**: explicit CIDR list in server config only, client IP from the trusted proxy, unknown = outside, VPN = outside; personal operator accounts only) |
| — | MFA_PENDING | `login` when MFA applies (role list or outside login) | MFA_PENDING accepts only `verifyMfa` and `logout` |
| MFA_PENDING | ACTIVE | `verifyMfa` | factor **DECIDED (DEC-050)**: TOTP (replay guard `last_used_step`); session id rotated |
| MFA_PENDING | EXPIRED | timeout | TECH 5 min |
| ACTIVE | EXPIRED | idle or absolute timeout | durations **DECIDED (DEC-051)**: users idle 2 h / absolute 12 h; operators idle 8 h / absolute 12 h (employer answer Q-0102, 2026-11-05), internal network only |
| ACTIVE, MFA_PENDING | LOGGED_OUT | `logout` | — |
| ACTIVE, MFA_PENDING | REVOKED | `revokeMySession`, `revokeUserSessions`, user DISABLED, password change/reset, MFA reset | reason stored for admin revoke |

Step-up (operations with `x-aleekhan-mfa-step-up`) does not change the state; it updates `mfa_verified_at`.
Window **DECIDED (DEC-051)**: 15 minutes (also inside the factory network, DEC-049). Concurrent session limit
**DECIDED (DEC-051)**: 3; on the 4th login the OLDEST live session is ended automatically (state REVOKED,
audited; parameter `session_limit_exceeded_action = END_OLDEST_SESSION`, employer answer Q-0101, 2026-11-05;
engine logic in 01.3).

### 4.3 WorkTask (operational task, page 39)
| From | To | Trigger | Guards |
|---|---|---|---|
| — | OPEN / ASSIGNED | `createTask` (ASSIGNED when the assignee is a user) | assignee within the creator's scope |
| OPEN, ASSIGNED, IN_PROGRESS, BLOCKED | ASSIGNED | `reassignTask` | reason; new assignee within scope; cross-unit reassignment recorded with both units |
| OPEN, ASSIGNED | IN_PROGRESS | `startTask` by the assignee (or a member of the assigned unit) | — |
| IN_PROGRESS | BLOCKED | `blockTask` | reason; optional blocking reference |
| BLOCKED | IN_PROGRESS | `unblockTask` | — |
| IN_PROGRESS | DONE | `completeTask` | DONE ≠ CLOSED (catalog invariant) |
| DONE | CLOSED | `verifyCloseTask` | verifier ≠ completer; verifier holds `platform.workflow.task.verify` in scope |
| any non-terminal | CANCELLED | `cancelTask` | reason; tasks owned by a workflow instance are cancelled only through §4.5 |

Terminal: CLOSED, CANCELLED. Reopen of DONE by the verifier is not in the 0.5.0 contract (proposal for 01.3 if the
owner asks). SLA clock and SLA pause: no approved rule exists (catalog: "Pause only per approved rule") → not
implemented in PHASE_01; `due_at` is informational only.

### 4.4 ApprovalRequest (maker-checker)
| From | To | Trigger | Guards |
|---|---|---|---|
| — | PENDING | raised by the owning use case (document approval, parameter publish, role grant if DEC-032 requires) | one PENDING per (resource, revision, action); which actions require it **DECIDED (DEC-032)**: document revision approval, BUSINESS_RULE parameter publish, assignment of roles holding a business-approval permission; route **DECIDED (DEC-048)**: role + unit scope only in PHASE_01 (`route_kind = ROLE_UNIT_SCOPE`) |
| PENDING | APPROVED | `approveRequest` | decider ≠ requester (403 `SELF_APPROVAL_FORBIDDEN`); decider in the resolved route and holds `platform.workflow.approval.decide` in scope; technical-admin roles never qualify (DEC-003); `resource_revision` equals the request revision; MFA step-up; one-time |
| PENDING | REJECTED | `rejectRequest` | same decider rules; note mandatory |
| PENDING | WITHDRAWN | `withdrawRequest` by the requester, or the owning workflow is cancelled | — |
| PENDING | SUPERSEDED | system: the resource got a new revision | approval never carries over to a new revision |
| PENDING | EXPIRED | system at `expires_at` | expiry period **DECIDED (DEC-032)**: 30 days (`approval_request_expiry_days`; `expires_at` NOT NULL) |

Terminal: all except PENDING. Single-person deadlock (requester is the only eligible approver, e.g. the owner):
the request stays PENDING; **DECIDED (DEC-032, D1)**: never self-approved; an emergency approval needs a later decision. Never auto-approve.

### 4.5 WorkflowInstance and cancellation
| From | To | Trigger | Guards / effects |
|---|---|---|---|
| — | RUNNING | owning use case starts a definition | definition ACTIVE; instance pins the definition version |
| RUNNING | WAITING | step waits for a task/approval | — |
| WAITING | RUNNING | the awaited task CLOSED / approval decided | — |
| RUNNING, WAITING | COMPLETED | last step done | — |
| RUNNING, WAITING | CANCEL_REQUESTED | `cancelWorkflowInstance` | reason; `platform.workflow.instance.cancel` in scope; MFA step-up |
| CANCEL_REQUESTED | COMPENSATING | definition has compensation steps for completed steps | in the same transaction: PENDING approvals → WITHDRAWN, open tasks → CANCELLED |
| CANCEL_REQUESTED, COMPENSATING | CANCELLED | no (more) compensation | completed side effects are reversed only by compensation steps (new records), never by deleting rows |
| RUNNING, WAITING, COMPENSATING | FAILED | unrecoverable error | failure + partial compensation recorded; visible on page 36; manual resolution task created |

PHASE_01 ships no business workflow definition; definitions for module flows arrive with their phases. The
cancellation machine is implemented and tested with a synthetic test-only definition.

### 4.6 Document revision and upload quarantine (SEC-03)
Scan status (file safety), independent of the approval status:

| From | To | Trigger | Guards |
|---|---|---|---|
| — | QUARANTINED | `uploadDocumentRevision` | stored under a random key in private storage, sha256 computed server-side, never executed/rendered; **DECIDED (DEC-053)**: PDF, PNG, JPG, DXF, XLSX without macros (never XLSM/DOCM/EXE/scripts), max 25 MB (`document_upload_max_bytes`), encrypted server folder |
| QUARANTINED | SCANNING | scanner job picks it up | scanner **DECIDED (DEC-053)**: ClamAV in an isolated container on the same server + magic bytes; scanner unavailable → stays QUARANTINED (never auto-CLEAN) |
| SCANNING | CLEAN | scanner verdict clean + magic-bytes type matches the allowlist | — |
| SCANNING | REJECTED | malware/type mismatch/parser bomb | finding stored (no file content in the finding); file bytes purged after 30 days of quarantine, metadata + hash kept (DEC-053) |

Revision status (business approval):

| From | To | Trigger | Guards |
|---|---|---|---|
| — | WORKING | upload accepted | — |
| WORKING | IN_REVIEW | `submitDocumentRevision` | scan_status CLEAN |
| IN_REVIEW | APPROVED | `approveDocumentRevision` (raises/uses §4.4) | approver ≠ uploader; MFA step-up; maker-checker **DECIDED (DEC-032)**; approvers = `document_approver` role in scope (DEC-049) |
| IN_REVIEW | REJECTED | `rejectDocumentRevision` | reason |
| WORKING | REJECTED | system when scan REJECTED | — |
| APPROVED | SUPERSEDED | system when a newer revision of the same document is APPROVED | approved bytes and metadata immutable |

Download (`downloadDocumentRevision`) only when scan_status = CLEAN; otherwise 409 `FILE_NOT_RELEASED`.

### 4.7 Job run (page 36; Gate-1 "Job kill تحت مجوز و دلیل")
| From | To | Trigger | Guards |
|---|---|---|---|
| — | QUEUED | system / owning use case | unique task key (idempotent enqueue) |
| QUEUED | RUNNING | worker start | — |
| RUNNING | SUCCEEDED / FAILED | worker end | error_code only, no exception text |
| QUEUED | CANCELLED | `requestJobCancel` before start | as below |
| RUNNING | CANCEL_REQUESTED | `requestJobCancel` | `platform.ops.job.cancel`; reason (≥ 3 chars); MFA step-up; job type `cancellable` and not `protected` (else 409 `JOB_PROTECTED`) |
| CANCEL_REQUESTED | CANCELLED | job reaches its next checkpoint and stops safely | — |
| CANCEL_REQUESTED | SUCCEEDED / FAILED | job ended before a checkpoint | outcome recorded as "cancel too late" |

Force kill: not in the contract; **BLOCKED (DEC-024)**, PHASE_11 (SEC-02). Protected types (migrations,
restore, backup) are seeded `protected=true`; the complete protected list is DEC-024. A retry is a new run
(new `job_id`), not a transition.

### 4.8 Role and RoleAssignment
| Machine | Transitions | Guards |
|---|---|---|
| Role | DRAFT → ACTIVE → RETIRED (DB-enforced since 01.2 rework, REV-0105: no other move; RETIRED terminal; kind/matrix_version frozen after DRAFT) | ACTIVE only if the permission set is in the approved matrix **DECIDED (DEC-049, v1.0)**; TECHNICAL roles never contain business-approval permissions (DEC-003); RETIRED requires no ACTIVE assignment |
| RoleAssignment | — → ACTIVE, or — → PENDING_APPROVAL → ACTIVE / REVOKED; ACTIVE → EXPIRED (system at `valid_to`); ACTIVE → REVOKED (`revokeRoleAssignment`, reason) | role ACTIVE; reason; self-assignment allowed only explicitly and always flagged (DEC-003); second approver **DECIDED (DEC-032)**: roles holding a business-approval permission wait PENDING_APPROVAL until a second eligible person approves (DB guard `ck_role_assignment_second_approval`) |

### 4.9 Parameter value revision (page 42)
`DRAFT → PENDING_APPROVAL → PUBLISHED | REJECTED`; `PUBLISHED → SUPERSEDED` (a newer revision becomes
effective). TECHNICAL parameters: DEC-032 requires maker-checker only for BUSINESS_RULE publish, so TECHNICAL publish has no
second person. OWNER_POLICY values (seeded DEC-048..054 values): proposed and published by the owner alone,
only by a holder of `owner_admin`, with reason, MFA step-up and audit (Q-0103, employer answer 2026-11-05). BUSINESS_RULE
parameters: publish **BLOCKED** by their own `decision_id` (e.g. DEC-016 thresholds) until that decision is
APPROVED. History is never rewritten; `effective_from` in the past is refused (TECH).

### 4.10 Org unit / position (effective-dated)
`ACTIVE → INACTIVE` (deactivate with effective date - never back-dated: `effective_from >= now - 60 s`, the
60 s being a TECHNICAL clock tolerance; a late change records the real date only in the audit reason
(employer answer 2026-11-05, REV-0107); unit must have no ACTIVE position; position must have no
current holder). `moveOrgUnit` closes the current parent link and opens a new one at `effective_from` (acyclic
check). **DECIDED (DEC-048)**: unit types COMPANY/DEPARTMENT/SECTION/LINE (admin may add), max depth 6, one
PRIMARY position per person + ACTING with an end date, reports-to between positions, edited by the owner/admin
only in PHASE_01, history with effective dates. No transition grants a permission.

### 4.11 Unspecified (ask the owner, do not assume)
Reopen of a DONE task; SLA clocks; delegation of approvals during absence (out of office); emergency access
(break-glass) **DECIDED (DEC-054)**: console recovery command now (audited), sealed emergency account before
production (schema flag + usage record in 01.2, no API); notification channels outside the app.

### 4.12 Open questions raised by 01.2 (not decided; the engine refuses, it does not guess)
| ID | Question | Proposed safe behaviour for 01.3 until the employer answers (proposal only) |
|---|---|---|
| Q-0101 | DEC-051 "max 3 concurrent sessions": refuse the 4th login, or end the oldest session? | **ANSWERED 2026-11-05**: end the oldest session automatically, audited (`session_limit_exceeded_action`) |
| Q-0102 | DEC-051 gives operators idle 8 h but no absolute session limit | **ANSWERED 2026-11-05**: 12 h (`session_operator_absolute_hours`) |
| Q-0103 | Does publishing a changed OWNER_POLICY value (e.g. lockout threshold) need a second person? | **ANSWERED 2026-11-05**: no second person; only a holder of `owner_admin` proposes/publishes, with reason, MFA step-up and audit (DB: `ck_parameter_value_owner_policy`; MFA/audit in 01.3/01.4) |
| Q-0104 | DEC-053 "25 مگابایت": 25 000 000 or 26 214 400 bytes? | **ANSWERED 2026-11-05**: 26 214 400 bytes (binary, as Windows shows it) |
| Q-0105 | Password history depth for the 90-day rotation (how many previous passwords are refused) | **ANSWERED 2026-11-05**: the last 5 passwords are refused (`password_history_reuse_depth`) |
| Q-0106 | May a position have several PRIMARY holders at once (e.g. many operators in one position)? | **ANSWERED 2026-11-05**: yes, up to `platform_position.primary_capacity` (default 1; unit-head positions always 1); one PRIMARY position per person stays |

All 01.2 questions Q-0101..Q-0106 are answered (employer, 2026-11-05).


### 4.13 Implemented by the 01.3 engine (2026-11-05)
All machines of 4.1-4.10 are implemented as `engine.state.StateMachine` definitions in their service modules
(`identity/auth.py` USER, `identity/sessions.py` SESSION, `workflow/tasks.py`, `workflow/approvals.py`,
`workflow/instances.py`, `documents/service.py` revision + scan, `jobs/service.py`, `identity/roles.py`,
`params/service.py`) and tested pair by pair. Engine-level additions and interpretations (CREATED -> LOCKED,
SCANNING -> QUARANTINED when the scanner is unavailable, QUEUED -> CANCELLED, login MFA role list, "own unit")
are listed in `docs/engine/PHASE01_ENGINE.md` section 3. REV-0109 (employer 2026-11-05): person-to-position
assignments are never back-dated either (migration 0011).

## 5. PHASE_02 machines (02.1, PROPOSED — engine in 02.3)

Sources: `STATE_EVENT_AND_API_CONTRACT.md` (CustomerPO), §2 above, CONFLICTS C-47…C-76, `DATA_TABLE.md` PHASE_02.
Rules for every machine: transitions run in ONE transaction with the audit record and the outbox event (UnitOfWork,
00.3); every action endpoint needs `Idempotency-Key` + `If-Match` (row version); an action that is not listed is
409 `STATE_TRANSITION_NOT_ALLOWED`; a guard whose rule is not approved is 409 `RULE_NOT_APPROVED` with its
`decision_id`; nobody approves their own request (DEC-032 pattern, `SELF_APPROVAL_FORBIDDEN`). Permission ids are
the proposals of `docs/api/openapi-draft.yaml` 0.7.0-draft; no role holds them before **DEC-057**.

### 5.1 CustomerOrder (PO header)
| From | Action (operation) | To | Guard | Event |
|---|---|---|---|---|
| — | `createCustomerOrder` | DRAFT | customer ACTIVE; `order_no` generated by the system (technical sequence, not the serial) | `CustomerOrderDrafted` (new, proposed) |
| DRAFT | `updateCustomerOrder`, `addCustomerOrderLine`, `updateCustomerOrderLine`, `removeCustomerOrderLine` | DRAFT | edits only in DRAFT | `CustomerOrderDraftChanged` (new) |
| DRAFT | `validateCustomerOrder` | VALIDATED | ≥ 1 line; every line has an ACTIVE style revision, quantity > 0, uom of the product type (DEC-058, DB trigger 0020); product code (if given) passes `validateProductCode`; duplicate PO number warning acknowledged | `CustomerOrderValidated` (new) |
| VALIDATED | `reopenCustomerOrder` | DRAFT | reason | `CustomerOrderReopened` (new) |
| VALIDATED | `confirmCustomerOrder` | CONFIRMED | **DEC-057** (who confirms); writes `CustomerOrderVersion` v1; serial allocation per line: at confirmation or separately = **DEC-006 q.2** | `CustomerOrderConfirmed` (handoff catalogue) |
| CONFIRMED | `releaseCustomerOrderToPlan` | RELEASED_TO_PLAN | every non-cancelled line has a serial (if DEC-006 answers "serial mandatory"); **DEC-057** (planning role); consumer is PHASE_05 | `CustomerOrderReleasedToPlan` (new) |
| DRAFT, VALIDATED | `cancelCustomerOrder` | CANCELLED | reason; nothing allocated yet | `CustomerOrderCancelled` (new) |
| CONFIRMED, RELEASED_TO_PLAN | change request `CANCEL_ORDER` APPLIED | CANCELLED | **DEC-059** (allowed? WIP disposition is PHASE_05/07) | `CustomerOrderChanged` + `CustomerOrderCancelled` |
| CONFIRMED, RELEASED_TO_PLAN | change request `HOLD` APPLIED | ON_HOLD | reason; **DEC-059** (who may hold; PAUSED vs ON_HOLD meaning) | `CustomerOrderChanged` |
| ON_HOLD / PAUSED | change request `RESUME` APPLIED | the state before the hold | **DEC-059** (exit rule; the contract does not define it) | `CustomerOrderChanged` |
| RELEASED_TO_PLAN | (PHASE_07/09) | PARTIAL_FULFILLED → FULFILLED → CLOSED | written only by later phases; FULFILLED → CLOSED BLOCKED (DEC-020) | — |

Reverse transitions not listed (for example RELEASED_TO_PLAN → CONFIRMED) do not exist until the owner asks for them
(§2 "Unspecified in the contract").

### 5.2 CustomerOrderLine
| From | Action | To | Guard |
|---|---|---|---|
| — | `addCustomerOrderLine` (order DRAFT) or change request `ADD_LINE` APPLIED | OPEN | one style per line; `line_no` = next free number of the order, never re-used |
| OPEN | order confirmed | CONFIRMED | order transition 5.1 |
| CONFIRMED | `allocateSerial` | SERIAL_ALLOCATED | **BLOCKED (DEC-006)**; idempotent; exactly one serial + snapshot v1 (ID-02/03/04) |
| OPEN | `removeCustomerOrderLine` (order DRAFT) | REMOVED | the row stays (history); `line_no` is not re-used |
| CONFIRMED, SERIAL_ALLOCATED | change request `CANCEL_LINE` APPLIED | CANCELLED | **DEC-059**; the serial moves to CANCELLED (5.4), its number is never re-used |
| CONFIRMED, SERIAL_ALLOCATED | change request `QTY_CHANGE` / `DUE_DATE_CHANGE` APPLIED | same state | new order version; new serial snapshot version; **DEC-059** (does a quantity change keep the serial?) |

### 5.3 CodeRuleRevision (product_code namespace)
| From | Action | To | Guard |
|---|---|---|---|
| — | `createCodeRuleRevision` | DRAFT | **BLOCKED (DEC-005)**: the `rule_spec` schema does not exist before the extraction |
| DRAFT | `submitCodeRuleRevision` | IN_REVIEW | `source_workbook_sha256` = registered v2 hash (DEC-037); ≥ 20 golden cases per covered family (Gate) all reproduce; creates an approval request |
| IN_REVIEW | `approveCodeRuleRevision` | APPROVED | approver ≠ maker (DEC-032); MFA step-up; the approver role is **DEC-057**; DEC-005 must be APPROVED |
| IN_REVIEW | `rejectCodeRuleRevision` | REJECTED | reason; a correction is a new revision (never an edit of the rejected one) |
| APPROVED | `activateCodeRuleRevision` | ACTIVE | at most one ACTIVE revision per covered class; the previous one becomes RETIRED in the same transaction |
| ACTIVE | superseded by a newer ACTIVE revision | RETIRED | codes issued under it keep their `rule_revision_id` |

### 5.4 Serial
| From | Action | To | Guard |
|---|---|---|---|
| — | `allocateSerial` | ALLOCATED | **BLOCKED (DEC-006)**; line CONFIRMED; no serial yet; namespace ACTIVE; number from the namespace under a row lock or a DB sequence (never `MAX()+1`); snapshot v1 + outbox `SerialAllocated` in the same transaction |
| ALLOCATED | change request applied | ALLOCATED (new snapshot version) | snapshot versions only grow; old versions immutable |
| ALLOCATED | line cancelled (5.2) | CANCELLED | **DEC-059**; the number is never re-used (INV-02-05) |
| ALLOCATED | production starts (PHASE_07) | IN_PRODUCTION | later phase; listed so the enum is reserved, not implemented in PHASE_02 |
| IN_PRODUCTION | partial/complete delivery (PHASE_09) | PARTIALLY_DELIVERED → DELIVERED → CLOSED | later phases; close rule **BLOCKED (DEC-020)** |

PHASE_02 implements ALLOCATED and CANCELLED only (after DEC-006/DEC-059). The other values are reserved in the
contract enum so later phases add no breaking change.

### 5.5 OrderChangeRequest (page 33, PHASE_02 part per C-61)
| From | Action | To | Guard |
|---|---|---|---|
| — | `createChangeRequest` | DRAFT | order is CONFIRMED / RELEASED_TO_PLAN / ON_HOLD / PAUSED (DRAFT orders are edited directly); `base_order_version` = current version; kind allowed in that state: **DEC-059** |
| DRAFT | `submitChangeRequest` | SUBMITTED | impact computed (PHASE_02 part: lines, serials, snapshots touched; other modules "not available"); creates an approval request; *PROPOSED, not decided (REV-0203): only one SUBMITTED/APPROVED request per order - not enforced in 02.2* |
| DRAFT, SUBMITTED | `withdrawChangeRequest` | WITHDRAWN | requester only; reason |
| SUBMITTED | `decideChangeRequest` (approve) | APPROVED | approver ≠ requester; approver role: **DEC-057**; kinds allowed: **DEC-059** |
| SUBMITTED | `decideChangeRequest` (reject) | REJECTED | reason |
| APPROVED | `applyChangeRequest` | APPLIED | `base_order_version` still current (else 409 `STATE_TRANSITION_NOT_ALLOWED`, re-submit on the new version); writes `CustomerOrderVersion` n+1, new serial snapshots, `CustomerOrderChanged` |
| SUBMITTED, APPROVED | expiry period | EXPIRED | *PROPOSED, not decided (REV-0203): DEC-032's 30 days apply to platform approval requests, not to order change requests; no period is enforced in 02.2* |

ECR/ECO (engineering changes) and WIP/material/cost dispositions are not part of this machine (C-61).

### 5.6 ProductCode registry
| From | Action | To | Guard |
|---|---|---|---|
| — | Rahkaran item import (PHASE_06 source) or legacy evidence | ACTIVE + ERP_MATCHED (Rahkaran) / RESERVED + ERP_PENDING (Planning only) | provenance IMP/LEG; never auto-linked to a style (similarity only suggests) |
| — | `issueProductCode` | RESERVED + ERP_PENDING | **BLOCKED (DEC-005)**: ACTIVE CodeRuleRevision for the class; uniqueness in the namespace (UNIQUE constraint; race → one winner, the other 409); idempotent |
| RESERVED | Rahkaran import shows the same code | ACTIVE + ERP_MATCHED | exact match in the `product_code` namespace only (SOURCE_MAPPING §6) |
| RESERVED | Rahkaran import shows the code with a different description/class | DISPUTED | conflict item raised (`DataConflictRaised`); a human decides |
| ACTIVE | retired in Rahkaran | RETIRED | import evidence; existing serials keep the code |

### 5.7 Not specified — ask the owner, do not assume
- Exits from ON_HOLD/PAUSED and the difference between the two (DEC-059).
- Cancellation after CONFIRMED and what happens to the allocated serial (DEC-059, DEC-006).
- Whether a quantity increase above some size becomes a new line or a new serial (DEC-059 q.4).
- Whether codes are proposed by our system or always created in Rahkaran first (DEC-005 Q-B; C-75).
- Who may confirm an order, release it to planning and approve changes (DEC-057).

### 5.8 Events (outbox) — names for docs/integration/EVENT_CATALOGUE.md in 02.6
From the handoff catalogue: `CustomerOrderConfirmed`, `SerialAllocated`, `CustomerOrderChanged`, `DataConflictRaised`,
`ImportBatchValidated`. Proposed new: `CustomerOrderDrafted`, `CustomerOrderValidated`, `CustomerOrderReleasedToPlan`,
`CustomerOrderCancelled`, `CustomerOrderLineCancelled`, `SerialCancelled`, `ProductCodeReserved`,
`ProductCodeErpMatched`, `CodeRuleRevisionActivated`, `ChangeRequestSubmitted`, `ChangeRequestDecided`.
Payloads carry identifiers and versions only. Customer names stay out of generic payloads; consumers
read the owning API.

### 5.9 02.2 result (DB, migrations 0019-0022)
The machines above are enforced in the database as decided on 2026-11-12 (ERD section 7): order DRAFT ->
VALIDATED -> CONFIRMED (version 1, every line gets its serial in the same transaction) -> RELEASED_TO_PLAN; a single
ON_HOLD resuming to `status_before_hold`; cancel only from DRAFT/VALIDATED, or from CONFIRMED with a version bump
(before release). Line OPEN -> CONFIRMED (with serial) / REMOVED; CONFIRMED -> CANCELLED (serial CANCELLED in the
same transaction). Serial ALLOCATED -> CANCELLED only in PHASE_02. Change request DRAFT -> SUBMITTED -> APPROVED /
REJECTED / WITHDRAWN / EXPIRED -> APPLIED (writes order version base + 1). Code rule DRAFT -> IN_REVIEW -> APPROVED
-> ACTIVE -> RETIRED / REJECTED. Who may act (DEC-057) and the error codes are the 02.3 engine.
