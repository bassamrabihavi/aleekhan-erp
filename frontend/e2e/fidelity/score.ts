// DEC-061 fidelity scorer (pure functions; unit tests in score.vitest.ts). The browser-side measurement lives in
// measure.ts; fidelity.spec.ts drives both. Method and formula: README.md.
import { DATA_ROW_KINDS, EXTRA_PENALTY, FORM_TOL, IOU_MIN, LABEL_TOKEN_SHARE, LATER_TEXT, PANEL_KINDS, THRESHOLD, TOL, WEIGHTS, WIDTHS, type Frame, type RegionKind, type Width } from "./config";
import { structureScore } from "./structure";

/** The visual form of a region (measure.ts formOf; README.md "Form"). Counts are of visible elements. */
export interface FormFeatures {
  /** Circular elements 18-72 px with an icon inside (stage / status circles). */
  circles: number;
  /** Status dots 5-14 px (element or ::before / ::after). */
  dots: number;
  /** Pills / badges (rounded, filled, with text; not a control). */
  pills: number;
  /** Progress bars / rails (outermost). */
  bars: number;
  /** Buttons styled as buttons (border or background, >= FORM_TOL.buttonMinPx high). */
  buttons: number;
  /** Framed boxes with a radius (border, shadow or own background), >= 80 x 44 px. */
  cards: number;
  /** Cards with an icon in their top 56 px (icon header / leading status icon). */
  icon_cards: number;
  /** Icons (svg, img, data-icon, glyph) up to 64 px. */
  icons: number;
  /** Tables (table / role=table / role=grid). */
  tables: number;
  /** Largest number of sibling controls on one line (tabs, step buttons). */
  row_controls: number;
  /** Largest font size of a short text with a digit or a dash value (the "big number"). */
  big_px: number | null;
  /** Largest image slot (img / role=img / background image >= 40 px), normalised like the region box. */
  image: { w: number; h: number } | null;
}

export type FormKey = keyof FormFeatures;

/**
 * The mockup's form of a region at one width. Extracted specs carry every feature; hand specs (pages 1 / 2) give
 * only the features they check (`hand: true`).
 */
export interface FormSpec {
  features: Partial<FormFeatures>;
  /** Per-row counts follow the data (>= 1 suffices); always true for DATA_ROW_KINDS. */
  data_rows?: boolean;
  /** Hand-authored: every listed feature is checked (row_controls for any kind). */
  hand?: boolean;
}

export interface FormCheck {
  feature: FormKey;
  ok: boolean;
  detail: string;
}

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
  /** The mockup's visual form at this width (README.md "Form"). */
  form?: FormSpec;
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

/** A visible top-level section / panel of the built content that carries no spec region (DEC-061 amendment). */
export interface ExtraSection {
  label: string;
  /** Content frame (normalised like the content regions). */
  box: Box;
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
  /** Visual form features (null when not visible). */
  form?: FormFeatures | null;
}

export interface BuiltPage {
  width: Width;
  regions: Record<string, BuiltRegion | undefined>;
  font_family: string;
  body_bg: string | null;
  primary_bg: string | null;
  tokens: { primary: string; bg: string };
  content_pad_px: number | null;
  /** Extra sections found by the built-page scan (measure.ts); none = []. */
  extras: ExtraSection[];
  /** Structure SSIM per region id (structure.ts); null = no mockup image for that region at that width. */
  structure?: Record<string, number | null>;
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
  /** Form checks of the region (empty = the mockup region has no checkable form). */
  form_checks: FormCheck[];
  /** Share of form checks met (null = no checks). */
  form: number | null;
  /** Structure SSIM (null = no mockup image). */
  ssim: number | null;
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
  /** Share of required regions in place, minus the extra-section penalty (floored at 0). */
  layout: number;
  /** Share of required regions in place (before the extra-section penalty). */
  layout_in_place: number;
  /** Number of extra (non-mockup) sections whose top lies above the bottom of the lowest mockup region. */
  extra_above: number;
  /** Their labels (tag.class[testid] «heading»). */
  extra_sections: string[];
  /** Extra sections found that are free (fully below all mockup regions): listed for transparency, no penalty. */
  extra_free: string[];
  style: number;
  /** Mean share of form checks met over the regions that have checks. */
  form_checks: number;
  /** Mean structure score over the regions with a mockup image. */
  structure: number;
  /** form = (WEIGHTS.form_checks x form_checks + WEIGHTS.structure x structure) / (their sum). */
  form: number;
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

// ------------------------------------------------------------------------------------------------ form
const COUNT_KEYS: readonly FormKey[] = ["circles", "dots", "pills", "bars", "buttons", "cards", "icon_cards", "icons", "row_controls"];
/** Per-row counts: relaxed to ">= 1" in data-row regions. */
const PER_ROW_KEYS: readonly FormKey[] = ["circles", "dots", "pills", "bars", "buttons", "cards", "icon_cards", "icons"];
/** Counts that also have an upper bound (a page full of extra badges does not look like the mockup either). */
const UPPER_KEYS: readonly FormKey[] = ["dots", "pills", "bars"];

/**
 * The form checks of one region: every feature the mockup HAS (count > 0, big number >= bigMinPx, an image slot)
 * must be matched by the built region; tables must agree both ways (table vs card layout at that width). Features
 * the mockup does not have are not checked (except tables). A region that is not visible fails every check.
 * row_controls is checked for kind "tabs" (and wherever a hand spec lists it).
 */
export function formChecks(kind: RegionKind, form: FormSpec, built: FormFeatures | null | undefined): FormCheck[] {
  const out: FormCheck[] = [];
  const m = form.features;
  const dataRows = !!form.data_rows || DATA_ROW_KINDS.includes(kind);
  for (const k of COUNT_KEYS) {
    const want = m[k];
    if (typeof want !== "number" || want <= 0) continue;
    if (k === "row_controls" && kind !== "tabs" && !form.hand) continue;
    const got = built ? (built[k] as number) : 0;
    const relaxed = dataRows && PER_ROW_KEYS.includes(k);
    const lo = relaxed ? 1 : Math.max(1, Math.round(want * (1 - FORM_TOL.count)));
    const hi = !relaxed && UPPER_KEYS.includes(k) ? Math.ceil(want * (1 + FORM_TOL.countUpper)) + FORM_TOL.countUpperSlack : Infinity;
    out.push({ feature: k, ok: !!built && got >= lo && got <= hi, detail: `${k} ${got} (mockup ${want}; need ${lo}${hi === Infinity ? "+" : `..${hi}`})` });
  }
  const big = m.big_px;
  if (typeof big === "number" && big >= FORM_TOL.bigMinPx) {
    const got = built?.big_px ?? null;
    const need = Math.round(big * FORM_TOL.bigRatio * 10) / 10;
    out.push({ feature: "big_px", ok: got !== null && got >= need, detail: `big number ${got ?? "-"}px (mockup ${big}px; need >= ${need})` });
  }
  if (m.image) {
    const got = built?.image ?? null;
    const ok = !!got && got.w >= m.image.w * FORM_TOL.imageRatio && got.h >= m.image.h * FORM_TOL.imageRatio;
    out.push({ feature: "image", ok, detail: `image slot ${got ? `${got.w.toFixed(3)}x${got.h.toFixed(3)}` : "none"} (mockup ${m.image.w.toFixed(3)}x${m.image.h.toFixed(3)})` });
  }
  if (typeof m.tables === "number") {
    const got = built?.tables ?? 0;
    if (m.tables > 0 || got > 0) out.push({ feature: "tables", ok: !!built && m.tables > 0 === got > 0, detail: `table ${got > 0 ? "yes" : "no"} (mockup ${m.tables > 0 ? "table" : "cards / no table"})` });
  }
  return out;
}

// ----------------------------------------------------------------------------------------------- score
export function scoreRegion(spec: SpecRegion, at: RegionAtWidth, built: BuiltRegion | undefined, ssimValue: number | null = null): RegionResult {
  const base = { id: spec.id, label_fa: spec.label_fa, ...(spec.later_phase ? { later_phase: spec.later_phase } : {}) };
  const fc = at.form ? formChecks(spec.kind, at.form, built?.visible ? built.form : null) : [];
  const formPart = { form_checks: fc, form: fc.length ? fc.filter((c) => c.ok).length / fc.length : null, ssim: ssimValue };
  if (!built?.visible || !built.box) {
    return { ...base, presence: 0, iou: null, in_place: false, missing_children: spec.children, note: built ? "not visible" : "no data-fid region on the built page", ...formPart };
  }
  const overlap = iou(at.box, built.box);
  const inPlace = overlap >= IOU_MIN;
  const honestLater = !!spec.later_phase && normalize(built.text).includes(normalize(LATER_TEXT));
  if (honestLater) {
    return { ...base, presence: 1, iou: overlap, in_place: inPlace, missing_children: [], note: `later phase: honest «${LATER_TEXT}» in place`, ...formPart };
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
  return { ...base, presence: got / total, iou: overlap, in_place: inPlace, missing_children: missing, note, ...formPart };
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

/**
 * DEC-061 amendment: the extra sections that lie above or between the mockup regions, i.e. whose top edge is above
 * the bottom edge of the lowest content region of the spec that is present (visible) on the built page at this width.
 * Sections fully below all mockup regions are free; with no content region present there is nothing to be above.
 */
export function extraAbove(spec: PageSpec, w: Width, built: BuiltPage): ExtraSection[] {
  const key = `${w}` as const;
  let bottom: number | null = null;
  for (const r of spec.regions) {
    if (r.frame !== "content" || !r.widths[key]) continue;
    const b = built.regions[r.id];
    if (!b?.visible || !b.box) continue;
    const y = b.box.y + b.box.h;
    if (bottom === null || y > bottom) bottom = y;
  }
  if (bottom === null) return [];
  const lowest = bottom;
  return built.extras.filter((e) => e.box.y < lowest);
}

export function scoreWidth(spec: PageSpec, w: Width, built: BuiltPage): WidthResult {
  const key = `${w}` as const;
  const regions: RegionResult[] = [];
  for (const r of spec.regions) {
    const at = r.widths[key];
    if (!at) continue; // not shown in the mockup at this width
    const st = built.structure?.[r.id];
    regions.push(scoreRegion(r, at, built.regions[r.id], typeof st === "number" ? st : null));
  }
  const presence = regions.length ? regions.reduce((s, r) => s + r.presence, 0) / regions.length : 1;
  const inPlace = regions.length ? regions.filter((r) => r.in_place).length / regions.length : 1;
  const extras = extraAbove(spec, w, built);
  const layout = Math.max(0, inPlace - (extras.length * EXTRA_PENALTY) / WEIGHTS.layout);
  const checks = styleChecks(spec, w, built);
  const style = checks.length ? checks.reduce((s, c) => s + c.ok, 0) / checks.length : 1;
  const withForm = regions.filter((r) => r.form !== null);
  const formChecksScore = withForm.length ? withForm.reduce((s, r) => s + (r.form ?? 0), 0) / withForm.length : 1;
  // structure: over the regions with a mockup image; nothing measured at all = 0 (never a free pass)
  const withImg = regions.filter((r) => r.ssim !== null);
  const structure = withImg.length ? withImg.reduce((s, r) => s + structureScore(r.ssim ?? 0), 0) / withImg.length : 0;
  const form = (WEIGHTS.form_checks * formChecksScore + WEIGHTS.structure * structure) / (WEIGHTS.form_checks + WEIGHTS.structure);
  const score = WEIGHTS.presence * presence + WEIGHTS.layout * layout + WEIGHTS.form_checks * formChecksScore + WEIGHTS.structure * structure + WEIGHTS.style * style;
  return {
    width: w,
    score,
    presence,
    layout,
    layout_in_place: inPlace,
    extra_above: extras.length,
    extra_sections: extras.map((e) => e.label),
    extra_free: built.extras.filter((e) => !extras.includes(e)).map((e) => e.label),
    style,
    form_checks: formChecksScore,
    structure,
    form,
    regions,
    style_checks: checks,
  };
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
  lines.push(`Score per width = ${WEIGHTS.presence} × presence + ${WEIGHTS.layout} × layout (IoU ≥ ${IOU_MIN}) + ${WEIGHTS.form_checks} × form checks + ${WEIGHTS.structure} × structure (blurred SSIM) + ${WEIGHTS.style} × style. Colours are checked against the approved brand tokens, not the mockup colours.`);
  lines.push(`Each extra (non-mockup) section above or between the mockup regions (\`extra_above\`) removes ${pct(EXTRA_PENALTY)} of the total from the layout part (DEC-061 amendment).`, "");
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
    lines.push(`| Width | score | presence | layout | in place | extra_above | form checks | structure | style |`, `|---|---|---|---|---|---|---|---|---|`);
    for (const w of p.widths) lines.push(`| ${w.width} | ${pct(w.score)} | ${pct(w.presence)} | ${pct(w.layout)} | ${pct(w.layout_in_place)} | ${w.extra_above} | ${pct(w.form_checks)} | ${pct(w.structure)} | ${pct(w.style)} |`);
    lines.push("");
    for (const w of p.widths) if (w.extra_sections.length) lines.push(`Extra sections above / between mockup regions at ${w.width}: ${w.extra_sections.map((x) => `\`${x}\``).join(", ")}`);
    for (const w of p.widths) if (w.extra_free.length) lines.push(`Extra sections below all mockup regions at ${w.width} (free): ${w.extra_free.map((x) => `\`${x}\``).join(", ")}`);
    if (p.widths.some((w) => w.extra_sections.length || w.extra_free.length)) lines.push("");
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
    lines.push("", "Form failures per width (region: failed checks; ssim when below full):", "");
    for (const w of p.widths) {
      const fails = w.regions
        .map((r) => {
          const bad = r.form_checks.filter((c) => !c.ok).map((c) => c.detail);
          const lowSsim = r.ssim !== null && structureScore(r.ssim) < 1;
          if (!bad.length && !lowSsim) return null;
          return `${r.id}: ${bad.length ? bad.join("; ") : "form ok"}${r.ssim !== null ? `; ssim ${r.ssim.toFixed(2)}` : ""}`;
        })
        .filter(Boolean);
      lines.push(`- ${w.width}: ${fails.length ? fails.join(" · ") : "none"}`);
    }
    lines.push("", "Style checks at 1440: " + w1440.style_checks.map((c) => `${c.id} ${c.ok === 1 ? "ok" : c.ok === 0 ? "FAIL" : pct(c.ok)} (${c.detail})`).join("; "), "");
  }
  return lines.join("\n") + "\n";
}
