// PHASE_01 operations (docs/api/openapi-draft.yaml 0.6.3-draft) used by the UI of step 01.5. Types mirror the
// contract schemas; guards check the required keys of every body (a body without them is a contract error).
import { apiRequest, newIdempotencyKey, type ApiResponse, type Query } from "./http";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** Guard: object with all `keys` present. */
export function shape<T extends object>(...keys: (keyof T & string)[]): (v: unknown) => v is T {
  return (v: unknown): v is T => isObj(v) && keys.every((k) => k in v);
}
export function pageOf<T>(item: (v: unknown) => v is T): (v: unknown) => v is Page<T> {
  return (v: unknown): v is Page<T> =>
    isObj(v) && Array.isArray(v.items) && v.items.every(item) && isObj(v.page) && "next_cursor" in v.page;
}
const isNothing = (v: unknown): v is undefined => v === undefined || v === null;

export interface Page<T> {
  items: T[];
  page: { page_size: number; next_cursor: string | null };
}
export interface EntityRef {
  entity_type: string;
  entity_id: string;
  revision?: number | null;
}
export interface Scope {
  kind: "GLOBAL" | "ORG_UNIT" | "ORG_UNIT_SUBTREE" | "SITE" | "WAREHOUSE" | "LINE" | "CUSTOMER";
  ref_id?: string | null;
}

// --------------------------------------------------------------------------------------------- auth / me
export type SessionState = "MFA_PENDING" | "ACTIVE" | "EXPIRED" | "REVOKED" | "LOGGED_OUT";
export interface SessionInfo {
  session_handle: string;
  state: SessionState;
  user_id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  mfa_verified_at: string | null;
  network_zone: "INTERNAL" | "EXTERNAL" | "UNKNOWN";
  is_current?: boolean;
  password_change_required?: boolean;
  mfa_enrolment_required?: boolean;
}
export type UserStatus = "CREATED" | "ACTIVE" | "LOCKED" | "DISABLED";
export interface User {
  user_id: string;
  username: string;
  display_name: string;
  status: UserStatus;
  account_kind: "PERSON" | "OPERATOR";
  network_policy: "INTERNAL_ONLY" | "ANY_WITH_MFA_OUTSIDE";
  mfa_enrolled: boolean;
  mfa_required?: boolean;
  last_login_at?: string | null;
  created_at: string;
  created_by: string | null;
  row_version: number;
}
export interface OneTimeCredential {
  user_id: string;
  one_time_password: string;
  expires_at: string;
}
export interface RoleAssignment {
  assignment_id: string;
  user_id: string;
  role_id: string;
  scope: Scope;
  valid_from: string;
  valid_to: string | null;
  status: "PENDING_APPROVAL" | "ACTIVE" | "EXPIRED" | "REVOKED";
  granted_by: string | null;
  self_assignment: boolean;
  approval_id?: string | null;
  reason: string;
  row_version: number;
}
export interface PositionAssignment {
  position_assignment_id: string;
  position_id: string;
  user_id: string;
  kind: "PRIMARY" | "ACTING";
  valid_from: string;
  valid_to: string | null;
  row_version: number;
}
export interface Me {
  user: User;
  roles: RoleAssignment[];
  positions: PositionAssignment[];
}
export interface EffectiveGrant {
  action: string;
  scope: Scope;
  via_role: string;
  mfa_step_up?: boolean;
}
export interface EffectivePermissions {
  user_id: string;
  computed_at: string;
  grants: EffectiveGrant[];
}

const isSession = shape<SessionInfo>("session_handle", "state", "user_id", "expires_at");
const isUser = shape<User>("user_id", "username", "display_name", "status", "row_version");
const isAssignment = shape<RoleAssignment>("assignment_id", "user_id", "role_id", "scope", "status");
const isEffective = shape<EffectivePermissions>("user_id", "computed_at", "grants");

export const auth = {
  context: () => apiRequest("/auth/login", shape<{ status: string }>("status")),
  login: (username: string, password: string) =>
    apiRequest("/auth/login", isSession, { method: "POST", body: { username, password } }),
  verifyMfa: (code: string) => apiRequest("/auth/mfa/verify", isSession, { method: "POST", body: { code } }),
  stepUp: (code: string) => apiRequest("/auth/mfa/step-up", isSession, { method: "POST", body: { code } }),
  logout: () => apiRequest("/auth/logout", isNothing, { method: "POST" }),
  session: (signal?: AbortSignal) => apiRequest("/auth/session", isSession, { signal }),
  changePassword: (current_password: string, new_password: string) =>
    apiRequest("/auth/password/change", isNothing, { method: "POST", body: { current_password, new_password } }),
  startEnrolment: () =>
    apiRequest("/auth/mfa/enrolment", shape<{ method: "TOTP"; provisioning_uri: string }>("provisioning_uri"), {
      method: "POST",
    }),
  confirmEnrolment: (code: string) =>
    apiRequest(
      "/auth/mfa/enrolment/confirm",
      shape<{ mfa_enrolled: boolean; recovery_codes?: string[] }>("mfa_enrolled"),
      { method: "POST", body: { code } },
    ),
  mySessions: (signal?: AbortSignal) => apiRequest("/auth/sessions", pageOf(isSession), { signal }),
  revokeMySession: (id: string, reason: string, key = newIdempotencyKey()) =>
    apiRequest(`/auth/sessions/${id}/revoke`, isSession, { method: "POST", body: { reason }, idempotencyKey: key }),
  me: (signal?: AbortSignal) => apiRequest("/me", shape<Me>("user", "roles", "positions"), { signal }),
  myPermissions: (signal?: AbortSignal) => apiRequest("/me/permissions", isEffective, { signal }),
};

// ----------------------------------------------------------------------------------------- generic write
/** Mutating call: Idempotency-Key always, If-Match when a version is given. */
export function write<T>(
  path: string,
  guard: (v: unknown) => v is T,
  body: unknown,
  key: string,
  ifMatch?: number | null,
  method: "POST" | "PATCH" = "POST",
): Promise<ApiResponse<T>> {
  return apiRequest(path, guard, { method, body, idempotencyKey: key, ifMatch });
}
export function read<T>(path: string, guard: (v: unknown) => v is T, query?: Query, signal?: AbortSignal) {
  return apiRequest(path, guard, { query, signal });
}

// ------------------------------------------------------------------------------------------- identity
export interface Role {
  role_id: string;
  code: string;
  name_fa: string;
  status: "DRAFT" | "ACTIVE" | "RETIRED";
  kind: "TECHNICAL" | "BUSINESS";
  permissions: string[];
  matrix_version?: string | null;
  row_version: number;
}
export interface Permission {
  action: string;
  module: string;
  description_fa: string;
  mfa_step_up: boolean;
  business_approval: boolean;
}
export const guards = {
  session: isSession,
  sessionPage: pageOf(isSession),
  user: isUser,
  userPage: pageOf(isUser),
  userCreated: shape<{ user: User; one_time_credential: OneTimeCredential }>("user", "one_time_credential"),
  oneTime: shape<OneTimeCredential>("user_id", "one_time_password", "expires_at"),
  role: shape<Role>("role_id", "code", "name_fa", "status", "kind", "permissions"),
  rolePage: pageOf(shape<Role>("role_id", "code", "name_fa", "status", "kind", "permissions")),
  permissionPage: pageOf(shape<Permission>("action", "description_fa", "business_approval")),
  assignment: isAssignment,
  assignmentPage: pageOf(isAssignment),
  effective: isEffective,
};

// ------------------------------------------------------------------------------------------------ org
export interface OrgUnit {
  unit_id: string;
  code: string;
  name_fa: string;
  unit_type: string;
  parent_unit_id: string | null;
  valid_from: string;
  valid_to: string | null;
  status: "ACTIVE" | "INACTIVE";
  row_version: number;
}
export interface Position {
  position_id: string;
  unit_id: string;
  code: string;
  title_fa: string;
  reports_to_position_id: string | null;
  is_unit_head: boolean;
  primary_capacity?: number;
  status: "ACTIVE" | "INACTIVE";
  row_version: number;
}
export interface TreeHolder {
  user_id: string;
  display_name: string;
  kind: "PRIMARY" | "ACTING";
}
export interface OrgTreeNode {
  unit: OrgUnit;
  positions: { position: Position; holders: TreeHolder[] }[];
  children: OrgTreeNode[];
  truncated?: boolean;
}
export interface OrgTree {
  as_of: string;
  roots: OrgTreeNode[];
}
export const orgGuards = {
  tree: shape<OrgTree>("as_of", "roots"),
  unit: shape<OrgUnit>("unit_id", "code", "name_fa", "unit_type", "status", "row_version"),
  unitPage: pageOf(shape<OrgUnit>("unit_id", "code", "name_fa", "unit_type", "status")),
  position: shape<Position>("position_id", "unit_id", "code", "title_fa", "is_unit_head"),
  positionPage: pageOf(shape<Position>("position_id", "unit_id", "code", "title_fa")),
  pa: shape<PositionAssignment>("position_assignment_id", "position_id", "user_id", "kind"),
  paPage: pageOf(shape<PositionAssignment>("position_assignment_id", "position_id", "user_id", "kind")),
};

// ------------------------------------------------------------------------------------------- workflow
export type TaskStatus = "OPEN" | "ASSIGNED" | "IN_PROGRESS" | "BLOCKED" | "DONE" | "CLOSED" | "CANCELLED";
export interface Task {
  task_id: string;
  subject: string;
  related?: EntityRef | null;
  status: TaskStatus;
  assignee: { kind: "USER" | "ORG_UNIT" | "POSITION"; ref_id: string };
  created_by: string | null;
  created_at: string;
  due_at: string | null;
  blocked_reason?: string | null;
  completed_by?: string | null;
  row_version: number;
}
export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED" | "WITHDRAWN" | "EXPIRED" | "SUPERSEDED";
export interface Approval {
  approval_id: string;
  action: string;
  resource: EntityRef;
  status: ApprovalStatus;
  requested_by: string;
  requested_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note?: string | null;
  expires_at?: string | null;
  bootstrap_self_approval?: boolean;
  row_version: number;
}
export const workGuards = {
  task: shape<Task>("task_id", "subject", "status", "assignee", "row_version"),
  taskPage: pageOf(shape<Task>("task_id", "subject", "status", "assignee")),
  approval: shape<Approval>("approval_id", "action", "resource", "status", "requested_by"),
  approvalPage: pageOf(shape<Approval>("approval_id", "action", "resource", "status", "requested_by")),
};

// ------------------------------------------------------------------------------------------ documents
export interface DocumentItem {
  document_id: string;
  document_type: string;
  title_fa: string;
  owner_entity: EntityRef | null;
  sensitivity?: "S1" | "S2" | "S3";
  current_approved_revision_id: string | null;
  legacy_location_ref?: string | null;
  created_at: string;
  created_by: string;
  row_version: number;
}
export interface DocumentRevision {
  revision_id: string;
  document_id: string;
  revision_no: number;
  parent_revision_id?: string | null;
  status: "WORKING" | "IN_REVIEW" | "APPROVED" | "REJECTED" | "SUPERSEDED";
  scan_status: "QUARANTINED" | "SCANNING" | "CLEAN" | "REJECTED";
  scan_finding?: string | null;
  sha256: string;
  size_bytes: number;
  media_type: string;
  original_name: string;
  change_note?: string | null;
  uploaded_by: string;
  uploaded_at: string;
  approved_by?: string | null;
  approved_at?: string | null;
  row_version: number;
}
export const docGuards = {
  doc: shape<DocumentItem>("document_id", "document_type", "title_fa", "row_version"),
  docPage: pageOf(shape<DocumentItem>("document_id", "document_type", "title_fa")),
  rev: shape<DocumentRevision>("revision_id", "revision_no", "status", "scan_status", "sha256"),
  revPage: pageOf(shape<DocumentRevision>("revision_id", "revision_no", "status", "scan_status")),
};

// ------------------------------------------------------------------------------------------ parameters
export type Datatype = "STRING" | "INTEGER" | "DECIMAL" | "BOOLEAN" | "DATE" | "DURATION" | "ENUM";
export interface ParameterValue {
  value_revision_id: string;
  value: { datatype: Datatype; value: string | boolean | null };
  status: "DRAFT" | "PENDING_APPROVAL" | "PUBLISHED" | "SUPERSEDED" | "REJECTED";
  effective_from: string;
  proposed_by: string | null;
  proposed_at: string;
  published_by?: string | null;
  published_at?: string | null;
  approval_id?: string | null;
  /** 0.6.1-draft: If-Match of publishParameterValue. */
  row_version?: number;
}
export interface Parameter {
  parameter_key: string;
  label_fa: string;
  datatype: Datatype;
  owner_module: string;
  classification: "TECHNICAL" | "OWNER_POLICY" | "BUSINESS_RULE";
  decision_id?: string | null;
  active_value: ParameterValue | null;
  row_version: number;
}
export const paramGuards = {
  param: shape<Parameter>("parameter_key", "label_fa", "datatype", "classification", "active_value"),
  paramPage: pageOf(shape<Parameter>("parameter_key", "label_fa", "datatype", "classification")),
  value: shape<ParameterValue>("value_revision_id", "value", "status", "effective_from"),
  valuePage: pageOf(shape<ParameterValue>("value_revision_id", "value", "status", "effective_from")),
};

// ------------------------------------------------------------------------------------------------- ops
export interface HealthDetail {
  checked_at: string;
  components: { name: string; status: "up" | "down" | "unknown" }[];
  outbox: { pending: number; failed: number; dead_letter: number; oldest_pending_at: string | null };
  jobs: {
    running: number;
    queued: number;
    failed_24h: number;
    // 0.6.3-draft (01.7): housekeeping job monitoring (overdue = no success within max_age_seconds, TECHNICAL DEFAULT)
    housekeeping_alerts?: number;
    housekeeping?: HousekeepingJobHealth[];
  };
  // 0.6.2-draft (01.6): event delivery freshness between modules (counts only)
  integration?: {
    lag_seconds: number | null;
    stale: boolean;
    stale_after_seconds: number;
    blocked_aggregates: number;
    held_events: number;
    open_conflicts: number;
    compensation_open: number;
    last_acked_at: string | null;
  };
  security?: { failed_logins_24h: number; locked_users: number };
}
export interface HousekeepingJobHealth {
  job_type: string;
  last_state: JobState | null;
  last_succeeded_at: string | null;
  last_failed_at: string | null;
  last_error_code: string | null;
  max_age_seconds: number;
  overdue: boolean;
  failing: boolean;
}
export interface JobDefinition {
  job_type: string;
  name_fa: string;
  cancellable: boolean;
  protected: boolean;
}
export type JobState = "QUEUED" | "RUNNING" | "CANCEL_REQUESTED" | "CANCELLED" | "SUCCEEDED" | "FAILED";
export interface Job {
  job_id: string;
  job_type: string;
  state: JobState;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress: number | null;
  cancel_reason?: string | null;
  error_code?: string | null;
  row_version: number;
}
export interface AuditIntegrity {
  checked_at: string | null;
  status: "OK" | "BROKEN" | "NEVER_RUN" | "ERROR";
  events_checked: number;
  first_broken_event_id?: string | null;
}
export const opsGuards = {
  health: shape<HealthDetail>("checked_at", "components", "outbox", "jobs"),
  defPage: pageOf(shape<JobDefinition>("job_type", "name_fa", "cancellable", "protected")),
  job: shape<Job>("job_id", "job_type", "state", "row_version"),
  jobPage: pageOf(shape<Job>("job_id", "job_type", "state", "queued_at")),
  integrity: shape<AuditIntegrity>("status", "events_checked"),
};
