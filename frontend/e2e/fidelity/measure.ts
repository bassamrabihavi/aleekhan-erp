// Browser-side measurement of a page (mockup or built) for the DEC-061 fidelity harness. `measureInPage` runs
// inside the page (page.evaluate): it must be self-contained (no imports, no closures over module values).
import type { Page } from "@playwright/test";

import { EXTRA_IGNORE_SELECTOR, EXTRA_SECTION_SELECTOR, FORM_TOL, type Frame, type RegionKind, type Width } from "./config";
import type { BuiltPage, BuiltRegion, ExtraSection, FormFeatures } from "./score";

export interface Probe {
  id: string;
  kind: RegionKind;
  frame: Frame;
  /** Mockup: CSS selector. Built: [data-fid="<id>"]. */
  selector: string;
  children?: string[];
  items?: string;
}

export interface Measured extends BuiltRegion {
  children: string[];
  /** Absolute page rectangle in CSS px (the structure crop). */
  px: { x: number; y: number; w: number; h: number } | null;
}

export interface PageMeasure {
  regions: Record<string, Measured | undefined>;
  font_family: string;
  body_bg: string | null;
  primary_bg: string | null;
  tokens: { primary: string; bg: string };
  content_pad_px: number | null;
  /** Built page only: visible top-level sections / panels of the content that carry no spec region (README.md). */
  extras: ExtraSection[];
}

interface Args {
  /** Minimum height of an element styled as a button (FORM_TOL.buttonMinPx). */
  buttonMinPx: number;
  probes: Probe[];
  content: string;
  primary: string;
  built: boolean;
  /** Built page only: the extra-section scan (spec region ids + the section / ignore selectors of config.ts). */
  extra: { ids: string[]; section: string; ignore: string } | null;
}

function measureInPage({ probes, content, primary, built, extra, buttonMinPx }: Args): PageMeasure {
  const vw = document.documentElement.clientWidth;
  const main = document.querySelector(content);
  const c = main ? main.getBoundingClientRect() : new DOMRect(0, 0, vw, 0);
  const cTop = c.top + window.scrollY;
  const visible = (el: Element): boolean => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    if (r.right <= 0 || r.left >= vw) return false; // off-canvas drawer (translateX)
    return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
  };
  const textOf = (el: Element, own: boolean): string => {
    const raw = own
      ? Array.from(el.childNodes)
          .filter((n) => n.nodeType === Node.TEXT_NODE)
          .map((n) => n.textContent ?? "")
          .join(" ")
      : ((el as HTMLElement).innerText || el.textContent || "");
    return (raw.split("\n").find((l) => l.trim() !== "") ?? "")
      .replace(/^[^\p{L}\p{N}]+/u, "")
      .replace(/[^\p{L}\p{N})]+$/u, "")
      .trim();
  };
  const px = (v: string): number | null => {
    const n = Number.parseFloat(v);
    return Number.isNaN(n) ? null : n;
  };
  // ---- visual form features of a region (README.md "Form"); the same code measures the mockup and the built page
  const alpha = (col: string): number => {
    if (!col || col === "transparent") return 0;
    const m = /rgba?\(([^)]+)\)/.exec(col);
    if (!m?.[1]) return 1;
    const parts = m[1].split(/[,/\s]+/).filter(Boolean);
    return parts.length >= 4 ? Number.parseFloat(parts[3] ?? "1") : 1;
  };
  const effBg = (e: Element | null): string => {
    for (let x = e; x; x = x.parentElement) {
      const b = getComputedStyle(x).backgroundColor;
      if (alpha(b) > 0.05) return b;
    }
    return "rgb(255, 255, 255)";
  };
  const ownText = (e: Element): string =>
    Array.from(e.childNodes)
      .filter((n) => n.nodeType === Node.TEXT_NODE)
      .map((n) => n.textContent ?? "")
      .join("")
      .trim();
  const glyph = (e: Element): boolean => {
    const own = ownText(e);
    return own.length > 0 && /^[^\p{L}\p{N}\s]{1,2}$/u.test(own);
  };
  const isIcon = (e: Element): boolean => {
    if (!visible(e)) return false;
    const r = e.getBoundingClientRect();
    if (r.width > 64 || r.height > 64) return false;
    return e.tagName.toLowerCase() === "svg" || e.tagName === "IMG" || e.hasAttribute("data-icon") || (e.children.length === 0 && glyph(e));
  };
  const SKIP_CARD = /^(BUTTON|INPUT|SELECT|TEXTAREA|A|LABEL|TABLE|THEAD|TBODY|TR|TD|TH|OPTION|IMG|svg)$/;
  const formOf = (el: Element, frame: Frame): FormFeatures => {
    const norm = frame === "content" && c.width > 0 ? c.width : vw;
    const all = [el, ...Array.from(el.querySelectorAll("*"))].filter(visible);
    const f: FormFeatures = { circles: 0, dots: 0, pills: 0, bars: 0, buttons: 0, cards: 0, icon_cards: 0, icons: 0, tables: 0, row_controls: 0, big_px: null, image: null };
    const bars = new Set<Element>();
    let imgArea = 0;
    const dot = (w: number, h: number, rr: number, bg: string) => w >= 5 && w <= 14 && Math.abs(w - h) <= 1.5 && rr >= w / 2 - 1 && alpha(bg) > 0.05;
    for (const e of all) {
      const r = e.getBoundingClientRect();
      const cs = getComputedStyle(e);
      const rad = px(cs.borderTopLeftRadius) ?? 0;
      const bw = px(cs.borderTopWidth) ?? 0;
      const bordered = bw >= 1 && cs.borderTopStyle !== "none" && alpha(cs.borderTopColor) > 0.05;
      const filled = alpha(cs.backgroundColor) > 0.05;
      const text = ((e as HTMLElement).innerText || "").trim();
      const tag = e.tagName;
      const role = e.getAttribute("role") ?? "";
      if (isIcon(e)) f.icons++;
      // step / status circle with an icon inside
      if (r.width >= 18 && r.width <= 72 && Math.abs(r.width - r.height) <= 3 && rad >= 0.45 * Math.min(r.width, r.height) && (filled || bordered)) {
        if (Array.from(e.querySelectorAll("svg, img, [data-icon]")).some(visible) || glyph(e)) f.circles++;
      }
      // status dot (the element itself or its ::before / ::after)
      if (dot(r.width, r.height, rad, cs.backgroundColor) && text === "") f.dots++;
      for (const pseudo of ["::before", "::after"]) {
        const ps = getComputedStyle(e, pseudo);
        if (ps.content === "none" || ps.content === "normal" || ps.display === "none") continue;
        const w = px(ps.width) ?? 0;
        const h = px(ps.height) ?? 0;
        const pr = ps.borderTopLeftRadius.endsWith("%") ? (Number.parseFloat(ps.borderTopLeftRadius) / 100) * w : (px(ps.borderTopLeftRadius) ?? 0);
        if (dot(w, h, pr, ps.backgroundColor)) f.dots++;
      }
      // pill / badge (not a control)
      const control = /^(BUTTON|INPUT|SELECT|TEXTAREA)$/.test(tag) || role === "tab" || role === "button";
      if (!control && r.height >= 14 && r.height <= 34 && r.width >= 1.3 * r.height && rad >= r.height / 2 - 2 && filled && text !== "") f.pills++;
      // progress bar / rail (outermost only)
      const barLike =
        role === "progressbar" || tag === "PROGRESS" || tag === "METER" || (r.height >= 3 && r.height <= 14 && r.width >= 40 && r.width >= 5 * r.height && filled && rad >= r.height / 2 - 1 && text === "");
      if (barLike) {
        let inner = false;
        for (let x = e.parentElement; x && x !== el.parentElement; x = x.parentElement) if (bars.has(x)) inner = true;
        bars.add(e);
        if (!inner) f.bars++;
      }
      // a button styled as a button (border or background, minimum height)
      const buttonish = tag === "BUTTON" || role === "button" || role === "tab" || (tag === "INPUT" && /^(button|submit)$/.test((e as HTMLInputElement).type)) || e.classList.contains("btn");
      if (buttonish && r.height >= buttonMinPx && (bordered || filled)) f.buttons++;
      // card: a framed box (border, shadow or its own background) with a radius
      const shadow = cs.boxShadow !== "none" && cs.boxShadow !== "";
      const ownBg = filled && effBg(e.parentElement) !== cs.backgroundColor;
      if (!SKIP_CARD.test(tag) && !control && rad >= 4 && r.width >= 80 && r.height >= 44 && (bordered || shadow || ownBg)) {
        f.cards++;
        const top = r.top;
        if (Array.from(e.querySelectorAll("*")).some((x) => isIcon(x) && x.getBoundingClientRect().top - top <= 56)) f.icon_cards++;
      }
      if (tag === "TABLE" || role === "table" || role === "grid") f.tables++;
      // big number: a short own text with a digit or a dash value
      const own = ownText(e);
      if (own && own.length <= 16 && /[\p{N}—–]/u.test(own)) {
        const fs = px(cs.fontSize) ?? 0;
        if (f.big_px === null || fs > f.big_px) f.big_px = fs;
      }
      // image slot (photo, illustration >= 40 px, or an honest image placeholder with role=img)
      if ((tag === "IMG" || tag.toLowerCase() === "svg" || tag === "PICTURE" || tag === "CANVAS" || tag === "VIDEO" || role === "img" || cs.backgroundImage.includes("url(")) && r.width >= 40 && r.height >= 40) {
        const area = r.width * r.height;
        if (area > imgArea) {
          imgArea = area;
          f.image = { w: Math.round((r.width / norm) * 10000) / 10000, h: Math.round((r.height / norm) * 10000) / 10000 };
        }
      }
      // a row of controls (tabs / step buttons): sibling controls on one line
      const kids = Array.from(e.children).filter((k) => visible(k) && (/^(BUTTON|A)$/.test(k.tagName) || /^(tab|button)$/.test(k.getAttribute("role") ?? "")));
      if (kids.length >= 3) {
        const rows = new Map<number, number>();
        for (const k of kids) {
          const t = Math.round(k.getBoundingClientRect().top / 6);
          rows.set(t, (rows.get(t) ?? 0) + 1);
        }
        f.row_controls = Math.max(f.row_controls, ...rows.values());
      }
    }
    if (f.big_px !== null) f.big_px = Math.round(f.big_px * 10) / 10;
    return f;
  };
  const regions: Record<string, Measured | undefined> = {};
  for (const p of probes) {
    const all = Array.from(document.querySelectorAll(p.selector));
    const el = all.find(visible) ?? all[0];
    if (!el) {
      regions[p.id] = undefined;
      continue;
    }
    const vis = visible(el);
    const r = el.getBoundingClientRect();
    const top = r.top + window.scrollY;
    const box = !vis
      ? null
      : p.frame === "content" && c.width > 0
        ? { x: (r.left - c.left) / c.width, y: (top - cTop) / c.width, w: r.width / c.width, h: r.height / c.width }
        : { x: r.left / vw, y: top / vw, w: r.width / vw, h: r.height / vw };
    const children: string[] = [];
    for (const sel of p.children ?? []) {
      const own = sel.endsWith("::own");
      const css = own ? sel.slice(0, -5) : sel;
      for (const ch of Array.from(el.querySelectorAll(css))) {
        const t = textOf(ch, own);
        if (t && !/^[\p{N}\s.,٬٫%]+$/u.test(t) && !children.includes(t)) children.push(t);
      }
    }
    const itemEls = p.items
      ? Array.from(el.querySelectorAll(p.items))
      : built
        ? (() => {
            const marked = Array.from(el.querySelectorAll("[data-fid-item]"));
            return marked.length ? marked : Array.from(el.children);
          })()
        : [];
    const items = itemEls.filter(visible).length;
    // a bare container (no radius / border / shadow) is styled by its first framed child (e.g. a stack of panels)
    const framed = (e: Element): boolean => {
      const x = getComputedStyle(e);
      return (px(x.borderTopLeftRadius) ?? 0) > 0 || (px(x.borderTopWidth) ?? 0) > 0 || (x.boxShadow !== "none" && x.boxShadow !== "");
    };
    const first = p.kind === "kpis" ? (itemEls.find(visible) ?? el) : el;
    const styleEl = framed(first) ? first : (Array.from(first.querySelectorAll("*")).find((e) => visible(e) && framed(e)) ?? first);
    const cs = getComputedStyle(styleEl);
    const heads = [el, ...Array.from(el.querySelectorAll("h1,h2,h3"))].filter((h) => /^H[1-3]$/.test(h.tagName) && visible(h));
    const headingPx = heads.length ? Math.max(...heads.map((h) => px(getComputedStyle(h).fontSize) ?? 0)) : null;
    const icons = Array.from(el.querySelectorAll("svg, img, [data-icon], .ni, a > span:first-child, a.navitem > span:first-child")).filter(
      (i) => visible(i) && (i.tagName !== "SPAN" || /^[^\p{L}\p{N}\s]{1,2}$/u.test(i.textContent.trim())),
    ).length;
    regions[p.id] = {
      visible: vis,
      box,
      text: [((el as HTMLElement).innerText || ""), el.getAttribute("aria-label") ?? ""].join(" ").slice(0, 20000),
      items,
      radius: px(cs.borderTopLeftRadius),
      border: px(cs.borderTopWidth),
      shadow: cs.boxShadow !== "none" && cs.boxShadow !== "",
      heading_px: headingPx,
      icons,
      children,
      form: vis ? formOf(el, p.frame) : null,
      px: vis ? { x: r.left + window.scrollX, y: top, w: r.width, h: r.height } : null,
    };
  }
  const head = regions["page-header"] ?? regions["serial-header"];
  const headEl = document.querySelector(probes.find((p) => p.id === "page-header" || p.id === "serial-header")?.selector ?? "#__none__");
  const pad = head?.visible && headEl && c.width > 0 ? Math.round(c.right - headEl.getBoundingClientRect().right) : null;
  const root = getComputedStyle(document.documentElement);
  const prim = Array.from(document.querySelectorAll(primary)).find(visible);
  const bodyBg = getComputedStyle(document.body).backgroundColor;
  const rootBg = root.backgroundColor;
  // DEC-061 amendment: scan the content for sections / panels that are not spec regions. Starting at <main>, an
  // element that is a spec region is skipped (its inside belongs to the region); an element that only CONTAINS spec
  // regions is a wrapper (page container, grid, tab panel) and is scanned the same way; any other visible element
  // that is, or contains, a section / panel is one extra section. Dialogs and fixed overlays are never counted;
  // tabs that are not the default view are not rendered / not visible and so are not counted either.
  const extras: { label: string; box: { x: number; y: number; w: number; h: number } }[] = [];
  if (built && extra && main && c.width > 0) {
    const ids = new Set(extra.ids);
    const isSpec = (e: Element): boolean => ids.has(e.getAttribute("data-fid") ?? "");
    const hasSpec = (e: Element): boolean => Array.from(e.querySelectorAll("[data-fid]")).some(isSpec);
    const ignored = (e: Element): boolean => !!e.closest(extra.ignore) || getComputedStyle(e).position === "fixed";
    const isSection = (e: Element): boolean => e.matches(extra.section) || !!e.querySelector(extra.section);
    const labelOf = (e: Element): string => {
      const h = e.querySelector("h1,h2,h3,h4");
      const name = e.getAttribute("aria-label") ?? (h ? ((h as HTMLElement).innerText || h.textContent || "").trim() : "");
      const tid = e.getAttribute("data-testid");
      const cls = e.getAttribute("class")?.split(/\s+/)[0];
      return `${e.tagName.toLowerCase()}${cls ? "." + cls : ""}${tid ? `[${tid}]` : ""}${name ? ` «${name.slice(0, 60)}»` : ""}`;
    };
    const scan = (container: Element): void => {
      for (const ch of Array.from(container.children)) {
        if (isSpec(ch)) continue;
        if (hasSpec(ch)) {
          scan(ch);
          continue;
        }
        if (ignored(ch) || !visible(ch) || !isSection(ch)) continue;
        const r = ch.getBoundingClientRect();
        extras.push({ label: labelOf(ch), box: { x: (r.left - c.left) / c.width, y: (r.top + window.scrollY - cTop) / c.width, w: r.width / c.width, h: r.height / c.width } });
      }
    };
    scan(main);
  }
  return {
    regions,
    font_family: getComputedStyle(document.body).fontFamily,
    body_bg: bodyBg && bodyBg !== "rgba(0, 0, 0, 0)" ? bodyBg : rootBg || null,
    primary_bg: prim ? getComputedStyle(prim).backgroundColor : null,
    tokens: { primary: root.getPropertyValue("--color-primary").trim(), bg: root.getPropertyValue("--color-bg").trim() },
    content_pad_px: pad,
    extras,
  };
}

export async function measure(page: Page, probes: Probe[], content: string, primary: string, built: boolean): Promise<PageMeasure> {
  const extra = built ? { ids: probes.map((p) => p.id), section: EXTRA_SECTION_SELECTOR, ignore: EXTRA_IGNORE_SELECTOR } : null;
  return page.evaluate(measureInPage, { probes, content, primary, built, extra, buttonMinPx: FORM_TOL.buttonMinPx });
}

export function asBuiltPage(m: PageMeasure, width: Width, structure: Record<string, number | null> = {}): BuiltPage {
  return { width, regions: m.regions, font_family: m.font_family, body_bg: m.body_bg, primary_bg: m.primary_bg, tokens: m.tokens, content_pad_px: m.content_pad_px, extras: m.extras, structure };
}

/** A region crop request for the browser-side grayscale reduction (rect in image px, grid before oversampling). */
export interface CropReq {
  id: string;
  rect: { x: number; y: number; w: number; h: number };
  grid: { w: number; h: number };
}

interface CropArgs {
  src: string;
  reqs: CropReq[];
  over: number;
}

/** Self-contained (page.evaluate): draws each crop of the image at over x grid and returns it as grayscale 0..1. */
async function cropsInPage({ src, reqs, over }: CropArgs): Promise<Record<string, { w: number; h: number; px: number[] }>> {
  const img = new Image();
  img.src = src;
  await img.decode();
  const out: Record<string, { w: number; h: number; px: number[] }> = {};
  for (const q of reqs) {
    const x = Math.max(0, q.rect.x);
    const y = Math.max(0, q.rect.y);
    const w = Math.min(img.naturalWidth, q.rect.x + q.rect.w) - x;
    const h = Math.min(img.naturalHeight, q.rect.y + q.rect.h) - y;
    const cw = q.grid.w * over;
    const ch = q.grid.h * over;
    const cv = document.createElement("canvas");
    cv.width = cw;
    cv.height = ch;
    const ctx = cv.getContext("2d");
    if (!ctx) continue;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, cw, ch);
    if (w >= 1 && h >= 1) {
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(img, x, y, w, h, 0, 0, cw, ch);
    }
    const d = ctx.getImageData(0, 0, cw, ch).data;
    const g = new Array<number>(cw * ch);
    for (let i = 0; i < cw * ch; i++) g[i] = (0.299 * (d[i * 4] ?? 0) + 0.587 * (d[i * 4 + 1] ?? 0) + 0.114 * (d[i * 4 + 2] ?? 0)) / 255;
    out[q.id] = { w: cw, h: ch, px: g };
  }
  return out;
}

/** Grayscale crops of an image (PNG buffer) for the structure similarity, reduced in a blank browser page. */
export async function grayCrops(page: Page, png: Buffer, reqs: CropReq[], over: number): Promise<Record<string, { w: number; h: number; px: number[] }>> {
  if (reqs.length === 0) return {};
  return page.evaluate(cropsInPage, { src: `data:image/png;base64,${png.toString("base64")}`, reqs, over });
}
