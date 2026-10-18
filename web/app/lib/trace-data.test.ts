import { describe, expect, it } from "vitest";

import sample from "~/api/fixtures/trace.sample.json";

import type { TraceStep } from "./trace";
import { formatMs, hasData, sortSteps, STEP_ORDER } from "./trace-data";

// The data keys per step, as the "Probar contract" decision lists them.
const KEYS: Record<string, string[]> = {
  received: ["invoice_id", "channel", "pages", "sha8", "filename", "language"],
  sanitize: ["hidden_content", "unicode_controls", "html_text_mismatch", "instructions"],
  read: ["mode", "calls", "fields", "stamps", "instructions_seen", "error"],
  verify: ["calls", "fields", "ungrounded", "disagreements", "amount_in_regex", "totals_reconcile", "jev", "risk", "risk_max"],
  rules: ["results"],
  decide: ["decision", "label_es", "determining_rule", "alerts", "reason_es", "payment"],
  record: ["record_id", "seq", "hash8", "prev_hash8"],
};

describe("trace data", () => {
  const steps = sample as unknown as TraceStep[];

  it("the sample follows the contract: seven steps in order with exactly their keys", () => {
    expect(steps.map((s) => s.step)).toEqual(STEP_ORDER);
    for (const s of steps) expect(Object.keys(s.data).sort(), s.step).toEqual([...KEYS[s.step]!].sort());
    const rules = steps.find((s) => s.step === "rules")!;
    expect(hasData(rules) && (rules.data as { results: unknown[] }).results).toHaveLength(16);
  });

  it("puts steps in contract order and treats a running step as empty", () => {
    expect(sortSteps([...steps].reverse()).map((s) => s.step)).toEqual(STEP_ORDER);
    expect(hasData({ ...steps[0]!, status: "running", data: {} } as TraceStep)).toBe(false);
  });

  it("formats durations in Spanish", () => {
    expect(formatMs(null)).toBeNull();
    expect(formatMs(640)).toBe("640 ms");
    expect(formatMs(6686)).toBe("6,7 s");
  });
});
