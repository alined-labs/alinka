import { describe, expect, it } from "vitest";

import { formatMoney, formatUsd } from "./format";

describe("formatMoney", () => {
  it("places the ISO 4217 decimal point", () => {
    expect(formatMoney(310000000, "COP")).toBe("COP 3.100.000,00");
    expect(formatUsd(118000)).toBe("USD 1.180,00");
    expect(formatMoney(1250000, "BRL")).toBe("BRL 12.500,00");
    expect(formatMoney(5, "USD")).toBe("USD 0,05");
    expect(formatMoney(1500, "CLP")).toBe("CLP 1.500");
    expect(formatMoney(-12345, "MXN")).toBe("-MXN 123,45");
  });

  it("shows a dash when the amount is unknown", () => {
    expect(formatMoney(null, "USD")).toBe("—");
    expect(formatMoney(100, null)).toBe("—");
  });
});
