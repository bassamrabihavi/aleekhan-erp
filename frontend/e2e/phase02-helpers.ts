// Helpers of the PHASE_02 E2E suite (02.5): a console seed of the throw-away E2E database and login / screenshot
// helpers. Everything here is SYNTHETIC and labelled «محیط آزمایشی — داده ساختگی»: product type segments 96/97
// (never a real Sorce value), synthetic people syn.e2e2.*, a synthetic workbook hash. The seed stands in for the
// server-side steps that have no UI in PHASE_02: the Planning "Sorce" import of product types / categories, the
// owner's role grants (tested through the UI in PHASE_01) and the server-only golden cases of the code rule.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Browser, type BrowserContext, type Page } from "@playwright/test";

import { SCREENSHOT_DIR, VIEWPORTS } from "./env";
import { Totp } from "./phase01-helpers";

// Synthetic test credential (not a secret), named SYN_PW_*.
export const SYN_PW_P2 = "Syn-E2E-Phase02-Pass-7!";

export const ROLES = {
  co: "commercial_officer",
  cm: "commercial_manager",
  po: "planning_officer",
  pds: "product_data_steward",
  cra: "code_rule_approver",
  viewer: "management_viewer",
  emp: "employee",
} as const;
export type Who = keyof typeof ROLES;

const SEED = (run: string) => `
import base64, json, time
from urllib.parse import parse_qs, urlparse
from platform_core.identity import mfa, totp
from platform_core.product_identity import codes
from platform_core.tests import phase02_factories as f
from platform_core.tests.engine_fixtures import caller, give_role, person

SYN = "(محیط آزمایشی — داده ساختگی)"
RUN = "${run}"
ROLES = ${JSON.stringify(ROLES)}
out = {}
for key, role in ROLES.items():
    u = person(username=f"syn.e2e2.{key}.{RUN}", display_name=f"{key} ساختگی {SYN}", password="${SYN_PW_P2}")
    give_role(u, role)
    c = caller(u)
    start = mfa.start_enrolment(c)
    b32 = parse_qs(urlparse(start.provisioning_uri).query)["secret"][0]
    secret = base64.b32decode(b32 + "=" * (-len(b32) % 8))
    mfa.confirm_enrolment(c, totp.totp(secret, time.time() - 30))
    out[key] = {"username": u.username, "secret": b32, "user_id": str(u.pk)}

# the Planning "Sorce" import (server side): two synthetic product types with one category each
bag = f.product_type("97", label_fa=f"کیف {SYN}", uom_id="PIECE")
f.category(bag, "07", label_fa=f"دسته اداری {SYN}")
belt = f.product_type("96", label_fa=f"کمربند {SYN}", uom_id="PIECE", product_no_scheme="BELT_BUCKLE_WIDTH")
f.category(belt, "07", label_fa=f"دسته کمربند {SYN}")

# code rule revision by the product data steward with SYNTHETIC golden cases (real cases: server only), IN_REVIEW
from platform_core.identity.models import User
pds = caller(User.objects.get(username=out["pds"]["username"]))
rule = codes.create_rule_revision(pds, product_type_codes=["96", "97"], source_workbook_sha256="e2" * 32)
cases = []
for i in range(1, 21):
    cases.append({"inputs": {"type_code": "97", "category_code": "07", "product_no": f"{9000 + i:04d}", "style_no": "0001"},
                  "expected_code": f"029707{9000 + i:04d}0001", "source_sheet": "SyntheticE2E", "source_cell_ref": f"A{i}"})
    cases.append({"inputs": {"type_code": "96", "category_code": "07", "product_no": f"{i:02d}35", "style_no": "0001",
                             "buckle_type_code": f"{i:02d}", "belt_width_code": "35"},
                  "expected_code": f"029607{i:02d}350001", "source_sheet": "SyntheticE2E", "source_cell_ref": f"B{i}"})
codes.add_golden_cases(pds, rule.pk, cases=cases)
rule.refresh_from_db()
codes.submit_rule_revision(pds, rule.pk, expected_version=rule.row_version)
out["rule_revision_id"] = str(rule.pk)
print("P2SEED:" + json.dumps(out))
`;

export interface Person {
  username: string;
  secret: string;
  user_id: string;
}
export type Seed = Record<Who, Person> & { rule_revision_id: string };

/** Seeds the synthetic PHASE_02 people / catalogue / code rule (stdout carries only synthetic values). */
export function seedPhase02(run: string): Seed {
  const python = process.env.E2E_PYTHON;
  if (!python) throw new Error("E2E_PYTHON not set (run through scripts/e2e.sh)");
  const backendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../backend");
  const r = spawnSync(python, ["manage.py", "shell", "-c", SEED(run)], { cwd: backendDir, encoding: "utf8", env: process.env });
  if (r.status !== 0) throw new Error(`phase02 seed failed (exit ${String(r.status)}): ${r.stderr.slice(-800)}`);
  const line = r.stdout.split(/\r?\n/).find((l) => l.startsWith("P2SEED:"));
  if (!line) throw new Error("phase02 seed printed no result");
  return JSON.parse(line.slice("P2SEED:".length)) as Seed;
}

export interface Session {
  ctx: BrowserContext;
  page: Page;
  totp: Totp;
}

/** Login through the UI (password, then TOTP when the server asks for it). */
export async function login(browser: Browser, p: Person): Promise<Session> {
  const ctx = await browser.newContext({ locale: "fa-IR", timezoneId: "Asia/Tehran", viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const totp = new Totp(p.secret);
  await page.goto("/#/");
  await page.getByTestId("login-username").fill(p.username);
  await page.getByTestId("login-password").fill(SYN_PW_P2);
  await page.getByTestId("login-submit").click();
  const mfaCode = page.getByTestId("mfa-code");
  await expect(mfaCode.or(page.getByTestId("page-home"))).toBeVisible();
  if (await mfaCode.isVisible()) {
    await mfaCode.fill(await totp.next());
    await page.getByTestId("mfa-submit").click();
  }
  await expect(page.getByTestId("page-home")).toBeVisible();
  return { ctx, page, totp };
}

/** REV-0251: at tablet width (768) the serial header title (#serial-title) stays on ONE line: its box height is at
 * most 1.5 x its computed line height (the 02.5 layout broke it into one word per line). */
export async function expectSerialTitleOneLine(page: Page): Promise<void> {
  await page.setViewportSize({ width: 768, height: 1024 });
  const title = page.locator("#serial-title");
  await expect(title).toBeVisible();
  const { height, lineHeight } = await title.evaluate((el) => {
    const cs = getComputedStyle(el);
    const lh = Number.parseFloat(cs.lineHeight);
    return { height: el.getBoundingClientRect().height, lineHeight: Number.isNaN(lh) ? Number.parseFloat(cs.fontSize) * 1.2 : lh };
  });
  expect(height).toBeLessThanOrEqual(lineHeight * 1.5);
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** Full-page screenshots at 1440/1180/768/390 (phase02-<name>-<size>.png), then back to 1440. */
export async function shots(page: Page, name: string, ready: () => Promise<void>): Promise<void> {
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await ready();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `phase02-${name}-${vp.name}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}
