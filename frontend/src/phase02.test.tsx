// Unit / component tests of the PHASE_02 pages (02.5). fetch is stubbed here only (MOCK_UI_BINDING §2 rule 1);
// bodies follow docs/api/openapi-draft.yaml 0.8.3-draft with SYNTHETIC values (type segment 97, product 9001,
// serial 63001, CU/SO/CR numbers of the synthetic year 1300). The E2E suite runs the flows against Django.
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { App } from "./App";
import { PageErrorBoundary } from "./components/ErrorBoundary";
import { LATER_TEXT } from "./components/Phase02";
import { createQueryClient } from "./queryClient";

const RID = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const OTHER = "aaaaaaaa-0000-4000-8000-000000000002";
const NOW = "2026-11-15T08:00:00Z";
const CUST = "c0000000-0000-4000-8000-000000000001";
const ORDER = "d0000000-0000-4000-8000-000000000001";
const LINE = "e0000000-0000-4000-8000-000000000001";
const SERIAL = "f0000000-0000-4000-8000-000000000001";
const STYLE = "b0000000-0000-4000-8000-000000000001";
const REV = "b1000000-0000-4000-8000-000000000001";
const PRODUCT = "a1000000-0000-4000-8000-000000000001";
const TYPE = "a2000000-0000-4000-8000-000000000001";
const BELT = "a2000000-0000-4000-8000-000000000002";
const CR = "cc000000-0000-4000-8000-000000000001";
const CODE = "02970790010001";

type Route = (body: unknown, headers: Headers) => Response;
interface Call {
  method: string;
  path: string;
  query: string;
  headers: Headers;
  body: unknown;
}

function ok(body: unknown, status = 200, etag?: number): Response {
  const h: Record<string, string> = { "Content-Type": "application/json", "X-Request-ID": RID };
  if (etag !== undefined) h.ETag = `"${String(etag)}"`;
  return new Response(JSON.stringify(body), { status, headers: h });
}
function prob(code: string, status: number, extra: Record<string, unknown> = {}): Response {
  return new Response(
    JSON.stringify({ type: "about:blank", title: code, status, code, message_fa: `پیام ساختگی ${code}`, request_id: RID, ...extra }),
    { status, headers: { "Content-Type": "application/problem+json", "X-Request-ID": RID } },
  );
}
const page = <T,>(items: T[]) => ({ items, page: { page_size: 25, next_cursor: null } });

function stub(routes: Record<string, Route>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const [rawPath, query = ""] = url.split("?");
      const path = (rawPath ?? url).replace("/api/v1", "");
      const method = init?.method ?? "GET";
      const headers = new Headers(init?.headers);
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : init?.body;
      calls.push({ method, path, query, headers, body });
      const r = routes[`${method} ${path}`];
      if (!r) return Promise.reject(new TypeError(`unrouted ${method} ${path}`));
      return Promise.resolve(r(body, headers));
    }),
  );
  return calls;
}

const VERSION = { api_version: "v1", contract_version: "0.8.4-draft", build_commit: "abcdef1234567", environment: "dev" };
function signedIn(actions: string[], extra: Record<string, Route> = {}): Record<string, Route> {
  return {
    "GET /version": () => ok(VERSION),
    "GET /auth/session": () =>
      ok({ session_handle: "s1", state: "ACTIVE", user_id: ME, created_at: NOW, last_seen_at: NOW, expires_at: NOW, mfa_verified_at: NOW, network_zone: "INTERNAL" }),
    "GET /me": () =>
      ok({
        user: { user_id: ME, username: "syn.user", display_name: "کاربر ساختگی", status: "ACTIVE", account_kind: "PERSON", network_policy: "ANY_WITH_MFA_OUTSIDE", mfa_enrolled: true, created_at: NOW, created_by: null, row_version: 1 },
        roles: [],
        positions: [],
      }),
    "GET /me/permissions": () => ok({ user_id: ME, computed_at: NOW, grants: actions.map((a) => ({ action: a, scope: { kind: "GLOBAL" }, via_role: "syn_role" })) }),
    ...extra,
  };
}

function renderAt(hash: string) {
  window.location.hash = hash;
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <App />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  document.cookie = "csrftoken=syn-csrf-token; path=/";
});

// ------------------------------------------------------------------------------------------ fixtures
const customer = { customer_id: CUST, customer_no: "CU-1300-000001", display_name_fa: "مشتری ساختگی", legal_name_fa: null, status: "ACTIVE", default_required_quality_ref: null, row_version: 1, created_at: NOW, updated_at: NOW };
const line = {
  line_id: LINE, line_no: 1, style_id: STYLE, style_revision_id: REV, product_code_id: "pc1", product_code: CODE, quantity: 40, uom: "PIECE",
  requested_due_date: "2026-12-09", status: "CONFIRMED", serial_id: SERIAL, serial_number: "63001", order_version: 1, row_version: 2,
};
function order(over: Record<string, unknown> = {}) {
  return {
    order_id: ORDER, order_no: "SO-1300-000001", customer_id: CUST, brand_id: null, external_po_number: "PO-SYN-1", order_type: "series_production",
    program_ref: null, order_date: "2026-11-15", requested_due_date: "2026-12-09", required_quality_requirement: "A (متن ساختگی)",
    customer_representative_name: "[REDACTED]", status: "CONFIRMED", status_before_hold: null, hold_reason: null, cancel_reason: null,
    current_version: 1, lines: [line], row_version: 5, created_at: NOW, updated_at: NOW, ...over,
  };
}
const serial = {
  serial_id: SERIAL, serial_number: "63001", serial_namespace: "factory_serial", order_id: ORDER, order_line_id: LINE, line_no: 1, customer_id: CUST,
  style_id: STYLE, style_revision_id: REV, product_code: CODE, status: "ALLOCATED", current_snapshot_version: 1, allocated_at: NOW, row_version: 1,
};
const UNAVAILABLE = [
  { section: "materials", phase: "PHASE_06" },
  { section: "wip", phase: "PHASE_07" },
  { section: "capacity", phase: "PHASE_05" },
  { section: "cost", phase: "PHASE_10" },
];
const style = { style_id: STYLE, product_id: PRODUCT, category_id: "cat", style_no: "0001", name_fa: "استایل ساختگی", current_revision_id: REV, status: "ACTIVE", row_version: 3, created_at: NOW };
const product = { product_id: PRODUCT, product_class_id: TYPE, product_no: "9001", name_fa: "کیف ساختگی", uom: "PIECE", buckle_type_code: null, belt_width_code: null, status: "ACTIVE", row_version: 2, created_at: NOW };
function cr(over: Record<string, unknown> = {}) {
  return {
    change_request_id: CR, request_no: "CR-1300-000001", order_id: ORDER, base_order_version: 1, kind: "DUE_DATE_CHANGE",
    items: [{ line_id: null, requested_due_date: "2026-12-20" }], reason: "تغییر ساختگی", status: "SUBMITTED", requested_by: OTHER,
    submitted_at: NOW, decided_by: null, decided_at: null, planning_required: true, planning_approved_by: null, planning_approved_at: null,
    planning_rejected_by: null, planning_rejected_at: null, applied_version: null, row_version: 2, created_at: NOW, ...over,
  };
}

const ALL_READ = [
  "identity.customer.read", "identity.product.read", "identity.serial.read", "commercial.order.read", "commercial.change.read",
  "identity.product_code.read", "identity.external_ref.read",
];

// ------------------------------------------------------------------------------------------ pages 1/2
describe("pages 1/2 serial control center (DEC-027 P-A)", () => {
  function serialRoutes(extra: Record<string, Route> = {}) {
    return signedIn(ALL_READ, {
      ["GET /identity/serials/" + SERIAL + "/tracking"]: () =>
        ok({
          serial, order_versions: [{ order_id: ORDER, version: 1, reason: "CONFIRMED", change_request_id: null, created_at: NOW }],
          events: [{ occurred_at: NOW, kind: "SERIAL_ALLOCATED", ref: { entity_type: "serial", entity_id: SERIAL, revision: 1 }, audit_event_id: "ev1" }],
          unavailable_sections: UNAVAILABLE, withheld_sections: [],
        }),
      ["GET /commercial/customer-orders/" + ORDER]: () => ok(order(), 200, 5),
      ["GET /identity/styles/" + STYLE]: () => ok(style, 200, 3),
      ["GET /identity/products/" + PRODUCT]: () => ok(product, 200, 2),
      "GET /identity/customers": () => ok(page([customer])),
      "GET /commercial/change-requests": () => ok(page([cr()])),
      ["GET /identity/serials/" + SERIAL + "/snapshots"]: () =>
        ok(page([{ serial_id: SERIAL, version: 1, reason: "ALLOCATED", order_version: 1, change_request_id: null, created_at: NOW, snapshot: { order_no: "SO-1300-000001", product_code: CODE, quantity: 40, uom: "PIECE", line_no: 1 } }])),
      "GET /identity/external-refs": () => ok(page([])),
      ...extra,
    });
  }

  it("summary: header from PHASE_02 data, codes as LTR text, later-phase sections without any number", async () => {
    stub(serialRoutes());
    renderAt(`#/serials/${SERIAL}`);
    const head = await screen.findByTestId("serial-header");
    expect(within(head).getByTestId("serial-number")).toHaveTextContent("63001");
    expect(within(head).getByTestId("serial-number")).toHaveAttribute("dir", "ltr");
    await waitFor(() => { expect(within(head).getByTestId("serial-code")).toHaveTextContent(CODE); }); // leading zero kept
    await waitFor(() => { expect(within(head).getByTestId("serial-qty")).toHaveTextContent("۴۰ عدد"); });
    expect(head).toHaveTextContent("کیف ساختگی");
    const later = await screen.findAllByTestId("later-section");
    expect(later.length).toBeGreaterThanOrEqual(6);
    for (const s of later) {
      const title = s.querySelector("h3")?.textContent ?? "";
      expect(s).toHaveTextContent(LATER_TEXT);
      expect(title + (s.querySelector(".later__text")?.textContent ?? "")).not.toMatch(/[0-9۰-۹]/); // no sample numbers
    }
    expect(await screen.findByTestId("serial-changes")).toHaveTextContent("CR-1300-000001");
  });

  it("order tab: masked representative, snapshot, versions and timeline; keyboard tabs (RTL arrows)", async () => {
    stub(serialRoutes());
    renderAt(`#/serials/${SERIAL}`);
    const tab = await screen.findByTestId("tab-summary");
    tab.focus();
    await userEvent.keyboard("{ArrowLeft}"); // RTL: next tab
    expect(screen.getByTestId("tab-order")).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByTestId("rep-masked")).toHaveTextContent("پنهان");
    expect(await screen.findByTestId("serial-snapshots")).toHaveTextContent(CODE);
    expect(screen.getByTestId("serial-versions")).toHaveTextContent("تأیید سفارش");
    expect(screen.getByTestId("serial-timeline")).toHaveTextContent("سریال تخصیص یافت");
    expect(screen.getByTestId("serial-order-no")).toHaveTextContent("SO-1300-000001");
  });

  it("order tab: the serial and the order reference panels have distinct titles (REV-0252)", async () => {
    stub(serialRoutes());
    renderAt(`#/serials/${SERIAL}`);
    const tab = await screen.findByTestId("tab-summary");
    tab.focus();
    await userEvent.keyboard("{ArrowLeft}");
    const serialRefs = await screen.findByRole("heading", { level: 2, name: "ارجاع‌های بیرونی سریال" });
    const orderRefs = await screen.findByRole("heading", { level: 2, name: "ارجاع‌های بیرونی سفارش" });
    expect(serialRefs).not.toBe(orderRefs);
    const titles = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(titles.filter((t) => t.startsWith("ارجاع‌های بیرونی"))).toEqual(["ارجاع‌های بیرونی سریال", "ارجاع‌های بیرونی سفارش"]);
  });

  it("search: empty state, and error state with request id + retry", async () => {
    let fail = true;
    stub(signedIn(ALL_READ, {
      "GET /identity/serials": () => (fail ? prob("INTERNAL_ERROR", 500) : ok(page([]))),
      "GET /identity/customers": () => ok(page([customer])),
    }));
    renderAt("#/serials");
    expect(await screen.findByTestId("state-error")).toHaveTextContent(RID);
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "تلاش مجدد" }));
    expect(await screen.findByTestId("state-empty")).toBeInTheDocument();
  });

  it("forbidden without identity.serial.read", async () => {
    stub(signedIn(["platform.workflow.task.read"]));
    renderAt("#/serials");
    expect(await screen.findByTestId("state-forbidden")).toBeInTheDocument();
    expect(screen.getByTestId("main-nav")).not.toHaveTextContent("مرکز کنترل سریال");
  });
});

// --------------------------------------------------------------------------------------------- page 29
describe("page 29 orders", () => {
  it("wizard step 1 sends ISO dates from Jalali input and keeps the Idempotency-Key across a retry", async () => {
    let attempts = 0;
    const calls = stub(signedIn([...ALL_READ, "commercial.order.manage"], {
      "GET /identity/customers": () => ok(page([customer])),
      "POST /commercial/customer-orders": () => {
        attempts += 1;
        // first attempt: the connection fails (no answer) - the client must keep the key for the retry
        return attempts === 1 ? (Promise.reject(new TypeError("network")) as unknown as Response) : ok(order({ status: "DRAFT", lines: [], current_version: null, customer_representative_name: "[REDACTED]" }), 201, 1);
      },
      ["GET /commercial/customer-orders/" + ORDER]: () => ok(order({ status: "DRAFT", lines: [], current_version: null, customer_representative_name: "نماینده ساختگی" }), 200, 1),
      ["GET /commercial/customer-orders/" + ORDER + "/versions"]: () => ok(page([])),
      "GET /identity/products": () => ok(page([])),
      "GET /identity/external-refs": () => ok(page([])),
    }));
    renderAt("#/orders/new");
    await screen.findByTestId("order-wizard");
    await waitFor(() => { expect(screen.getByTestId("wiz-customer").querySelectorAll("option").length).toBe(2); });
    await userEvent.selectOptions(screen.getByTestId("wiz-customer"), CUST);
    await userEvent.type(screen.getByTestId("wiz-po"), "PO-SYN-1");
    await userEvent.type(screen.getByTestId("wiz-rep"), "نماینده ساختگی");
    const orderDate = screen.getByTestId("wiz-order-date");
    await userEvent.clear(orderDate);
    await userEvent.type(orderDate, "۱۴۰۵/۰۸/۲۴");
    await userEvent.type(screen.getByTestId("wiz-due"), "1405/09/18");
    await userEvent.click(screen.getByTestId("wiz-create"));
    expect(await screen.findByTestId("action-error-code")).toHaveTextContent("NETWORK");
    await userEvent.click(screen.getByTestId("wiz-create"));
    await screen.findByTestId("order-detail");
    const posts = calls.filter((c) => c.method === "POST" && c.path === "/commercial/customer-orders");
    expect(posts).toHaveLength(2);
    expect(posts[0]?.headers.get("Idempotency-Key")).toBeTruthy();
    expect(posts[1]?.headers.get("Idempotency-Key")).toBe(posts[0]?.headers.get("Idempotency-Key")); // ID-04
    expect(posts[1]?.body).toMatchObject({ customer_id: CUST, order_date: "2026-11-15", requested_due_date: "2026-12-09", external_po_number: "PO-SYN-1" });
    expect(screen.getByTestId("rep-value")).toHaveTextContent("نماینده ساختگی");
  });

  it("validate: duplicate PO warning must be acknowledged, then sent with acknowledge_possible_duplicate", async () => {
    let n = 0;
    const draft = order({ status: "DRAFT", current_version: null, lines: [{ ...line, status: "OPEN", serial_id: null, serial_number: null }] });
    const calls = stub(signedIn([...ALL_READ, "commercial.order.manage"], {
      ["GET /commercial/customer-orders/" + ORDER]: () => ok(draft, 200, 5),
      "GET /identity/customers": () => ok(page([customer])),
      ["GET /commercial/customer-orders/" + ORDER + "/versions"]: () => ok(page([])),
      "GET /identity/products": () => ok(page([product])),
      "GET /identity/external-refs": () => ok(page([])),
      ["POST /commercial/customer-orders/" + ORDER + "/validate"]: () => {
        n += 1;
        return n === 1 ? prob("VALIDATION_FAILED", 400, { errors: [{ field: "external_po_number", code: "DUPLICATE_PO_NUMBER" }] }) : ok({ ...draft, status: "VALIDATED" }, 200, 6);
      },
    }));
    renderAt(`#/orders/${ORDER}`);
    await userEvent.click(await screen.findByTestId("order-validate"));
    await userEvent.click(screen.getByTestId("validate-submit"));
    expect(await screen.findByTestId("po-dup-warning")).toBeInTheDocument();
    expect(screen.getByTestId("validate-submit")).toBeDisabled();
    await userEvent.click(screen.getByTestId("po-dup-ack"));
    await userEvent.click(screen.getByTestId("validate-submit"));
    await waitFor(() => { expect(screen.queryByTestId("validate-dialog")).not.toBeInTheDocument(); });
    const v = calls.filter((c) => c.path.endsWith("/validate"));
    expect(v[0]?.headers.get("If-Match")).toBe('"5"');
    expect(v[0]?.body).toEqual({});
    expect(v[1]?.body).toEqual({ acknowledge_possible_duplicate: true });
  });

  it("confirm answers 401 MFA_REQUIRED -> fresh MFA prompt; a 412 shows the data-changed state", async () => {
    const validated = order({ status: "VALIDATED", current_version: null, lines: [{ ...line, status: "OPEN", serial_id: null, serial_number: null }] });
    let confirm = 0;
    stub(signedIn([...ALL_READ, "commercial.order.confirm"], {
      ["GET /commercial/customer-orders/" + ORDER]: () => ok(validated, 200, 6),
      "GET /identity/customers": () => ok(page([customer])),
      ["GET /commercial/customer-orders/" + ORDER + "/versions"]: () => ok(page([])),
      "GET /identity/external-refs": () => ok(page([])),
      "POST /auth/mfa/step-up": () => ok({ session_handle: "s1", state: "ACTIVE", user_id: ME, expires_at: NOW }),
      ["POST /commercial/customer-orders/" + ORDER + "/confirm"]: () => {
        confirm += 1;
        return confirm === 1 ? prob("MFA_REQUIRED", 401) : prob("VERSION_CONFLICT", 412);
      },
    }));
    renderAt(`#/orders/${ORDER}`);
    await userEvent.click(await screen.findByTestId("order-confirm"));
    await userEvent.click(screen.getByTestId("confirm-submit"));
    const dialog = await screen.findByTestId("step-up-dialog");
    await userEvent.type(within(dialog).getByTestId("step-up-code"), "123456");
    await userEvent.click(within(dialog).getByTestId("step-up-submit"));
    expect(await screen.findByTestId("version-conflict")).toHaveTextContent("تغییر کرده است");
    expect(screen.getByTestId("version-conflict-reload")).toBeInTheDocument();
    expect(confirm).toBe(2);
  });

  it("management_viewer: read-only (no create / validate / confirm buttons)", async () => {
    stub(signedIn(ALL_READ, {
      "GET /commercial/customer-orders": () => ok(page([{ order_id: ORDER, order_no: "SO-1300-000001", customer_id: CUST, external_po_number: null, order_type: "sampling", status: "DRAFT", order_date: "2026-11-15", requested_due_date: null, current_version: null, line_count: 1, row_version: 1 }])),
      "GET /identity/customers": () => ok(page([customer])),
    }));
    renderAt("#/orders");
    const table = await screen.findByTestId("orders-table");
    expect(table).toHaveTextContent("SO-1300-000001");
    expect(table).toHaveTextContent("نمونه‌سازی");
    expect(table).toHaveTextContent("۲۴ آبان ۱۴۰۵");
    expect(screen.queryByTestId("order-new")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------------------------- page 4
describe("page 4 products and styles", () => {
  it("belt type asks buckle + 2-digit width and sends them; other types never do", async () => {
    const calls = stub(signedIn([...ALL_READ, "identity.product.manage"], {
      "GET /identity/products": () => ok(page([])),
      "GET /identity/product-classes": () =>
        ok(page([
          { product_class_id: TYPE, parent_class_id: null, level_key: "product_type", label_fa: "کیف ساختگی", segment_value: "97", uom: "PIECE", product_no_scheme: "SEQUENTIAL_PER_TYPE", status: "ACTIVE", row_version: 1 },
          { product_class_id: BELT, parent_class_id: null, level_key: "product_type", label_fa: "کمربند ساختگی", segment_value: "96", uom: "PIECE", product_no_scheme: "BELT_BUCKLE_WIDTH", status: "ACTIVE", row_version: 1 },
        ])),
      "POST /identity/products": () => ok({ ...product, product_class_id: BELT, product_no: "0735", buckle_type_code: "07", belt_width_code: "35", status: "DRAFT" }, 201, 1),
      ["GET /identity/products/" + PRODUCT]: () => ok({ ...product, product_class_id: BELT, product_no: "0735", buckle_type_code: "07", belt_width_code: "35", status: "DRAFT" }, 200, 1),
      ["GET /identity/products/" + PRODUCT + "/styles"]: () => ok(page([])),
    }));
    renderAt("#/products");
    expect(await screen.findByTestId("code-check")).toBeInTheDocument();
    await userEvent.click(await screen.findByTestId("product-create-open"));
    await waitFor(() => { expect(screen.getByTestId("product-type").querySelectorAll("option").length).toBe(3); });
    await userEvent.selectOptions(screen.getByTestId("product-type"), TYPE);
    expect(screen.queryByTestId("belt-fields")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByTestId("product-type"), BELT);
    expect(screen.getByTestId("belt-fields")).toBeInTheDocument();
    await userEvent.type(screen.getByTestId("product-name"), "کمربند ساختگی");
    expect(screen.getByTestId("product-submit")).toBeDisabled();
    await userEvent.type(screen.getByTestId("product-buckle"), "07");
    await userEvent.type(screen.getByTestId("product-width"), "35");
    await userEvent.click(screen.getByTestId("product-submit"));
    expect(await screen.findByTestId("product-no")).toHaveTextContent("0735"); // leading zero kept
    const post = calls.find((c) => c.method === "POST" && c.path === "/identity/products");
    expect(post?.body).toEqual({ product_class_id: BELT, name_fa: "کمربند ساختگی", buckle_type_code: "07", belt_width_code: "35" });
  });

  it("style: code preview (side-effect free, no Idempotency-Key) then issue (Idempotency-Key, rule revision)", async () => {
    let issued = false;
    const calls = stub(signedIn([...ALL_READ, "identity.product.manage", "identity.product_code.issue"], {
      "GET /identity/products": () => ok(page([product])),
      ["GET /identity/products/" + PRODUCT]: () => ok(product, 200, 2),
      "GET /identity/product-classes": () => ok(page([])),
      ["GET /identity/products/" + PRODUCT + "/styles"]: () => ok(page([style])),
      ["GET /identity/styles/" + STYLE]: () => ok(style, 200, 3),
      ["GET /identity/styles/" + STYLE + "/revisions"]: () => ok(page([{ style_revision_id: REV, style_id: STYLE, revision_no: 1, attributes: { colour_fa: "مشکی ساختگی" }, status: "ACTIVE", created_at: NOW, row_version: 1 }])),
      ["GET /identity/styles/" + STYLE + "/tracking"]: () => ok({ style, counts: { serials_total: 0, serials_active: 0, orders_total: null }, serials: [], unavailable_sections: UNAVAILABLE, withheld_sections: ["orders"], page: { page_size: 25, next_cursor: null } }),
      "GET /identity/customers": () => ok(page([customer])),
      "GET /identity/product-codes": () => ok(page(issued ? [{ product_code_id: "pc1", code: CODE, code_namespace: "product_code", style_id: STYLE, rule_revision_id: "r1", status: "RESERVED", erp_status: "ERP_PENDING", issued_at: NOW, row_version: 1 }] : [])),
      "POST /identity/product-codes/preview": () => ok({ code: CODE, rule_revision_id: "r1", segments: [], new_product: false, legacy_only: false, issued: false }),
      "POST /identity/product-codes": () => {
        issued = true;
        return ok({ product_code_id: "pc1", code: CODE, code_namespace: "product_code", style_id: STYLE, rule_revision_id: "r1", status: "RESERVED", erp_status: "ERP_PENDING", issued_at: NOW, row_version: 1 }, 201, 1);
      },
    }));
    renderAt(`#/products/${PRODUCT}/${STYLE}`);
    await userEvent.click(await screen.findByTestId("code-preview"));
    expect(await screen.findByTestId("code-preview-value")).toHaveTextContent(CODE);
    await userEvent.click(screen.getByTestId("code-issue"));
    expect(await screen.findByTestId("issued-code")).toHaveTextContent(CODE);
    expect(screen.getByTestId("style-codes")).toHaveTextContent("منتظر ثبت دستی در راهکاران");
    const preview = calls.find((c) => c.path === "/identity/product-codes/preview");
    expect(preview?.headers.get("Idempotency-Key")).toBeNull();
    const issue = calls.find((c) => c.method === "POST" && c.path === "/identity/product-codes");
    expect(issue?.headers.get("Idempotency-Key")).toBeTruthy();
    expect(issue?.body).toEqual({ style_id: STYLE, rule_revision_id: "r1" });
    expect(screen.getByTestId("style-counts")).toHaveTextContent("بدون مجوز"); // withheld order count
    expect(screen.getByTestId("withheld")).toBeInTheDocument();
  });

  it("RULE_NOT_APPROVED on preview names the decision and blocks the action", async () => {
    stub(signedIn([...ALL_READ], {
      "GET /identity/products": () => ok(page([product])),
      ["GET /identity/products/" + PRODUCT]: () => ok(product, 200, 2),
      "GET /identity/product-classes": () => ok(page([])),
      ["GET /identity/products/" + PRODUCT + "/styles"]: () => ok(page([style])),
      ["GET /identity/styles/" + STYLE]: () => ok(style, 200, 3),
      ["GET /identity/styles/" + STYLE + "/revisions"]: () => ok(page([])),
      ["GET /identity/styles/" + STYLE + "/tracking"]: () => ok({ style, counts: { serials_total: 0, serials_active: 0, orders_total: 0 }, serials: [], unavailable_sections: UNAVAILABLE, page: { page_size: 25, next_cursor: null } }),
      "GET /identity/customers": () => ok(page([customer])),
      "GET /identity/product-codes": () => ok(page([])),
      "POST /identity/product-codes/preview": () => prob("RULE_NOT_APPROVED", 409, { decision_id: "DEC-005", errors: [{ field: "rule", code: "NO_ACTIVE_CODE_RULE" }] }),
    }));
    renderAt(`#/products/${PRODUCT}/${STYLE}`);
    await userEvent.click(await screen.findByTestId("code-preview"));
    const blocked = await screen.findByTestId("rule-blocked");
    expect(blocked).toHaveTextContent("DEC-005");
    expect(blocked).toHaveTextContent("قاعده کد فعالی وجود ندارد");
    expect(screen.queryByTestId("code-issue")).not.toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------------------------- page 33
describe("page 33 change requests", () => {
  function routes(c: ReturnType<typeof cr>, perms: string[]) {
    return signedIn([...ALL_READ, ...perms], {
      ["GET /commercial/change-requests/" + CR]: () => ok(c, 200, c.row_version),
      ["GET /commercial/change-requests/" + CR + "/impact"]: () => ok({ change_request_id: CR, base_order_version: 1, lines_affected: [], serials_affected: [], new_lines: 0, snapshots_to_write: 0, unavailable_sections: UNAVAILABLE }),
      ["GET /commercial/customer-orders/" + ORDER]: () => ok(order(), 200, 5),
      ["POST /commercial/change-requests/" + CR + "/planning-decision"]: () => ok({ ...c, planning_approved_by: ME, planning_approved_at: NOW, row_version: 3 }, 200, 3),
    });
  }

  it("planning officer sees the planning decision (not the commercial one); before/after in Jalali; impact later sections", async () => {
    const calls = stub(routes(cr(), ["commercial.change.planning_approve"]));
    renderAt(`#/changes/${CR}`);
    const ba = await screen.findByTestId("cr-before-after");
    await waitFor(() => { expect(screen.getByTestId("cr-before-after")).toHaveTextContent("۱۸ آذر ۱۴۰۵"); }); // current value from the order
    expect(ba).toHaveTextContent("۲۹ آذر ۱۴۰۵");
    expect(screen.queryByTestId("cr-approve")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("cr-plan-approve"));
    await userEvent.click(screen.getByTestId("cr-decision-submit"));
    await waitFor(() => { expect(screen.queryByTestId("cr-decision-dialog")).not.toBeInTheDocument(); });
    const post = calls.find((x) => x.path.endsWith("/planning-decision"));
    expect(post?.body).toEqual({ decision: "APPROVE" });
    expect(post?.headers.get("If-Match")).toBe('"2"');
    const impact = await screen.findByTestId("cr-impact");
    expect(impact).toBeInTheDocument();
    expect(screen.getAllByTestId("later-section").length).toBe(4);
  });

  it("the requester never gets decide buttons (maker-checker); a planning reject needs a reason", async () => {
    stub(routes(cr({ requested_by: ME }), ["commercial.change.decide", "commercial.change.planning_approve", "commercial.change.request"]));
    renderAt(`#/changes/${CR}`);
    expect(await screen.findByTestId("cr-own")).toBeInTheDocument();
    expect(screen.queryByTestId("cr-approve")).not.toBeInTheDocument();
    expect(screen.queryByTestId("cr-plan-approve")).not.toBeInTheDocument();
    expect(screen.getByTestId("cr-withdraw")).toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------------------------- page 39
describe("page 39 inbox: PHASE_02 decisions", () => {
  it("lists the decisions waiting for me with links to their pages", async () => {
    stub(signedIn(["commercial.order.confirm", "identity.code_rule.approve"], {
      "GET /me/decision-inbox": () =>
        ok({
          as_of: NOW,
          truncated: false,
          items: [
            { kind: "ORDER_CONFIRM", entity_type: "customer_order", entity_id: ORDER, number: "SO-1300-000001", revision_no: null, requested_by: OTHER, requested_at: NOW, row_version: 4 },
            { kind: "CODE_RULE_APPROVE", entity_type: "code_rule_revision", entity_id: "11111111-0000-4000-8000-000000000009", number: null, revision_no: 2, requested_by: OTHER, requested_at: NOW, row_version: 3 },
          ],
        }),
    }));
    renderAt("#/work");
    expect(await screen.findByTestId("tab-decisions")).toHaveAttribute("aria-selected", "true");
    const list = await screen.findByTestId("decisions-list");
    expect(within(list).getByTestId("decision-ORDER_CONFIRM")).toHaveTextContent("SO-1300-000001");
    const links = within(list).getAllByTestId("decision-open");
    expect(links[0]).toHaveAttribute("href", `#/orders/${ORDER}`);
    expect(links[1]).toHaveAttribute("href", "#/code-rules/11111111-0000-4000-8000-000000000009");
    expect(screen.getByTestId("main-nav")).toHaveTextContent("کارها و تأییدها");
  });

  it("empty inbox", async () => {
    stub(signedIn(["commercial.change.decide"], { "GET /me/decision-inbox": () => ok({ as_of: NOW, truncated: false, items: [] }) }));
    renderAt("#/work");
    expect(await screen.findByTestId("state-empty")).toHaveTextContent("تصمیمی منتظر شما نیست");
  });
});

// ------------------------------------------------------------------------------------- customers / rules
describe("customers and code rules", () => {
  it("customer create: duplicate-name warning must be acknowledged; the CU- number is shown as text", async () => {
    let n = 0;
    const calls = stub(signedIn(["identity.customer.read", "identity.customer.manage"], {
      "GET /identity/customers": () => ok(page([])),
      "POST /identity/customers": () => {
        n += 1;
        return n === 1 ? prob("VALIDATION_FAILED", 400, { errors: [{ field: "display_name_fa", code: "DUPLICATE_CUSTOMER_NAME" }] }) : ok(customer, 201, 1);
      },
      ["GET /identity/customers/" + CUST]: () => ok(customer, 200, 1),
      ["GET /identity/customers/" + CUST + "/brands"]: () => ok(page([])),
    }));
    renderAt("#/customers");
    expect(await screen.findByTestId("state-empty")).toHaveTextContent("هنوز مشتری‌ای ثبت نشده است");
    await userEvent.click(screen.getByTestId("customer-create-open"));
    await userEvent.type(screen.getByTestId("customer-name"), "مشتری ساختگی");
    await userEvent.click(screen.getByTestId("customer-submit"));
    expect(await screen.findByTestId("customer-dup-warning")).toBeInTheDocument();
    expect(screen.getByTestId("customer-submit")).toBeDisabled();
    await userEvent.click(screen.getByTestId("customer-dup-ack"));
    await userEvent.click(screen.getByTestId("customer-submit"));
    expect(await screen.findByTestId("customer-no")).toHaveTextContent("CU-1300-000001");
    const posts = calls.filter((c) => c.method === "POST");
    expect(posts[0]?.body).not.toHaveProperty("acknowledge_possible_duplicate");
    expect(posts[1]?.body).toMatchObject({ display_name_fa: "مشتری ساختگی", acknowledge_possible_duplicate: true });
  });

  it("code rule: the maker sees no approve button; an approver approves with resource_revision + If-Match", async () => {
    const RULE = "11111111-0000-4000-8000-000000000009";
    const rule = (over: Record<string, unknown> = {}) => ({
      rule_revision_id: RULE, code_namespace: "product_code", revision_no: 2, scope: { product_types: ["96", "97"] }, rule_spec: {},
      source_workbook_sha256: "e2".repeat(32), golden_case_count: 40, status: "IN_REVIEW", decision_id: "DEC-005", created_by: OTHER,
      approved_by: null, approved_at: null, row_version: 4,
      golden_summary: { total: 40, per_family: { "96": 20, "97": 20 }, belt_checked: 20, legacy_only_style_0000: 0, not_reproduced: 0, families_below_minimum: [] },
      ...over,
    });
    const calls = stub(signedIn(["identity.code_rule.read", "identity.code_rule.approve"], {
      "GET /identity/code-rule-revisions": () => ok(page([rule()])),
      ["GET /identity/code-rule-revisions/" + RULE]: () => ok(rule(), 200, 4),
      ["POST /identity/code-rule-revisions/" + RULE + "/approve"]: () => ok(rule({ status: "APPROVED", approved_by: ME, approved_at: NOW, row_version: 5 }), 200, 5),
    }));
    renderAt(`#/code-rules/${RULE}`);
    expect(await screen.findByTestId("golden-summary")).toHaveTextContent("۴۰");
    await userEvent.click(screen.getByTestId("rule-approve"));
    await userEvent.type(screen.getByTestId("reason-input"), "تأیید ساختگی");
    await userEvent.click(screen.getByTestId("reason-submit"));
    await waitFor(() => { expect(calls.some((c) => c.path.endsWith("/approve"))).toBe(true); });
    const post = calls.find((c) => c.path.endsWith("/approve"));
    expect(post?.body).toEqual({ resource_revision: 2, note: "تأیید ساختگی" });
    expect(post?.headers.get("If-Match")).toBe('"4"');
  });

  it("code rule: own revision -> no approve button", async () => {
    const RULE = "11111111-0000-4000-8000-000000000008";
    const r = {
      rule_revision_id: RULE, code_namespace: "product_code", revision_no: 3, scope: {}, rule_spec: {}, source_workbook_sha256: "e3".repeat(32),
      golden_case_count: 0, status: "IN_REVIEW", decision_id: "DEC-005", created_by: ME, approved_by: null, approved_at: null, row_version: 1,
    };
    stub(signedIn(["identity.code_rule.read", "identity.code_rule.approve"], {
      "GET /identity/code-rule-revisions": () => ok(page([r])),
      ["GET /identity/code-rule-revisions/" + RULE]: () => ok(r, 200, 1),
    }));
    renderAt(`#/code-rules/${RULE}`);
    expect(await screen.findByTestId("rule-own")).toBeInTheDocument();
    expect(screen.queryByTestId("rule-approve")).not.toBeInTheDocument();
  });
});

// ------------------------------------------------------------------- regression (02.5 E2E, test 16)
describe("regression: one react-query cache, order page then serial page", () => {
  it("the serial header renders after the order page cached the same order (no shape collision)", async () => {
    stub(signedIn([...ALL_READ, "commercial.order.confirm"], {
      ["GET /commercial/customer-orders/" + ORDER]: () => ok(order(), 200, 5),
      ["GET /commercial/customer-orders/" + ORDER + "/versions"]: () => ok(page([{ order_id: ORDER, version: 1, reason: "CONFIRMED", change_request_id: null, created_at: NOW }])),
      ["GET /identity/serials/" + SERIAL + "/tracking"]: () =>
        ok({ serial, order_versions: [], events: [], unavailable_sections: UNAVAILABLE, withheld_sections: [] }),
      ["GET /identity/serials/" + SERIAL + "/snapshots"]: () => ok(page([])),
      ["GET /identity/styles/" + STYLE]: () => ok(style, 200, 3),
      ["GET /identity/products/" + PRODUCT]: () => ok(product, 200, 2),
      "GET /identity/customers": () => ok(page([customer])),
      "GET /commercial/change-requests": () => ok(page([])),
      "GET /identity/external-refs": () => ok(page([])),
    }));
    renderAt(`#/orders/${ORDER}`);
    await userEvent.click(await screen.findByTestId("line-serial")); // same client, hash navigation
    const head = await screen.findByTestId("serial-header");
    await waitFor(() => { expect(within(head).getByTestId("serial-qty")).toHaveTextContent("۴۰ عدد"); });
    expect(screen.queryByTestId("state-render-error")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("tab-order"));
    expect(await screen.findByTestId("serial-order-no")).toHaveTextContent("SO-1300-000001");
  });

  it("a render error shows the page error state instead of an empty page", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    function Broken(): never {
      throw new TypeError("synthetic render failure");
    }
    render(
      <PageErrorBoundary>
        <Broken />
      </PageErrorBoundary>,
    );
    expect(screen.getByTestId("state-render-error")).toHaveTextContent("نمایش این صفحه با خطا روبه‌رو شد");
    spy.mockRestore();
  });
});
