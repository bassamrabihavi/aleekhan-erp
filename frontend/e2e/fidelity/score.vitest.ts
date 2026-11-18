// Unit tests of the DEC-061 fidelity scorer (pure functions; run by vitest with the app tests).
import { describe, expect, it } from "vitest";

import { THRESHOLD, WEIGHTS } from "./config";
import { iou, labelPresent, normalize, pageResult, rgb, scoreRegion, scoreWidth, type BuiltPage, type BuiltRegion, type PageSpec } from "./score";

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
