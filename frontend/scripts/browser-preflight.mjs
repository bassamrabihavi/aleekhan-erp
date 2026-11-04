// E2E browser preflight (REV-0603): print which browser Playwright will use and fail early, with a clear
// message, when it is not available. Prints no secrets (no env values other than the channel name).
//
//   E2E_BROWSER_CHANNEL unset    -> Playwright's bundled Chromium; checks the executable exists
//   E2E_BROWSER_CHANNEL=msedge|chrome|... -> launches the installed browser once (headless) and closes it
import fs from "node:fs";

import { chromium } from "@playwright/test";

const channel = process.env.E2E_BROWSER_CHANNEL ?? "";
const pwVersion = JSON.parse(
  fs.readFileSync(new URL("../node_modules/@playwright/test/package.json", import.meta.url), "utf8"),
).version;

function fail(msg) {
  console.error(`E2E preflight FAILED: ${msg}`);
  console.error(
    "Fix: `npx playwright install chromium` (bundled browser, needs the Playwright CDN), or set " +
      "E2E_BROWSER_CHANNEL=msedge (or chrome) to use an installed Chromium-based browser.",
  );
  process.exit(2);
}

console.log(`playwright: ${pwVersion}`);
console.log(`node: ${process.version} (${process.platform}/${process.arch})`);
console.log(`browser channel: ${channel || "(bundled chromium)"}`);
console.log(`PLAYWRIGHT_BROWSERS_PATH set: ${process.env.PLAYWRIGHT_BROWSERS_PATH ? "yes" : "no"}`);

if (!channel) {
  const exe = chromium.executablePath();
  if (!exe || !fs.existsSync(exe)) fail("bundled Chromium is not installed for this Playwright version");
}
try {
  const browser = await chromium.launch({ channel: channel || undefined, headless: true });
  console.log(`browser version: ${browser.version()}`);
  await browser.close();
} catch (err) {
  const first = String(err instanceof Error ? err.message : err).split("\n")[0];
  fail(`cannot launch browser (${channel || "bundled chromium"}): ${first}`);
}
