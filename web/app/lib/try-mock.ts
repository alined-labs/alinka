/*
 * The local mock of /api/try (contract shapes, real traces from alinka/trace.py's build_trace on
 * the recorded runs). Loaded only in fixture or mock mode. Regenerate try-mock.json from the
 * recorded runs if the trace builders change.
 */

import data from "~/api/try-mock.json";
import type { DoneEvent, TraceStep } from "~/lib/trace";

import { type Job, type RunInput, type Sample, type SamplesResponse, type StreamHandlers, TryError } from "./try";

const traces = data.traces as unknown as Record<string, TraceStep[]>;
const samples = data.samples as Sample[];
const jobs = new Map<string, { sample: Sample; mode: "replay" | "live"; invoiceId: string; filename?: string }>();
let n = 0;

/** Roughly how long each step takes on the server, so the mock feels like a run. */
const DURATION: Record<TraceStep["step"], number> = {
  received: 120,
  sanitize: 300,
  read: 2400,
  verify: 1600,
  rules: 60,
  decide: 20,
  record: 40,
};

export function mockSamples(): SamplesResponse {
  return {
    live_uploads: true,
    upload_limits: { types: ["pdf", "png", "jpg"], max_mb: 4, max_pages: 3, per_10_min: 5, per_day: 30, keep_hours: 24 },
    samples: structuredClone(samples),
  };
}

export async function mockStart(input: RunInput): Promise<Job> {
  const job_id = `mock-${++n}`;
  if ("file" in input) {
    // An upload replays the routine sample as a live reading.
    jobs.set(job_id, { sample: samples[0]!, mode: "live", invoiceId: `UPL-${String(n).padStart(8, "0")}`, filename: input.file.name });
  } else {
    const sample = samples.find((s) => s.id === input.sampleId);
    if (!sample) throw new TryError(404, "No existe esa muestra.");
    jobs.set(job_id, { sample, mode: "replay", invoiceId: `TRY-${sample.id}-${n}` });
  }
  return { job_id, events_url: `/api/try/${job_id}/events` };
}

export function mockSubscribe(eventsUrl: string, h: StreamHandlers): () => void {
  const job = jobs.get(eventsUrl.split("/").at(-2) ?? "");
  if (!job) {
    const t = setTimeout(() => h.error("Esta ejecución ya no existe."), 50);
    return () => clearTimeout(t);
  }
  const timers: ReturnType<typeof setTimeout>[] = [];
  let at = 0;
  for (const final of traces[job.sample.id]!) {
    const data = structuredClone(final.data);
    if (final.step === "received") {
      data.invoice_id = job.invoiceId;
      if (job.filename) data.filename = job.filename;
    }
    if (final.step === "read") data.mode = job.mode;
    const ms = DURATION[final.step];
    const running: TraceStep = { ...final, status: "running", ms: null, data: {} };
    timers.push(setTimeout(() => h.step(running), at));
    at += ms;
    timers.push(setTimeout(() => h.step({ ...final, ms, data }), at));
  }
  const decide = traces[job.sample.id]!.find((s) => s.step === "decide")!.data;
  const done: DoneEvent = {
    invoice_id: job.invoiceId,
    decision: decide.decision,
    label_es: decide.label_es,
    href: `/facturas/${job.invoiceId}`,
  };
  timers.push(setTimeout(() => h.done(done), at + 20));
  return () => timers.forEach(clearTimeout);
}
