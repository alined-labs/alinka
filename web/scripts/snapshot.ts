/*
 * Record the live Alinka API into web/public/snapshot/, the files the frozen API answers from.
 *   pnpm --filter ./web run snapshot             # or: node web/scripts/snapshot.ts
 *   node web/scripts/snapshot.ts --origin URL --out DIR
 *
 * Why: the Worker (edge/src/frozen.ts) answers every /api/* call the web app makes from these
 * files, so the site runs on Cloudflare alone, with no API server or database. Whatever is not
 * recorded here cannot be answered, so the script walks every state a visitor can reach:
 *   - the canonical run: board, each invoice (detail, trace, page images), rules, log, eval;
 *   - one fresh visitor sandbox before "Ejecutar agente" (inbox), the run itself, the sandbox
 *     after it (decided), a second run with nothing left to decide, and "Restablecer sandbox";
 *   - each Probar sample in a fresh sandbox (the duplicate trap after the invoice it repeats):
 *     its event stream with the delay of every event, then what the page asks for next (the new
 *     invoice's detail, trace and page images);
 *   - each approvable escalation approved, and rejected, each in a sandbox of its own. These
 *     are recorded only: the frozen API refuses approvals until the owner decides otherwise.
 *
 * It talks to the public site through the Worker, as a browser would: no secrets, and the
 * alinka_sandbox cookie kept by hand, since Node's fetch keeps none. Probar runs go one at a time
 * (the API allows one per visitor and 60 samples per hour per IP). It never uploads a file and
 * never sends PUT.
 *
 * Output: manifest.json maps a request key to {file, status, content_type, headers}. A key is the
 * method, path and view as the web app sends them, prefixed by the sandbox state when the answer
 * depends on it: "GET /api/board?view=canonical", "inbox GET /api/board?view=sandbox". Page
 * images are the same in every view, so their keys carry only the scale. Bodies are kept byte for
 * byte as received, and identical bodies are stored once (by SHA-256). The run writes into
 * <out>.partial and replaces <out> only when it finished, so a failed run keeps the last snapshot.
 */

import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const { values: opts } = parseArgs({ options: { origin: { type: "string" }, out: { type: "string" } } });
const ORIGIN = (opts.origin ?? "https://alinka.alinedlabs.co").replace(/\/+$/, "");
const OUT = resolve(opts.out ?? fileURLToPath(new URL("../public/snapshot", import.meta.url)));
const WORK = `${OUT}.partial`;

const UA = "alinka-snapshot/1 (web/scripts/snapshot.ts)";
const APPROVER = "Demo"; // a neutral name for the recorded approvals and rejections
const SCALES = [1, 2, 3] as const;
// Above this, page images at scale 3 are dropped and the Worker serves scale 2 in their place.
const PAGE_BUDGET = 30 * 1024 * 1024;
// The duplicate trap only fires after the invoice it repeats, and its hint says to run it after
// that one: the replayed stream is the one recorded in that order. The fresh run is kept too.
const DUP_SAMPLE = "DUP-GEN-084-1";
const DUP_AFTER = "GEN-084-1";
// A Probar job lives in the memory of the API process that started it, so its events 404 when
// the request reaches another one (INFERENCE: more than one replica, no affinity). The job keeps
// every event for 10 minutes for late subscribers, so the stream is asked for again, and only
// if that keeps failing does the run start over in a fresh sandbox.
const LISTEN_TRIES = 8;
const TRIES = 3;

type Entry = { file: string; status: number; content_type: string; headers?: Record<string, string> };
type Reply = { status: number; type: string; headers: Headers; body: Uint8Array };
type StreamEvent = { event: string; data: string; delay_ms: number; id?: string };
type Stream = { status: number; type: string; events: StreamEvent[]; asks?: number };
type Card = { invoice_id: string; state: string; approvable: boolean; approver: string | null };
type Board = { head_hash: string | null; inbox: Card[]; columns: { decision: string; cards: Card[] }[] };
type Detail = { card: Card; pages: { n: number; url: string }[] };
type SampleRun = { started: string; events: string; invoice_id: string | null; decision: string | null; after?: string };
type PageImage = { key: string; scale: number; file: string; reply: Reply };

const responses: Record<string, Entry> = {};
const recordedOnly: Record<string, Entry> = {};
const samples: Record<string, SampleRun> = {};
const failures: string[] = [];
const pageImages: PageImage[] = [];
const stored = new Map<string, string>(); // SHA-256 of a body -> the file that holds it
const tally = { files: 0, bytes: 0, requests: 0, pings: 0 };

/** One browser: the sandbox cookie the API sets on a visitor's first sandbox call, sent back after. */
class Visitor {
  cookie: string | null = null;

  /** Keeps alinka_sandbox from Set-Cookie; the API sets it when it creates the sandbox. */
  keep(headers: Headers): void {
    for (const line of headers.getSetCookie()) {
      const m = /^alinka_sandbox=([^;]*)/.exec(line);
      if (m) this.cookie = m[1] || null;
    }
  }
}

const sleep = (ms: number) => new Promise((done) => setTimeout(done, ms));
const sha256 = (body: Uint8Array) => createHash("sha256").update(body).digest("hex");
const safe = (name: string) => name.replace(/[^A-Za-z0-9._-]/g, "_");
const json = <T>(reply: Reply): T => JSON.parse(new TextDecoder().decode(reply.body)) as T;
const cardsOf = (b: Board): Card[] => [...b.inbox, ...b.columns.flatMap((c) => c.cards)];
const message = (err: unknown) => (err instanceof Error ? err.message : String(err));

/** The page image URL at a scale, the way page-viewer.tsx's scaledUrl builds it. */
function scaled(url: string, scale: number): string {
  if (scale === 1) return url;
  const [path, query = ""] = url.split("?", 2);
  const params = new URLSearchParams(query);
  params.set("scale", String(scale));
  return `${path}?${params}`;
}

/**
 * One request as the visitor. GETs are retried on a network error or a 5xx, since they change
 * nothing; a POST is sent once, so a sandbox never sees the same write twice.
 */
async function send(v: Visitor | null, method: string, path: string, body?: unknown): Promise<Reply> {
  const headers: Record<string, string> = { "user-agent": UA, accept: "application/json, */*" };
  if (v?.cookie) headers.cookie = `alinka_sandbox=${v.cookie}`;
  if (body !== undefined) headers["content-type"] = "application/json";
  const tries = method === "GET" ? 3 : 1;
  for (let attempt = 1; ; attempt++) {
    tally.requests++;
    try {
      const res = await fetch(ORIGIN + path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        redirect: "manual",
        signal: AbortSignal.timeout(120_000),
      });
      v?.keep(res.headers);
      // Cloudflare's cache keys on the URL alone: a hit may be another visitor's sandbox.
      if (res.headers.get("cf-cache-status") === "HIT") failures.push(`${method} ${path}: answered by Cloudflare's cache`);
      const type = res.headers.get("content-type") ?? "";
      const reply = { status: res.status, type, headers: res.headers, body: new Uint8Array(await res.arrayBuffer()) };
      if (reply.status < 500 || attempt >= tries) return reply;
    } catch (err) {
      if (attempt >= tries) throw err;
    }
    await sleep(2_000 * attempt);
  }
}

/** Writes a body once: a body already stored under another name returns that file instead. */
function save(file: string, body: Uint8Array): string {
  const hash = sha256(body);
  const known = stored.get(hash);
  if (known) return known;
  const path = join(WORK, file);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, body);
  stored.set(hash, file);
  tally.files++;
  tally.bytes += body.length;
  return file;
}

/**
 * Files a reply under its key. A 4xx is an answer the frozen API repeats (a trace before the
 * decision is a 404); a 5xx is a failure, listed in the manifest instead.
 */
function record(key: string, reply: Reply, file: string, only = false): void {
  const into = only ? recordedOnly : responses;
  if (key in into) throw new Error(`recorded twice: ${key}`);
  if (reply.status >= 500) {
    failures.push(`${key}: HTTP ${reply.status}`);
    return;
  }
  const e: Entry = { file: save(file, reply.body), status: reply.status, content_type: reply.type };
  const headers: Record<string, string> = {};
  // The headers worth replaying. Date, cf-ray, set-cookie and the rest are not; nor is the
  // max-age Cloudflare adds to the CSV, since a sandbox's CSV changes. The API sets a cache
  // policy only on page images.
  const disposition = reply.headers.get("content-disposition");
  const cache = reply.headers.get("cache-control");
  if (disposition) headers["content-disposition"] = disposition;
  if (cache && reply.type.startsWith("image/")) headers["cache-control"] = cache;
  if (Object.keys(headers).length > 0) e.headers = headers;
  into[key] = e;
}

/**
 * Sends the request a key names ("inbox GET /api/board?view=sandbox": a GET of that path) and
 * records the reply; `path` replaces the key's path on the wire. A failure is listed instead of
 * thrown, so one miss never stops the run.
 */
async function capture(
  v: Visitor | null,
  key: string,
  file: string,
  opts: { body?: unknown; only?: boolean; path?: string } = {},
): Promise<Reply | null> {
  const [, method = "GET", keyPath = ""] = /\b(GET|POST) (\S+)/.exec(key) ?? [];
  try {
    const reply = await send(v, method, opts.path ?? keyPath, opts.body);
    record(key, reply, file, opts.only);
    return reply;
  } catch (err) {
    failures.push(`${key}: ${message(err)}`);
    return null;
  }
}

/** Runs fn over items with at most n in flight: quick, and gentle with a small server. */
async function pool<T>(items: readonly T[], n: number, fn: (item: T) => Promise<void>): Promise<void> {
  let next = 0;
  const worker = async () => {
    while (next < items.length) await fn(items[next++] as T);
  };
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, worker));
}

function extension(type: string): string {
  if (type.startsWith("image/png")) return ".png";
  if (type.startsWith("image/jpeg")) return ".jpg";
  return ".json"; // a 404 page answer is FastAPI's {"detail": ...}
}

/**
 * Every page of the given invoices at scales 1, 2 and 3, requested like the page viewer does and
 * kept in memory: whether scale 3 ships depends on the size of all of them, known only at the end.
 */
async function pages(v: Visitor | null, details: Detail[]): Promise<void> {
  const jobs = details.flatMap((d) => d.pages.flatMap((p) => SCALES.map((scale) => ({ id: d.card.invoice_id, p, scale }))));
  await pool(jobs, 3, async ({ id, p, scale }) => {
    const key = `GET /api/invoices/${id}/pages/${p.n}?scale=${scale}`;
    try {
      const reply = await send(v, "GET", scaled(p.url, scale));
      if (reply.status >= 500) failures.push(`${key}: HTTP ${reply.status}`);
      else pageImages.push({ key, scale, file: `pages/${safe(id)}/${p.n}@${scale}x${extension(reply.type)}`, reply });
    } catch (err) {
      failures.push(`${key}: ${message(err)}`);
    }
  });
}

/** Detail and trace of each invoice in one view and state; returns the details that answered 200. */
async function invoices(v: Visitor | null, ids: string[], scope: "canonical" | "inbox" | "decided"): Promise<Detail[]> {
  const view = scope === "canonical" ? "canonical" : "sandbox";
  const prefix = scope === "canonical" ? "" : `${scope} `;
  const details: Detail[] = [];
  await pool(ids, 4, async (id) => {
    const dir = `invoices/${safe(id)}`;
    const detail = await capture(v, `${prefix}GET /api/invoices/${id}?view=${view}`, `${dir}/${scope}.json`);
    await capture(v, `${prefix}GET /api/invoices/${id}/trace?view=${view}`, `${dir}/trace-${scope}.json`);
    if (detail?.status === 200) details.push(json<Detail>(detail));
  });
  return details;
}

/**
 * The log, its chain check and its CSV in one view and state ("" for canonical). Cloudflare
 * caches URLs ending in .csv whatever the cookie, so the CSV is asked with a parameter the API
 * ignores and no cache has seen.
 */
async function logReads(v: Visitor | null, view: string, prefix: string, name: string, only = false): Promise<void> {
  await capture(v, `${prefix}GET /api/log?view=${view}`, `${name}.json`, { only });
  await capture(v, `${prefix}GET /api/log/verify?view=${view}`, `${name}-verify.json`, { only });
  const path = `/api/log/export.csv?view=${view}&nocache=${randomUUID()}`;
  await capture(v, `${prefix}GET /api/log/export.csv?view=${view}`, `${name}.csv`, { only, path });
}

async function canonical(): Promise<{ head: string | null; version: string; sampleIds: string[] }> {
  const health = await capture(null, "GET /api/health", "health.json");
  if (health?.status !== 200) throw new Error("the API is not answering /api/health");
  const { canonical_head: head, version } = json<{ canonical_head: string | null; version: string }>(health);
  const board = await capture(null, "GET /api/board?view=canonical", "board/canonical.json");
  if (board?.status !== 200) throw new Error("no canonical board");
  const b = json<Board>(board);
  if (b.head_hash !== head) failures.push(`the canonical board's head ${b.head_hash} differs from /api/health's ${head}`);
  await pages(null, await invoices(null, cardsOf(b).map((c) => c.invoice_id), "canonical"));
  await capture(null, "GET /api/rules?view=canonical", "rules/canonical.json");
  await logReads(null, "canonical", "", "log/canonical");
  await capture(null, "GET /api/eval", "eval.json");
  const list = await capture(null, "GET /api/try/samples", "try/samples.json");
  if (list?.status !== 200) throw new Error("no Probar samples");
  return { head, version, sampleIds: json<{ samples: { id: string }[] }>(list).samples.map((s) => s.id) };
}

/** A fresh visitor: the inbox, the run, the decided sandbox, a run with nothing left, the reset. */
async function sandbox(): Promise<Board | null> {
  const v = new Visitor();
  const inbox = await capture(v, "inbox GET /api/board?view=sandbox", "board/inbox.json");
  if (inbox?.status !== 200 || !v.cookie) throw new Error("no sandbox was created");
  const ids = cardsOf(json<Board>(inbox)).map((c) => c.invoice_id);
  await invoices(v, ids, "inbox");
  await capture(v, "inbox GET /api/rules?view=sandbox", "rules/inbox.json");
  await logReads(v, "sandbox", "inbox ", "log/inbox");
  const run = await capture(v, "inbox POST /api/run", "run/inbox.json");
  if (run?.status !== 200) throw new Error("POST /api/run failed");
  const decided = await capture(v, "decided GET /api/board?view=sandbox", "board/decided.json");
  await invoices(v, ids, "decided");
  await capture(v, "decided GET /api/rules?view=sandbox", "rules/decided.json");
  await logReads(v, "sandbox", "decided ", "log/decided");
  await capture(v, "decided POST /api/run", "run/decided.json");
  await sameInEveryView(v, ids);
  await capture(v, "POST /api/sandbox/reset", "sandbox-reset.json");
  return decided?.status === 200 ? json<Board>(decided) : null;
}

/**
 * Page images are keyed without the view because the API renders them from the source document
 * whatever the view. Checked here on page 1 of every sixth invoice, through the visitor's sandbox.
 */
async function sameInEveryView(v: Visitor, ids: string[]): Promise<void> {
  for (const id of ids.filter((_, i) => i % 6 === 0)) {
    const canon = pageImages.find((p) => p.key === `GET /api/invoices/${id}/pages/1?scale=1`);
    const reply = await send(v, "GET", `/api/invoices/${id}/pages/1?view=sandbox`).catch(() => null);
    if (!canon || reply?.status !== 200) failures.push(`page 1 of ${id}: no image to compare the views with`);
    else if (sha256(reply.body) !== sha256(canon.reply.body)) failures.push(`page 1 of ${id} differs between the views`);
  }
}

/**
 * Listens to a Probar job's Server-Sent Events until the API closes the stream. Each event keeps
 * its name, data and the milliseconds since the stream opened, which the Worker replays.
 */
async function listen(v: Visitor, path: string): Promise<Stream> {
  tally.requests++;
  const headers: Record<string, string> = { "user-agent": UA, accept: "text/event-stream" };
  if (v.cookie) headers.cookie = `alinka_sandbox=${v.cookie}`;
  const res = await fetch(ORIGIN + path, { headers, signal: AbortSignal.timeout(180_000) });
  const opened = performance.now();
  const type = res.headers.get("content-type") ?? "";
  const events: StreamEvent[] = [];
  if (!res.ok || !res.body) {
    await res.body?.cancel(); // a 404 has nothing to replay: free the connection
    return { status: res.status, type, events };
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let carriage = ""; // a chunk's last "\r" waits for the next chunk: it may be half of "\r\n"
  for (;;) {
    const { value, done } = await reader.read();
    const at = Math.round(performance.now() - opened);
    let chunk = carriage + decoder.decode(value, { stream: !done });
    carriage = !done && chunk.endsWith("\r") ? "\r" : "";
    if (carriage) chunk = chunk.slice(0, -1);
    text += chunk.replace(/\r\n?/g, "\n");
    for (let end = text.indexOf("\n\n"); end >= 0; end = text.indexOf("\n\n")) {
      const parsed = parseEvent(text.slice(0, end));
      text = text.slice(end + 2);
      if (parsed) events.push({ ...parsed, delay_ms: at });
      else tally.pings++;
    }
    if (done) break; // per the SSE spec, an event cut off by the end of the stream is dropped
  }
  return { status: res.status, type, events };
}

/** One SSE block per the spec: data lines joined by "\n", event defaults to "message"; null for a comment. */
function parseEvent(block: string): { event: string; data: string; id?: string } | null {
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
    else if (field === "id") id = value;
  }
  if (data.length === 0) return null;
  return id === undefined ? { event, data: data.join("\n") } : { event, data: data.join("\n"), id };
}

/** POST /api/try, waiting out one 429 (another job of this visitor, or the hourly limit). */
async function start(v: Visitor, id: string): Promise<Reply | null> {
  for (let attempt = 1; attempt <= 2; attempt++) {
    const reply = await send(v, "POST", "/api/try", { sample_id: id }).catch((err: unknown) => {
      failures.push(`${id}: POST /api/try failed: ${message(err)}`);
      return null;
    });
    if (reply?.status !== 429 || attempt === 2) return reply;
    const wait = Math.min(Number(reply.headers.get("retry-after")) || 10, 120);
    console.log(`  ${id}: 429, waiting ${wait} s`);
    await sleep(wait * 1_000);
  }
  return null;
}

/** A sample started in the visitor's sandbox and followed to the end of its stream; null when lost. */
async function runSample(v: Visitor, id: string): Promise<{ started: Reply; stream: Stream } | null> {
  const started = await start(v, id);
  if (started?.status !== 202) {
    console.log(`  ${id}: POST /api/try answered ${started?.status ?? "nothing"}`);
    return null;
  }
  const job = json<{ job_id: string; events_url: string }>(started);
  let stream: Stream | null = null;
  let asks = 0;
  while (asks < LISTEN_TRIES && stream?.status !== 200) {
    asks++;
    stream = await listen(v, job.events_url).catch((err: unknown) => {
      console.log(`  ${id}: the event stream failed: ${message(err)}`);
      return null;
    });
  }
  if (stream?.status !== 200 || !stream.events.some((e) => e.event === "done" || e.event === "error")) {
    console.log(`  ${id}: no complete event stream (HTTP ${stream?.status ?? "-"}, ${stream?.events.length ?? 0} events)`);
    return null;
  }
  // A stream that opened late gives the events the job had already sent all at once.
  if (asks > 1) console.log(`  ${id}: the stream opened on ask ${asks}`);
  return { started, stream: { ...stream, asks } };
}

const finished = (run: { stream: Stream }) => run.stream.events.some((e) => e.event === "done");

/**
 * One Probar scenario: the samples run in order in one fresh sandbox, and the last one is
 * recorded. A lost stream, or a run that ended in an error event, starts the scenario over in
 * a fresh sandbox before anything of it was recorded; an error on the last try is recorded as
 * it happened, since that is what the API did.
 */
async function scenario(ids: string[], replayed: boolean): Promise<void> {
  const id = ids.at(-1) ?? "";
  const after = ids.slice(0, -1).join("+") || undefined;
  for (let attempt = 1; attempt <= TRIES; attempt++) {
    const v = new Visitor();
    let run: { started: Reply; stream: Stream } | null = null;
    let reached = 0;
    for (const sample of ids) {
      run = await runSample(v, sample);
      if (!run) break;
      reached++;
      if (!finished(run)) break;
    }
    if (run && reached === ids.length && (finished(run) || attempt === TRIES)) {
      await keepRun(v, id, after, run, replayed);
      return;
    }
    console.log(`  ${id}: trying again in a fresh sandbox`);
    await sleep(3_000);
  }
  failures.push(`${id}: no complete event stream in ${TRIES} tries`);
}

/**
 * Records a Probar run and what the page asks for after it: the new invoice's detail, page
 * images and trace. The board and log after it are recorded only, since the frozen board does
 * not grow with Probar runs. The run that is not replayed (the duplicate in a fresh sandbox)
 * is recorded only, under keys that start with "fresh".
 */
async function keepRun(v: Visitor, id: string, after: string | undefined, run: { started: Reply; stream: Stream }, replayed: boolean) {
  const dir = `try/${safe(id)}${replayed ? "" : "-fresh"}`;
  const prefix = replayed ? "" : "fresh ";
  const suffix = replayed ? "" : "-fresh";
  const startKey = `${prefix}POST /api/try {"sample_id":"${id}"}`;
  record(startKey, run.started, `${dir}/started.json`, !replayed);
  const { stream } = run;
  // listen_asks above 1: the stream opened late, and the delays count from that late opening.
  const body = { sample_id: id, after: after ?? null, status: stream.status, content_type: stream.type, listen_asks: stream.asks ?? 1, events: stream.events };
  const events = save(`${dir}/events.json`, new TextEncoder().encode(`${JSON.stringify(body, null, 2)}\n`));
  const done = stream.events.find((e) => e.event === "done");
  const result = done ? (JSON.parse(done.data) as { invoice_id: string; decision: string }) : null;
  if (result) {
    const tid = result.invoice_id;
    const detail = await capture(v, `${prefix}GET /api/invoices/${tid}?view=sandbox`, `invoices/${safe(tid)}/sandbox${suffix}.json`, { only: !replayed });
    if (replayed && detail?.status === 200) await pages(v, [json<Detail>(detail)]);
    await capture(v, `${prefix}GET /api/invoices/${tid}/trace?view=sandbox`, `invoices/${safe(tid)}/trace-sandbox${suffix}.json`, { only: !replayed });
  } else {
    failures.push(`${id}: every try ended in an error event; the replay repeats the last one`);
  }
  const state = `tried:${after ? `${after}+` : ""}${id}`;
  await capture(v, `${state} GET /api/board?view=sandbox`, `${dir}/board.json`, { only: true });
  await capture(v, `${state} GET /api/log?view=sandbox`, `${dir}/log.json`, { only: true });
  if (replayed) {
    const started = responses[startKey]?.file ?? "";
    samples[id] = { started, events, invoice_id: result?.invoice_id ?? null, decision: result?.decision ?? null, ...(after ? { after } : {}) };
  }
  const took = stream.events.at(-1)?.delay_ms ?? 0;
  const outcome = result ? `${result.invoice_id} ${result.decision}` : "error";
  console.log(`  ${id}${after ? ` after ${after}` : ""}${replayed ? "" : " (fresh, recorded only)"}: ${stream.events.length} events in ${took} ms -> ${outcome}`);
}

/** Every sample in the order the API lists them; the duplicate once after its original, once alone. */
async function probar(ids: string[]): Promise<void> {
  for (const id of ids) {
    if (id === DUP_SAMPLE) {
      await scenario([DUP_AFTER, DUP_SAMPLE], true);
      await scenario([DUP_SAMPLE], false);
    } else {
      await scenario([id], true);
    }
    await sleep(1_000);
  }
}

/**
 * Each escalation a person may approve, approved and then rejected, each in a fresh sandbox
 * decided by "Ejecutar agente", with what the screens reload right after: the invoice, its
 * trace, the board and the log. Recorded only, under states such as "approved:OCT-08".
 */
async function approvals(decided: Board): Promise<void> {
  const pending = decided.columns.flatMap((c) => c.cards).filter((c) => c.state === "ESCALATE" && c.approvable && !c.approver);
  for (const { invoice_id: id } of pending) {
    for (const action of ["approve", "reject"] as const) {
      const v = new Visitor();
      const run = await send(v, "POST", "/api/run").catch(() => null);
      if (run?.status !== 200) {
        failures.push(`${action} ${id}: the sandbox run answered ${run?.status ?? "nothing"}`);
        continue;
      }
      const state = `${action === "approve" ? "approved" : "rejected"}:${id}`;
      const dir = `approvals/${safe(id)}/${action}`;
      const r = await capture(v, `decided POST /api/invoices/${id}/${action}`, `${dir}.json`, {
        body: { approver: APPROVER, note: null },
        only: true,
      });
      await capture(v, `${state} GET /api/invoices/${id}?view=sandbox`, `${dir}-detail.json`, { only: true });
      await capture(v, `${state} GET /api/invoices/${id}/trace?view=sandbox`, `${dir}-trace.json`, { only: true });
      await capture(v, `${state} GET /api/board?view=sandbox`, `${dir}-board.json`, { only: true });
      await logReads(v, "sandbox", `${state} `, `${dir}-log`, true);
      console.log(`  ${action} ${id}: HTTP ${r?.status ?? "-"}`);
    }
  }
}

/** Ships scale 3 only while all page images stay under PAGE_BUDGET; returns the scales kept. */
function shipPages(): { scales: number[]; all: number; kept: number } {
  const size = (list: PageImage[]) => {
    const unique = new Map<string, number>();
    for (const p of list) unique.set(sha256(p.reply.body), p.reply.body.length);
    return [...unique.values()].reduce((a, b) => a + b, 0);
  };
  const all = size(pageImages);
  const scales = all > PAGE_BUDGET ? [1, 2] : [1, 2, 3];
  const kept = pageImages.filter((p) => scales.includes(p.scale));
  kept.sort((a, b) => a.key.localeCompare(b.key, "en", { numeric: true }));
  for (const p of kept) record(p.key, p.reply, p.file);
  return { scales, all, kept: size(kept) };
}

function sorted<T>(map: Record<string, T>): Record<string, T> {
  return Object.fromEntries(Object.entries(map).sort(([a], [b]) => a.localeCompare(b, "en", { numeric: true })));
}

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1)} MB`;

async function main(): Promise<void> {
  rmSync(WORK, { recursive: true, force: true });
  mkdirSync(WORK, { recursive: true });
  console.log(`recording ${ORIGIN} into ${OUT}`);
  const recordedAt = new Date().toISOString().replace(/\.\d+Z$/, "Z");
  console.log("the canonical run");
  const { head, version, sampleIds } = await canonical();
  console.log("a fresh sandbox: inbox, run, decided, reset");
  const decided = await sandbox();
  console.log("Probar samples, one at a time");
  await probar(sampleIds);
  console.log("approvals and rejections (recorded only)");
  if (decided) await approvals(decided);
  const shipped = shipPages();
  const manifest = {
    format: 1,
    about: "Recorded answers of the Alinka API, replayed by the frozen Worker (edge/src/frozen.ts). Written by web/scripts/snapshot.ts.",
    recorded_at: recordedAt,
    source: ORIGIN,
    site_build_sha: null, // the site exposes none: neither its pages nor /api/health carry one
    api_version: version,
    canonical_head: head,
    page_scales: shipped.scales,
    responses: sorted(responses),
    samples,
    recorded_only: sorted(recordedOnly),
    failures,
  };
  writeFileSync(join(WORK, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  renameSync(WORK, OUT);
  console.log(
    [
      `done: ${tally.requests} requests, ${Object.keys(responses).length} replayed keys, ${Object.keys(recordedOnly).length} recorded-only keys`,
      `files: ${tally.files} bodies (${mb(tally.bytes)}) and manifest.json`,
      `page images: ${mb(shipped.all)} at scales 1-3, ${mb(shipped.kept)} shipped at scales ${shipped.scales.join(", ")}`,
      `samples replayed: ${Object.keys(samples).length}; ping comments seen: ${tally.pings}`,
      `failures: ${failures.length}${failures.length ? `\n  ${failures.join("\n  ")}` : ""}`,
    ].join("\n"),
  );
}

try {
  await main();
} catch (err) {
  console.error(`snapshot failed: ${message(err)} (the previous snapshot, if any, is untouched)`);
  process.exitCode = 1;
}
