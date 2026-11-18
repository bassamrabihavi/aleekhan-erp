// DEC-061 fidelity scorer (pure functions; unit tests in score.vitest.ts). The browser-side measurement lives in
// measure.ts; fidelity.spec.ts drives both. Method and formula: README.md.
import { IOU_MIN, LABEL_TOKEN_SHARE, LATER_TEXT, PANEL_KINDS, THRESHOLD, TOL, WEIGHTS, WIDTHS, type Frame, type RegionKind, type Width } from "./config";

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** What one region looks like at one width (mockup spec or built measurement). */
export interface RegionAtWidth {
  box: Box;
  items?: number;
  radius?: number | null;
  border?: number | null;
  shadow?: boolean | null;
  heading_px?: number | null;
}

export interface SpecRegion {
  id: string;
  label_fa: string;
  kind: RegionKind;
  frame: Frame;
  later_phase?: string;
  /** Required child labels (headings, column headers, field labels, button labels, KPI titles; never values). */
  children: string[];
  /** null / missing = not shown at that width in the mockup (not required there). */
  widths: Partial<Record<`${Width}`, RegionAtWidth | null>>;
}

export interface PageSpec {
  schema: 1;
  page: string;
  title_fa: string;
  route: string;
  ready_testid: string;
  after_load?: "open-order-tab";
  authored: "extracted" | "hand";
  source_note: string;
  mockup: { html?: string; query?: string; files: { path: string; sha256: string }[] };
  excluded: string[];
  widths: Partial<Record<`${Width}`, { content_pad_px: number | null }>>;
  regions: SpecRegion[];
}

/** Built page measurement of one region at one width. */
export interface BuiltRegion {
  visible: boolean;
  box: Box | null;
  text: string;
  items: number;
  radius: number | null;
  border: number | null;
  shadow: boolean | null;
  heading_px: number | null;
  icons: number;
}

export interface BuiltPage {
  width: Width;
  regions: Record<string, BuiltRegion | undefined>;
  font_family: string;
  body_bg: string | null;
  primary_bg: string | null;
  tokens: { primary: string; bg: string };
  content_pad_px: number | null;
}

export interface RegionResult {
  id: string;
  label_fa: string;
  later_phase?: string;
  presence: number;
  iou: number | null;
  in_place: boolean;
  missing_children: string[];
  note: string;
}

export interface StyleCheck {
  id: string;
  ok: number;
  detail: string;
}

export interface WidthResult {
  width: Width;
  score: number;
  presence: number;
  layout: number;
  style: number;
  regions: RegionResult[];
  style_checks: StyleCheck[];
}

export interface PageResult {
  page: string;
  title_fa: string;
  authored: "extracted" | "hand";
  widths: WidthResult[];
  min: number;
  passed: boolean;
}

// ------------------------------------------------------------------------------------------------ text
const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

/** Comparable text: Arabic/Persian letter variants unified, ZWNJ / tatweel / punctuation dropped, digits Latin. */
export function normalize(s: string): string {
  return s
    .replace(/‌|‍|ـ/g, "")
    .replace(/ي/g, "ی")
    .replace(/ك/g, "ک")
    .replace(/[۰-۹]/g, (d) => String(FA_DIGITS.indexOf(d)))
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** True when >= LABEL_TOKEN_SHARE of the label's words (2+ letters) occur in the text (substring match). */
export function labelPresent(label: string, text: string): boolean {
  const words = normalize(label).split(" ").filter((w) => w.length >= 2);
  if (words.length === 0) return true;
  const hay = normalize(text);
  const found = words.filter((w) => hay.includes(w)).length;
  return found / words.length >= LABEL_TOKEN_SHARE;
}

// ---------------------------------------------------------------------------------------------- layout
export function iou(a: Box, b: Box): number {
  const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
  const iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
  const inter = ix * iy;
  const union = a.w * a.h + b.w * b.h - inter;
  return union > 0 ? inter / union : 0;
}

function median(xs: number[]): number | null {
  if (xs.length === 0) return null;
  const s = [...xs].sort((p, q) => p - q);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? (s[m] ?? null) : ((s[m - 1] ?? 0) + (s[m] ?? 0)) / 2;
}

function sameColour(a: string | null, b: string): boolean {
  if (!a) return false;
  return rgb(a) === rgb(b);
}

/** "#01392d" / "rgb(1, 57, 45)" -> "1,57,45". */
export function rgb(c: string): string {
  const t = c.trim().toLowerCase();
  const hex = /^#([0-9a-f]{6})$/.exec(t);
  if (hex?.[1]) {
    const v = hex[1];
    return [0, 2, 4].map((i) => Number.parseInt(v.slice(i, i + 2), 16)).join(",");
  }
  const m = /^rgba?\(([^)]+)\)$/.exec(t);
  if (m?.[1]) return m[1].split(",").slice(0, 3).map((x) => String(Math.round(Number.parseFloat(x)))).join(",");
  return t;
}

// ----------------------------------------------------------------------------------------------- score
export function scoreRegion(spec: SpecRegion, at: RegionAtWidth, built: BuiltRegion | undefined): RegionResult {
  const base = { id: spec.id, label_fa: spec.label_fa, ...(spec.later_phase ? { later_phase: spec.later_phase } : {}) };
  if (!built?.visible || !built.box) {
    return { ...base, presence: 0, iou: null, in_place: false, missing_children: spec.children, note: built ? "not visible" : "no data-fid region on the built page" };
  }
  const overlap = iou(at.box, built.box);
  const inPlace = overlap >= IOU_MIN;
  const honestLater = !!spec.later_phase && normalize(built.text).includes(normalize(LATER_TEXT));
  if (honestLater) {
    return { ...base, presence: 1, iou: overlap, in_place: inPlace, missing_children: [], note: `later phase: honest «${LATER_TEXT}» in place` };
  }
  const missing = spec.children.filter((c) => !labelPresent(c, built.text));
  let got = 1 + (spec.children.length - missing.length);
  let total = 1 + spec.children.length;
  let note = "";
  if (at.items && at.items > 0) {
    got += Math.min(built.items / at.items, 1);
    total += 1;
    if (built.items < at.items) note = `items ${built.items}/${at.items}`;
  }
  return { ...base, presence: got / total, iou: overlap, in_place: inPlace, missing_children: missing, note };
}

function styleChecks(spec: PageSpec, w: Width, built: BuiltPage): StyleCheck[] {
  const key = `${w}` as const;
  const out: StyleCheck[] = [];
  const reg = (id: string) => spec.regions.find((r) => r.id === id);
  // 1. side menu with icons (or, where the mockup hides it, the menu toggle)
  const menu = reg("side-menu")?.widths[key];
  const toggle = reg("menu-toggle")?.widths[key];
  if (menu) {
    const b = built.regions["side-menu"];
    const ok = !!b?.visible && b.icons >= 3;
    out.push({ id: "side-menu-icons", ok: ok ? 1 : 0, detail: b?.visible ? `menu visible, ${b.icons} icons` : "no side menu" });
  } else if (toggle) {
    const b = built.regions["menu-toggle"];
    out.push({ id: "menu-toggle", ok: b?.visible ? 1 : 0, detail: b?.visible ? "toggle visible" : "no menu toggle" });
  }
  // 2./3. card / panel radius and border-or-shadow
  const panels = spec.regions.filter((r) => PANEL_KINDS.includes(r.kind));
  const specRadius = median(panels.map((r) => r.widths[key]?.radius).filter((x): x is number => typeof x === "number"));
  const builtPanels = panels.map((r) => built.regions[r.id]).filter((b): b is BuiltRegion => !!b?.visible);
  if (specRadius !== null) {
    const br = median(builtPanels.map((b) => b.radius).filter((x): x is number => typeof x === "number"));
    const ok = br !== null && Math.abs(br - specRadius) <= TOL.radiusPx;
    out.push({ id: "panel-radius", ok: ok ? 1 : 0, detail: `built ${br ?? "-"}px vs mockup ${specRadius}px (±${TOL.radiusPx})` });
    const framed = builtPanels.filter((b) => (b.border ?? 0) > 0 || b.shadow).length;
    out.push({ id: "panel-border", ok: builtPanels.length ? framed / builtPanels.length : 0, detail: `${framed}/${builtPanels.length} built panels with border or shadow` });
  }
  // 4. font family (approved token stack, not the mockup's Tahoma / Noto)
  const vaz = /vazirmatn/i.test(built.font_family);
  out.push({ id: "font-family", ok: vaz ? 1 : 0, detail: vaz ? "Vazirmatn (approved token)" : `font ${built.font_family}` });
  // 5. heading size of the page header
  const hSpec = reg("page-header")?.widths[key]?.heading_px ?? reg("serial-header")?.widths[key]?.heading_px ?? null;
  if (hSpec) {
    const hb = built.regions["page-header"]?.heading_px ?? built.regions["serial-header"]?.heading_px ?? null;
    const ok = hb !== null && Math.abs(hb - hSpec) / hSpec <= TOL.headingRatio;
    out.push({ id: "heading-size", ok: ok ? 1 : 0, detail: `built ${hb ?? "-"}px vs mockup ${hSpec}px (±${TOL.headingRatio * 100}%)` });
  }
  // 6. spacing: content inset of the page header
  const pSpec = spec.widths[key]?.content_pad_px ?? null;
  if (pSpec !== null) {
    const pb = built.content_pad_px;
    const ok = pb !== null && Math.abs(pb - pSpec) <= TOL.paddingPx;
    out.push({ id: "content-padding", ok: ok ? 1 : 0, detail: `built ${pb ?? "-"}px vs mockup ${pSpec}px (±${TOL.paddingPx})` });
  }
  // 7. colours against the APPROVED brand tokens (00.6 brand beats the mockup colours)
  const bgOk = sameColour(built.body_bg, built.tokens.bg);
  const prOk = built.primary_bg === null ? null : sameColour(built.primary_bg, built.tokens.primary);
  const parts = prOk === null ? [bgOk] : [bgOk, prOk];
  out.push({
    id: "brand-colours",
    ok: parts.filter(Boolean).length / parts.length,
    detail: `page bg ${bgOk ? "=" : "≠"} --color-bg${prOk === null ? "" : `, primary button ${prOk ? "=" : "≠"} --color-primary`}`,
  });
  return out;
}

export function scoreWidth(spec: PageSpec, w: Width, built: BuiltPage): WidthResult {
  const key = `${w}` as const;
  const regions: RegionResult[] = [];
  for (const r of spec.regions) {
    const at = r.widths[key];
    if (!at) continue; // not shown in the mockup at this width
    regions.push(scoreRegion(r, at, built.regions[r.id]));
  }
  const presence = regions.length ? regions.reduce((s, r) => s + r.presence, 0) / regions.length : 1;
  const layout = regions.length ? regions.filter((r) => r.in_place).length / regions.length : 1;
  const checks = styleChecks(spec, w, built);
  const style = checks.length ? checks.reduce((s, c) => s + c.ok, 0) / checks.length : 1;
  const score = WEIGHTS.presence * presence + WEIGHTS.layout * layout + WEIGHTS.style * style;
  return { width: w, score, presence, layout, style, regions, style_checks: checks };
}

export function pageResult(spec: PageSpec, widths: WidthResult[]): PageResult {
  const min = widths.length ? Math.min(...widths.map((x) => x.score)) : 0;
  return { page: spec.page, title_fa: spec.title_fa, authored: spec.authored, widths, min, passed: widths.length === WIDTHS.length && min >= THRESHOLD };
}

// -------------------------------------------------------------------------------------------- report
const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

export function renderMarkdown(results: PageResult[], meta: { commit: string; date: string; channel: string }): string {
  const lines: string[] = [];
  lines.push("# PHASE_02 UI fidelity baseline (DEC-061)", "");
  lines.push(`Measured by \`frontend/e2e/fidelity/fidelity.spec.ts\` (method: \`frontend/e2e/fidelity/README.md\`).`);
  lines.push(`Commit \`${meta.commit}\` · ${meta.date} · browser channel ${meta.channel} · threshold ${pct(THRESHOLD)} at every width.`, "");
  lines.push("Score per width = 0.5 × presence + 0.3 × layout (IoU ≥ 0.5) + 0.2 × style. Colours are checked against the approved brand tokens, not the mockup colours.", "");
  lines.push(`| Page | ${WIDTHS.join(" | ")} | min | ≥ 95%? |`, `|---|${WIDTHS.map(() => "---").join("|")}|---|---|`);
  for (const p of results) {
    const cells = WIDTHS.map((w) => {
      const r = p.widths.find((x) => x.width === w);
      return r ? pct(r.score) : "-";
    });
    lines.push(`| ${p.page} ${p.title_fa}${p.authored === "hand" ? " (hand spec)" : ""} | ${cells.join(" | ")} | ${pct(p.min)} | ${p.passed ? "yes" : "no"} |`);
  }
  lines.push("");
  for (const p of results) {
    lines.push(`## Page ${p.page} — ${p.title_fa}`, "");
    lines.push(`| Width | score | presence | layout | style |`, `|---|---|---|---|---|`);
    for (const w of p.widths) lines.push(`| ${w.width} | ${pct(w.score)} | ${pct(w.presence)} | ${pct(w.layout)} | ${pct(w.style)} |`);
    lines.push("");
    const w1440 = p.widths.find((x) => x.width === 1440) ?? p.widths[0];
    if (!w1440) continue;
    lines.push("To-do for the restyle (regions at 1440; widths where a region differs are listed after it):", "");
    lines.push("| Region | state | IoU | missing labels / note |", "|---|---|---|---|");
    for (const r of w1440.regions) {
      const state = r.presence === 0 ? "MISSING" : r.presence < 1 ? (r.in_place ? "incomplete" : "incomplete + misplaced") : r.in_place ? "ok" : "misplaced";
      const other = p.widths
        .filter((x) => x.width !== 1440)
        .map((x) => {
          const o = x.regions.find((y) => y.id === r.id);
          if (!o) return null;
          const s = o.presence === 0 ? "missing" : o.in_place ? null : "misplaced";
          return s ? `${x.width}: ${s}` : null;
        })
        .filter(Boolean)
        .join(", ");
      const miss = r.missing_children.length ? r.missing_children.map((c) => `«${c}»`).join("، ") : "";
      lines.push(`| ${r.id} (${r.label_fa})${r.later_phase ? ` [${r.later_phase}]` : ""} | ${state} | ${r.iou === null ? "-" : r.iou.toFixed(2)} | ${[miss, r.note, other].filter(Boolean).join(" · ")} |`);
    }
    lines.push("", "Style checks at 1440: " + w1440.style_checks.map((c) => `${c.id} ${c.ok === 1 ? "ok" : c.ok === 0 ? "FAIL" : pct(c.ok)} (${c.detail})`).join("; "), "");
  }
  return lines.join("\n") + "\n";
}
