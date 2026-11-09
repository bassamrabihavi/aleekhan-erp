// Unit tests of the PHASE_01 shell and pages (01.5). fetch is stubbed here only (MOCK_UI_BINDING §2 rule 1);
// bodies follow docs/api/openapi-draft.yaml 0.6.1-draft with synthetic values. The E2E suite runs the same
// flows against the real Django backend.
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { App } from "./App";
import { ApiError } from "./api/client";
import { apiRequest } from "./api/http";
import { shape } from "./api/phase01";
import { ActionError } from "./components/ActionError";
import { createQueryClient } from "./queryClient";

const RID = "11111111-2222-4333-8444-555555555555";
const ME_ID = "aaaaaaaa-0000-4000-8000-000000000001";
const NOW = "2026-11-06T08:00:00Z";
// Synthetic test credential (not a secret), named SYN_PW_*.
const SYN_PW_OTP = "Syn-Otp-Pass-1";

type Route = (body: unknown, headers: Headers) => Response;
interface Call {
  method: string;
  path: string;
  headers: Headers;
  body: unknown;
}

function ok(body: unknown, status = 200, etag?: number): Response {
  const h: Record<string, string> = { "Content-Type": "application/json", "X-Request-ID": RID };
  if (etag !== undefined) h.ETag = `"${String(etag)}"`;
  return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: h });
}
function prob(code: string, status: number, extra: Record<string, unknown> = {}): Response {
  return new Response(
    JSON.stringify({ type: "about:blank", title: code, status, code, message_fa: `پیام ساختگی ${code}`, request_id: RID, ...extra }),
    { status, headers: { "Content-Type": "application/problem+json", "X-Request-ID": RID } },
  );
}

function stub(routes: Record<string, Route>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const path = (url.split("?")[0] ?? url).replace("/api/v1", "");
      const method = init?.method ?? "GET";
      const headers = new Headers(init?.headers);
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : init?.body;
      calls.push({ method, path, headers, body });
      const r = routes[`${method} ${path}`];
      if (!r) return Promise.reject(new TypeError(`unrouted ${method} ${path}`));
      return Promise.resolve(r(body, headers));
    }),
  );
  return calls;
}

const SESSION = {
  session_handle: "bbbbbbbb-0000-4000-8000-000000000001",
  state: "ACTIVE",
  user_id: ME_ID,
  created_at: NOW,
  last_seen_at: NOW,
  expires_at: "2026-11-06T10:00:00Z",
  mfa_verified_at: NOW,
  network_zone: "INTERNAL",
  is_current: true,
};
const USER = {
  user_id: ME_ID,
  username: "syn.owner",
  display_name: "مالک ساختگی",
  status: "ACTIVE",
  account_kind: "PERSON",
  network_policy: "ANY_WITH_MFA_OUTSIDE",
  mfa_enrolled: true,
  mfa_required: true,
  created_at: NOW,
  created_by: null,
  row_version: 3,
};
const VERSION = { api_version: "v1", contract_version: "0.6.1-draft", build_commit: "abcdef1234567", environment: "dev" };

function grants(actions: string[]) {
  return {
    user_id: ME_ID,
    computed_at: NOW,
    grants: actions.map((a) => ({ action: a, scope: { kind: "GLOBAL" }, via_role: "owner_admin" })),
  };
}

function signedIn(actions: string[], extra: Record<string, Route> = {}): Record<string, Route> {
  return {
    "GET /version": () => ok(VERSION),
    "GET /auth/session": () => ok(SESSION),
    "GET /me": () => ok({ user: USER, roles: [], positions: [] }),
    "GET /me/permissions": () => ok(grants(actions)),
    ...extra,
  };
}

function renderAt(hash: string) {
  window.location.hash = hash;
  const client = createQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  document.cookie = "csrftoken=syn-csrf-token; path=/";
});

describe("request core", () => {
  it("sends CSRF header, Idempotency-Key and If-Match; parses the ETag version", async () => {
    const calls = stub({ "POST /x": () => ok({ a: 1 }, 200, 7) });
    const r = await apiRequest("/x", shape<{ a: number }>("a"), {
      method: "POST",
      body: { reason: "synthetic" },
      idempotencyKey: "cccccccc-0000-4000-8000-000000000001",
      ifMatch: 6,
    });
    expect(r.version).toBe(7);
    const h = calls[0]?.headers;
    expect(h?.get("X-CSRFToken")).toBe("syn-csrf-token");
    expect(h?.get("Idempotency-Key")).toBe("cccccccc-0000-4000-8000-000000000001");
    expect(h?.get("If-Match")).toBe('"6"');
  });

  it("a body that misses contract keys is a contract error, never data", async () => {
    stub({ "GET /x": () => ok({ b: 1 }) });
    await expect(apiRequest("/x", shape<{ a: number }>("a"))).rejects.toMatchObject({ kind: "contract" });
  });
});

describe("ActionError", () => {
  it("RULE_NOT_APPROVED names the decision and says the action is blocked", () => {
    render(
      <ActionError
        error={new ApiError({ kind: "problem", status: 409, code: "RULE_NOT_APPROVED", decisionId: "DEC-018", requestId: RID })}
      />,
    );
    expect(screen.getByTestId("rule-blocked")).toHaveTextContent("این قاعده هنوز تصویب نشده است (DEC-018)");
    expect(screen.getByTestId("rule-blocked")).toHaveTextContent(RID);
  });
});

describe("shell and login", () => {
  it("no session -> login form; a failed login shows the server message with code and request id", async () => {
    stub({
      "GET /version": () => ok(VERSION),
      "GET /auth/session": () => prob("AUTHENTICATION_REQUIRED", 401),
      "GET /auth/login": () => ok({ status: "ok" }),
      "POST /auth/login": () => prob("INVALID_CREDENTIALS", 401),
    });
    renderAt("#/");
    expect(await screen.findByTestId("login")).toBeInTheDocument();
    await userEvent.type(screen.getByTestId("login-username"), "syn.user");
    await userEvent.type(screen.getByTestId("login-password"), "x");
    await userEvent.click(screen.getByTestId("login-submit"));
    expect(await screen.findByTestId("action-error")).toHaveTextContent("INVALID_CREDENTIALS");
    expect(screen.getByTestId("action-error")).toHaveTextContent(RID);
    expect(screen.queryByTestId("main-nav")).not.toBeInTheDocument();
  });

  it("MFA pending session -> code screen; forced password change -> password screen", async () => {
    stub({ "GET /version": () => ok(VERSION), "GET /auth/session": () => prob("MFA_REQUIRED", 401) });
    const first = renderAt("#/");
    expect(await screen.findByTestId("mfa")).toBeInTheDocument();
    first.unmount();
    stub({
      "GET /version": () => ok(VERSION),
      "GET /auth/session": () => ok(SESSION),
      "GET /me": () => prob("PASSWORD_CHANGE_REQUIRED", 403),
    });
    renderAt("#/");
    expect(await screen.findByTestId("password-change")).toBeInTheDocument();
  });

  it("role-sensitive navigation: only granted sections are listed; env banner says synthetic data", async () => {
    stub(signedIn(["platform.document.read", "platform.org.read"]));
    renderAt("#/");
    const nav = await screen.findByTestId("main-nav");
    expect(within(nav).getByText("اسناد")).toBeInTheDocument();
    expect(within(nav).getByText("درخت سازمانی")).toBeInTheDocument();
    expect(within(nav).queryByText("امنیت و کاربران")).not.toBeInTheDocument();
    expect(within(nav).queryByText("سلامت سامانه و Job")).not.toBeInTheDocument();
    expect(await screen.findByTestId("env-banner")).toHaveTextContent("محیط آزمایشی — داده ساختگی");
  });

  it("a 401 on a page call (session ended) returns to the login screen with a notice", async () => {
    let session = true;
    const routes = signedIn(["platform.document.read"], {
      "GET /documents": () => prob("AUTHENTICATION_REQUIRED", 401),
      "GET /auth/session": () => (session ? ok(SESSION) : prob("AUTHENTICATION_REQUIRED", 401)),
      "GET /auth/login": () => ok({ status: "ok" }),
    });
    stub(routes);
    renderAt("#/");
    await screen.findByTestId("main-nav");
    session = false;
    act(() => {
      window.location.hash = "#/documents";
    });
    expect(await screen.findByTestId("login-notice")).toHaveTextContent("جلسه شما پایان یافته است");
  });
});

describe("MFA step-up", () => {
  it("401 MFA_REQUIRED opens the step-up dialog, then the action is re-sent once with a new key", async () => {
    let attempts = 0;
    const calls = stub(
      signedIn(["platform.ops.job.read", "platform.ops.job.cancel"], {
        "GET /admin/job-definitions": () =>
          ok({ items: [{ job_type: "audit_integrity_check", name_fa: "بررسی ساختگی", cancellable: true, protected: false }], page: { page_size: 100, next_cursor: null } }),
        "GET /admin/jobs": () =>
          ok({
            items: [{ job_id: "dddddddd-0000-4000-8000-000000000001", job_type: "audit_integrity_check", state: "QUEUED", queued_at: NOW, started_at: null, finished_at: null, progress: null, row_version: 1 }],
            page: { page_size: 25, next_cursor: null },
          }),
        "POST /admin/jobs/dddddddd-0000-4000-8000-000000000001/request-cancel": () => {
          attempts += 1;
          return attempts === 1
            ? prob("MFA_REQUIRED", 401)
            : ok({ job_id: "dddddddd-0000-4000-8000-000000000001", job_type: "audit_integrity_check", state: "CANCELLED", queued_at: NOW, started_at: null, finished_at: NOW, progress: null, row_version: 2 });
        },
        "POST /auth/mfa/step-up": () => ok(SESSION),
      }),
    );
    renderAt("#/ops");
    await userEvent.click(await screen.findByTestId("job-cancel"));
    await userEvent.type(screen.getByTestId("reason-input"), "پایان ساختگی");
    await userEvent.click(screen.getByTestId("reason-submit"));
    const dialog = await screen.findByTestId("step-up-dialog");
    await userEvent.type(within(dialog).getByTestId("step-up-code"), "123456");
    await userEvent.click(within(dialog).getByTestId("step-up-submit"));
    await waitFor(() => {
      expect(attempts).toBe(2);
    });
    const cancels = calls.filter((c) => c.path.endsWith("/request-cancel"));
    expect(cancels[0]?.headers.get("If-Match")).toBe('"1"');
    expect(cancels[0]?.headers.get("Idempotency-Key")).not.toBe(cancels[1]?.headers.get("Idempotency-Key"));
    await waitFor(() => {
      expect(screen.queryByTestId("job-cancel-dialog")).not.toBeInTheDocument();
    });
  });

  it("protected job types are shown as not cancellable", async () => {
    stub(
      signedIn(["platform.ops.job.read", "platform.ops.job.cancel"], {
        "GET /admin/job-definitions": () =>
          ok({ items: [{ job_type: "db_backup", name_fa: "پشتیبان‌گیری", cancellable: false, protected: true }], page: { page_size: 100, next_cursor: null } }),
        "GET /admin/jobs": () =>
          ok({
            items: [{ job_id: "dddddddd-0000-4000-8000-000000000002", job_type: "db_backup", state: "RUNNING", queued_at: NOW, started_at: NOW, finished_at: null, progress: null, row_version: 1 }],
            page: { page_size: 25, next_cursor: null },
          }),
      }),
    );
    renderAt("#/ops");
    expect(await screen.findByTestId("job-not-cancellable")).toHaveTextContent("محافظت‌شده");
    expect(screen.queryByTestId("job-cancel")).not.toBeInTheDocument();
  });
});

describe("page 46: one-time password", () => {
  it("is shown once after create and the dialog closes only after acknowledgement", async () => {
    const calls = stub(
      signedIn(["platform.identity.user.read", "platform.identity.user.create"], {
        "GET /admin/users": () => ok({ items: [USER], page: { page_size: 25, next_cursor: null } }),
        "POST /admin/users": () =>
          ok({ user: { ...USER, user_id: "aaaaaaaa-0000-4000-8000-000000000002", username: "syn.new", status: "CREATED" }, one_time_credential: { user_id: "aaaaaaaa-0000-4000-8000-000000000002", one_time_password: SYN_PW_OTP, expires_at: NOW } }, 201),
      }),
    );
    renderAt("#/security");
    await userEvent.click(await screen.findByTestId("user-create-open"));
    await userEvent.type(screen.getByTestId("new-username"), "syn.new");
    await userEvent.type(screen.getByTestId("new-display-name"), "کاربر ساختگی");
    await userEvent.type(screen.getByTestId("new-reason"), "آزمون ساختگی");
    await userEvent.click(screen.getByTestId("user-create-submit"));
    expect(await screen.findByTestId("otp-value")).toHaveTextContent(SYN_PW_OTP);
    expect(screen.getByTestId("otp-close")).toBeDisabled();
    await userEvent.keyboard("{Escape}");
    expect(screen.getByTestId("otp-dialog")).toBeInTheDocument(); // Escape does not dismiss it
    await userEvent.click(screen.getByTestId("otp-ack"));
    await userEvent.click(screen.getByTestId("otp-close"));
    await waitFor(() => {
      expect(screen.queryByText(SYN_PW_OTP)).not.toBeInTheDocument();
    });
    expect(calls.find((c) => c.method === "POST" && c.path === "/admin/users")?.headers.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe("org tree", () => {
  it("is a keyboard tree: arrows move focus, ArrowRight collapses (RTL), aria-expanded follows", async () => {
    const unit = (id: string, name: string, parent: string | null) => ({
      unit_id: id, code: `syn_${id.slice(0, 4)}`, name_fa: name, unit_type: parent ? "DEPARTMENT" : "COMPANY",
      parent_unit_id: parent, valid_from: NOW, valid_to: null, status: "ACTIVE", row_version: 1,
    });
    const root = "eeeeeeee-0000-4000-8000-000000000001";
    const child = "eeeeeeee-0000-4000-8000-000000000002";
    stub(
      signedIn(["platform.org.read"], {
        "GET /org/tree": () =>
          ok({
            as_of: NOW,
            roots: [{ unit: unit(root, "شرکت ساختگی", null), positions: [], children: [{ unit: unit(child, "اداره ساختگی", root), positions: [], children: [] }] }],
          }),
      }),
    );
    renderAt("#/org");
    const tree = await screen.findByTestId("org-tree");
    const items = within(tree).getAllByRole("treeitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveAttribute("aria-expanded", "true");
    expect(items[0]).toHaveAttribute("tabindex", "0");
    items[0]?.focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(within(tree).getAllByRole("treeitem")[1]);
    await userEvent.keyboard("{ArrowRight}"); // leaf -> parent
    expect(document.activeElement).toBe(within(tree).getAllByRole("treeitem")[0]);
    await userEvent.keyboard("{ArrowRight}"); // collapse
    expect(within(tree).getAllByRole("treeitem")).toHaveLength(1);
    expect(within(tree).getAllByRole("treeitem")[0]).toHaveAttribute("aria-expanded", "false");
  });
});
