// The frozen API: how alinka-edge answers /api/* since the Azure API was retired on 22 Oct 2026.
// Every answer was recorded from the live API by web/scripts/snapshot.ts into
// web/public/snapshot/, which the assets layer serves at /snapshot/; manifest.json there lists
// each recorded request. This module is pure: route() takes a request and the visitor's sandbox
// state and says what to answer (a recorded file, a JSON body, or a recorded event stream to
// replay) and how the state changes. index.ts does the I/O. Pure, so frozen.test.ts covers the
// whole routing table without a Worker runtime.
//
// The only state is the sandbox's: "inbox" until the visitor presses "Ejecutar agente", then
// "decided" until "Restablecer sandbox". It lives in a small cookie, so every visitor replays
// the same recorded sandbox and still sees their own run stick. Writes the recording cannot
// answer (rules, beneficiaries, approvals, uploads, settings) get a 403 that says why, and the
// samples list says uploads are off.

/** The sandbox's state: its inbox untouched, or decided by "Ejecutar agente". */
export type State = "inbox" | "decided";

/** One recorded answer in manifest.json: the file under /snapshot/ and how to serve it. */
export interface Entry {
  file: string;
  status: number;
  content_type: string;
  headers?: Record<string, string>;
}

/** A recorded Probar run: the stream to replay and the invoice it created. */
export interface SampleRun {
  started: string;
  events: string;
  invoice_id: string;
  decision: string;
  after?: string; // the sample recorded before it, in the same sandbox (the duplicate trap)
}

/** The parts of manifest.json the Worker reads. */
export interface Manifest {
  recorded_at: string;
  page_scales: number[];
  responses: Record<string, Entry>;
  samples: Record<string, SampleRun>;
}

/** One Server-Sent Event as recorded: its name, data and milliseconds since the stream opened. */
export interface StreamEvent {
  event: string;
  data: string;
  delay_ms: number;
  id?: string;
}

/** A recorded stream file (try/<sample>/events.json). */
export interface Recording {
  status: number;
  content_type: string;
  events: StreamEvent[];
}

/** A request, reduced to what routing needs. The nonce makes each Probar job id unique. */
export interface Ask {
  method: string;
  url: URL;
  contentType: string;
  body: string; // read only for POST /api/try with JSON; empty otherwise
  state: State;
  nonce: string;
}

/**
 * What to send back; `next` is the sandbox state to store, when it changes. A file's `patch`
 * replaces top-level fields of its recorded JSON (see patched()).
 */
export type Answer = (
  | { kind: "file"; entry: Entry; patch?: Record<string, unknown> }
  | { kind: "json"; status: number; body: unknown; headers?: Record<string, string> }
  | { kind: "stream"; file: string }
) & { next?: State };

export const STATE_COOKIE = "alinka_frozen";
const STATE_TTL_S = 24 * 60 * 60; // as long as a sandbox lived on the live API

/** The 403 detail for every write: shown by the screens in their error banner. */
export const FROZEN_ES =
  "La demo está congelada desde que su API se retiró el 22 de octubre de 2026, así que ya no acepta cambios ni documentos nuevos.";

type View = "canonical" | "sandbox";
type Context = Ask & { m: Manifest };
type Handler = (c: Context, params: string[]) => Answer;

const json = (status: number, body: unknown, headers?: Record<string, string>): Answer => ({ kind: "json", status, body, headers });
const detail = (status: number, text: string): Answer => json(status, { detail: text });
const frozen: Handler = () => detail(403, FROZEN_ES);

// Every route of alinka/api/app.py and try_routes.py, with what the frozen API does for each method.
const ROUTES: { pattern: RegExp; methods: Record<string, Handler> }[] = [
  { pattern: /^\/api\/health$/, methods: { GET: (c) => recorded(c, "GET /api/health") } },
  { pattern: /^\/api\/board$/, methods: { GET: (c) => viewed(c, "/api/board") } },
  { pattern: /^\/api\/run$/, methods: { POST: run } },
  { pattern: /^\/api\/sandbox\/reset$/, methods: { POST: reset } },
  { pattern: /^\/api\/invoices\/([^/]+)$/, methods: { GET: invoice } },
  { pattern: /^\/api\/invoices\/([^/]+)\/pages\/(\d+)$/, methods: { GET: page } },
  { pattern: /^\/api\/invoices\/([^/]+)\/trace$/, methods: { GET: trace } },
  { pattern: /^\/api\/invoices\/([^/]+)\/(?:approve|reject)$/, methods: { POST: frozen } },
  { pattern: /^\/api\/rules$/, methods: { GET: (c) => viewed(c, "/api/rules"), PUT: frozen } },
  { pattern: /^\/api\/beneficiaries$/, methods: { POST: frozen } },
  { pattern: /^\/api\/log$/, methods: { GET: (c) => viewed(c, "/api/log") } },
  { pattern: /^\/api\/log\/verify$/, methods: { GET: (c) => viewed(c, "/api/log/verify") } },
  { pattern: /^\/api\/log\/export\.csv$/, methods: { GET: (c) => viewed(c, "/api/log/export.csv") } },
  { pattern: /^\/api\/eval$/, methods: { GET: (c) => recorded(c, "GET /api/eval") } },
  { pattern: /^\/api\/try\/samples$/, methods: { GET: samplesList } },
  { pattern: /^\/api\/try$/, methods: { POST: startTry } },
  { pattern: /^\/api\/try\/([^/]+)\/events$/, methods: { GET: events } },
  { pattern: /^\/api\/admin\/settings$/, methods: { PUT: frozen } },
];

/**
 * The answer to one /api/* request. A path the API never had is a 404 and a known path with
 * another method a 405, both with FastAPI's {"detail": ...} body, which the screens display.
 * HEAD is answered as GET (index.ts drops the body).
 */
export function route(ask: Ask, m: Manifest): Answer {
  const method = ask.method === "HEAD" ? "GET" : ask.method;
  for (const { pattern, methods } of ROUTES) {
    const match = pattern.exec(ask.url.pathname);
    if (!match) continue;
    const handler = methods[method];
    if (!handler) return json(405, { detail: "Método no permitido." }, { allow: Object.keys(methods).join(", ") });
    let params: string[];
    try {
      params = match.slice(1).map((p) => decodeURIComponent(p ?? ""));
    } catch {
      return detail(404, `No existe la ruta ${ask.url.pathname}.`); // a malformed %-escape
    }
    return handler({ ...ask, m }, params);
  }
  return detail(404, `No existe la ruta ${ask.url.pathname}.`);
}

/** The view the request asks for: ?view=canonical, else the visitor's sandbox (the API's default). */
function viewOf(c: Context): View | null {
  const view = c.url.searchParams.get("view") ?? "sandbox";
  return view === "canonical" || view === "sandbox" ? view : null;
}

const badView = () => detail(422, "view debe ser sandbox o canonical.");

/**
 * The recorded answer to a GET in the request's view. Canonical keys carry ?view=canonical;
 * sandbox keys carry the state first ("decided GET /api/board?view=sandbox"), except the
 * invoices Probar created, recorded once for every state.
 */
function lookup(c: Context, view: View, path: string): Entry | undefined {
  if (view === "canonical") return c.m.responses[`GET ${path}?view=canonical`];
  return c.m.responses[`${c.state} GET ${path}?view=sandbox`] ?? c.m.responses[`GET ${path}?view=sandbox`];
}

function recorded(c: Context, key: string): Answer {
  const entry = c.m.responses[key];
  return entry ? { kind: "file", entry } : detail(404, "Esta respuesta no quedó grabada en la demo congelada.");
}

function viewed(c: Context, path: string): Answer {
  const view = viewOf(c);
  if (!view) return badView();
  const entry = lookup(c, view, path);
  return entry ? { kind: "file", entry } : detail(404, "Esta respuesta no quedó grabada en la demo congelada.");
}

/** "Ejecutar agente": the recorded run from the inbox (or, once decided, the run with nothing left). */
function run(c: Context): Answer {
  const answer = recorded(c, `${c.state} POST /api/run`);
  return answer.kind === "file" ? { ...answer, next: "decided" } : answer;
}

/** "Restablecer sandbox": the recorded fresh board, and the state back to the inbox. */
function reset(c: Context): Answer {
  return { ...recorded(c, "POST /api/sandbox/reset"), next: "inbox" };
}

function invoice(c: Context, [id = ""]: string[]): Answer {
  const view = viewOf(c);
  if (!view) return badView();
  const entry = lookup(c, view, `/api/invoices/${id}`);
  return entry ? { kind: "file", entry } : detail(404, `No existe la factura ${id}.`);
}

function trace(c: Context, [id = ""]: string[]): Answer {
  const view = viewOf(c);
  if (!view) return badView();
  const entry = lookup(c, view, `/api/invoices/${id}/trace`);
  if (entry) return { kind: "file", entry };
  if (lookup(c, view, `/api/invoices/${id}`)) return detail(404, `La factura ${id} aún no tiene decisión.`);
  return detail(404, `No existe la factura ${id}.`);
}

/**
 * A page image. Images are the same in every view, so they are keyed by scale only; the view
 * still decides whether the invoice exists (a Probar invoice is not in the canonical run). A
 * scale the snapshot left out (3, when the images were too large) gets the next one down.
 */
function page(c: Context, [id = "", n = ""]: string[]): Answer {
  const view = viewOf(c);
  if (!view) return badView();
  const scale = c.url.searchParams.get("scale") ?? "1";
  if (!/^[123]$/.test(scale)) return detail(422, "scale debe ser 1, 2 o 3.");
  if (!lookup(c, view, `/api/invoices/${id}`)) return detail(404, `No existe la factura ${id}.`);
  const served = Math.max(1, ...c.m.page_scales.filter((s) => s <= Number(scale)));
  const entry = c.m.responses[`GET /api/invoices/${id}/pages/${Number(n)}?scale=${served}`];
  return entry ? { kind: "file", entry } : detail(404, `La factura ${id} no tiene página ${Number(n)}.`);
}

/**
 * Probar: a sample starts a job whose events URL replays that sample's recorded stream. The
 * job id is the sample id and a nonce, so each run is a new job, as on the live API. An upload
 * is refused: nothing can read a new document any more.
 */
function startTry(c: Context): Answer {
  if (c.contentType.startsWith("multipart/form-data")) return detail(403, FROZEN_ES);
  let sampleId: unknown;
  try {
    sampleId = (JSON.parse(c.body) as { sample_id?: unknown } | null)?.sample_id;
  } catch {
    sampleId = undefined;
  }
  if (typeof sampleId !== "string") return detail(422, 'Envía {"sample_id": ...} o un archivo.');
  if (!c.m.samples[sampleId]) return detail(404, `No existe la muestra ${sampleId}.`);
  const jobId = `${sampleId}.${c.nonce}`;
  return json(202, { job_id: jobId, events_url: `/api/try/${encodeURIComponent(jobId)}/events` });
}

/**
 * The Probar samples as recorded, but with uploads off for good: the owner's decision for the
 * frozen demo, since nothing can read a new document any more (an upload still gets the 403).
 * With live_uploads false, Probar hides its upload box and Cómo funciona says uploads are off.
 */
function samplesList(c: Context): Answer {
  const answer = recorded(c, "GET /api/try/samples");
  return answer.kind === "file" ? { ...answer, patch: { live_uploads: false } } : answer;
}

/** A recorded JSON object with the patch's top-level fields replaced; the rest keeps its values and order. */
export function patched(body: string, patch: Record<string, unknown>): string {
  return JSON.stringify({ ...(JSON.parse(body) as Record<string, unknown>), ...patch });
}

/** The sample of a job id from startTry ("GEN-084-1.3f9a2c1b"); a bare sample id works too. */
export function sampleOf(jobId: string): string {
  const dot = jobId.lastIndexOf(".");
  return dot < 0 ? jobId : jobId.slice(0, dot);
}

function events(c: Context, [jobId = ""]: string[]): Answer {
  const sample = c.m.samples[sampleOf(jobId)];
  return sample ? { kind: "stream", file: sample.events } : detail(404, `No existe la prueba ${jobId}.`);
}

/** The sandbox state from the Cookie header: "decided" only when the cookie says so. */
export function readState(cookie: string | null): State {
  for (const part of (cookie ?? "").split(";")) {
    const [name = "", value = ""] = part.trim().split("=", 2);
    if (name === STATE_COOKIE && value === "decided") return "decided";
  }
  return "inbox";
}

/**
 * The Set-Cookie value that stores a state. "inbox" is the default, so it clears the cookie.
 * Path=/api: only the API reads it; HttpOnly and SameSite=Lax as the live sandbox cookie was.
 */
export function stateCookie(state: State): string {
  const attributes = "Path=/api; HttpOnly; Secure; SameSite=Lax";
  return state === "decided"
    ? `${STATE_COOKIE}=decided; Max-Age=${STATE_TTL_S}; ${attributes}`
    : `${STATE_COOKIE}=; Max-Age=0; ${attributes}`;
}

/** One event in the wire format FastAPI wrote: event line, a data line per line of data, then id. */
export function sseFrame(e: StreamEvent): string {
  const lines = [`event: ${e.event}`, ...e.data.split("\n").map((line) => `data: ${line}`)];
  if (e.id !== undefined) lines.push(`id: ${e.id}`);
  return `${lines.join("\n")}\n\n`;
}

/** The wait before each event, so a replay keeps the recorded pacing; never negative. */
export function gaps(events: StreamEvent[]): number[] {
  let at = 0;
  return events.map((e) => {
    const wait = Math.max(0, e.delay_ms - at);
    at = Math.max(at, e.delay_ms);
    return wait;
  });
}
