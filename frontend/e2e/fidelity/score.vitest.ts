// Unit tests of the DEC-061 fidelity scorer (pure functions; run by vitest with the app tests).
import { describe, expect, it } from "vitest";

import { EXTRA_PENALTY, FORM_TOL, STRUCTURE, THRESHOLD, WEIGHTS } from "./config";
import { extraAbove, formChecks, iou, labelPresent, normalize, pageResult, rgb, scoreRegion, scoreWidth, type BuiltPage, type BuiltRegion, type FormFeatures, type PageSpec } from "./score";
import { downsample, gaussianBlur, gridFor, normaliseContrast, originScrollLeft, ssim, structureScore, structureSimilarity, type Gray } from "./structure";

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
      structure: { "page-header": 0.9, kpis: 0.6, chart: 0.75 },
    };
    const w = scoreWidth(spec, 1440, page);
    expect(w.regions).toHaveLength(3); // mobile-only region is not required at 1440
    expect(w.presence).toBe(1);
    expect(w.layout).toBe(1);
    expect(w.style).toBe(1);
    expect(w.form_checks).toBe(1); // no region has a form spec: nothing to fail
    expect(w.structure).toBe(1); // every SSIM >= STRUCTURE.full
    expect(w.score).toBeCloseTo(WEIGHTS.presence + WEIGHTS.layout + WEIGHTS.form_checks + WEIGHTS.structure + WEIGHTS.style);
    expect(WEIGHTS.presence + WEIGHTS.layout + WEIGHTS.form_checks + WEIGHTS.structure + WEIGHTS.style).toBeCloseTo(1);
    expect(scoreWidth(spec, 1440, { ...page, structure: {} }).structure).toBe(0); // nothing measured is never a free pass
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
    structure: { "page-header": 1, kpis: 1, chart: 1, topbar: 1 },
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
    expect(w.score).toBeCloseTo(WEIGHTS.presence + WEIGHTS.form_checks + WEIGHTS.structure + WEIGHTS.style);
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

const feats = (over: Partial<FormFeatures> = {}): FormFeatures => ({ circles: 0, dots: 0, pills: 0, bars: 0, buttons: 0, cards: 0, icon_cards: 0, icons: 0, tables: 0, row_controls: 0, big_px: null, image: null, ...over });

describe("form checks (harness tightening 2026-11-18)", () => {
  it("requires every count the mockup has, within the tolerance; dots / pills / bars also have an upper bound", () => {
    const form = { features: { circles: 8, dots: 4, buttons: 5 } };
    const ok = formChecks("chart", form, feats({ circles: 6, dots: 5, buttons: 4 }));
    expect(ok.map((c) => [c.feature, c.ok])).toEqual([["circles", true], ["dots", true], ["buttons", true]]);
    expect(1 - FORM_TOL.count).toBe(0.75);
    const low = formChecks("chart", form, feats({ circles: 5, dots: 4, buttons: 3 }));
    expect(low.filter((c) => !c.ok).map((c) => c.feature)).toEqual(["circles", "buttons"]);
    const many = formChecks("chart", form, feats({ circles: 30, dots: 40, buttons: 30 }));
    expect(many.filter((c) => !c.ok).map((c) => c.feature)).toEqual(["dots"]); // ceil(4 x 1.5) + 2 = 8
  });

  it("only requires per-row forms to exist in data-row regions (demo record counts are never required)", () => {
    expect(formChecks("table", { features: { pills: 7, dots: 7 } }, feats({ pills: 1, dots: 1 })).every((c) => c.ok)).toBe(true);
    expect(formChecks("panel", { features: { cards: 5 }, data_rows: true }, feats({ cards: 1 })).every((c) => c.ok)).toBe(true);
    expect(formChecks("table", { features: { pills: 7 } }, feats({ pills: 0 }))[0]?.ok).toBe(false);
  });

  it("checks the big number, the image slot and table-vs-cards both ways", () => {
    const f = { features: { big_px: 23, image: { w: 0.1, h: 0.1 }, tables: 0 } };
    expect(formChecks("kpis", f, feats({ big_px: 19, image: { w: 0.07, h: 0.06 } })).every((c) => c.ok)).toBe(true);
    const bad = formChecks("kpis", f, feats({ big_px: 14, image: { w: 0.05, h: 0.1 }, tables: 1 }));
    expect(bad.map((c) => [c.feature, c.ok])).toEqual([["big_px", false], ["image", false], ["tables", false]]);
    expect(formChecks("table", { features: { tables: 1 } }, feats({ tables: 0 }))[0]?.ok).toBe(false);
    expect(formChecks("kpis", { features: { big_px: 12 } }, feats())).toHaveLength(0); // small text is not a big number
  });

  it("checks a row of controls for tabs (and wherever a hand spec lists it); a hidden region fails every check", () => {
    expect(formChecks("panel", { features: { row_controls: 4 } }, feats())).toHaveLength(0);
    expect(formChecks("tabs", { features: { row_controls: 4 } }, feats({ row_controls: 3 }))[0]?.ok).toBe(true);
    expect(formChecks("actions", { features: { row_controls: 5 }, hand: true }, feats({ row_controls: 2 }))[0]?.ok).toBe(false);
    expect(formChecks("kpis", { features: { cards: 3, big_px: 18 } }, null).every((c) => !c.ok)).toBe(true);
  });

  it("puts the region form share into the width score with WEIGHTS.form_checks", () => {
    const one: PageSpec = {
      ...spec,
      regions: [{ id: "kpis", label_fa: "KPI", kind: "kpis", frame: "content", children: [], widths: { "1440": { box, form: { features: { cards: 4, big_px: 20 } } } } }],
    };
    const bp = (f: FormFeatures): BuiltPage => ({
      width: 1440,
      regions: { kpis: built({ form: f }) },
      font_family: "Vazirmatn",
      body_bg: "rgb(245, 246, 248)",
      primary_bg: null,
      tokens: { primary: "#01392d", bg: "#f5f6f8" },
      content_pad_px: 20,
      extras: [],
      structure: { kpis: 1 },
    });
    const full = scoreWidth(one, 1440, bp(feats({ cards: 4, big_px: 20 })));
    const half = scoreWidth(one, 1440, bp(feats({ cards: 4, big_px: 10 })));
    expect(full.form_checks).toBe(1);
    expect(half.form_checks).toBe(0.5);
    expect(full.score - half.score).toBeCloseTo(0.5 * WEIGHTS.form_checks);
    expect(half.regions[0]?.form_checks.find((c) => !c.ok)?.feature).toBe("big_px");
  });
});

describe("structure similarity (blurred grayscale SSIM)", () => {
  const W = 64 * STRUCTURE.oversample;
  const H = 32 * STRUCTURE.oversample;
  // a card layout: white page, two gray blocks, a dark bar; "text" = fine stripes inside the blocks
  const layout = (shift: number, text: number, invert = false): Gray => {
    const px: number[] = [];
    for (let y = 0; y < H; y++)
      for (let x = 0; x < W; x++) {
        let v = 1;
        if (y > 20 && y < 60 && x > 10 + shift && x < 120 + shift) v = 0.6;
        if (y > 20 && y < 60 && x > 136 + shift && x < 246) v = 0.6;
        if (y > 80 && y < 96 && x > 10 && x < 200) v = 0.1;
        if (text && y > 24 && y < 56 && y % 4 === 0 && (x * text) % 7 < 3) v -= 0.3;
        px.push(invert ? 1 - v : v);
      }
    return { w: W, h: H, px };
  };
  const blank: Gray = { w: W, h: H, px: new Array<number>(W * H).fill(1) };

  it("is 1 for identical images and low for an inverted or blank one", () => {
    const a = layout(0, 0);
    expect(ssim(a, a)).toBeCloseTo(1, 5);
    expect(structureSimilarity(a, a)).toBeCloseTo(1, 5);
    expect(structureSimilarity(a, layout(0, 0, true))).toBeLessThan(0.2);
    expect(structureSimilarity(a, blank)).toBeLessThan(0.2);
  });

  it("ignores text content and tolerates small shifts, but not a different arrangement", () => {
    const a = layout(0, 0);
    expect(structureSimilarity(a, layout(0, 3))).toBeGreaterThan(STRUCTURE.full);
    expect(structureSimilarity(a, layout(4, 5))).toBeGreaterThan(STRUCTURE.full);
    const other: Gray = { ...a, px: a.px.map((_, i) => (Math.floor(i / W) > 64 ? 0.2 : 1)) };
    expect(structureSimilarity(a, other)).toBeLessThan(STRUCTURE.full);
  });

  it("blurs without changing the mean, area-averages, sizes the grid from the mockup box", () => {
    const g: Gray = { w: 8, h: 8, px: Array.from({ length: 64 }, (_, i) => (i % 3 === 0 ? 1 : 0)) };
    const mean = (x: Gray) => x.px.reduce((p, q) => p + q, 0) / x.px.length;
    expect(mean(gaussianBlur(g, 1.5))).toBeCloseTo(mean(g), 1);
    expect(downsample({ w: 2, h: 2, px: [0, 1, 1, 0] }, 2).px).toEqual([0.5]);
    expect(gridFor({ w: 1000, h: 500 })).toEqual({ w: 64, h: 32 });
    expect(gridFor({ w: 1000, h: 10 }).h).toBe(STRUCTURE.gridMinH);
    expect(gridFor({ w: 100, h: 5000 }).h).toBe(STRUCTURE.gridMaxH);
    expect(normaliseContrast({ w: 2, h: 1, px: [0.4, 0.6] }).px).toEqual([0, 1]);
    expect(structureScore(STRUCTURE.full)).toBe(1);
    expect(structureScore(STRUCTURE.full / 2)).toBeCloseTo(0.5);
    expect(structureScore(-0.3)).toBe(0);
  });
});

describe("screenshot origin of a horizontally overflowing page", () => {
  it("scrolls an overflowing RTL page to its left origin and leaves every other page alone", () => {
    expect(originScrollLeft("rtl", 942, 768)).toBe(-174); // page-4 mockup at 768
    expect(originScrollLeft("rtl", 768, 768)).toBe(0); // no overflow: nothing changes
    expect(originScrollLeft("rtl", 767.6, 768)).toBe(0);
    expect(originScrollLeft("ltr", 942, 768)).toBe(0); // LTR is already captured from its scroll origin
  });
});
