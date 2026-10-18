import { afterEach, describe, expect, it, vi } from "vitest";

import type { DoneEvent, TraceStep } from "./trace";
import { HOLD_MS, paced, splitCodePoint, uploadsSentence } from "./try";
import { mockSamples, mockStart, mockSubscribe } from "./try-mock";

describe("paced", () => {
  it("shows the next event only after the current one has been on screen HOLD_MS", () => {
    expect(paced(3, 1, 1000, 1000 + HOLD_MS - 1)).toBe(1);
    expect(paced(3, 1, 1000, 1000 + HOLD_MS)).toBe(2);
  });

  it("never runs past what was received", () => {
    expect(paced(2, 2, 0, 10_000)).toBe(2);
  });
});

describe("splitCodePoint", () => {
  it("separates the code point so it can be drawn as a hidden character", () => {
    expect(splitCodePoint("U+200B ZERO WIDTH SPACE ×3")).toEqual(["U+200B", "ZERO WIDTH SPACE ×3"]);
    expect(splitCodePoint("U+E0041")).toEqual(["U+E0041", ""]);
  });

  it("leaves other text alone", () => {
    expect(splitCodePoint("tag characters spelling 'x'")).toEqual([null, "tag characters spelling 'x'"]);
  });
});

describe("the mock stream", () => {
  afterEach(() => vi.useRealTimers());

  it("lists samples of every kind with the contract's fields", () => {
    const r = mockSamples();
    expect(new Set(r.samples.map((s) => s.kind))).toEqual(new Set(["routine", "trap", "attack"]));
    for (const s of r.samples) expect(Object.keys(s).sort()).toEqual(["channel", "hint_es", "id", "kind", "pages", "preview_url", "title_es"]);
    expect(r.upload_limits.max_mb).toBe(4);
  });

  it("sends each step running then final, in order, and ends with done", async () => {
    vi.useFakeTimers();
    const job = await mockStart({ sampleId: "ATK-01-1" });
    const steps: TraceStep[] = [];
    let done: DoneEvent | null = null;
    mockSubscribe(job.events_url, { step: (s) => steps.push(s), done: (d) => (done = d), error: () => {} });
    await vi.runAllTimersAsync();
    const order = ["received", "sanitize", "read", "verify", "rules", "decide", "record"];
    expect(steps.map((s) => s.step)).toEqual(order.flatMap((s) => [s, s]));
    steps.forEach((s, k) => {
      if (k % 2 === 0) expect(s).toMatchObject({ status: "running", data: {}, ms: null });
      else expect(s.status).not.toBe("running");
    });
    expect(steps[1]!.data.invoice_id).toMatch(/^TRY-ATK-01-1-/);
    expect(steps.find((s) => s.step === "sanitize" && s.status !== "running")!.status).toBe("flagged");
    expect(steps.find((s) => s.step === "rules" && s.status !== "running")!.data.results).toHaveLength(16);
    expect(done).toMatchObject({ decision: "ESCALATE", label_es: "Pendiente de aprobación" });
  });
});

describe("uploadsSentence", () => {
  it("follows the live_uploads switch and says nothing until it is known", () => {
    expect(uploadsSentence(false)).toBe("La carga de documentos nuevos está apagada.");
    expect(uploadsSentence(true)).toMatch(/subir una factura ficticia/);
    expect(uploadsSentence(undefined)).toBeNull();
  });
});
