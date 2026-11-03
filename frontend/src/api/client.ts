// Thin fetch wrapper for the versioned API (same origin; the Vite dev server proxies /api to Django).
import { isProblem } from "./guards";
import type { Problem } from "./types";

export const API_BASE = "/api/v1";

/**
 * problem  - the server answered with application/problem+json (code, message_fa, request_id)
 * network  - no API answer at all (server down, proxy failure, connection reset)
 * contract - an answer that does not match the OpenAPI contract
 */
export type ApiErrorKind = "problem" | "network" | "contract";

/** Generic Persian texts, used only when the server did not supply `message_fa`. */
export const FALLBACK_MESSAGES: Record<ApiErrorKind, string> = {
  problem: "درخواست با خطا روبه‌رو شد.",
  network: "ارتباط با سرور برقرار نشد. روشن بودن سرور یا اتصال شبکه را بررسی کنید.",
  contract: "پاسخ سرور با قرارداد API مطابقت ندارد.",
};

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly messageFa: string;
  readonly requestId: string | null;

  constructor(init: {
    kind: ApiErrorKind;
    status: number | null;
    code?: string | null;
    messageFa?: string | null;
    requestId?: string | null;
  }) {
    super(init.code ?? init.kind);
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status;
    this.code = init.code ?? null;
    this.messageFa = init.messageFa ?? FALLBACK_MESSAGES[init.kind];
    this.requestId = init.requestId ?? null;
  }

  static fromProblem(p: Problem, headerRequestId: string | null): ApiError {
    return new ApiError({
      kind: "problem",
      status: p.status,
      code: p.code,
      messageFa: p.message_fa ?? null,
      requestId: p.request_id || headerRequestId,
    });
  }
}

export interface GetOptions<T> {
  signal?: AbortSignal | undefined;
  /** Contract check of the success body. */
  guard: (body: unknown) => body is T;
  /** Non-2xx statuses whose JSON body is still a valid representation (e.g. readiness 503 not_ready). */
  acceptStatuses?: readonly number[];
}

export async function getJson<T>(path: string, opts: GetOptions<T>): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      headers: { Accept: "application/json, application/problem+json" },
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
  let body: unknown = null;
  if (contentType.includes("json")) {
    try {
      body = await res.json();
    } catch {
      body = null;
    }
  }

  if (contentType.includes("application/problem+json") && isProblem(body)) {
    throw ApiError.fromProblem(body, requestId);
  }
  const accepted = res.ok || (opts.acceptStatuses ?? []).includes(res.status);
  if (accepted && contentType.includes("application/json") && opts.guard(body)) {
    return body;
  }
  if (!accepted && res.status >= 500 && !contentType.includes("json")) {
    // Not an API answer (e.g. the dev proxy could not reach the backend: 5xx without a problem body).
    throw new ApiError({ kind: "network", status: res.status, requestId });
  }
  throw new ApiError({ kind: "contract", status: res.status, requestId });
}
