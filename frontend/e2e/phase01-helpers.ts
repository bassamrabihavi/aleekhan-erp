// Helpers of the PHASE_01 E2E suite (real Django + PostgreSQL). Synthetic test credentials only (SYN_PW_*);
// the TOTP generator is RFC 6238 (SHA-1, 30 s, 6 digits) on node:crypto - the same algorithm the backend checks.
import { createHmac } from "node:crypto";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

import { SCREENSHOT_DIR, VIEWPORTS } from "./env";

// Synthetic test credentials (not secrets), named SYN_PW_*.
export const SYN_PW_OWNER_ONE_TIME = "Syn-E2E-Owner-Pass-1!";
export const SYN_PW_OWNER_NEW = "Syn-E2E-Owner-Pass-2!";
export const SYN_PW_DOCCTL_NEW = "Syn-E2E-Docctl-Pass-3!";
export const OWNER_USERNAME = "syn.e2e.owner";
export const SYN_LABEL = "محیط آزمایشی — داده ساختگی";

function base32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of secret.replace(/=+$/, "").toUpperCase()) {
    const v = alphabet.indexOf(c);
    if (v < 0) throw new Error("invalid base32");
    bits += v.toString(2).padStart(5, "0");
  }
  const out: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(out);
}

export function totpAt(secret: string, step: number): string {
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(step));
  const h = createHmac("sha1", base32(secret)).update(msg).digest();
  const offset = (h[h.length - 1] ?? 0) & 0x0f;
  const code = ((h.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString();
  return code.padStart(6, "0");
}

/** TOTP codes with a strictly increasing time step (the server refuses a reused step: replay guard). */
export class Totp {
  private last = -1;
  constructor(readonly secret: string) {}
  async next(): Promise<string> {
    for (;;) {
      const step = Math.floor(Date.now() / 1000 / 30);
      if (step > this.last && Date.now() / 1000 - step * 30 < 27) {
        this.last = step;
        return totpAt(this.secret, step);
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
}

/** If the MFA step-up dialog appears within `ms`, answer it with a fresh TOTP code. */
export async function answerStepUp(page: Page, totp: Totp, ms = 4000): Promise<boolean> {
  const dialog = page.getByTestId("step-up-dialog");
  try {
    await dialog.waitFor({ state: "visible", timeout: ms });
  } catch {
    return false;
  }
  await dialog.getByTestId("step-up-code").fill(await totp.next());
  await dialog.getByTestId("step-up-submit").click();
  await expect(dialog).toBeHidden();
  return true;
}

export async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

/** Full-page screenshots at the four acceptance widths (1440/1180/768/390), then back to 1440. */
export async function screenshots(page: Page, name: string, ready: () => Promise<void>): Promise<void> {
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await ready();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `phase01-${name}-${vp.name}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}
