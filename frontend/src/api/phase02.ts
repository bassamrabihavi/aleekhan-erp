// PHASE_02 operations (docs/api/openapi-draft.yaml 0.8.3-draft) used by the UI of step 02.5. Types mirror the
// contract schemas; guards check the required keys of every body (a body without them is a contract error and
// is never rendered). 14-digit codes, serial numbers and SO-/CU-/CR- numbers are strings end to end.
import { apiRequest, type ApiResponse, type Query } from "./http";
import { pageOf, shape, type EntityRef, type Page } from "./phase01";

export type { Page };

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

// ------------------------------------------------------------------------------------------ identity
export type PartyStatus = "ACTIVE" | "INACTIVE";
export type MasterStatus = "DRAFT" | "ACTIVE" | "RETIRED";

export interface Customer {
  customer_id: string;
  customer_no: string;
  display_name_fa: string;
  legal_name_fa: string | null;
  status: PartyStatus;
  default_required_quality_ref: string | null;
  row_version: number;
  created_at: string;
  updated_at: string;
}
export interface CustomerBrand {
  brand_id: string;
  customer_id: string;
  brand_name_fa: string;
  status: PartyStatus;
  row_version: number;
}
export interface ProductClass {
  product_class_id: string;
  parent_class_id: string | null;
  level_key: "product_type" | "category";
  label_fa: string;
  segment_value: string;
  uom: string | null;
  product_no_scheme: string | null;
  status: MasterStatus;
  row_version: number;
}
export interface Product {
  product_id: string;
  product_class_id: string;
  product_no: string;
  name_fa: string;
  uom: string;
  buckle_type_code: string | null;
  belt_width_code: string | null;
  status: MasterStatus;
  row_version: number;
  created_at: string;
}
export interface Style {
  style_id: string;
  product_id: string;
  category_id: string;
  style_no: string;
  name_fa: string;
  current_revision_id: string | null;
  status: MasterStatus;
  row_version: number;
  created_at: string;
}
export interface StyleAttributes {
  colour_fa?: string;
  main_material_fa?: string;
  lining_fa?: string;
  hardware_colour_fa?: string;
  notes_fa?: string;
}
export interface StyleRevision {
  style_revision_id: string;
  style_id: string;
  revision_no: number;
  attributes: StyleAttributes;
  /** DRAFT | ACTIVE | SUPERSEDED */
  status: string;
  created_at: string;
  row_version: number;
}
export interface ProductCode {
  product_code_id: string;
  code: string;
  code_namespace: string;
  style_id: string | null;
  rule_revision_id: string | null;
  status: string;
  erp_status: string | null;
  issued_at: string | null;
  row_version: number;
}
export interface GoldenSummary {
  total: number;
  per_family: Record<string, number>;
  belt_checked: number;
  legacy_only_style_0000: number;
  not_reproduced: number;
  families_below_minimum: string[];
}
export interface CodeRuleRevision {
  rule_revision_id: string;
  code_namespace: string;
  revision_no: number;
  scope: Record<string, unknown>;
  rule_spec: Record<string, unknown>;
  source_workbook_sha256: string;
  golden_case_count: number;
  status: "DRAFT" | "IN_REVIEW" | "APPROVED" | "ACTIVE" | "RETIRED" | "REJECTED";
  decision_id: string;
  created_by: string | null;
  approved_by: string | null;
  approved_at: string | null;
  golden_summary?: GoldenSummary;
  row_version: number;
}
export interface CodePreview {
  code: string;
  rule_revision_id: string | null;
  segments: { level_key: string; value: string }[];
  new_product: boolean;
  legacy_only: boolean;
  issued: boolean;
}
export interface CodeValidation {
  input: string;
  format_valid: boolean;
  code_namespace: string;
  registry_entry: ProductCode | null;
  segments_checked: boolean;
  reasons: string[];
}
/** ALLOCATED | CANCELLED (later phases add production states) */
export type SerialStatus = string;
export interface Serial {
  serial_id: string;
  serial_number: string;
  serial_namespace: string;
  order_id: string | null;
  order_line_id: string | null;
  line_no: number | null;
  customer_id: string;
  style_id: string;
  style_revision_id: string;
  product_code: string | null;
  status: SerialStatus;
  current_snapshot_version: number;
  allocated_at: string;
  row_version: number;
}
export interface SerialSummary {
  serial_id: string;
  serial_number: string;
  status: SerialStatus;
  customer_id: string;
  order_id: string | null;
  line_no: number | null;
  quantity: number | null;
  uom: string | null;
  attributes: StyleAttributes;
  allocated_at: string;
}
export interface SerialSnapshot {
  serial_id: string;
  version: number;
  reason: string;
  order_version: number | null;
  change_request_id: string | null;
  created_at: string;
  snapshot: Record<string, unknown>;
}
export interface UnavailableSection {
  section: string;
  phase: string;
}
export interface TrackingEvent {
  occurred_at: string;
  kind: string;
  ref: EntityRef;
  audit_event_id: string;
}
export interface OrderVersionSummary {
  order_id: string;
  version: number;
  reason: string;
  change_request_id: string | null;
  created_at: string;
}
export interface SerialTracking {
  serial: Serial;
  order_versions: OrderVersionSummary[];
  events: TrackingEvent[];
  unavailable_sections: UnavailableSection[];
  withheld_sections?: string[];
}
export interface StyleTracking {
  style: Style;
  counts: {
    serials_total: number | null;
    serials_active: number | null;
    orders_total: number | null;
    /** REV-0295: orders with a confirmed line of this style that are confirmed / released / on hold / partial */
    orders_active?: number | null;
    quantity_total?: number | null;
  };
  /** REV-0295: order facts of the listed serials by order_id (empty without commercial.order.read) */
  orders?: Record<string, { order_no: string; program_ref: string | null; required_quality_requirement: string | null }>;
  serials: SerialSummary[];
  unavailable_sections: UnavailableSection[];
  withheld_sections?: string[];
  page: { page_size: number; next_cursor: string | null };
}
/** REV-0295: page 33 KPI counts (server-computed over the scoped change requests). */
export interface ChangeCounts {
  open: number;
  awaiting_decision: number;
  applied: number;
  cancel_open: number;
}
export interface StyleSuggestion {
  style_id: string;
  product_id: string;
  name_fa: string;
  score: number;
  reasons: string[];
}
export interface ExternalRef {
  external_ref_id: string;
  target_type: string;
  target_id: string;
  system: string;
  namespace: string;
  value: string;
  valid_from: string;
  valid_to: string | null;
  row_version: number;
}

// --------------------------------------------------------------------------------------------- commercial
export type OrderStatus =
  | "DRAFT"
  | "VALIDATED"
  | "CONFIRMED"
  | "RELEASED_TO_PLAN"
  | "ON_HOLD"
  | "CANCELLED"
  | "PARTIAL_FULFILLED"
  | "FULFILLED"
  | "CLOSED";
export interface OrderLine {
  line_id: string;
  line_no: number;
  style_id: string;
  style_revision_id: string;
  product_code_id: string | null;
  product_code: string | null;
  quantity: number;
  uom: string;
  requested_due_date: string | null;
  status: "OPEN" | "CONFIRMED" | "REMOVED" | "CANCELLED";
  serial_id: string | null;
  serial_number: string | null;
  order_version: number | null;
  row_version: number;
}
export interface CustomerOrder {
  order_id: string;
  order_no: string;
  customer_id: string;
  brand_id: string | null;
  external_po_number: string | null;
  order_type: string;
  program_ref: string | null;
  order_date: string;
  requested_due_date: string | null;
  required_quality_requirement: string | null;
  customer_representative_name: string | null;
  status: OrderStatus;
  status_before_hold: string | null;
  hold_reason: string | null;
  cancel_reason: string | null;
  current_version: number | null;
  lines: OrderLine[];
  row_version: number;
  created_at: string;
  updated_at: string;
}
export interface OrderSummary {
  order_id: string;
  order_no: string;
  customer_id: string;
  external_po_number: string | null;
  order_type: string;
  status: OrderStatus;
  order_date: string;
  requested_due_date: string | null;
  current_version: number | null;
  line_count: number;
  row_version: number;
}
export interface OrderVersion extends OrderVersionSummary {
  created_by: string | null;
  image: Record<string, unknown>;
}
export type ChangeKind =
  | "QTY_CHANGE"
  | "DUE_DATE_CHANGE"
  | "ADD_LINE"
  | "CANCEL_LINE"
  | "CANCEL_ORDER"
  | "HOLD"
  | "RESUME";
export type ChangeStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED" | "APPLIED" | "WITHDRAWN" | "EXPIRED";
export interface ChangeItem {
  line_id?: string | null;
  quantity?: number;
  requested_due_date?: string;
  style_id?: string;
  style_revision_id?: string;
  product_code_id?: string | null;
}
export interface ChangeRequest {
  change_request_id: string;
  request_no: string;
  order_id: string;
  base_order_version: number;
  kind: ChangeKind;
  items: ChangeItem[];
  reason: string;
  status: ChangeStatus;
  requested_by: string | null;
  /** DEC-032 amendment 2026-11-17: internal display name of the requester. */
  requested_by_name?: string | null;
  submitted_at: string | null;
  /** DEC-059 amendment 2026-11-17: an open request expires 30 days after submit. */
  expires_at?: string | null;
  decided_by: string | null;
  decided_at: string | null;
  planning_required: boolean;
  planning_approved_by: string | null;
  planning_approved_at: string | null;
  planning_rejected_by: string | null;
  planning_rejected_at: string | null;
  applied_version: number | null;
  row_version: number;
  created_at: string;
}
export interface ChangeImpact {
  change_request_id: string;
  base_order_version: number;
  lines_affected: string[];
  serials_affected: string[];
  new_lines: number;
  snapshots_to_write: number;
  unavailable_sections: UnavailableSection[];
}
export type DecisionKind = "ORDER_CONFIRM" | "CHANGE_DECIDE" | "CHANGE_PLANNING_DECISION" | "CODE_RULE_APPROVE";
export interface DecisionItem {
  kind: DecisionKind;
  entity_type: "customer_order" | "change_request" | "code_rule_revision";
  entity_id: string;
  number: string | null;
  revision_no: number | null;
  requested_by: string | null;
  requested_by_name?: string | null;
  requested_at: string;
  row_version: number;
}
export interface DecisionInbox {
  as_of: string;
  items: DecisionItem[];
  truncated: boolean;
}

// ---------------------------------------------------------------------------------------------- guards
const customer = shape<Customer>("customer_id", "customer_no", "display_name_fa", "status", "row_version");
const brand = shape<CustomerBrand>("brand_id", "customer_id", "brand_name_fa", "status", "row_version");
const pclass = shape<ProductClass>("product_class_id", "level_key", "label_fa", "segment_value", "status");
const product = shape<Product>("product_id", "product_class_id", "product_no", "name_fa", "status", "row_version");
const style = shape<Style>("style_id", "product_id", "category_id", "style_no", "name_fa", "status", "row_version");
const revision = shape<StyleRevision>("style_revision_id", "style_id", "revision_no", "attributes", "status");
const code = shape<ProductCode>("product_code_id", "code", "status", "row_version");
const rule = shape<CodeRuleRevision>("rule_revision_id", "revision_no", "status", "row_version");
const serial = shape<Serial>("serial_id", "serial_number", "status", "customer_id", "style_id", "row_version");
const order = shape<CustomerOrder>("order_id", "order_no", "customer_id", "status", "lines", "row_version");
const orderSummary = shape<OrderSummary>("order_id", "order_no", "customer_id", "status", "order_date");
const cr = shape<ChangeRequest>("change_request_id", "request_no", "order_id", "kind", "items", "status", "row_version");
const extRef = shape<ExternalRef>("external_ref_id", "target_type", "target_id", "system", "namespace", "value");
const versionSummary = shape<OrderVersionSummary>("order_id", "version", "reason", "created_at");

/** A 14-digit code is a 14-character digit string (never a number). */
export const CODE14 = /^[0-9]{14}$/;
const isCode14OrNull = (v: unknown): boolean => v === null || v === undefined || (typeof v === "string" && CODE14.test(v));

export const g = {
  customer,
  customerPage: pageOf(customer),
  brand,
  brandPage: pageOf(brand),
  classPage: pageOf(pclass),
  product,
  productPage: pageOf(product),
  style,
  stylePage: pageOf(style),
  revision,
  revisionPage: pageOf(revision),
  code: (v: unknown): v is ProductCode => code(v) && isCode14OrNull(v.code),
  codePage: pageOf((v: unknown): v is ProductCode => code(v) && isCode14OrNull(v.code)),
  rule,
  rulePage: pageOf(rule),
  preview: (v: unknown): v is CodePreview =>
    shape<CodePreview>("code", "segments", "new_product", "legacy_only", "issued")(v) && isCode14OrNull(v.code),
  validation: shape<CodeValidation>("input", "format_valid", "reasons"),
  serial,
  serialPage: pageOf(serial),
  snapshotPage: pageOf(shape<SerialSnapshot>("serial_id", "version", "reason", "snapshot")),
  serialTracking: shape<SerialTracking>("serial", "order_versions", "events", "unavailable_sections"),
  styleTracking: shape<StyleTracking>("style", "counts", "serials", "unavailable_sections", "page"),
  suggestions: (v: unknown): v is { items: StyleSuggestion[] } => isObj(v) && Array.isArray(v.items),
  extRefPage: pageOf(extRef),
  extRef,
  order,
  orderPage: pageOf(orderSummary),
  versionPage: pageOf(versionSummary),
  version: shape<OrderVersion>("order_id", "version", "reason", "image"),
  cr,
  crPage: pageOf(cr),
  changeCounts: shape<ChangeCounts>("open", "awaiting_decision", "applied", "cancel_open"),
  impact: shape<ChangeImpact>("change_request_id", "lines_affected", "serials_affected", "unavailable_sections"),
  inbox: (v: unknown): v is DecisionInbox => isObj(v) && Array.isArray(v.items) && typeof v.truncated === "boolean",
};

// -------------------------------------------------------------------------------------------- requests
export function get<T>(path: string, guard: (v: unknown) => v is T, query?: Query, signal?: AbortSignal): Promise<ApiResponse<T>> {
  return apiRequest(path, guard, { query, signal });
}
/** Mutation: Idempotency-Key always; If-Match when a row version is given. */
export function send<T>(
  path: string,
  guard: (v: unknown) => v is T,
  body: unknown,
  key: string,
  ifMatch?: number | null,
  method: "POST" | "PATCH" = "POST",
): Promise<ApiResponse<T>> {
  return apiRequest(path, guard, { method, body, idempotencyKey: key, ifMatch });
}
/** Side-effect free POST (validate / preview: no Idempotency-Key, contract `side_effect_free_operations`). */
export function probe<T>(path: string, guard: (v: unknown) => v is T, body: unknown): Promise<ApiResponse<T>> {
  return apiRequest(path, guard, { method: "POST", body });
}

/** Query keys of the PHASE_02 pages (all under "p2" so a reload invalidates them together). Convention: a
 * `[..., "one", id]` entry always caches the full ApiResponse (data + ETag version); a view that needs only the
 * body uses `select: (r) => r.data`. Two shapes under one key crashed the serial page (02.5 E2E). */
export const K2 = {
  all: ["p2"] as const,
  customers: ["p2", "customers"] as const,
  products: ["p2", "products"] as const,
  classes: ["p2", "classes"] as const,
  styles: ["p2", "styles"] as const,
  codes: ["p2", "codes"] as const,
  rules: ["p2", "rules"] as const,
  serials: ["p2", "serials"] as const,
  orders: ["p2", "orders"] as const,
  changes: ["p2", "changes"] as const,
  refs: ["p2", "refs"] as const,
  inbox: ["p2", "inbox"] as const,
};

export const PERM = {
  customerRead: "identity.customer.read",
  customerManage: "identity.customer.manage",
  productRead: "identity.product.read",
  productManage: "identity.product.manage",
  codeRead: "identity.product_code.read",
  codeIssue: "identity.product_code.issue",
  ruleRead: "identity.code_rule.read",
  ruleManage: "identity.code_rule.manage",
  ruleApprove: "identity.code_rule.approve",
  serialRead: "identity.serial.read",
  refRead: "identity.external_ref.read",
  refManage: "identity.external_ref.manage",
  orderRead: "commercial.order.read",
  orderManage: "commercial.order.manage",
  orderConfirm: "commercial.order.confirm",
  orderRelease: "commercial.order.release",
  changeRead: "commercial.change.read",
  changeRequest: "commercial.change.request",
  changeDecide: "commercial.change.decide",
  changePlanning: "commercial.change.planning_approve",
  changeApply: "commercial.change.apply",
} as const;

export const DECIDE_PERMS = [PERM.orderConfirm, PERM.changeDecide, PERM.changePlanning, PERM.ruleApprove] as const;

/** Masked representative name (DEC-058: management_viewer, write responses). */
export const REDACTED = "[REDACTED]";
