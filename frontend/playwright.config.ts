// Playwright E2E against the REAL stack: Django runserver (throwaway PostgreSQL DB prepared by scripts/e2e.sh)
// + Vite dev server proxying /api to it. No API mocking except in tests explicitly named "[simulated failure]".
//
// E2E_MODE=backend-down starts only Vite (no Django) and runs the tests tagged @backend-down: the real
// "server is not running" failure.
import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";

import { BACKEND_URL, FRONTEND_URL } from "./e2e/env";

const here = path.dirname(fileURLToPath(import.meta.url));
const backendDir = path.resolve(here, "../backend");
const defaultPython =
  process.platform === "win32"
    ? path.resolve(here, "../.venv/Scripts/python.exe")
    : path.resolve(here, "../.venv/bin/python");
const python = process.env.E2E_PYTHON ?? defaultPython;
const backendDown = process.env.E2E_MODE === "backend-down";

const vite = {
  command: "npx vite --strictPort",
  cwd: here,
  url: FRONTEND_URL,
  reuseExistingServer: false,
  timeout: 120_000,
  stdout: "ignore" as const,
  stderr: "pipe" as const,
};

const django = {
  // --noreload: a single process that Playwright can stop cleanly at the end of the run.
  command: `"${python}" manage.py runserver 127.0.0.1:8000 --noreload`,
  cwd: backendDir,
  url: `${BACKEND_URL}/api/v1/health/live`,
  reuseExistingServer: false,
  timeout: 120_000,
  stdout: "ignore" as const,
  stderr: "pipe" as const,
};

export default defineConfig({
  testDir: "./e2e",
  outputDir: process.env.E2E_OUTPUT_DIR ?? "./test-results",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: process.env.E2E_HTML_REPORT ?? "./playwright-report" }],
  ],
  grep: backendDown ? /@backend-down/ : undefined,
  grepInvert: backendDown ? undefined : /@backend-down/,
  use: {
    baseURL: FRONTEND_URL,
    locale: "fa-IR",
    timezoneId: "Asia/Tehran",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        // Bundled Playwright Chromium by default. Where its CDN is unreachable (403 by region on the work
        // machine) set E2E_BROWSER_CHANNEL=msedge to use the installed Microsoft Edge (Chromium).
        ...(process.env.E2E_BROWSER_CHANNEL ? { channel: process.env.E2E_BROWSER_CHANNEL } : {}),
      },
    },
  ],
  webServer: backendDown ? [vite] : [django, vite],
});
