// DEC-061 fidelity harness: mockup-only run (no backend, no database). Extracts / verifies specs/page-*.json:
//   FIDELITY_EXTRACT=1 E2E_BROWSER_CHANNEL=msedge npx playwright test -c e2e/fidelity/extract.config.ts
import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: here,
  testMatch: "fidelity.spec.ts",
  grep: /@fidelity mockup specs/,
  outputDir: path.resolve(here, "../../test-results/fidelity-extract"),
  workers: 1,
  forbidOnly: true,
  retries: 0,
  reporter: [["list"]],
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(process.env.E2E_BROWSER_CHANNEL ? { channel: process.env.E2E_BROWSER_CHANNEL } : {}),
      },
    },
  ],
});
