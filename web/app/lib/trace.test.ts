import { describe, expect, it } from "vitest";

import { DEMO_TRACE, flowFromSteps, STAGES, stageSummary } from "./trace";

describe("flowFromSteps", () => {
  it("starts with every stage idle", () => {
    const flow = flowFromSteps([]);
    expect(Object.values(flow.states).every((s) => s === "idle")).toBe(true);
    expect(flow.current).toBeNull();
  });

  it("marks a step running, then its final status", () => {
    const [running, final] = DEMO_TRACE;
    expect(flowFromSteps([running!]).states.received).toBe("running");
    expect(flowFromSteps([running!, final!]).states.received).toBe("done");
  });

  it("opens the trust boundary when verify finishes, never before", () => {
    const upToVerifyRunning = DEMO_TRACE.slice(0, 7);
    expect(upToVerifyRunning.at(-1)).toMatchObject({ step: "verify", status: "running" });
    expect(flowFromSteps(upToVerifyRunning).states.boundary).toBe("idle");
    const afterVerify = flowFromSteps(DEMO_TRACE.slice(0, 8));
    expect(afterVerify.states.boundary).toBe("done");
    expect(afterVerify.current).toBe("boundary");
  });

  it("reads the rules, the decision and the new link from the final events", () => {
    const flow = flowFromSteps(DEMO_TRACE);
    expect(flow.rules).toHaveLength(16);
    expect(flow.rules.filter((r) => r.outcome !== "pass").map((r) => r.rule)).toEqual(["R11"]);
    expect(flow.decision).toBe("ESCALATE");
    expect(flow.record).toEqual({ seq: 31, hash8: "9c2e41ab", prev_hash8: "d2d59a87" });
    expect(flow.states.sanitize).toBe("flagged");
    expect(flow.current).toBe("record");
  });

  it("shows nothing for rules still running", () => {
    const flow = flowFromSteps(DEMO_TRACE.slice(0, 9));
    expect(flow.states.rules).toBe("running");
    expect(flow.rules).toEqual([]);
  });
});

describe("DEMO_TRACE", () => {
  it("sends each of the seven steps twice, in the contract's order", () => {
    const order = ["received", "sanitize", "read", "verify", "rules", "decide", "record"];
    expect(DEMO_TRACE.map((e) => e.step)).toEqual(order.flatMap((s) => [s, s]));
    DEMO_TRACE.forEach((e, k) => {
      if (k % 2 === 0) expect(e).toMatchObject({ status: "running", data: {}, ms: null });
      else expect(e.status).not.toBe("running");
    });
  });

  it("has a sentence for every stage once finished", () => {
    const flow = flowFromSteps(DEMO_TRACE);
    for (const s of STAGES) expect(stageSummary(flow, s.id)).not.toBe("");
  });
});
