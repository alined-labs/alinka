// alinka-edge: the front end on alinka.alinedlabs.co, and the frozen API behind /api/*. Files and
// prerendered pages come straight from the assets layer; this code runs first for /api/* and
// otherwise only for paths that match no file. The Azure API was retired on 22 Oct 2026, so /api/*
// is answered from the responses recorded before it went (web/public/snapshot/, which the same
// assets serve at /snapshot/): the routing is in frozen.ts, the reading and streaming here.

import { type Answer, gaps, type Manifest, patched, type Recording, readState, route, sseFrame, stateCookie, type StreamEvent } from "./frozen.ts";
import { contentRange, parseRange } from "./ranges.ts";

interface Env {
  ASSETS: { fetch(request: Request): Promise<Response> };
}

// React Router writes __spa-fallback.html when "/" is prerendered, else index.html is the shell.
const FALLBACKS = ["/__spa-fallback", "/"];
const SNAPSHOT = "/snapshot/";
const NOT_RECORDED_ES = "Esta respuesta no quedó grabada en la demo congelada.";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      return api(request, url, env);
    }
    if (url.pathname.startsWith("/media/")) {
      return media(request, env);
    }
    return page(request, url, env);
  },
};

// The manifest, read once per isolate: the snapshot only changes with a deploy.
let manifest: Promise<Manifest> | undefined;

function snapshotFile(env: Env, url: URL, file: string): Promise<Response> {
  return env.ASSETS.fetch(new Request(new URL(SNAPSHOT + file, url)));
}

async function loadManifest(env: Env, url: URL): Promise<Manifest> {
  manifest ??= snapshotFile(env, url, "manifest.json").then((res) => {
    if (!res.ok) throw new Error(`manifest.json: HTTP ${res.status}`);
    return res.json() as Promise<Manifest>;
  });
  try {
    return await manifest;
  } catch (err) {
    manifest = undefined; // a failed read is retried by the next request, not kept for the isolate
    throw err;
  }
}

/** /api/*: the recorded answer for this request in the visitor's sandbox state, which it may move. */
async function api(request: Request, url: URL, env: Env): Promise<Response> {
  let m: Manifest;
  try {
    m = await loadManifest(env, url);
  } catch {
    return Response.json({ detail: "La demo no encontró sus respuestas grabadas." }, { status: 503 });
  }
  const contentType = request.headers.get("content-type") ?? "";
  // The one body the frozen API reads: which Probar sample to replay. An upload is never read.
  const readsBody = request.method === "POST" && url.pathname === "/api/try" && !contentType.startsWith("multipart/form-data");
  const answer = route(
    {
      method: request.method,
      url,
      contentType,
      body: readsBody ? await request.text() : "",
      state: readState(request.headers.get("cookie")),
      nonce: crypto.randomUUID().slice(0, 8),
    },
    m,
  );
  const response = await respond(answer, env, url, request.method === "HEAD");
  // Only page images carry a recorded cache policy. Anything else is never kept: a sandbox's
  // answers change with its state, and a kept CSV would outlive "Ejecutar agente".
  if (!response.headers.has("cache-control")) response.headers.set("cache-control", "no-store");
  if (answer.next) response.headers.append("set-cookie", stateCookie(answer.next));
  // Tells anyone looking that this answer is a recording, and when it was made.
  response.headers.set("x-alinka-snapshot", m.recorded_at);
  return response;
}

/** Turns a routing answer into a response, reading recorded files through the assets binding. */
async function respond(answer: Answer, env: Env, url: URL, head: boolean): Promise<Response> {
  if (answer.kind === "json") {
    const headers = new Headers(answer.headers);
    headers.set("content-type", "application/json");
    return new Response(head ? null : JSON.stringify(answer.body), { status: answer.status, headers });
  }
  const file = await snapshotFile(env, url, answer.kind === "file" ? answer.entry.file : answer.file);
  if (!file.ok) return Response.json({ detail: NOT_RECORDED_ES }, { status: 404 });
  if (answer.kind === "file") {
    // The recorded headers only: the asset's own (its ETag and cache policy) describe the file.
    const headers = new Headers(answer.entry.headers);
    headers.set("content-type", answer.entry.content_type);
    const body = answer.patch ? patched(await file.text(), answer.patch) : file.body;
    return new Response(head ? null : body, { status: answer.entry.status, headers });
  }
  const recording = (await file.json()) as Recording;
  const headers = new Headers({ "content-type": recording.content_type || "text/event-stream; charset=utf-8" });
  // As the API's stream was sent: never cached, and no proxy may buffer or compress it.
  headers.set("cache-control", "no-cache, no-transform");
  return new Response(head ? null : replay(recording.events), { status: recording.status, headers });
}

/**
 * A recorded Probar stream, written again with the delays it was recorded with, so the steps
 * reach the page as they came from the live pipeline. It ends after the last event, as the API's
 * did after "done"; the page closes its EventSource on done, so it does not reconnect.
 */
function replay(events: StreamEvent[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const waits = gaps(events);
  let next = 0;
  let cancelled = false;
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      const event = events[next];
      if (!event) {
        controller.close();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, waits[next] ?? 0));
      next++;
      if (!cancelled) controller.enqueue(encoder.encode(sseFrame(event)));
    },
    cancel() {
      cancelled = true; // the visitor left: nothing more to write
    },
  });
}

/**
 * /media/*: the file from the assets layer, plus the byte ranges that layer does not serve. A
 * request without a Range header streams the whole file as it comes; one with a single byte range
 * gets that slice with 206 (Safari asks for bytes=0-1 before it plays an MP4 and needs that 206),
 * and a range past the end gets 416. A 304 or a 404 from the assets layer passes through.
 */
async function media(request: Request, env: Env): Promise<Response> {
  const file = await env.ASSETS.fetch(request);
  const range = request.headers.get("range");
  if (!file.ok || !range) {
    const whole = new Response(file.body, file);
    if (file.ok) whole.headers.set("accept-ranges", "bytes");
    return whole;
  }
  const bytes = await file.arrayBuffer();
  const span = parseRange(range, bytes.byteLength);
  const headers = new Headers(file.headers);
  headers.set("accept-ranges", "bytes");
  if (span === null) {
    return new Response(request.method === "HEAD" ? null : bytes, { status: 200, headers });
  }
  if (span === "unsatisfiable") {
    headers.set("content-range", contentRange(null, bytes.byteLength));
    headers.delete("content-length");
    return new Response(null, { status: 416, headers });
  }
  headers.set("content-range", contentRange(span, bytes.byteLength));
  headers.set("content-length", String(span.end - span.start + 1));
  const body = request.method === "HEAD" ? null : bytes.slice(span.start, span.end + 1);
  return new Response(body, { status: 206, headers });
}

// No file matched. A route of the app (no extension) gets the SPA fallback, which hydrates any
// path; prerendered pages never reach here. Anything else is a missing file.
async function page(request: Request, url: URL, env: Env): Promise<Response> {
  const read = request.method === "GET" || request.method === "HEAD";
  const last = url.pathname.split("/").pop() ?? "";
  if (read && !last.includes(".")) {
    for (const path of FALLBACKS) {
      const html = await env.ASSETS.fetch(new Request(new URL(path, url), request));
      if (html.ok || html.status === 304) return html;
    }
  }
  return new Response("No encontrado.", { status: 404 });
}
