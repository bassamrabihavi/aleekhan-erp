// Unit tests of the DEC-061 fidelity scorer (pure functions; run by vitest with the app tests).
import { describe, expect, it } from "vitest";

import { EXTRA_PENALTY, THRESHOLD, WEIGHTS } from "./config";
import { extraAbove, iou, labelPresent, normalize, pageResult, rgb, scoreRegion, scoreWidth, type BuiltPage, type BuiltRegion, type PageSpec } from "./score";

const box = { x: 0.1, y: 0.1, w: 0.5, h: 0.2 };
const built = (over: Partial<BuiltRegion> = {}): BuiltRegion => ({ visible: true, box, text: "", items: 0, radius: 11, border: 1, shadow: true, heading_px: 21, icons: 0, ...over });

const spec: PageSpec = {
  schema: 1,
  page: "99",
  title_fa: "صفحه آزمایشی",
  route: "/x",
  ready_testid: "x",
  authored: "hand",
  source_note: "synthetic",
  mockup: { files: [] },
  excluded: [],
  widths: { "1440": { content_pad_px: 20 } },
  regions: [
    { id: "page-header", label_fa: "سربرگ", kind: "header", frame: "content", children: ["ردیابی محصول و استایل"], widths: { "1440": { box, heading_px: 21 } } },
    { id: "kpis", label_fa: "KPI", kind: "kpis", frame: "content", children: ["سریال‌های مرتبط"], widths: { "1440": { box, items: 4, radius: 11 } } },
    { id: "chart", label_fa: "نمودار", kind: "chart", frame: "content", later_phase: "PHASE_07", children: ["توزیع سریال‌ها"], widths: { "1440": { box, radius: 11 } } },
    { id: "mobile-only", label_fa: "فقط موبایل", kind: "bottom-nav", frame: "viewport", children: [], widths: { "1440": null } },
  ],
};

describe("fidelity scorer", () => {
  it("normalises Persian text (ZWNJ, Arabic letters, digits, punctuation)", () => {
    expect(normalize("سریال‌های  مرتبط (۲۴۵۱)")).toBe("سریالهای مرتبط 2451");
    expect(normalize("كيف")).toBe("کیف");
  });

  it("finds a label by its words, tolerating inflections", () => {
    expect(labelPresent("ردیابی محصول و استایل", "ردیابی محصولات و استایل‌ها")).toBe(true);
    expect(labelPresent("جنس و رنگ واقعی", "سریال مشتری")).toBe(false);
  });

  it("computes IoU", () => {
    expect(iou(box, box)).toBeCloseTo(1);
    expect(iou(box, { x: 0.6, y: 0.1, w: 0.5, h: 0.2 })).toBe(0);
    expect(iou(box, { x: 0.35, y: 0.1, w: 0.5, h: 0.2 })).toBeCloseTo(1 / 3);
  });

  it("compares colours as rgb", () => {
    expect(rgb("#01392d")).toBe(rgb("rgb(1, 57, 45)"));
  });

  it("scores a missing region 0 and a later-phase placeholder as present (never mock numbers)", () => {
    const r0 = spec.regions[1];
    const r2 = spec.regions[2];
    if (!r0 || !r2) throw new Error("fixture");
    expect(scoreRegion(r0, { box, items: 4 }, undefined).presence).toBe(0);
    const later = scoreRegion(r2, { box }, built({ text: "نمودار — در دست ساخت" }));
    expect(later.presence).toBe(1);
    const half = scoreRegion(r0, { box, items: 4 }, built({ text: "سریال‌های مرتبط", items: 2 }));
    expect(half.presence).toBeCloseTo((1 + 1 + 0.5) / 3);
  });

  it("combines presence, layout and style with the configured weights and skips regions hidden at the width", () => {
    const page: BuiltPage = {
      width: 1440,
      regions: { "page-header": built({ text: "ردیابی محصولات و استایل‌ها" }), kpis: built({ text: "سریال‌های مرتبط", items: 4 }), chart: built({ text: "در دست ساخت" }) },
      font_family: "Vazirmatn, Tahoma",
      body_bg: "rgb(245, 246, 248)",
      primary_bg: "rgb(1, 57, 45)",
      tokens: { primary: "#01392d", bg: "#f5f6f8" },
      content_pad_px: 20,
      extras: [],
    };
    const w = scoreWidth(spec, 1440, page);
    expect(w.regions).toHaveLength(3); // mobile-only region is not required at 1440
    expect(w.presence).toBe(1);
    expect(w.layout).toBe(1);
    expect(w.style).toBe(1);
    expect(w.score).toBeCloseTo(WEIGHTS.presence + WEIGHTS.layout + WEIGHTS.style);
    const res = pageResult(spec, [w]);
    expect(res.passed).toBe(false); // all four widths are required
    expect(THRESHOLD).toBe(0.95);
  });
});

describe("extra-section penalty (DEC-061 amendment 2026-11-18)", () => {
  // three content regions stacked: header 0.00-0.10, kpis 0.20-0.40, chart 0.50-0.90 (lowest bottom 0.90)
  const stacked: PageSpec = {
    ...spec,
    regions: [
      { id: "page-header", label_fa: "سربرگ", kind: "header", frame: "content", children: [], widths: { "1440": { box: { x: 0, y: 0, w: 1, h: 0.1 } } } },
      { id: "kpis", label_fa: "KPI", kind: "kpis", frame: "content", children: [], widths: { "1440": { box: { x: 0, y: 0.2, w: 1, h: 0.2 } } } },
      { id: "chart", label_fa: "نمودار", kind: "chart", frame: "content", children: [], widths: { "1440": { box: { x: 0, y: 0.5, w: 1, h: 0.4 } } } },
      { id: "topbar", label_fa: "نوار بالا", kind: "topbar", frame: "viewport", children: [], widths: { "1440": { box: { x: 0, y: 0, w: 1, h: 3 } } } },
    ],
  };
  const page = (extras: BuiltPage["extras"], over: Partial<BuiltPage["regions"]> = {}): BuiltPage => ({
    width: 1440,
    regions: {
      "page-header": built({ box: { x: 0, y: 0, w: 1, h: 0.1 } }),
      kpis: built({ box: { x: 0, y: 0.2, w: 1, h: 0.2 } }),
      chart: built({ box: { x: 0, y: 0.5, w: 1, h: 0.4 } }),
      topbar: built({ box: { x: 0, y: 0, w: 1, h: 3 } }), // a viewport region never sets the content bottom
      ...over,
    },
    font_family: "Vazirmatn",
    body_bg: "rgb(245, 246, 248)",
    primary_bg: null,
    tokens: { primary: "#01392d", bg: "#f5f6f8" },
    content_pad_px: 20,
    extras,
  });
  const sec = (label: string, y: number) => ({ label, box: { x: 0, y, w: 1, h: 0.1 } });

  it("charges nothing for sections fully below all mockup regions (top at or under the lowest bottom)", () => {
    const w = scoreWidth(stacked, 1440, page([sec("below", 0.9), sec("far below", 2)]));
    expect(w.extra_above).toBe(0);
    expect(w.layout).toBe(1);
    expect(w.score).toBeCloseTo(1);
  });

  it("charges EXTRA_PENALTY of the total per section above or between mockup regions", () => {
    const w = scoreWidth(stacked, 1440, page([sec("above", 0.05), sec("between", 0.42), sec("overlapping the last", 0.89), sec("below", 0.95)]));
    expect(w.extra_above).toBe(3);
    expect(w.extra_sections).toEqual(["above", "between", "overlapping the last"]);
    expect(w.extra_free).toEqual(["below"]);
    expect(w.layout_in_place).toBe(1);
    expect(w.layout).toBeCloseTo(1 - (3 * EXTRA_PENALTY) / WEIGHTS.layout);
    expect(w.score).toBeCloseTo(1 - 3 * EXTRA_PENALTY);
  });

  it("caps the penalty at the layout weight (layout never below 0)", () => {
    const many = Array.from({ length: 12 }, (_, i) => sec(`s${i}`, 0.01 * i));
    const w = scoreWidth(stacked, 1440, page(many));
    expect(w.extra_above).toBe(12);
    expect(w.layout).toBe(0);
    expect(w.score).toBeCloseTo(WEIGHTS.presence + WEIGHTS.style);
  });

  it("uses the lowest mockup region that is present on the built page at that width", () => {
    // chart missing on the built page: the lowest present region is kpis (bottom 0.40)
    const noChart = page([sec("after kpis", 0.45)], { chart: undefined });
    expect(extraAbove(stacked, 1440, noChart)).toHaveLength(0);
    // chart present but not required at this width (hidden in the mockup): it does not move the bottom either
    const hidden: PageSpec = { ...stacked, regions: stacked.regions.map((r) => (r.id === "chart" ? { ...r, widths: { "1440": null } } : r)) };
    expect(extraAbove(hidden, 1440, page([sec("after kpis", 0.45)]))).toHaveLength(0);
    // with chart present the same section is between mockup regions
    expect(extraAbove(stacked, 1440, page([sec("between", 0.45)]))).toHaveLength(1);
  });

  it("charges nothing when no content region is present (nothing to be above)", () => {
    const none = page([sec("alone", 0)], { "page-header": undefined, kpis: undefined, chart: undefined });
    expect(extraAbove(stacked, 1440, none)).toHaveLength(0);
  });

  it("one offending section alone takes a 100 % page down to exactly the threshold", () => {
    const w = scoreWidth(stacked, 1440, page([sec("above", 0.05)]));
    expect(w.score).toBeCloseTo(1 - EXTRA_PENALTY);
    expect(EXTRA_PENALTY).toBe(0.05);
  });
});
