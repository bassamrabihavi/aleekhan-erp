// DEC-061 visual-structure similarity (pure functions; unit tests in score.vitest.ts). A region of the mockup and
// the same region of the built page are cropped from screenshots, reduced to a small grayscale grid (the browser
// does the crop, fidelity.spec.ts), then here: area-averaged, heavily blurred (so text content does not matter,
// only the arrangement of blocks, lines, icons and fills), contrast-normalised (so the approved brand colours, which
// beat the mockup colours, do not matter) and compared with SSIM. Method: README.md "Structure".
import { STRUCTURE } from "./config";

/** A grayscale image: values 0..1, row-major. */
export interface Gray {
  w: number;
  h: number;
  px: number[];
}

/** Area average by an integer factor (the browser crop is drawn at `factor` x the grid size). */
export function downsample(img: Gray, factor: number): Gray {
  const w = Math.floor(img.w / factor);
  const h = Math.floor(img.h / factor);
  const px = new Array<number>(w * h).fill(0);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let s = 0;
      for (let dy = 0; dy < factor; dy++) for (let dx = 0; dx < factor; dx++) s += img.px[(y * factor + dy) * img.w + x * factor + dx] ?? 0;
      px[y * w + x] = s / (factor * factor);
    }
  }
  return { w, h, px };
}

/** Separable Gaussian blur (edges clamped). */
export function gaussianBlur(img: Gray, sigma: number): Gray {
  if (sigma <= 0) return { ...img, px: [...img.px] };
  const r = Math.max(1, Math.ceil(sigma * 3));
  const k: number[] = [];
  for (let i = -r; i <= r; i++) k.push(Math.exp(-(i * i) / (2 * sigma * sigma)));
  const ks = k.reduce((a, b) => a + b, 0);
  const kn = k.map((v) => v / ks);
  const at = (p: number[], x: number, y: number) => p[Math.min(img.h - 1, Math.max(0, y)) * img.w + Math.min(img.w - 1, Math.max(0, x))] ?? 0;
  const tmp = new Array<number>(img.w * img.h).fill(0);
  for (let y = 0; y < img.h; y++)
    for (let x = 0; x < img.w; x++) {
      let s = 0;
      for (let i = -r; i <= r; i++) s += (kn[i + r] ?? 0) * at(img.px, x + i, y);
      tmp[y * img.w + x] = s;
    }
  const out = new Array<number>(img.w * img.h).fill(0);
  for (let y = 0; y < img.h; y++)
    for (let x = 0; x < img.w; x++) {
      let s = 0;
      for (let i = -r; i <= r; i++) s += (kn[i + r] ?? 0) * at(tmp, x, y + i);
      out[y * img.w + x] = s;
    }
  return { w: img.w, h: img.h, px: out };
}

/** Linear stretch to 0..1 (a flat image stays flat at 0). */
export function normaliseContrast(img: Gray): Gray {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of img.px) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  const span = hi - lo;
  return { w: img.w, h: img.h, px: img.px.map((v) => (span > 1e-6 ? (v - lo) / span : 0)) };
}

/** Mean SSIM over all `win` x `win` windows (stride 1), constants for a 0..1 range. Same-size images only. */
export function ssim(a: Gray, b: Gray, win = 7): number {
  if (a.w !== b.w || a.h !== b.h) throw new Error(`ssim: size ${a.w}x${a.h} vs ${b.w}x${b.h}`);
  const C1 = 0.01 ** 2;
  const C2 = 0.03 ** 2;
  const ww = Math.min(win, a.w);
  const wh = Math.min(win, a.h);
  let total = 0;
  let n = 0;
  for (let y = 0; y + wh <= a.h; y++) {
    for (let x = 0; x + ww <= a.w; x++) {
      let sa = 0;
      let sb = 0;
      let saa = 0;
      let sbb = 0;
      let sab = 0;
      for (let dy = 0; dy < wh; dy++)
        for (let dx = 0; dx < ww; dx++) {
          const i = (y + dy) * a.w + x + dx;
          const va = a.px[i] ?? 0;
          const vb = b.px[i] ?? 0;
          sa += va;
          sb += vb;
          saa += va * va;
          sbb += vb * vb;
          sab += va * vb;
        }
      const m = ww * wh;
      const ma = sa / m;
      const mb = sb / m;
      const va = Math.max(0, saa / m - ma * ma);
      const vb = Math.max(0, sbb / m - mb * mb);
      const cov = sab / m - ma * mb;
      total += ((2 * ma * mb + C1) * (2 * cov + C2)) / ((ma * ma + mb * mb + C1) * (va + vb + C2));
      n++;
    }
  }
  return n ? total / n : 0;
}

/** The structure similarity of two region crops (same grid; each drawn at STRUCTURE.oversample x the grid). */
export function structureSimilarity(mockup: Gray, built: Gray): number {
  const prep = (g: Gray) => normaliseContrast(gaussianBlur(downsample(g, STRUCTURE.oversample), STRUCTURE.blurSigma));
  return ssim(prep(mockup), prep(built), STRUCTURE.window);
}

/** Grid size (width x height, before oversampling) of a region crop: the mockup box's aspect at a fixed width. */
export function gridFor(box: { w: number; h: number }): { w: number; h: number } {
  const w = STRUCTURE.gridW;
  const h = Math.min(STRUCTURE.gridMaxH, Math.max(STRUCTURE.gridMinH, Math.round((w * box.h) / Math.max(1e-6, box.w))));
  return { w, h };
}

/**
 * Horizontal scroll position at which a viewport screenshot and getBoundingClientRect() share one origin. Chromium
 * captures a horizontally overflowing page from the document's left origin; in RTL the initial scroll position is
 * the right edge (scrollX 0), so the capture is offset by scrollWidth - clientWidth against the rectangles (page 4
 * mockup at 768: 942 - 768 = 174 px). Scrolling to the left origin (scrollX = -(overflow) in RTL) aligns both;
 * fixed elements (side menu) keep their viewport position and stay in the capture. No overflow / LTR: 0.
 */
export function originScrollLeft(direction: string, scrollWidth: number, clientWidth: number): number {
  const overflow = Math.max(0, Math.round(scrollWidth - clientWidth));
  return direction === "rtl" && overflow > 0 ? -overflow : 0;
}

/** Region structure score: SSIM at or above STRUCTURE.full counts as 1, below that linearly (negative = 0). */
export function structureScore(s: number): number {
  return Math.min(1, Math.max(0, s) / STRUCTURE.full);
}
