// Browser-side measurement of a page (mockup or built) for the DEC-061 fidelity harness. `measureInPage` runs
// inside the page (page.evaluate): it must be self-contained (no imports, no closures over module values).
import type { Page } from "@playwright/test";

import { EXTRA_IGNORE_SELECTOR, EXTRA_SECTION_SELECTOR, type Frame, type RegionKind, type Width } from "./config";
import type { BuiltPage, BuiltRegion, ExtraSection } from "./score";

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
  probes: Probe[];
  content: string;
  primary: string;
  built: boolean;
  /** Built page only: the extra-section scan (spec region ids + the section / ignore selectors of config.ts). */
  extra: { ids: string[]; section: string; ignore: string } | null;
}

function measureInPage({ probes, content, primary, built, extra }: Args): PageMeasure {
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
  return page.evaluate(measureInPage, { probes, content, primary, built, extra });
}

export function asBuiltPage(m: PageMeasure, width: Width): BuiltPage {
  return { width, regions: m.regions, font_family: m.font_family, body_bg: m.body_bg, primary_bg: m.primary_bg, tokens: m.tokens, content_pad_px: m.content_pad_px, extras: m.extras };
}
