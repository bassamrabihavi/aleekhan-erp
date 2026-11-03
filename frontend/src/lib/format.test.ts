import { formatAge, formatJalaliDateTime, toFaDigits } from "./format";

describe("toFaDigits", () => {
  it("converts Latin and Arabic-Indic digits to Persian", () => {
    expect(toFaDigits("0123456789")).toBe("۰۱۲۳۴۵۶۷۸۹");
    expect(toFaDigits("٠١٢")).toBe("۰۱۲");
    expect(toFaDigits(503)).toBe("۵۰۳");
  });

  it("keeps leading zeros (14-digit codes are strings)", () => {
    expect(toFaDigits("02040400240007")).toBe("۰۲۰۴۰۴۰۰۲۴۰۰۰۷");
  });
});

describe("formatJalaliDateTime", () => {
  it("renders a UTC instant as Jalali date/time in Asia/Tehran (+03:30) with Persian digits", () => {
    const text = formatJalaliDateTime("2026-11-03T10:00:00Z");
    expect(text).toContain("۱۲ آبان ۱۴۰۵");
    expect(text).toContain("۱۳:۳۰:۰۰");
    expect(text).not.toMatch(/[0-9]/);
  });

  it("returns a dash for invalid input", () => {
    expect(formatJalaliDateTime("not a date")).toBe("—");
  });
});

describe("formatAge", () => {
  const t0 = Date.UTC(2026, 10, 3, 10, 0, 0);
  it.each([
    [0, "همین حالا"],
    [12_000, "۱۲ ثانیه پیش"],
    [125_000, "۲ دقیقه پیش"],
    [2 * 3_600_000, "۲ ساعت پیش"],
  ])("age %i ms -> %s", (delta, expected) => {
    expect(formatAge(t0, t0 + delta)).toBe(expected);
  });
});
