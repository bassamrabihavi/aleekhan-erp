# PHASE_01 domain engine — step 01.3

Services only (no HTTP view, no URL): the API of 01.4 calls these functions. Every write runs in
`engine.uow.unit_of_work` (write + audit + outbox in one transaction); every number comes from a versioned
parameter (`params.values.effective*`), never from code. Error codes: [ERROR_CODES.md](ERROR_CODES.md).
Production authorization stays deny-all (`api.permissions.ACCESS_POLICY = DenyAllPolicy`, no authentication
class) until 01.4 installs `authz.policy.RbacPolicy` together with session authentication.

## 1. Module map

| Area | Module | Contract |
|---|---|---|
| Authorization | `authz/policy.py` | `Caller`, `RecordScope`, `decide/can`, `require_permission` (403), `require_record` (404 out of scope, SEC-01), `require_step_up` (401 MFA_REQUIRED), `decider_permission`, `requires_login_mfa`, `scope_q`, `redact_fields`, `RbacPolicy` |
| Passwords | `identity/passwords.py` | DEC-051 policy (`policy_failures`), last-5 reuse (Q-0105), PBKDF2 via Django hashers, one-time 72 h credential |
| TOTP | `identity/totp.py` | RFC 6238 (SHA1/6 digits/30 s, ±1 step), replay guard on `last_used_step` |
| Secrets at rest | `identity/crypto.py` | AES-256-GCM (`cryptography`), AAD binds purpose + owner, keys only from `ALEEKHAN_DATA_KEYS` |
| Network | `identity/network.py` | INTERNAL only inside `ALEEKHAN_INTERNAL_CIDRS`; VPN ranges, other and unknown addresses = outside (DEC-052) |
| Sessions | `identity/sessions.py` | token SHA-256 only, timeouts per account kind, cap 3 -> END_OLDEST_SESSION (`CONCURRENT_LIMIT`), revoke own / user, expiry sweep |
| Login / MFA | `identity/auth.py` | login ceremony, `verify_mfa` (token rotated), `step_up`, lockout 5/15 min -> 15 min, password change |
| MFA admin | `identity/mfa.py` | enrolment (URI shown once), 10 recovery codes (hash only, single use), admin reset (reason + step-up + audit, never on oneself) |
| Users | `identity/users.py` | create (one-time password, operators INTERNAL_ONLY), disable (sessions revoked, last disabler protected), enable, unlock (it_ops, no password change), reset password, console bootstrap / recovery |
| Roles | `identity/roles.py` | DRAFT -> ACTIVE -> RETIRED, grants only in DRAFT, activation only for an approved matrix permission set (else RULE_NOT_APPROVED DEC-049), assignments with DEC-032 second approval, expiry sweep |
| Org | `org/service.py` | units / positions / assignments, never back-dated (0008 + 0011), DB guard refusals -> 409 with the rule name |
| Approvals | `workflow/approvals.py` | maker-checker machine, route = role + unit scope, BUSINESS roles only, one decision (row lock), 30-day expiry sweep, resource handlers |
| Tasks | `workflow/tasks.py` | WorkTask machine, verifier != completer, cancel with reason, instance-owned tasks only via the instance |
| Instances | `workflow/instances.py` | cancellation machine (CANCEL_REQUESTED -> COMPENSATING -> CANCELLED), withdraw approvals / cancel tasks in the same transaction |
| Documents | `documents/{filetypes,scanner,storage,service}.py` | allow-list + magic bytes + no macros + bomb guard, quarantine until CLEAN, ClamAV `INSTREAM` adapter, encrypted storage, maker-checker approval, attachment-only download, purge after 30 days |
| Parameters | `params/{values,service}.py` | effective values via `platform_param_value`; OWNER_POLICY by the owner alone (Q-0103); BUSINESS_RULE blocked by its own decision |
| Jobs | `jobs/{service,retention}.py` | job-run machine, safe cancel only (JOB_PROTECTED), no force kill (RULE_NOT_APPROVED DEC-024), housekeeping jobs, login-event retention 24 months, audit never purged |
| Engine | `engine/{audit_chain,dbrules,commands}.py` | hash chain + verification, DB refusal mapping, idempotent commands |
| Console | `manage.py bootstrap_owner` | first owner (owner_admin only) / `--recover` (DEC-054 C); password from tty or stdin, never printed |

## 2. Audit hash chain and lock order

`chain_seq` / `prev_hash` / `event_hash = sha256(prev_hash || "\n" || canonical JSON)` (canonical = sorted
keys, compact, UTF-8; JSON values normalised through PostgreSQL `jsonb` first so the hash covers exactly what is
read back). The **outermost unit of work takes the chain advisory lock first**, before any business row lock;
all writers lock in the same order, so the chain lock never takes part in a lock cycle. Rule for every service:
open the unit of work before `select_for_update`. Sweeps that often find nothing use
`unit_of_work_or_nothing` + `NothingToDo` instead of writing an empty audit row. Verification
(`audit_chain.verify_chain`, job `audit_integrity_check`) records an append-only `platform_audit_integrity_run`:
BROKEN on a changed field, a broken link, a sequence gap (deleted row) or an unchained row written after the
chain started (insert that bypassed the engine). Consequence: write transactions are serialised for the time
between the start of their unit of work and the commit (short; acceptable at factory scale, perf in 01.7).

## 3. Engine interpretations (traceable; confirm or correct)

| # | Topic | Engine behaviour | Source |
|---|---|---|---|
| E-1 | Login MFA role list (DEC-003 "manager/finance/HR/approver") | a role with any permission flagged MFA step-up or business approval -> MFA at login (owner_admin, it_ops, security_auditor, unit_manager, document/config/workflow approver) | C-06 / C-36: binding = MFA column of matrix v1.0 |
| E-2 | MFA required but not enrolled | inside the network: ACTIVE session flagged `mfa_enrolment_required`, every MFA action refused until enrolment; outside: 401 MFA_REQUIRED (enrol inside first) | safe direction; DEC-042 |
| E-3 | "Own unit" cells of the matrix | units where the caller currently holds a PRIMARY or ACTING position, inside the assignment scope | matrix v1.0 section 3 (meaning not spelled out) |
| E-4 | Decider of a request | the request's action if it is a business-approval permission (document approve, parameter publish), else `platform.workflow.approval.decide` (role grants) | STATE_TRANSITIONS 4.4 + matrix |
| E-5 | Lockout of a CREATED account | CREATED -> LOCKED is allowed; unlock returns to CREATED while the one-time password is unchanged | 4.1 lists only ACTIVE -> LOCKED |
| E-6 | "Last 5 passwords" | current password + 4 previous ones | Q-0105 |
| E-7 | Job cancel while QUEUED | QUEUED -> CANCELLED at once (STATE_TRANSITIONS 4.7); the OpenAPI text of `requestJobCancel` says QUEUED -> CANCEL_REQUESTED | conflict noted, 4.7 followed |
| E-8 | Scanner unavailable | SCANNING -> QUARANTINED (back to the queue), never CLEAN | 4.6 "stays QUARANTINED" |
| E-9 | Activation of a runtime-created role | refused: RULE_NOT_APPROVED (DEC-049) - only matrix v1.0 sets are approved | PERMISSION_MATRIX section 6 |
| E-10 | Login failures | audit + login event only (no outbox event); the lock emits `platform.identity.user.status_changed` | page 36/46 counters read audit/login events |

## 4. Known gaps (not implemented on purpose)

- An IN_REVIEW revision whose request expires / is withdrawn stays IN_REVIEW (4.6 has no IN_REVIEW -> WORKING);
  a new revision must be uploaded.
- Workflow FAILED: the "manual resolution task" of 4.5 is not created (no approved assignee rule).
- Yearly archive of business audit (DEC-032 R-A): no archive target decided; audit is kept, never deleted.
- Break-glass account (DEC-054 A): before production, not in 01.3.
- Force kill (DEC-024), SLA clocks, task reopen, approval delegation: not approved (4.11).

## 5. Rework round 1 (review of 6fc3eea)

- REV-0111: documents ○ (operator_terminal) = assignee of a live task linked to the document; only the
  document's current APPROVED, CLEAN revision (a task with `related_revision` only while that revision is the
  current approved one). `revision_scope` (object check, used by `download` and `get_revision`) and
  `revision_list_q` / `document_list_q` (lists) implement the same rule. The creator is no longer an owner.
- REV-0112: `scope_q` = per-grant `grant_q` (queryset form of `grant_allows`): GLOBAL uses a non-empty match-all
  (`~Q(pk__in=[])`; an empty `Q()` vanishes in `|`), the sensitivity cap is applied per grant
  (`sensitivity_field`), and a capped grant used without a sensitivity field matches nothing (fail closed).
  Tested: list == object check for every scope kind x grant mode and for the document sensitivity cells.
- REV-0113: migration 0012 `platform_param_value_at(key, at)`; a SUPERSEDED value counts only if
  `superseded_at > effective_from` (it really was in force), so a future value superseded before its date never
  applies. `platform_param_value(key)` = `platform_param_value_at(key, now)`; `params.values.effective_at`.
- REV-0114: refused outside login without MFA factor is recorded as `MFA_ENROLMENT_REQUIRED` (audit DENIED) and
  does not reset the lockout window.
- REV-0115: purge deletes the bytes in `transaction.on_commit` (idempotent delete).

## 6. DEC-055 (option B, APPROVED 2026-11-05): first holder of a business-approval role

`workflow.approvals.bootstrap_self_approve(caller, request_id, reason=)`: the owner (ACTIVE `owner_admin`)
approves his own `platform.identity.assignment.grant` request for the FIRST holder of a business-approval role
- once per role, only while the role has no ACTIVE holder and no earlier bootstrap approval, with a fresh MFA
step-up and a mandatory reason; the request carries `bootstrap_self_approval = true` and the audit event the
scope flag `bootstrap_self_approval`. Anything else -> 403 `SELF_APPROVAL_FORBIDDEN`; from the second holder on
DEC-032 is unchanged. DB (migration 0013): CHECK `ck_approval_request_maker_checker` allows decider = requester
only for a flagged APPROVED row, `ck_approval_request_bootstrap_scope`, trigger
`trg_approval_request_bootstrap_guard` (rule `ck_approval_request_bootstrap_self_approval`, per-role advisory
lock: concurrent bootstrap approvals of one role -> exactly one wins) and the 0008 role-assignment guard accepting
only such a flagged request. API exposure (an operation or an `approveRequest` variant) is a 01.4 contract item.
