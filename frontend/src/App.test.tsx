// State rendering of the public system-status page (#/status) (loading / data / error / empty / stale / forbidden).
// fetch is stubbed here only (unit level); the E2E suite runs against the real Django backend.
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./App";
import { STALE_AFTER_MS, staleness } from "./pages/useSystemStatus";
import { createQueryClient } from "./queryClient";
import {
  defaultRoutes,
  json,
  problem,
  READY_BODY,
  stubFetch,
  SYN_REQUEST_ID,
  UNAUTH_PROBLEM,
} from "./test/fetchStub";

function renderApp() {
  window.location.hash = "#/status"; // PHASE_00 public status page (01.5: "/" is the login / dashboard)
  const client = createQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

describe("System status page", () => {
  it("shows loading first, then real-shaped data with Persian labels and digits", async () => {
    stubFetch(defaultRoutes());
    renderApp();
    expect(screen.getAllByTestId("state-loading").length).toBeGreaterThan(0);
    expect(screen.getByTestId("live-region")).toHaveTextContent("در حال بررسی وضعیت سامانه");

    expect(await screen.findByTestId("ready-chip")).toHaveTextContent("آماده");
    expect(screen.getByTestId("ready-chip")).toHaveAttribute("data-tone", "success");
    expect(screen.getByRole("img", { name: "لوگوی سراجی سنتی عالیخان" })).toBeInTheDocument();
    expect(screen.getByTestId("live-region")).toHaveTextContent("سامانه آماده است.");
    const table = screen.getByTestId("components-table");
    expect(within(table).getByText("پایگاه داده")).toBeInTheDocument();
    expect(within(table).getAllByText("سالم")).toHaveLength(3);
    expect(screen.getByTestId("ready-checked-at")).toHaveTextContent("۱۲ آبان ۱۴۰۵");
    expect(screen.getByTestId("version-build")).toHaveTextContent("abcdef1234567");
    expect(screen.getByTestId("footer-build")).toHaveTextContent("abcdef1234567");
    expect(screen.getByTestId("env-banner")).toHaveTextContent("داده ساختگی");
    expect(screen.queryByTestId("state-error")).not.toBeInTheDocument();
  });

  it("access gate 401 is rendered as the no-access state with message_fa and request id", async () => {
    stubFetch(defaultRoutes());
    renderApp();
    const forbidden = await screen.findByTestId("state-forbidden");
    expect(within(forbidden).getByTestId("forbidden-message")).toHaveTextContent(UNAUTH_PROBLEM.message_fa);
    expect(within(forbidden).getByTestId("forbidden-code")).toHaveTextContent("AUTHENTICATION_REQUIRED");
    expect(within(forbidden).getByTestId("forbidden-request-id")).toHaveTextContent(UNAUTH_PROBLEM.request_id);
  });

  it("not_ready (503) shows the down component and a danger chip", async () => {
    const routes = defaultRoutes();
    routes["/api/v1/health/ready"] = () =>
      json(
        { ...READY_BODY, status: "not_ready", components: [{ name: "database", status: "down" }, { name: "migrations", status: "unknown" }] },
        503,
      );
    stubFetch(routes);
    renderApp();
    expect(await screen.findByTestId("ready-chip")).toHaveTextContent("آماده نیست");
    expect(screen.getByText("از کار افتاده")).toBeInTheDocument();
    expect(screen.getByText("نامعلوم")).toBeInTheDocument();
    expect(screen.getByTestId("live-region")).toHaveTextContent("سامانه آماده نیست.");
  });

  it("error state shows server message_fa, code, HTTP status and request id; retry recovers", async () => {
    const routes = stubFetch(defaultRoutes());
    routes["/api/v1/health/ready"] = () =>
      problem({ code: "INTERNAL_ERROR", message_fa: "خطای داخلی سرور.", request_id: SYN_REQUEST_ID }, 500);
    renderApp();
    const err = await screen.findByTestId("state-error");
    expect(within(err).getByTestId("error-message")).toHaveTextContent("خطای داخلی سرور.");
    expect(within(err).getByTestId("error-code")).toHaveTextContent("INTERNAL_ERROR");
    expect(within(err).getByText("۵۰۰")).toBeInTheDocument();
    expect(within(err).getByTestId("error-request-id")).toHaveTextContent(SYN_REQUEST_ID);
    expect(screen.getByTestId("live-region")).toHaveTextContent("بررسی وضعیت سامانه ناموفق بود");

    routes["/api/v1/health/ready"] = () => json(READY_BODY);
    await userEvent.click(within(err).getByRole("button", { name: "تلاش مجدد" }));
    expect(await screen.findByTestId("ready-chip")).toHaveTextContent("آماده");
    expect(screen.queryByTestId("state-error")).not.toBeInTheDocument();
  });

  it("network failure shows the Persian fallback and no request id", async () => {
    const routes = stubFetch(defaultRoutes());
    routes["/api/v1/health/ready"] = () => Promise.reject(new TypeError("Failed to fetch"));
    renderApp();
    const err = await screen.findByTestId("state-error");
    expect(err).toHaveTextContent("ارتباط با سرور برقرار نشد");
    expect(within(err).getByTestId("error-code")).toHaveTextContent("NETWORK");
    expect(err).toHaveTextContent("ثبت نشده");
  });

  it("empty components list renders the empty state", async () => {
    const routes = defaultRoutes();
    routes["/api/v1/health/ready"] = () => json({ ...READY_BODY, components: [] });
    stubFetch(routes);
    renderApp();
    expect(await screen.findByTestId("state-empty")).toHaveTextContent("هیچ مؤلفه‌ای گزارش نشده است.");
  });

  it("failed refresh keeps last data and flags it as stale", async () => {
    const routes = stubFetch(defaultRoutes());
    renderApp();
    await screen.findByTestId("ready-chip");
    expect(screen.queryByTestId("state-stale")).not.toBeInTheDocument();

    routes["/api/v1/health/ready"] = () => Promise.reject(new TypeError("Failed to fetch"));
    await userEvent.click(screen.getByTestId("refresh"));
    const stale = await screen.findAllByTestId("state-stale");
    expect(stale[0]).toHaveTextContent("داده قدیمی");
    expect(stale[0]).toHaveTextContent("آخرین بررسی ناموفق بود");
    expect(screen.getByTestId("ready-chip")).toBeInTheDocument();
    expect(screen.getByTestId("ready-chip")).toHaveAttribute("data-tone", "neutral"); // REV-0503
    expect(screen.getByTestId("state-error")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("live-region")).toHaveTextContent("وضعیت نمایش‌داده‌شده قدیمی است");
    });
  });

  it("refresh button is a real button reachable by keyboard", async () => {
    stubFetch(defaultRoutes());
    renderApp();
    await screen.findByTestId("ready-chip");
    const user = userEvent.setup();
    await user.tab();
    expect(screen.getByText("رفتن به محتوای اصلی")).toHaveFocus();
    await user.tab();
    expect(screen.getByTestId("refresh")).toHaveFocus();
    await act(async () => {
      await user.keyboard("{Enter}");
    });
    expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(4);
  });
});

describe("staleness()", () => {
  const now = 1_000_000_000;
  it("no data -> null; error with data -> failed; old data -> age; fresh -> null", () => {
    expect(staleness({ data: undefined, isError: true, dataUpdatedAt: 0 }, now)).toBeNull();
    expect(staleness({ data: {}, isError: true, dataUpdatedAt: now }, now)).toBe("failed");
    expect(staleness({ data: {}, isError: false, dataUpdatedAt: now - STALE_AFTER_MS - 1 }, now)).toBe("age");
    expect(staleness({ data: {}, isError: false, dataUpdatedAt: now - 1000 }, now)).toBeNull();
  });
});
