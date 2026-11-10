# Permission matrix — PHASE_01 platform actions (APPROVED v1.2)

**Status: APPROVED v1.2 — DEC-049 (v1.0, employer بسام ربیهاوی, 2026-11-04) + DEC-056 (v1.1, 2026-11-06) + DEC-056
extension (v1.2, 2026-11-10). v1.0 in force from PHASE_01 / 01.2; v1.1 from PHASE_01 / 01.5 (migration
`platform_core.0014_dec056_owner_approval_rights`); v1.2 from PHASE_01 / 01.6 (migration
`platform_core.0015_dec056_matrix_v12`).**

**Change note v1.2 (DEC-056 extension, employer 2026-11-10, REV-0125).** Two more cells of the `owner_admin` (OA)
column change from `—` to `●`: `platform.document.approve` (the owner approves / rejects document revisions
directly) and `platform.config.parameter.publish` (the owner publishes / rejects proposed values of
**BUSINESS_RULE** parameters directly; for TECHNICAL values his grant does not count — the engine answers 403
`ACCESS_DENIED` — because the decision names BUSINESS_RULE publish only). The explicit exception of principle 2
now covers exactly three pairs (`owner_admin` + `platform.workflow.approval.decide`, `platform.document.approve`,
`platform.config.parameter.publish`), in the engine (`authz.policy.OWNER_BA_ACTIONS`) and in the DB guard
`ck_role_technical_no_business_approval`. Unchanged: maker ≠ checker — the owner never decides his own request,
his own upload or his own proposal (also no rejection of his own BUSINESS_RULE proposal), except the one-time
DEC-055 bootstrap approval; `it_ops` and `security_auditor` hold no business approval; the owner gets **no**
`platform.document.read` / `download` (not part of the decision: he decides from the approval request; see the
01.6 report, open question). `owner_admin` carries `matrix_version = 1.2`; the other ten roles keep `1.0`.

**Change note v1.1 (DEC-056, APPROVED 2026-11-06).** Two cells of the `owner_admin` (OA) column change from `—` to
`●`: `platform.workflow.approval.read` (the owner reads every approval request; his assignment is GLOBAL) and
`platform.workflow.approval.decide` (the owner decides approval requests directly, without assigning himself a
separate approver role). Principle 2 gets exactly one explicit exception (the pair `owner_admin` +
`platform.workflow.approval.decide`), in the engine and in the DB guard `ck_role_technical_no_business_approval`.
Unchanged: maker ≠ checker (principle 4) — the owner never decides his own request, except the one-time
DEC-055 bootstrap approval; `it_ops` and `security_auditor` hold no business approval; `document.approve` and
`config.parameter.publish` are not granted to the owner (in v1.1; granted by v1.2 above). Every owner decision is audited with the deciding role
(`scope.via_role`). Consequence (DEC-032 read literally): `owner_admin` now holds a business-approval permission,
so an in-app grant of `owner_admin` to another person waits PENDING_APPROVAL for a second eligible person; the
console bootstrap of the first owner (DEC-049 item 4 / DEC-054 C) is not an in-app grant and is exempt. Only
`owner_admin` carries `matrix_version = 1.1`; the other ten roles are unchanged and keep `1.0`.

Approved content = the draft v0.1 below without a change of any cell; the employer's answers are recorded in
section 5. Seeded by migration `platform_core.0010_seed_phase01_catalogue` (roles carry `matrix_version = 1.0`);
the seed is compared cell by cell with this file by
`backend/platform_core/tests/test_phase01_schema.py::test_seeded_grants_equal_the_approved_matrix_document`.
Any change = new matrix version + reviewed commit + DEC entry (section 6). The file name keeps the `_DRAFT`
suffix only so that existing references stay valid.

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
   **Single exception (DEC-056, v1.1 / v1.2):** `owner_admin` holds `platform.workflow.approval.decide`,
   `platform.document.approve` and `platform.config.parameter.publish` (BUSINESS_RULE values only); maker ≠
   checker (principle 4) still applies to the owner.
3. **The owner may hold business roles only explicitly.** The owner/admin may assign himself a BUSINESS role;
   the assignment is flagged `self_assignment=true` and audited (DEC-003). DEC-032 (APPROVED): an assignment
   of a role holding a **BA** permission waits `PENDING_APPROVAL` until a second eligible person approves it
   (never self-approved; DB guard `ck_role_assignment_second_approval`).
4. **No self-approval.** For rows marked **SoD** the deciding user must differ from the maker
   (requester / uploader / proposer / completer); the server answers 403 `SELF_APPROVAL_FORBIDDEN`.
5. **Holding an org position grants nothing.** Permissions come only from role assignments (DEC-043 tree is
   structure; DEC-048 APPROVED: PHASE_01 routing = role + unit scope only).
6. **MFA.** Rows marked **MFA** need a recent MFA verification (step-up window 15 min, DEC-051; also inside the
   factory network, DEC-049 item 5) for every caller; in
   addition, MFA at login applies to the role list of DEC-003/SECURITY_BASELINE and to every login from outside
   the factory network (DEC-042). Factor: TOTP (DEC-050).
7. **Scope.** `●` = allowed within the assignment's scope (GLOBAL, ORG_UNIT, ORG_UNIT_SUBTREE); `○` = own
   records only (own tasks, own requests, own sessions); `—` = denied. Documents additionally respect the
   document's sensitivity class (S1–S3) and owner entity.

## 2. Roles (PHASE_01, approved)
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
**SoD** = decider ≠ maker. (v0.1 also marked **BLK** = blocked until a decision; all those decisions are
APPROVED since 2026-11-04, so no row is blocked in v1.0.)

| Permission (`x-aleekhan-permission`) | Operations | Flags | OA | IT | AUD | MGT | EMP | MGR | DOCC | DOCA | CFGA | APR | OPT |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| platform.identity.user.read | listUsers, getUser, getUserEffectivePermissions | | ● | ● | ● | — | — | — | — | — | — | — | — |
| platform.identity.user.create | createUser | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.user.update | updateUser | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.user.disable | disableUser, enableUser | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.user.unlock | unlockUser | MFA | ● | ● (option) | — | — | — | — | — | — | — | — | — |
| platform.identity.user.reset_password | resetUserPassword | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.user.reset_mfa | resetUserMfa | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.session.read | listUserSessions | | ● | ● | ● | — | — | — | — | — | — | — | — |
| platform.identity.session.revoke | revokeUserSessions | MFA | ● | ● | — | — | — | — | — | — | — | — | — |
| platform.identity.role.read | listPermissions, listRoles, getRole | | ● | ● | ● | — | — | — | — | — | — | — | — |
| platform.identity.role.manage | createRole, updateRole, activateRole, retireRole | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.identity.assignment.read | listRoleAssignments, getRoleAssignment | | ● | — | ● | — | — | — | — | — | — | — | — |
| platform.identity.assignment.grant | createRoleAssignment, revokeRoleAssignment | MFA; second person for business-approval roles (DEC-032) | ● | — | — | — | — | — | — | — | — | — | — |
| platform.org.read | getOrgTree, list/get units, positions, position assignments | | ● | — | ● | ● | ● | ● | ● | ● | ● | ● | — |
| platform.org.manage | create/update/move/deactivate units, positions, position assignments | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.workflow.task.read | listTasks, getTask | | — | — | — | — | ○ + own unit | ● subtree | ○ | ○ | ○ | ○ | ○ |
| platform.workflow.task.create | createTask | | — | — | — | — | ● own unit | ● | — | — | — | — | — |
| platform.workflow.task.work | startTask, completeTask, blockTask, unblockTask | | — | — | — | — | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| platform.workflow.task.assign | reassignTask | | — | — | — | — | — | ● | — | — | — | — | — |
| platform.workflow.task.verify | verifyCloseTask | SoD (≠ completer) | — | — | — | — | — | ● | — | — | — | — | — |
| platform.workflow.task.cancel | cancelTask | | — | — | — | — | ○ (created by me) | ● | — | — | — | — | — |
| platform.workflow.approval.read | listApprovals, getApproval, getWorkflowInstance | | ● | — | ● | ● | ○ | ● | ○ | ● | ● | ● | — |
| platform.workflow.approval.request | withdrawRequest | | — | — | — | — | ○ | ○ | ○ | ○ | ○ | ○ | — |
| platform.workflow.approval.decide | approveRequest, rejectRequest | MFA, BA, SoD | ● | — | — | — | — | — | — | — | — | ● | — |
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
| platform.document.upload | uploadDocumentRevision | quarantine (DEC-053) | — | — | — | — | — | — | ● | — | — | — | — |
| platform.document.approve | approveDocumentRevision, rejectDocumentRevision | MFA, BA, SoD (≠ uploader) | ● | — | — | — | — | — | — | ● | — | — | — |
| platform.config.parameter.read | listParameters, getParameter, listParameterValues | | ● | ● | ● | — | — | — | — | — | ● | — | — |
| platform.config.parameter.define | createParameterDefinition | MFA | ● | — | — | — | — | — | — | — | — | — | — |
| platform.config.parameter.propose | proposeParameterValue | | ● | ● | — | — | — | — | — | — | — | — | — |
| platform.config.parameter.publish | publishParameterValue | MFA, BA, SoD (≠ proposer) | ● | — | — | — | — | — | — | — | ● | — | — |
| platform.config.field.read | listDynamicFields, getDynamicField | | ● | ● | — | — | — | — | — | — | — | — | — |
| platform.config.field.define | createDynamicField, updateDynamicField (DRAFT only) | | ● | — | — | — | — | — | — | — | — | — | — |

Session-only operations (no permission row; any authenticated session acting on itself): `getCurrentSession`,
`listMySessions`, `revokeMySession`, `logout`, `getMe`, `getMyEffectivePermissions`, `changeMyPassword`
(DEC-051), `startMfaEnrolment` / `confirmMfaEnrolment` / `verifyMfa` (DEC-050). Pre-login:
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

## 5. Employer answers (DEC-049, 2026-11-04)
1. All 11 roles are created with these names.
2. `it_ops` may unlock users (row `user.unlock`, with MFA and audit; it cannot change passwords).
3. Document visibility was not asked separately: the v0.1 default applies (EMP: S1, MGR/MGT: S1–S2); the
   employer may change it later (new matrix version).
4. At go-live the employer holds `owner_admin` only; business roles come later, explicitly, flagged as
   self-assignment (and, for BA roles, confirmed by a second person, DEC-032).
5. MFA step-up is required on every MFA row, also inside the factory network.

## 6. Change control
- v1.0 (DEC-049, 2026-11-04): approved draft v0.1 unchanged.
- v1.1 (DEC-056, 2026-11-06): owner_admin `approval.read` ● and `approval.decide` ● (change note at the top).
- v1.2 (DEC-056 extension, 2026-11-10): owner_admin `document.approve` ● and `config.parameter.publish` ●
  (BUSINESS_RULE values only) (change note at the top).

A change to this matrix = new matrix version + reviewed commit + DEC entry; roles keep `matrix_version`. Seeds
for dev/test use synthetic users only (`محیط آزمایشی — داده ساختگی`).
