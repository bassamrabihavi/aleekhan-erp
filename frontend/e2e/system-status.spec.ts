// E2E for the "وضعیت سامانه" smoke page against the real Django backend (scripts/e2e.sh).
// Only tests whose title starts with "[simulated failure]" intercept network traffic; everything else
// reads real responses from /api/v1 through the Vite proxy.
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { BACKEND_URL, SCREENSHOT_DIR, UUID_RE, VIEWPORTS } from "./env";

const READY_PATH = "**/api/v1/health/ready";

async function openReady(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByTestId("ready-chip")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(
    results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
  ).toEqual([]);
}

test.describe("system status page - real backend", () => {
  test("loads as Farsi RTL with the Persian font bundled locally", async ({ page }) => {
    const external: string[] = [];
    page.on("request", (r) => {
      if (!r.url().startsWith("http://127.0.0.1:5173/")) external.push(r.url());
    });
    await openReady(page);
    await expect(page.locator("html")).toHaveAttribute("lang", "fa");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1, name: "وضعیت سامانه" })).toBeVisible();
    const direction = await page.evaluate(() => getComputedStyle(document.body).direction);
    expect(direction).toBe("rtl");
    const vazirLoaded = await page.evaluate(() => document.fonts.check('16px "Vazirmatn"', "سامانه"));
    expect(vazirLoaded).toBe(true);
    expect(external, "no request may leave the same-origin dev server (no CDN)").toEqual([]);
  });

  test("shows the real version and build commit returned by /api/v1/version", async ({ page, request }) => {
    const api = await request.get(`${BACKEND_URL}/api/v1/version`);
    expect(api.status()).toBe(200);
    const version = (await api.json()) as { build_commit: string; contract_version: string; environment: string };
    const expectedCommit = process.env.E2E_EXPECT_COMMIT;
    if (expectedCommit) expect(version.build_commit).toBe(expectedCommit);

    await openReady(page);
    await expect(page.getByTestId("version-build")).toHaveText(version.build_commit);
    await expect(page.getByTestId("footer-build")).toHaveText(version.build_commit);
    await expect(page.getByTestId("version-contract")).toHaveText(version.contract_version);
    expect(version.environment).toBe("dev");
    await expect(page.getByTestId("version-env")).toHaveText("توسعه");
    await expect(page.getByTestId("env-banner")).toContainText("داده ساختگی");
  });

  test("shows real readiness: ready, with database / migrations / cache up", async ({ page, request }) => {
    const api = await request.get(`${BACKEND_URL}/api/v1/health/ready`);
    expect(api.status()).toBe(200);
    expect(((await api.json()) as { status: string }).status).toBe("ready");

    await openReady(page);
    await expect(page.getByTestId("ready-chip")).toHaveText("آماده");
    for (const name of ["database", "migrations", "cache"]) {
      await expect(page.getByTestId(`component-${name}`)).toContainText("سالم");
    }
    await expect(page.getByTestId("live-chip")).toHaveText("پاسخ‌گو");
    await expect(page.getByTestId("live-region")).toHaveText("سامانه آماده است.");
    // Jalali date with Persian digits, no Latin digits in the server check time.
    await expect(page.getByTestId("ready-checked-at")).not.toHaveText(/[0-9]/);
    await expect(page.getByTestId("ready-checked-at")).toHaveText(/[۰-۹]/);
    await expect(page.getByTestId("state-error")).toHaveCount(0);
    await expect(page.getByTestId("state-stale")).toHaveCount(0);
  });

  test("real no-access state: access gate answers 401 problem with message_fa and request id", async ({
    page,
    request,
  }) => {
    const api = await request.get(`${BACKEND_URL}/api/v1/access-gate/check?action=platform.status.view`);
    expect(api.status()).toBe(401);
    const problem = (await api.json()) as { code: string; message_fa: string };
    expect(problem.code).toBe("AUTHENTICATION_REQUIRED");

    await openReady(page);
    const forbidden = page.getByTestId("state-forbidden");
    await expect(forbidden).toBeVisible();
    await expect(forbidden.getByTestId("forbidden-message")).toHaveText(problem.message_fa);
    await expect(forbidden.getByTestId("forbidden-code")).toHaveText("AUTHENTICATION_REQUIRED");
    await expect(forbidden.getByTestId("forbidden-request-id")).toHaveText(UUID_RE);
  });

  test("keyboard: skip link, focus to main, refresh with Enter triggers a real re-check", async ({ page }) => {
    await openReady(page);
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "رفتن به محتوای اصلی" });
    await expect(skip).toBeFocused();
    await expect(skip).toBeInViewport();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main")).toBeFocused();

    await page.keyboard.press("Tab");
    const refresh = page.getByTestId("refresh");
    await expect(refresh).toBeFocused();
    const outline = await refresh.evaluate((el) => getComputedStyle(el).boxShadow);
    expect(outline, "visible focus ring").not.toBe("none");

    const reCheck = page.waitForResponse((r) => r.url().endsWith("/api/v1/health/ready") && r.status() === 200);
    await page.keyboard.press("Enter");
    await reCheck;
    await expect(page.getByTestId("ready-chip")).toHaveText("آماده");
  });

  test("axe: no WCAG 2.1 A/AA violations (ready state)", async ({ page }) => {
    await openReady(page);
    await expect(page.getByTestId("state-forbidden")).toBeVisible();
    await expectNoAxeViolations(page);
  });

  test("screenshots at 1440 / 1180 / 768 / 390 (real data)", async ({ page }) => {
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await openReady(page);
      await expect(page.getByTestId("state-forbidden")).toBeVisible();
      await expect(page.getByTestId("version-build")).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `no horizontal scroll at ${vp.width}px`).toBeLessThanOrEqual(0);
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, `system-status_real_${vp.name}.png`),
        fullPage: true,
      });
    }
  });
});

test.describe("system status page - [simulated failure] states (network interception)", () => {
  test("[simulated failure] readiness routed to a real backend 404 problem shows message_fa + request_id", async ({
    page,
  }) => {
    let realRequestId = "";
    // The browser's readiness call is answered by a REAL backend error (unknown URL -> problem+json);
    // only the routing is simulated, the body/headers are the server's own.
    await page.route(READY_PATH, async (route) => {
      const resp = await route.fetch({ url: `${BACKEND_URL}/api/v1/__e2e_unknown_route__` });
      realRequestId = resp.headers()["x-request-id"] ?? "";
      await route.fulfill({ response: resp });
    });
    await page.goto("/");
    const err = page.getByTestId("state-error").first();
    await expect(err).toBeVisible();
    await expect(err.getByTestId("error-code")).toHaveText("NOT_FOUND");
    await expect(err.getByTestId("error-message")).not.toBeEmpty();
    expect(realRequestId).toMatch(UUID_RE);
    await expect(err.getByTestId("error-request-id")).toHaveText(realRequestId);
    await expect(page.getByTestId("live-region")).toContainText("بررسی وضعیت سامانه ناموفق بود");
    await expectNoAxeViolations(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "system-status_SIMULATED-error_390-mobile.png"),
      fullPage: true,
    });

    await page.unroute(READY_PATH);
    await err.getByRole("button", { name: "تلاش مجدد" }).click();
    await expect(page.getByTestId("ready-chip")).toHaveText("آماده");
  });

  test("[simulated failure] refresh fails after real data: last data kept and flagged stale", async ({ page }) => {
    await openReady(page);
    await page.route(READY_PATH, (route) => route.abort("connectionrefused"));
    await page.getByTestId("refresh").click();
    const stale = page.getByTestId("state-stale").first();
    await expect(stale).toContainText("داده قدیمی");
    await expect(stale).toContainText("آخرین بررسی ناموفق بود");
    await expect(page.getByTestId("ready-chip")).toHaveText("آماده");
    await expect(page.getByTestId("state-error").first().getByTestId("error-code")).toHaveText("NETWORK");
    await expect(page.getByTestId("live-region")).toHaveText(/قدیمی است/);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "system-status_SIMULATED-stale_1440-desktop.png"),
      fullPage: true,
    });
  });

  test("[simulated failure] no answer for longer than the freshness window: stale by age", async ({ page }) => {
    await page.clock.install();
    await openReady(page);
    // Later readiness calls never get an answer (request hangs) - real data stays on screen and ages.
    await page.route(READY_PATH, () => undefined);
    await page.clock.fastForward("01:30");
    const stale = page.getByTestId("state-stale").first();
    await expect(stale).toContainText("داده قدیمی");
    await expect(stale).toContainText("به‌روزرسانی انجام نشده");
    await expect(page.getByTestId("ready-chip")).toHaveText("آماده");
    await page.unrouteAll({ behavior: "ignoreErrors" });
  });
});

test.describe("system status page - backend stopped", () => {
  test("real failure: Django is not running, the page shows the network error state @backend-down", async ({
    page,
  }) => {
    const health = await page.request.get(`${BACKEND_URL}/api/v1/health/live`).catch(() => null);
    expect(health, "backend must really be down for this test").toBeNull();

    await page.goto("/");
    const err = page.getByTestId("state-error").first();
    await expect(err).toBeVisible();
    await expect(err.getByTestId("error-code")).toHaveText("NETWORK");
    await expect(err.getByTestId("error-message")).toContainText("ارتباط با سرور برقرار نشد");
    await expect(page.getByTestId("live-region")).toContainText("بررسی وضعیت سامانه ناموفق بود");
    await expect(page.getByTestId("footer-version")).toContainText("نسخه سامانه دریافت نشد");
    await expect(page.getByTestId("ready-chip")).toHaveCount(0);
    await expectNoAxeViolations(page);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "system-status_real-backend-down_1440-desktop.png"),
      fullPage: true,
    });
  });
});
