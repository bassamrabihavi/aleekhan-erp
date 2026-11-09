// Unit-test-only fetch stub (MOCK_UI_BINDING §2 rule 1: fakes live in unit tests only, never in the bundle).
// Bodies follow docs/api/openapi-draft.yaml; values are synthetic.
import { vi } from "vitest";

export type Handler = () => Response | Promise<Response>;

export const json = (body: unknown, status = 200, extra: Record<string, string> = {}): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "X-Request-ID": SYN_REQUEST_ID, ...extra },
  });

export const problem = (body: Record<string, unknown>, status: number): Response =>
  new Response(JSON.stringify({ type: "about:blank", title: "x", status, ...body }), {
    status,
    headers: { "Content-Type": "application/problem+json", "X-Request-ID": String(body.request_id) },
  });

export const SYN_REQUEST_ID = "11111111-2222-4333-8444-555555555555";

export const READY_BODY = {
  status: "ready",
  checked_at: "2026-11-03T10:00:00Z",
  components: [
    { name: "database", status: "up" },
    { name: "migrations", status: "up" },
    { name: "cache", status: "up" },
  ],
};

export const VERSION_BODY = {
  api_version: "v1",
  contract_version: "0.3.0-draft",
  build_commit: "abcdef1234567",
  environment: "dev",
};

export const UNAUTH_PROBLEM = {
  code: "AUTHENTICATION_REQUIRED",
  message_fa: "ابتدا وارد سامانه شوید.",
  request_id: "99999999-8888-4777-8666-555555555555",
};

export function defaultRoutes(): Record<string, Handler> {
  return {
    "/api/v1/health/ready": () => json(READY_BODY),
    "/api/v1/health/live": () => json({ status: "ok" }),
    "/api/v1/version": () => json(VERSION_BODY),
    "/api/v1/access-gate/check": () => problem(UNAUTH_PROBLEM, 401),
    "/api/v1/auth/session": () => problem(UNAUTH_PROBLEM, 401),
  };
}

/** Installs a fetch stub; the returned object can be mutated by the test to change later answers. */
export function stubFetch(routes: Record<string, Handler>): Record<string, Handler> {
  const fn = vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = url.split("?")[0] ?? url;
    const handler = routes[path];
    if (!handler) return Promise.reject(new TypeError(`unrouted ${path}`));
    return Promise.resolve(handler());
  });
  vi.stubGlobal("fetch", fn);
  return routes;
}
