import { describe, expect, it } from "vitest";

import { invoiceTransitionName } from "./motion";

describe("invoiceTransitionName", () => {
  it("keeps plain ids readable", () => {
    expect(invoiceTransitionName("OCT-14")).toBe("inv-OCT-14");
  });

  it("never gives two different ids the same name", () => {
    const ids = ["ATK 10.1", "ATK_10_1", "ATK-10-1", "ATK.10.1", "Ñ/1", "N/1"];
    const names = ids.map(invoiceTransitionName);
    expect(new Set(names).size).toBe(ids.length);
    for (const n of names) expect(n).toMatch(/^inv-[A-Za-z0-9_-]+$/);
  });
});
