import { formatJalaliDate, isoToJalaliInput, jalaliInputToIso, toGregorian, toJalali, todayTehranIso } from "./jalali";

describe("jalali calendar", () => {
  it.each([
    [[2026, 3, 21], [1405, 1, 1]], // Nowruz 1405 (backend jalali.py boundary)
    [[2026, 3, 20], [1404, 12, 29]],
    [[2026, 11, 3], [1405, 8, 12]],
    [[2025, 3, 20], [1403, 12, 30]], // 1403 is a leap year
    [[2026, 12, 9], [1405, 9, 18]],
  ])("%j <-> %j", (g, j) => {
    expect(toJalali(g[0] ?? 0, g[1] ?? 0, g[2] ?? 0)).toEqual(j);
    expect(toGregorian(j[0] ?? 0, j[1] ?? 0, j[2] ?? 0)).toEqual(g);
  });

  it("parses Latin and Persian digit input to ISO and refuses impossible dates", () => {
    expect(jalaliInputToIso("1405/09/18")).toBe("2026-12-09");
    expect(jalaliInputToIso("۱۴۰۵/۰۹/۱۸")).toBe("2026-12-09");
    expect(jalaliInputToIso("1405-1-1")).toBe("2026-03-21");
    expect(jalaliInputToIso("1405/07/31")).toBeNull(); // month 7 has 30 days
    expect(jalaliInputToIso("1404/12/30")).toBeNull(); // 1404 is not a leap year
    expect(jalaliInputToIso("2026-12-09")).toBeNull();
    expect(jalaliInputToIso("abc")).toBeNull();
  });

  it("formats ISO dates as Jalali with Persian digits and back to the input form", () => {
    expect(formatJalaliDate("2026-12-09")).toBe("۱۸ آذر ۱۴۰۵");
    expect(formatJalaliDate(null)).toBe("—");
    expect(isoToJalaliInput("2026-03-21")).toBe("1405/01/01");
  });

  it("today is taken in Asia/Tehran (+03:30)", () => {
    expect(todayTehranIso(new Date("2026-03-20T20:31:00Z"))).toBe("2026-03-21");
    expect(todayTehranIso(new Date("2026-03-20T20:29:00Z"))).toBe("2026-03-20");
  });
});
