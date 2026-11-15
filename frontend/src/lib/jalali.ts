// Jalali <-> Gregorian calendar dates (jalaali algorithm, Borkowski; same results as the backend
// product_identity/jalali.py). Calendar DATES only (no time zone): the API sends ISO dates (YYYY-MM-DD), the UI
// shows and accepts Jalali dates. "Today" is taken in Asia/Tehran.
import { DISPLAY_TIME_ZONE, toFaDigits } from "./format";

const BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];
const div = (a: number, b: number): number => Math.trunc(a / b);
const mod = (a: number, b: number): number => a - Math.trunc(a / b) * b;

function jalCal(jy: number): { leap: number; gy: number; march: number } {
  const gy = jy + 621;
  let leapJ = -14;
  let jp = BREAKS[0] ?? -61;
  let jump = 0;
  if (jy < jp || jy >= (BREAKS[BREAKS.length - 1] ?? 3178)) throw new RangeError("jalali year out of range");
  for (let i = 1; i < BREAKS.length; i += 1) {
    const jm = BREAKS[i] ?? 0;
    jump = jm - jp;
    if (jy < jm) break;
    leapJ = leapJ + div(jump, 33) * 8 + div(mod(jump, 33), 4);
    jp = jm;
  }
  let n = jy - jp;
  leapJ = leapJ + div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
  if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;
  const leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
  const march = 20 + leapJ - leapG;
  if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
  let leap = mod(mod(n + 1, 33) - 1, 4);
  if (leap === -1) leap = 4;
  return { leap, gy, march };
}

function g2d(gy: number, gm: number, gd: number): number {
  let d = div((gy + div(gm - 8, 6) + 100100) * 1461, 4) + div(153 * mod(gm + 9, 12) + 2, 5) + gd - 34840408;
  d = d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
  return d;
}

function d2g(jdn: number): [number, number, number] {
  let j = 4 * jdn + 139361631;
  j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
  const i = div(mod(j, 1461), 4) * 5 + 308;
  const gd = div(mod(i, 153), 5) + 1;
  const gm = mod(div(i, 153), 12) + 1;
  const gy = div(j, 1461) - 100100 + div(8 - gm, 6);
  return [gy, gm, gd];
}

export function toJalali(gy: number, gm: number, gd: number): [number, number, number] {
  const jdn = g2d(gy, gm, gd);
  const gyy = d2g(jdn)[0];
  let jy = gyy - 621;
  const r = jalCal(jy);
  const jdn1f = g2d(gyy, 3, r.march);
  let k = jdn - jdn1f;
  if (k >= 0) {
    if (k <= 185) return [jy, 1 + div(k, 31), mod(k, 31) + 1];
    k -= 186;
  } else {
    jy -= 1;
    k += 179;
    if (r.leap === 1) k += 1;
  }
  return [jy, 7 + div(k, 30), mod(k, 30) + 1];
}

export function toGregorian(jy: number, jm: number, jd: number): [number, number, number] {
  const r = jalCal(jy);
  const jdn = g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
  return d2g(jdn);
}

export function isLeapJalali(jy: number): boolean {
  return jalCal(jy).leap === 0;
}

export function jalaliMonthLength(jy: number, jm: number): number {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  return isLeapJalali(jy) ? 30 : 29;
}

export const JALALI_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];

const pad = (n: number, w = 2): string => String(n).padStart(w, "0");
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** "2026-12-09" -> [1405, 9, 18]; null for anything that is not an ISO calendar date. */
export function isoToJalali(iso: string): [number, number, number] | null {
  const m = ISO_DATE.exec(iso);
  if (!m) return null;
  return toJalali(Number(m[1]), Number(m[2]), Number(m[3]));
}

/** ISO date -> "۱۸ آذر ۱۴۰۵" (Persian digits). Null / invalid -> "—". */
export function formatJalaliDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const j = isoToJalali(iso);
  if (!j) return "—";
  return `${toFaDigits(j[2])} ${JALALI_MONTHS[j[1] - 1] ?? ""} ${toFaDigits(j[0])}`;
}

/** ISO date -> "1405/09/18" (Latin digits, the editable form of the date input). */
export function isoToJalaliInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const j = isoToJalali(iso);
  return j ? `${String(j[0])}/${pad(j[1])}/${pad(j[2])}` : "";
}

/** Persian / Arabic-Indic digits -> Latin (input normalisation only; codes are never converted). */
export function toLatinDigits(s: string): string {
  return s
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));
}

/** "1405/09/18" (Latin or Persian digits, "/" or "-") -> "2026-12-09"; null when it is not a real Jalali date. */
export function jalaliInputToIso(text: string): string | null {
  const m = /^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$/.exec(toLatinDigits(text));
  if (!m) return null;
  const jy = Number(m[1]);
  const jm = Number(m[2]);
  const jd = Number(m[3]);
  if (jy < 1300 || jy > 1500 || jm < 1 || jm > 12 || jd < 1 || jd > jalaliMonthLength(jy, jm)) return null;
  const [gy, gm, gd] = toGregorian(jy, jm, jd);
  return `${String(gy)}-${pad(gm)}-${pad(gd)}`;
}

/** Today's calendar date in Asia/Tehran as ISO (YYYY-MM-DD). */
export function todayTehranIso(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: DISPLAY_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}
