import { describe, expect, it } from "vitest";

import type { TraceStep } from "./trace";
import { formatMs, hasData, sortSteps, STEP_ORDER } from "./trace-data";

describe("trace data", () => {
  const steps = STEP_ORDER.map(
    (step) => ({ step, status: "done", title_es: step, summary_es: "", ms: null, data: { x: 1 } }) as TraceStep,
  );

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
