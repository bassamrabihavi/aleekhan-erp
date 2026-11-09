// Request core for the PHASE_01 API (docs/api/API_RUNTIME.md §2, §9): session cookie (same origin), CSRF header
// on unsafe methods, Idempotency-Key on writes, If-Match from the ETag, problem+json -> ApiError. A body that
// fails the contract guard is rejected (kind "contract") and never rendered as data.
import { API_BASE, ApiError } from "./client";
import { isProblem } from "./guards";

export type Method = "GET" | "POST" | "PATCH";
export type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  method?: Method;
  query?: Query | undefined;
  body?: unknown;
  form?: FormData;
  /** Row version from the ETag (sent as `If-Match: "<n>"`). */
  ifMatch?: number | null | undefined;
  /** UUID; required by the server for every mutating, non-ceremony request. */
  idempotencyKey?: string | undefined;
  signal?: AbortSignal | undefined;
}

export interface ApiResponse<T> {
  data: T;
  status: number;
  /** Row version parsed from `ETag: "<n>"` (null when absent or not numeric). */
  version: number | null;
  requestId: string | null;
  replayed: boolean;
}

/** Fired on 401 AUTHENTICATION_REQUIRED / 403 PASSWORD_CHANGE_REQUIRED of a non-auth call (session gone). */
export const AUTH_LOST_EVENT = "aleekhan:auth-lost";

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export function readCookie(name: string): string | null {
  const parts = document.cookie ? document.cookie.split("; ") : [];
  for (const p of parts) {
    const i = p.indexOf("=");
    if (i > 0 && p.slice(0, i) === name) return decodeURIComponent(p.slice(i + 1));
  }
  return null;
}

function buildUrl(path: string, query?: Query): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const s = qs.toString();
  return `${API_BASE}${path}${s ? `?${s}` : ""}`;
}

function parseVersion(etag: string | null): number | null {
  if (!etag) return null;
  const m = /^"(\d+)"$/.exec(etag.trim());
  return m ? Number(m[1]) : null;
}

export async function apiRequest<T>(
  path: string,
  guard: (body: unknown) => body is T,
  opts: RequestOptions = {},
): Promise<ApiResponse<T>> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json, application/problem+json" };
  let body: BodyInit | null = null;
  if (opts.form) {
    body = opts.form; // multipart boundary set by the browser
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (method !== "GET") {
    const csrf = readCookie("csrftoken");
    if (csrf) headers["X-CSRFToken"] = csrf;
  }
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
  if (opts.ifMatch !== undefined && opts.ifMatch !== null) headers["If-Match"] = `"${opts.ifMatch}"`;

  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method,
      headers,
      body,
      credentials: "same-origin",
      cache: "no-store",
      signal: opts.signal ?? null,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError({ kind: "network", status: null });
  }

  const requestId = res.headers.get("X-Request-ID");
  const contentType = (res.headers.get("Content-Type") ?? "").toLowerCase();
  let parsed: unknown = undefined;
  if (contentType.includes("json")) {
    try {
      parsed = await res.json();
    } catch {
      parsed = null;
    }
  }

  if (contentType.includes("application/problem+json") && isProblem(parsed)) {
    const e = ApiError.fromProblem(parsed, requestId);
    if (!path.startsWith("/auth/") && (e.code === "AUTHENTICATION_REQUIRED" || e.code === "PASSWORD_CHANGE_REQUIRED")) {
      window.dispatchEvent(new CustomEvent(AUTH_LOST_EVENT, { detail: e.code }));
    }
    throw e;
  }
  if (res.ok) {
    if (res.status === 204) parsed = undefined;
    if (guard(parsed)) {
      return {
        data: parsed,
        status: res.status,
        version: parseVersion(res.headers.get("ETag")),
        requestId,
        replayed: res.headers.get("Idempotent-Replayed") === "true",
      };
    }
    throw new ApiError({ kind: "contract", status: res.status, requestId });
  }
  if (res.status >= 500 && !contentType.includes("json")) {
    throw new ApiError({ kind: "network", status: res.status, requestId });
  }
  throw new ApiError({ kind: "contract", status: res.status, requestId });
}
