import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { cents, pct, readReport, seconds } from "./eval";

const root = join(import.meta.dirname, "../../..");
const sample = JSON.parse(readFileSync(join(root, "alinka/api/fixtures/samples/eval.json"), "utf8"));

describe("readReport", () => {
  it("reads Lane D's fixture report", () => {
    const v = readReport(sample.report);
    expect(v).not.toBeNull();
    expect(v?.k).toBe(0);
    expect(v?.jevOn.length).toBeGreaterThan(0);
  });

  it("reads Lane A's report when it is on main", () => {
    let report: unknown;
    try {
      report = JSON.parse(readFileSync(join(root, "evals/report.json"), "utf8"));
    } catch {
      return; // not written yet
    }
    const v = readReport(report);
    expect(v).not.toBeNull();
    expect(v!.K).toBeGreaterThan(0);
    expect(v!.ceiling).toBeGreaterThanOrEqual(0);
    expect(v!.jevOn.every((p, i, a) => i === 0 || a[i - 1]!.coverage <= p.coverage)).toBe(true);
  });

  it("refuses a report without the headline numbers", () => {
    expect(readReport(null)).toBeNull();
    expect(readReport({ invoices: 3 })).toBeNull();
  });
});

describe("formatting", () => {
  it("writes percentages, cents and seconds in Spanish", () => {
    expect(pct(0.0346)).toBe("3,5%");
    expect(pct(0.72)).toBe("72%");
    expect(cents(0.02348)).toBe("2,3 centavos de dólar");
    expect(seconds(16379)).toBe("16,4 s");
  });
});
