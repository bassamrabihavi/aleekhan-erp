// DEC-061 fidelity harness (PHASE_02 / 02.8 rework, REV-0295 measurement only): scores how closely each built
// PHASE_02 page matches its design-catalogue mockup at 1440/1180/768/390. Runs only with E2E_FIDELITY=1 (tag
// @fidelity; `npm run fidelity`, README.md) against the real seeded stack, like the phase02 suite. Synthetic data
// only («محیط آزمایشی — داده ساختگی»); no API mocking; mockups are opened read-only from handoff/.
//
//   FIDELITY_EXTRACT=1  re-extract specs/page-04|29|33.json from the rendered HTML mockups (otherwise the stored
//                       specs are used and their mockup sha256 must still match).
//   FIDELITY_ENFORCE=1  fail unless every page reaches THRESHOLD at every width (the later restyle gate).
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { HAND_PAGES, HEIGHTS, MOCKUPS, OUT_DIR, REPO, SHOT_WIDTHS, SPEC_DIR, THRESHOLD, WIDTHS, type MockupDef, type Width } from "./config";
import { asBuiltPage, measure, type Probe } from "./measure";
import { pageResult, renderMarkdown, scoreWidth, type PageResult, type PageSpec, type SpecRegion, type WidthResult } from "./score";
import { login, SYN_PW_P2, type Person, type Session } from "../phase02-helpers";

test.describe.configure({ mode: "serial" });
test.setTimeout(900_000);

const RUN = Date.now().toString(36).slice(-5);
const specPath = (page: string) => path.join(SPEC_DIR, `page-${page}.json`);
const sha256 = (file: string) => createHash("sha256").update(fs.readFileSync(path.join(REPO, file))).digest("hex");

// ------------------------------------------------------------------------------------------------ seed
const SEED = `
import base64, json, time, uuid
from urllib.parse import parse_qs, urlparse
from platform_core.identity import mfa, totp
from platform_core.devtools import phase02_factories as f
from platform_core.devtools.engine_fixtures import caller, give_role, person
from platform_core.commercial import changes
from platform_core.commercial.models import CustomerOrder, CustomerOrderLine

SYN = "(محیط آزمایشی — داده ساختگی)"
u = person(username="syn.fid.viewer.${RUN}", display_name=f"بیننده ساختگی {SYN}", password="${SYN_PW_P2}")
for role in ("commercial_officer", "product_data_steward", "planning_officer"):
    give_role(u, role)
c = caller(u)
start = mfa.start_enrolment(c)
b32 = parse_qs(urlparse(start.provisioning_uri).query)["secret"][0]
secret = base64.b32decode(b32 + "=" * (-len(b32) % 8))
mfa.confirm_enrolment(c, totp.totp(secret, time.time() - 30))
t = f.product_type(f.free_type_segment(), label_fa=f"کیف {SYN}", uom_id="PIECE")
cat = f.category(t, "07", label_fa=f"دسته اداری {SYN}")
prod = f.product(t, "9001", name_fa=f"کیف اداری ساختگی {SYN}")
sty = f.style(prod, cat, "0001", name_fa=f"استایل ساختگی {SYN}")
rev = f.style_revision(sty)
cust = f.customer()
o = f.order(cust, u)
f.line(o, sty, rev)
CustomerOrder.objects.filter(pk=o.pk).update(status="VALIDATED")
confirmer = person(username="syn.fid.po.${RUN}")
give_role(confirmer, "planning_officer")
f.confirm_order(o.pk, confirmer)
o.refresh_from_db()
changes.create_change_request(c, o.pk, kind="HOLD", items=[], reason=f"توقف ساختگی {SYN}", expected_version=o.row_version, submit=True)
# REV-0295: a realistic volume for page 4 - the style has several synthetic orders / serials (the catalogue
# sample shows seven); every one is synthetic and created through the same confirm harness
for _ in range(6):
    oi = f.order(f.customer(), u)
    f.line(oi, sty, rev)
    CustomerOrder.objects.filter(pk=oi.pk).update(status="VALIDATED")
    f.confirm_order(oi.pk, confirmer)
serial_id = CustomerOrderLine.objects.get(order=o).serial_id
print("FIDSEED:" + json.dumps({"person": {"username": u.username, "secret": b32, "user_id": str(u.pk)},
      "product_id": str(prod.pk), "style_id": str(sty.pk), "serial_id": str(serial_id), "order_id": str(o.pk)}))
`;

interface FidSeed {
  person: Person;
  product_id: string;
  style_id: string;
  serial_id: string;
  order_id: string;
}

function seed(): FidSeed {
  const python = process.env.E2E_PYTHON;
  if (!python) throw new Error("E2E_PYTHON not set (run through scripts/e2e.sh / npm run fidelity)");
  const r = spawnSync(python, ["manage.py", "shell", "-c", SEED], { cwd: path.join(REPO, "backend"), encoding: "utf8", env: process.env });
  if (r.status !== 0) throw new Error(`fidelity seed failed (exit ${String(r.status)}): ${r.stderr.slice(-800)}`);
  const line = r.stdout.split(/\r?\n/).find((l) => l.startsWith("FIDSEED:"));
  if (!line) throw new Error("fidelity seed printed no result");
  return JSON.parse(line.slice("FIDSEED:".length)) as FidSeed;
}

// ------------------------------------------------------------------------------------------- mockups
function mockupUrl(def: MockupDef): string {
  return pathToFileURL(path.join(REPO, def.html)).href + (def.query ?? "");
}

async function openMockup(browser: Browser, def: MockupDef, w: Width): Promise<Page> {
  const page = await browser.newPage({ viewport: { width: w, height: HEIGHTS[w] }, locale: "fa-IR" });
  await page.goto(mockupUrl(def));
  await page.waitForTimeout(400); // the catalogue renders with JS and short CSS transitions
  return page;
}

async function extract(browser: Browser, def: MockupDef): Promise<PageSpec> {
  const regions: SpecRegion[] = def.regions.map((r) => ({
    id: r.id,
    label_fa: r.label_fa,
    kind: r.kind,
    frame: r.frame,
    ...(r.later_phase ? { later_phase: r.later_phase } : {}),
    children: [],
    widths: {},
  }));
  const widths: PageSpec["widths"] = {};
  for (const w of WIDTHS) {
    const page = await openMockup(browser, def, w);
    const probes: Probe[] = def.regions.map((r) => ({ id: r.id, kind: r.kind, frame: r.frame, selector: r.selector, ...(r.children ? { children: r.children } : {}), ...(r.items ? { items: r.items } : {}) }));
    const m = await measure(page, probes, def.content_selector, ".btn.primary", false);
    await page.close();
    widths[`${w}`] = { content_pad_px: m.content_pad_px };
    for (const [i, r] of def.regions.entries()) {
      const got = m.regions[r.id];
      const spec = regions[i];
      if (!spec) continue;
      if (w === 1440) spec.children = [...(got?.children ?? []), ...(r.extra_children ?? [])];
      spec.widths[`${w}`] =
        got?.visible && got.box
          ? { box: round(got.box), ...(r.items ? { items: got.items } : {}), radius: got.radius, border: got.border, shadow: got.shadow, heading_px: got.heading_px }
          : null;
    }
  }
  return {
    schema: 1,
    page: def.page,
    title_fa: def.title_fa,
    route: def.route,
    ready_testid: def.ready_testid,
    authored: "extracted",
    source_note: `Extracted by fidelity.spec.ts (FIDELITY_EXTRACT=1) from ${def.html}${def.query ?? ""} rendered at ${WIDTHS.join("/")} (Playwright, channel ${process.env.E2E_BROWSER_CHANNEL ?? "chromium"}). Region selectors: config.ts.`,
    mockup: { html: def.html, ...(def.query ? { query: def.query } : {}), files: def.files.map((f) => ({ path: f, sha256: sha256(f) })) },
    excluded: def.excluded,
    widths,
    regions,
  };
}

function round(b: { x: number; y: number; w: number; h: number }) {
  const r = (x: number) => Math.round(x * 10000) / 10000;
  return { x: r(b.x), y: r(b.y), w: r(b.w), h: r(b.h) };
}

function readSpec(page: string): PageSpec {
  return JSON.parse(fs.readFileSync(specPath(page), "utf8")) as PageSpec;
}

// --------------------------------------------------------------------------------------------- built
async function loadOnce(s: Session, spec: PageSpec, route: string): Promise<boolean> {
  await s.page.goto("/#/"); // leave the page first: a same-hash goto keeps the old view state (open tab)
  await expect(s.page.getByTestId("page-home")).toBeVisible();
  await s.page.goto(`/#${route}`);
  if (spec.after_load === "open-order-tab") {
    await expect(s.page.getByTestId("serial-summary")).toBeVisible();
    await s.page.getByRole("tab", { name: "سفارش" }).click();
  }
  await expect(s.page.getByTestId(spec.ready_testid)).toBeVisible();
  await s.page.evaluate(() => document.fonts.ready);
  await s.page.waitForLoadState("networkidle");
  await expect(s.page.locator(".state--loading")).toHaveCount(0); // every DataView has its data
  // a transient dev-server refusal (Vite proxy ECONNREFUSED under load) shows an error / stale state: never score it
  return (await s.page.locator('[data-testid="state-error"], [data-testid="state-stale"]').count()) === 0;
}

async function openBuilt(s: Session, spec: PageSpec, route: string, w: Width): Promise<void> {
  await s.page.setViewportSize({ width: w, height: HEIGHTS[w] });
  let clean = false;
  for (let attempt = 1; attempt <= 3 && !clean; attempt++) {
    clean = await loadOnce(s, spec, route);
    if (!clean) await s.page.reload();
  }
  expect(clean, `page ${spec.page} at ${w}: an error / stale state stayed after 3 loads`).toBe(true);
  await s.page.evaluate(() => { window.scrollTo(0, 0); });
}

function builtProbes(spec: PageSpec): Probe[] {
  return spec.regions.map((r) => ({ id: r.id, kind: r.kind, frame: r.frame, selector: `[data-fid="${r.id}"]` }));
}

async function sideBySide(browser: Browser, left: Buffer, right: Buffer, w: Width, file: string): Promise<void> {
  const scale = w >= 1000 ? 0.5 : 1;
  const colW = Math.round(w * scale);
  const page = await browser.newPage({ viewport: { width: colW * 2 + 48, height: 600 } });
  const img = (b: Buffer) => `data:image/png;base64,${b.toString("base64")}`;
  await page.setContent(`<!doctype html><html dir="ltr"><body style="margin:0;background:#ddd;font:14px sans-serif">
    <div style="display:flex;gap:16px;padding:8px;align-items:flex-start">
    <figure style="margin:0;width:${colW}px"><figcaption>mockup (handoff design catalogue)</figcaption><img style="width:${colW}px" src="${img(left)}"></figure>
    <figure style="margin:0;width:${colW}px"><figcaption>built (E2E seed, synthetic data)</figcaption><img style="width:${colW}px" src="${img(right)}"></figure>
    </div></body></html>`);
  await page.evaluate(async () => {
    await Promise.all(Array.from(document.images).map((i) => (i.complete ? Promise.resolve() : new Promise((ok) => { i.onload = ok; }))));
  });
  await page.screenshot({ path: file, fullPage: true, type: "jpeg", quality: 70 });
  await page.close();
}

async function mockupShot(browser: Browser, spec: PageSpec, w: Width): Promise<Buffer> {
  const def = MOCKUPS.find((m) => m.page === spec.page);
  if (def) {
    const page = await openMockup(browser, def, w);
    const b = await page.screenshot({ fullPage: true });
    await page.close();
    return b;
  }
  // hand pages: the concept PNG for that width class (README.md)
  const png = spec.mockup.files.find((f) => (w >= 1000 ? f.path.includes("مدیریت") : f.path.includes("کنترل")));
  if (!png) throw new Error(`no concept PNG for page ${spec.page}`);
  return fs.readFileSync(path.join(REPO, png.path));
}

// ---------------------------------------------------------------------------------------------- tests
test("@fidelity mockup specs: extracted (FIDELITY_EXTRACT=1) or verified against the mockup sha256", async ({ browser }) => {
  fs.mkdirSync(SPEC_DIR, { recursive: true });
  if (process.env.FIDELITY_EXTRACT === "1") {
    for (const def of MOCKUPS) {
      const spec = await extract(browser, def);
      fs.writeFileSync(specPath(def.page), JSON.stringify(spec, null, 2) + "\n", "utf8");
    }
  }
  for (const page of [...MOCKUPS.map((m) => m.page), ...HAND_PAGES.map((h) => h.page)]) {
    expect(fs.existsSync(specPath(page)), `spec of page ${page} (run with FIDELITY_EXTRACT=1)`).toBe(true);
    const spec = readSpec(page);
    for (const f of spec.mockup.files) expect(sha256(f.path), `${f.path} changed since the spec was made: re-extract / re-author`).toBe(f.sha256);
    expect(spec.regions.length).toBeGreaterThan(3);
  }
});

test("@fidelity built pages: score per page per width, baseline + side-by-side screenshots", async ({ browser }) => {
  const sd = seed();
  const s = await login(browser, sd.person);
  const vars: Record<string, string> = { product_id: sd.product_id, style_id: sd.style_id, serial_id: sd.serial_id, order_id: sd.order_id };
  const shots = path.join(OUT_DIR, "shots");
  fs.mkdirSync(shots, { recursive: true });
  const results: PageResult[] = [];
  for (const page of ["01", "02", "04", "29", "33"]) {
    const spec = readSpec(page);
    const route = spec.route.replace(/\{(\w+)\}/g, (_m, k: string) => vars[k] ?? `{${k}}`);
    const per: WidthResult[] = [];
    for (const w of WIDTHS) {
      await openBuilt(s, spec, route, w);
      const m = await measure(s.page, builtProbes(spec), "main#main", ".btn--primary", true);
      per.push(scoreWidth(spec, w, asBuiltPage(m, w)));
      if (SHOT_WIDTHS.includes(w)) {
        const built = await s.page.screenshot({ fullPage: true });
        await sideBySide(browser, await mockupShot(browser, spec, w), built, w, path.join(shots, `page-${page}-${w}.jpg`));
      }
    }
    results.push(pageResult(spec, per));
  }
  await s.ctx.close();
  const commit = process.env.ALEEKHAN_BUILD_COMMIT ?? "unknown";
  const meta = { commit: commit.slice(0, 12), date: new Date().toISOString().slice(0, 10), channel: process.env.E2E_BROWSER_CHANNEL ?? "chromium" };
  fs.writeFileSync(
    path.join(OUT_DIR, "baseline.json"),
    JSON.stringify({ schema: 1, threshold: THRESHOLD, ...meta, results }, null, 2) + "\n",
    "utf8",
  );
  fs.writeFileSync(path.join(OUT_DIR, "BASELINE.md"), renderMarkdown(results, meta), "utf8");
  for (const r of results) expect(r.widths).toHaveLength(WIDTHS.length);
  if (process.env.FIDELITY_ENFORCE === "1") for (const r of results) expect(r.min, `page ${r.page}`).toBeGreaterThanOrEqual(THRESHOLD);
});
