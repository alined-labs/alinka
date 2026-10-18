import { describe, expect, it } from "vitest";

import { amountParts, formatDay, formatMoney, formatUsd, parseMajor } from "./format";

describe("formatMoney", () => {
  it("places the ISO 4217 decimal point", () => {
    expect(formatMoney(310000000, "COP")).toBe("3.100.000,00 COP");
    expect(formatUsd(118000)).toBe("1.180,00 USD");
    expect(formatMoney(1250000, "BRL")).toBe("12.500,00 BRL");
    expect(formatMoney(5, "USD")).toBe("0,05 USD");
    expect(formatMoney(1500, "CLP")).toBe("1.500 CLP");
    expect(formatMoney(-12345, "MXN")).toBe("-123,45 MXN");
  });

  it("shows a dash when the amount is unknown", () => {
    expect(formatMoney(null, "USD")).toBe("—");
    expect(formatMoney(100, null)).toBe("—");
  });
});

describe("amountParts and formatDay", () => {
  it("splits the number from its currency", () => {
    expect(amountParts(120000, "USD")).toEqual({ number: "1.200,00", currency: "USD" });
    expect(amountParts(undefined, "USD")).toBeNull();
  });

  it("formats a received date as a short Spanish day", () => {
    expect(formatDay("2026-10-03T09:30:00Z")).toMatch(/^3 oct\.? 2026$/);
  });
});

describe("parseMajor", () => {
  it("reads Spanish and English decimal marks into minor units", () => {
    expect(parseMajor("5.200.000,50", "COP")).toBe(520000050);
    expect(parseMajor("5200000.50", "COP")).toBe(520000050);
    expect(parseMajor("2.400.000", "COP")).toBe(240000000);
    expect(parseMajor("1,200", "USD")).toBe(120000);
    expect(parseMajor("780", "USD")).toBe(78000);
    expect(parseMajor("1500", "CLP")).toBe(1500);
  });

  it("refuses text that is not an amount", () => {
    expect(parseMajor("", "USD")).toBeNull();
    expect(parseMajor("abc", "USD")).toBeNull();
    expect(parseMajor("-5", "USD")).toBeNull();
  });
});
