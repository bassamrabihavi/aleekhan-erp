// Display helpers: Persian digits, Jalali calendar in Asia/Tehran (ADR-001 "زمان و زبان").
// Storage/transport stays UTC (RFC 3339); conversion happens only here, at display time.

const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
export const DISPLAY_TIME_ZONE = "Asia/Tehran";

/** Latin and Arabic-Indic digits -> Persian digits. For user-facing numbers, dates and times. */
export function toFaDigits(value: string | number): string {
  return String(value)
    .replace(/[0-9]/g, (d) => FA_DIGITS.charAt(Number(d)))
    .replace(/[٠-٩]/g, (d) => FA_DIGITS.charAt(d.charCodeAt(0) - 0x0660));
}

const jalaliDateTime = new Intl.DateTimeFormat("fa-IR-u-ca-persian-nu-arabext", {
  timeZone: DISPLAY_TIME_ZONE,
  year: "numeric",
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

/** e.g. "۱۲ آبان ۱۴۰۵، ۱۴:۰۵:۰۹" in Asia/Tehran. Invalid input -> "—". */
export function formatJalaliDateTime(value: string | number | Date): string {
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return toFaDigits(jalaliDateTime.format(d));
}

/** Coarse Persian age of a timestamp: "۵ ثانیه پیش", "۳ دقیقه پیش". */
export function formatAge(fromMs: number, nowMs: number): string {
  const seconds = Math.max(0, Math.floor((nowMs - fromMs) / 1000));
  if (seconds < 5) return "همین حالا";
  if (seconds < 60) return `${toFaDigits(seconds)} ثانیه پیش`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${toFaDigits(minutes)} دقیقه پیش`;
  return `${toFaDigits(Math.floor(minutes / 60))} ساعت پیش`;
}
