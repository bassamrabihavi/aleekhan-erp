# Permission matrix — PHASE_01 platform actions (DRAFT v0.1)

**Status: PROPOSED — for employer approval (DEC-049). Not in force.** Until DEC-049 is approved the system
stays deny-all (DEC-047): no role can be activated (`activateRole` → 409 `RULE_NOT_APPROVED`, DEC-049).

Prepared in PHASE_01 / 01.1 (2026-11-04) from `handoff/05_SECURITY/ROLE_PERMISSION_MATRIX_FA.md` (PROPOSED,
"default deny … detailed design in Phase 1"), `SECURITY_BASELINE_FA.md` §1, DEC-003, DEC-042, DEC-043, DEC-047,
and the planned operations of `docs/api/openapi-draft.yaml` 0.5.0 (`x-aleekhan-permission`). Business-module
actions (orders, engineering, stock, QC, payroll, …) are **not** in this version; each module adds its rows in
its own xx.1 and the matrix version increases.

## 1. Principles (apply to every row)
1. **Deny by default.** A permission not listed for a role is denied; the backend checks action + record scope
   (+ field) on every request; hiding a button is not a control.
2. **Admin ≠ business approval (DEC-003).** Roles of kind TECHNICAL never contain a permission flagged
   `business_approval` (rows marked **BA**). The database refuses such a role (DATA_TABLE: Role CHECK).
3. **The owner may hold business roles only explicitly.** The owner/admin may assign himself a BUSINESS role;
   the assignment is flagged `self_assignment=true` and audited (DEC-003). Whether a second person must confirm
   it: DEC-032 item 1-c.
4. **No self-approval.** For rows marked **SoD** the deciding user must differ from the maker
   (requester / uploader / proposer / completer); the server answers 403 `SELF_APPROVAL_FORBIDDEN`.
5. **Holding an org position grants nothing.** Permissions come only from role assignments (DEC-043 tree is
   structure; its use in routing: DEC-048).
6. **MFA.** Rows marked **MFA** need a recent MFA verification (step-up window DEC-051) for every caller; in
   addition, MFA at login applies to the role list of DEC-003/SECURITY_BASELINE and to every login from outside
   the factory network (DEC-042). Factor type: DEC-050.
7. **Scope.** `●` = allowed within the assignment's scope (GLOBAL, ORG_UNIT, ORG_UNIT_SUBTREE); `○` = own
   records only (own tasks, own requests, own sessions); `—` = denied. Documents additionally respect the
   document's sensitivity class (S1–S3) and owner entity.

## 2. Proposed roles (PHASE_01)
| Code | Kind | Meaning (proposal) | Typical holder (employer decides) |
|---|---|---|---|
| `owner_admin` (OA) | TECHNICAL | system owner / main administrator: users, roles, org tree, parameter definitions | the employer (DEC-003) |
| `it_ops` (IT) | TECHNICAL | operations: health detail, jobs, safe cancel, sessions | IT staff (optional) |
| `security_auditor` (AUD) | TECHNICAL | read-only: audit query, identity/role read | auditor / reviewer (optional) |
| `management_viewer` (MGT) | BUSINESS | CEO/management read-only views (handoff matrix: "R health only") | management |
| `employee` (EMP) | BUSINESS | baseline for every personal account: own inbox, org tree, documents in scope | every person |
| `unit_manager` (MGR) | BUSINESS | tasks of the unit subtree: create, assign, verify-close, cancel | unit heads |
| `document_controller` (DOCC) | BUSINESS | register documents, upload revisions, submit for review | engineering/QA document owners |
| `document_approver` (DOCA) | BUSINESS | approve/reject document revisions | owners per document type |
| `config_approver` (CFGA) | BUSINESS | approve/publish parameter values | per owning module |
| `workflow_approver` (APR) | BUSINESS | decide approval requests in scope (module flows add their own approver roles later) | per flow |
| `operator_terminal` (OPT) | BUSINESS | shop-floor account: own tasks only, internal network only (DEC-042; account model DEC-052) | operators |

## 3. Matrix (platform actions of OpenAPI 0.5.0)
Flags: **MFA** = step-up required · **BA** = business-approval permission (never in TECHNICAL roles) ·
**SoD** = decider ≠ maker · **BLK** = operation blocked until the named decision (independent of the matrix).

| Permission (`x-aleekhan-permission`) | Operations | Flags | OA | IT | AUD | MGT | EMP | MGR | DOCC | DOCA | CFGA | APR | OPT |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| platform.identity.user.read | listUsers, getUser, getUserEffectivePermissions | | ● | ● | ● | — | — | — | — | — | — | — | — |
| platform.identity.user.create | createUser | MFA, BLK DEC-051 | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.user.update | updateUser | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.user.disable | disableUser, enableUser | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.user.unlock | unlockUser | MFA | ● | ● (option) | — | — | — | — | — | — | — | — | — |
| platform.identity.user.reset_password | resetUserPassword | MFA, BLK DEC-051 | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.user.reset_mfa | resetUserMfa | MFA, BLK DEC-050 | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.session.read | listUserSessions | | ● | ● | ● | — | — | — | — | — | — | — | — |
| platform.identity.session.revoke | revokeUserSessions | MFA | ● | ● | — | — | — | — | — | — | — | — | — |
| platform.identity.role.read | listPermissions, listRoles, getRole | | ● | ● | ● | — | — | — | — | — | — | — | — |
| platform.identity.role.manage | createRole, updateRole, activateRole, retireRole | MFA, BLK DEC-049 (activate) | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.assignment.read | listRoleAssignments, getRoleAssignment | | ● | — | ● | — | — | — | — | — | — | — | — |
| platform.identity.assignment.grant | createRoleAssignment, revokeRoleAssignment | MFA, BLK DEC-049; second approver DEC-032 | ● | — | — | — | — | — | — | — | — | — | — |
| platform.org.read | getOrgTree, list/get units, positions, position assignments | | ● | — | ● | ● | ● | ● | ● | ● | ● | ● | — |
| platform.org.manage | create/update/move/deactivate units, positions, position assignments | MFA, BLK DEC-048 (create) | ● | — | — | — | — | — | — | — | — | — | — |
| platform.workflow.task.read | listTasks, getTask | | — | — | — | — | ○ + own unit | ● subtree | ○ | ○ | ○ | ○ | ○ |
| platform.workflow.task.create | createTask | | — | — | — | — | ● own unit | ● | — | — | — | — | — |
| platform.workflow.task.work | startTask, completeTask, blockTask, unblockTask | | — | — | — | — | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| platform.workflow.task.assign | reassignTask | | — | — | — | — | — | ● | — | — | — | — | — |
| platform.workflow.task.verify | verifyCloseTask | SoD (≠ completer) | — | — | — | — | — | ● | — | — | — | — | — |
| platform.workflow.task.cancel | cancelTask | | — | — | — | — | ○ (created by me) | ● | — | — | — | — | — |
| platform.workflow.approval.read | listApprovals, getApproval, getWorkflowInstance | | — | — | ● | ● | ○ | ● | ○ | ● | ● | ● | — |
| platform.workflow.approval.request | withdrawRequest | | — | — | — | — | ○ | ○ | ○ | ○ | ○ | ○ | — |
| platform.workflow.approval.decide | approveRequest, rejectRequest | MFA, BA, SoD, BLK DEC-032 | — | — | — | — | — | — | — | — | — | ● | — |
| platform.workflow.definition.read | listWorkflowDefinitions, getWorkflowDefinition | | ● | — | ● | — | — | ● | — | — | — | ● | — |
| platform.workflow.instance.cancel | cancelWorkflowInstance | MFA | — | — | — | — | — | ● | — | — | — | — | — |
| platform.audit.read | listAuditEvents, getAuditEvent | MFA | ● | — | ● | — | — | — | — | — | — | — | — |
| platform.audit.integrity.read | getAuditIntegrity | | ● | ● | ● | — | — | — | — | — | — | — | — |
| platform.ops.health.read | getHealthDetail | | ● | ● | — | ● | — | — | — | — | — | — | — |
| platform.ops.job.read | listJobDefinitions, listJobs, getJob | | ● | ● | — | — | — | — | — | — | — | — | — |
| platform.ops.job.cancel | requestJobCancel (safe cancel only) | MFA | ● | ● | — | — | — | — | — | — | — | — | — |
| platform.document.read | listDocuments, getDocument, list/get revisions | | — | — | — | ● (S1–S2) | ● (S1) | ● (S1–S2) | ● | ● | — | — | ○ (approved, linked to own tasks) |
| platform.document.download | downloadDocumentRevision (CLEAN only) | | — | — | — | ● (S1–S2) | ● (S1) | ● (S1–S2) | ● | ● | — | — | ○ |
| platform.document.create | createDocument | | — | — | — | — | — | — | ● | — | — | — | — |
| platform.document.update | updateDocument, submitDocumentRevision | | — | — | — | — | — | — | ● | — | — | — | — |
| platform.document.upload | uploadDocumentRevision | BLK DEC-053 | — | — | — | — | — | — | ● | — | — | — | — |
| platform.document.approve | approveDocumentRevision, rejectDocumentRevision | MFA, BA, SoD (≠ uploader), BLK DEC-032 | — | — | — | — | — | — | — | ● | — | — | — |
| platform.config.parameter.read | listParameters, getParameter, listParameterValues | | ● | ● | ● | — | — | — | — | — | ● | — | — |
| platform.config.parameter.define | createParameterDefinition | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.config.parameter.propose | proposeParameterValue | | ● | ● | — | — | — | — | — | — | — | — | — |
| platform.config.parameter.publish | publishParameterValue | MFA, BA, SoD (≠ proposer), BLK DEC-032 | — | — | — | — | — | — | — | — | ● | — | — |
| platform.config.field.read | listDynamicFields, getDynamicField | | ● | ● | — | — | — | — | — | — | — | — | — |
| platform.config.field.define | createDynamicField, updateDynamicField (DRAFT only) | | ● | — | — | — | — | — | — | — | — | — | — |

Session-only operations (no permission row; any authenticated session acting on itself): `getCurrentSession`,
`listMySessions`, `revokeMySession`, `logout`, `getMe`, `getMyEffectivePermissions`, `changeMyPassword`
(BLK DEC-051), `startMfaEnrolment` / `confirmMfaEnrolment` / `verifyMfa` (BLK DEC-050). Pre-login:
`getLoginContext`, `login` (C-26).

Note on OA and audit: the owner reads the audit trail (MFA step-up), but there is no API to change or delete
audit events for anyone (append-only, DB triggers since 00.2).

## 4. Consistency with the handoff matrix (`ROLE_PERMISSION_MATRIX_FA.md`, column "Config / Jobs")
| Handoff row | Handoff value | This draft |
|---|---|---|
| IT Admin | C/U infra; safe job cancel with MFA/audit; X business approval | `owner_admin`/`it_ops`: TECHNICAL, `platform.ops.job.cancel` with MFA; no BA row |
| Planning | R health only | `platform.ops.health.read` can be added to the planning role when PHASE_05 defines it (not a PHASE_01 role) |
| CEO/Management | R health only | `management_viewer`: `platform.ops.health.read` |
| AI Copilot | X write/kill | no AI role in PHASE_01 (PHASE_11, DEC-023) |
| all other rows | X | no Config/Jobs permission |

## 5. Questions for the employer (answer with DEC-049)
1. Are the 11 roles and their names acceptable? Which are not needed now (e.g. `it_ops`, `security_auditor`)?
2. Should `it_ops` be able to unlock users (column IT, row `user.unlock`)?
3. Document visibility by sensitivity for EMP/MGR/MGT (S1 / S1–S2) — acceptable?
4. Which roles does the employer assign to himself at go-live (each one audited as self-assignment)?
5. Confirm that MFA step-up is required on all rows marked MFA, also inside the factory network.

## 6. Change control
A change to this matrix = new matrix version + reviewed commit + DEC entry; roles keep `matrix_version`. Seeds
for dev/test use synthetic users only (`محیط آزمایشی — داده ساختگی`).
