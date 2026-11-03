import { json, problem, READY_BODY, stubFetch, SYN_REQUEST_ID } from "../test/fetchStub";
import { ApiError, FALLBACK_MESSAGES } from "./client";
import { fetchReadiness, fetchVersion } from "./platform";

async function caught(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p;
  } catch (e) {
    if (e instanceof ApiError) return e;
    throw e;
  }
  throw new Error("expected ApiError");
}

describe("getJson / platform client", () => {
  it("returns a contract-valid readiness body", async () => {
    stubFetch({ "/api/v1/health/ready": () => json(READY_BODY) });
    await expect(fetchReadiness()).resolves.toEqual(READY_BODY);
  });

  it("accepts 503 not_ready as data (not an error)", async () => {
    const body = { ...READY_BODY, status: "not_ready", components: [{ name: "database", status: "down" }] };
    stubFetch({ "/api/v1/health/ready": () => json(body, 503, { "Retry-After": "5" }) });
    await expect(fetchReadiness()).resolves.toMatchObject({ status: "not_ready" });
  });

  it("maps application/problem+json to ApiError with message_fa, code and request_id", async () => {
    stubFetch({
      "/api/v1/version": () =>
        problem({ code: "RATE_LIMITED", message_fa: "تعداد درخواست‌ها زیاد است.", request_id: SYN_REQUEST_ID }, 429),
    });
    const e = await caught(fetchVersion());
    expect(e.kind).toBe("problem");
    expect(e.status).toBe(429);
    expect(e.code).toBe("RATE_LIMITED");
    expect(e.messageFa).toBe("تعداد درخواست‌ها زیاد است.");
    expect(e.requestId).toBe(SYN_REQUEST_ID);
  });

  it("network failure -> kind network with Persian fallback message and no request id", async () => {
    stubFetch({});
    const e = await caught(fetchVersion());
    expect(e.kind).toBe("network");
    expect(e.status).toBeNull();
    expect(e.messageFa).toBe(FALLBACK_MESSAGES.network);
    expect(e.requestId).toBeNull();
  });

  it("5xx without a JSON body (dev proxy cannot reach backend) -> network", async () => {
    stubFetch({ "/api/v1/version": () => new Response("proxy error", { status: 502 }) });
    const e = await caught(fetchVersion());
    expect(e.kind).toBe("network");
    expect(e.status).toBe(502);
  });

  it("body that violates the contract is rejected, never rendered as data", async () => {
    stubFetch({ "/api/v1/version": () => json({ api_version: "v1", build_commit: "NOT-HEX" }) });
    const e = await caught(fetchVersion());
    expect(e.kind).toBe("contract");
    expect(e.messageFa).toBe(FALLBACK_MESSAGES.contract);
  });
});
