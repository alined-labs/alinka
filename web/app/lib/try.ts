/*
 * Probar's side of the contract: the samples, starting a run, and the job's event stream.
 * With VITE_FIXTURES=1 or VITE_TRY_MOCK=1 the same calls are answered by a local mock that
 * replays traces built by alinka/trace.py from the recorded runs (api/try-mock.json).
 */

import { errorDetail, FIXTURES } from "~/api/client";
import type { DoneEvent, TraceStep } from "~/lib/trace";

export type SampleKind = "routine" | "trap" | "attack";
export const KIND_ES: Record<SampleKind, string> = { routine: "Rutina", trap: "Trampa", attack: "Ataque" };

export interface Sample {
  id: string;
  title_es: string;
  channel: "pdf" | "image" | "email" | "chat";
  kind: SampleKind;
  hint_es: string;
  pages: number;
  preview_url: string | null;
}

export interface UploadLimits {
  types: string[];
  max_mb: number;
  max_pages: number;
  per_10_min: number;
  per_day: number;
  keep_hours: number;
}

export interface SamplesResponse {
  live_uploads: boolean;
  upload_limits: UploadLimits;
  samples: Sample[];
}

export interface Job {
  job_id: string;
  events_url: string;
}

export type RunInput = { sampleId: string } | { file: File };

export interface StreamHandlers {
  step: (s: TraceStep) => void;
  done: (d: DoneEvent) => void;
  error: (message: string) => void;
}

export const TRY_MOCK = FIXTURES || import.meta.env.VITE_TRY_MOCK === "1";

export class TryError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly retryAfter: number | null = null,
  ) {
    super(message);
  }
}

const mock = () => import("./try-mock");

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => undefined);
  if (res.ok) return body as T;
  const retry = Number(res.headers.get("retry-after"));
  throw new TryError(res.status, errorDetail(body, res.status), Number.isFinite(retry) && retry > 0 ? retry : null);
}

export async function fetchSamples(): Promise<SamplesResponse> {
  if (TRY_MOCK) return (await mock()).mockSamples();
  return json(await fetch("/api/try/samples", { credentials: "same-origin" }));
}

/** Shared by Probar and Cómo funciona, so both read the same live_uploads. */
export const samplesQuery = { queryKey: ["try-samples"], queryFn: fetchSamples, staleTime: 60_000 } as const;

/** The uploads sentence for the limits, or null until the switch is known. */
export function uploadsSentence(liveUploads: boolean | undefined): string | null {
  if (liveUploads === undefined) return null;
  return liveUploads
    ? "En Probar también puedes subir una factura ficticia: esa se lee en vivo."
    : "La carga de documentos nuevos está apagada.";
}

export async function startTry(input: RunInput): Promise<Job> {
  if (TRY_MOCK) return (await mock()).mockStart(input);
  let init: RequestInit;
  if ("file" in input) {
    const form = new FormData();
    form.append("file", input.file);
    init = { method: "POST", body: form };
  } else {
    init = { method: "POST", body: JSON.stringify({ sample_id: input.sampleId }), headers: { "content-type": "application/json" } };
  }
  return json(await fetch("/api/try", { ...init, credentials: "same-origin" }));
}

/** Listens to a job's events; returns the function that stops listening. Closes itself on done or error. */
export function subscribe(eventsUrl: string, h: StreamHandlers): () => void {
  if (TRY_MOCK) {
    let stop = () => {};
    let cancelled = false;
    void mock().then((m) => {
      if (!cancelled) stop = m.mockSubscribe(eventsUrl, h);
    });
    return () => {
      cancelled = true;
      stop();
    };
  }
  const es = new EventSource(eventsUrl, { withCredentials: true });
  const parse = (e: Event) => JSON.parse((e as MessageEvent<string>).data);
  es.addEventListener("step", (e) => h.step(parse(e)));
  es.addEventListener("done", (e) => {
    es.close();
    h.done(parse(e));
  });
  // A server "error" event has data; a dropped connection has none and the browser reconnects.
  es.addEventListener("error", (e) => {
    const data = (e as MessageEvent<string>).data;
    if (!data) return;
    es.close();
    h.error(JSON.parse(data).message_es ?? "La ejecución falló.");
  });
  return () => es.close();
}

/** The page image of a run, as the invoice routes serve it for the visitor's sandbox. */
export function pageUrl(invoiceId: string, n: number): string {
  return `/api/invoices/${encodeURIComponent(invoiceId)}/pages/${n}?view=sandbox`;
}

/** "U+200B ZERO WIDTH SPACE ×3" -> ["U+200B", "ZERO WIDTH SPACE ×3"]; anything else has no code point. */
export function splitCodePoint(text: string): [string | null, string] {
  const m = /^(U\+[0-9A-F]{4,6})\s*(.*)$/.exec(text);
  return m ? [m[1]!, m[2]!] : [null, text];
}

export const HOLD_MS = 500;

/**
 * Paces a stream for reading: each event stays on screen at least HOLD_MS, however fast the
 * server sent the next one. Returns how many of the received events to show at `now`.
 */
export function paced(received: number, shown: number, lastShownAt: number, now: number, hold = HOLD_MS): number {
  return shown < received && now - lastShownAt >= hold ? shown + 1 : shown;
}
