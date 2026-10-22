// The frozen API's routing table (frozen.ts), against a small hand-written manifest. Runs on
// Node's own test runner, so the Worker needs no test dependency of its own:
//   node --test 'edge/src/*.test.ts'               (from the repo root; Node 24 strips the types)
//   pnpm --filter ./web exec tsc -p ../edge        (type-checks the Worker and this file)

import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  type Answer,
  type Ask,
  type Entry,
  FROZEN_ES,
  gaps,
  type Manifest,
  patched,
  readState,
  route,
  sampleOf,
  sseFrame,
  stateCookie,
  type State,
} from "./frozen.ts";

const file = (name: string, status = 200, content_type = "application/json", headers?: Record<string, string>): Entry =>
  headers ? { file: name, status, content_type, headers } : { file: name, status, content_type };

const M: Manifest = {
  recorded_at: "2026-10-22T08:30:00Z",
  page_scales: [1, 2],
  responses: {
    "GET /api/health": file("health.json"),
    "GET /api/board?view=canonical": file("board/canonical.json"),
    "inbox GET /api/board?view=sandbox": file("board/inbox.json"),
    "decided GET /api/board?view=sandbox": file("board/decided.json"),
    "inbox POST /api/run": file("run/inbox.json"),
    "decided POST /api/run": file("run/decided.json"),
    "POST /api/sandbox/reset": file("sandbox-reset.json"),
    "GET /api/invoices/OCT-01?view=canonical": file("invoices/OCT-01/canonical.json"),
    "inbox GET /api/invoices/OCT-01?view=sandbox": file("invoices/OCT-01/inbox.json"),
    "decided GET /api/invoices/OCT-01?view=sandbox": file("invoices/OCT-01/decided.json"),
    "GET /api/invoices/OCT-01/trace?view=canonical": file("invoices/OCT-01/trace-canonical.json"),
    "GET /api/invoices/OCT-02?view=canonical": file("invoices/OCT-02/canonical.json"), // and no trace
    "inbox GET /api/invoices/OCT-01/trace?view=sandbox": file("invoices/OCT-01/trace-inbox.json", 404),
    "decided GET /api/invoices/OCT-01/trace?view=sandbox": file("invoices/OCT-01/trace-decided.json"),
    "GET /api/invoices/OCT-01/pages/1?scale=1": file("pages/OCT-01/1@1x.png", 200, "image/png", { "cache-control": "max-age=3600" }),
    "GET /api/invoices/OCT-01/pages/1?scale=2": file("pages/OCT-01/1@2x.png", 200, "image/png"),
    "GET /api/invoices/TRY-GEN-084-1-1?view=sandbox": file("invoices/TRY-GEN-084-1-1/sandbox.json"),
    "GET /api/invoices/TRY-GEN-084-1-1/trace?view=sandbox": file("invoices/TRY-GEN-084-1-1/trace-sandbox.json"),
    "GET /api/invoices/TRY-GEN-084-1-1/pages/1?scale=1": file("pages/TRY-GEN-084-1-1/1@1x.png", 200, "image/png"),
    "GET /api/rules?view=canonical": file("rules/canonical.json"),
    "inbox GET /api/rules?view=sandbox": file("rules/inbox.json"),
    "decided GET /api/rules?view=sandbox": file("rules/inbox.json"),
    "GET /api/log?view=canonical": file("log/canonical.json"),
    "inbox GET /api/log?view=sandbox": file("log/inbox.json"),
    "decided GET /api/log?view=sandbox": file("log/decided.json"),
    "decided GET /api/log/verify?view=sandbox": file("log/decided-verify.json"),
    "GET /api/log/export.csv?view=canonical": file("log/canonical.csv", 200, "text/csv; charset=utf-8", {
      "content-disposition": 'attachment; filename="alinka-canonical.csv"',
    }),
    "GET /api/eval": file("eval.json"),
    "GET /api/try/samples": file("try/samples.json"),
  },
  samples: {
    "GEN-084-1": { started: "try/GEN-084-1/started.json", events: "try/GEN-084-1/events.json", invoice_id: "TRY-GEN-084-1-1", decision: "PAY" },
  },
};

/** route() for a request, with the state and body a test needs and everything else defaulted. */
function ask(method: string, path: string, opts: { state?: State; body?: string; contentType?: string } = {}): Answer {
  const request: Ask = {
    method,
    url: new URL(path, "https://alinka.alinedlabs.co"),
    contentType: opts.contentType ?? "",
    body: opts.body ?? "",
    state: opts.state ?? "inbox",
    nonce: "n0nce123",
  };
  return route(request, M);
}

/** The file an answer serves, or a description of what it is instead. */
function served(a: Answer): string {
  if (a.kind === "file") return a.entry.file;
  if (a.kind === "stream") return `stream ${a.file}`;
  return `${a.status} ${JSON.stringify(a.body)}`;
}

const detailOf = (a: Answer) => (a.kind === "json" ? (a.body as { detail?: string }).detail : undefined);

describe("reads by view and sandbox state", () => {
  test("the canonical view ignores the sandbox state", () => {
    assert.equal(served(ask("GET", "/api/board?view=canonical", { state: "decided" })), "board/canonical.json");
  });

  test("the sandbox view follows the state; no view means the sandbox, as on the API", () => {
    assert.equal(served(ask("GET", "/api/board?view=sandbox")), "board/inbox.json");
    assert.equal(served(ask("GET", "/api/board?view=sandbox", { state: "decided" })), "board/decided.json");
    assert.equal(served(ask("GET", "/api/board", { state: "decided" })), "board/decided.json");
  });

  test("an unknown view is a 422", () => {
    const a = ask("GET", "/api/board?view=otra");
    assert.equal(a.kind === "json" && a.status, 422);
  });

  test("health, eval and the samples do not depend on the view", () => {
    assert.equal(served(ask("GET", "/api/health")), "health.json");
    assert.equal(served(ask("GET", "/api/eval?view=canonical")), "eval.json");
    assert.equal(served(ask("GET", "/api/try/samples")), "try/samples.json");
  });

  test("HEAD is answered as GET", () => {
    assert.equal(served(ask("HEAD", "/api/health")), "health.json");
  });

  test("the CSV keeps its recorded headers", () => {
    const a = ask("GET", "/api/log/export.csv?view=canonical");
    assert.equal(a.kind === "file" && a.entry.headers?.["content-disposition"], 'attachment; filename="alinka-canonical.csv"');
  });

  test("rules and log follow the state too", () => {
    assert.equal(served(ask("GET", "/api/log?view=sandbox", { state: "decided" })), "log/decided.json");
    assert.equal(served(ask("GET", "/api/log/verify?view=sandbox", { state: "decided" })), "log/decided-verify.json");
    assert.equal(served(ask("GET", "/api/rules?view=canonical")), "rules/canonical.json");
  });
});

describe("Ejecutar agente and Restablecer sandbox", () => {
  test("a run from the inbox replays the recorded run and stores decided", () => {
    const a = ask("POST", "/api/run");
    assert.equal(served(a), "run/inbox.json");
    assert.equal(a.next, "decided");
  });

  test("a run once decided replays the run with nothing left", () => {
    assert.equal(served(ask("POST", "/api/run", { state: "decided" })), "run/decided.json");
  });

  test("the reset replays the fresh board and stores the inbox again", () => {
    const a = ask("POST", "/api/sandbox/reset", { state: "decided" });
    assert.equal(served(a), "sandbox-reset.json");
    assert.equal(a.next, "inbox");
  });

  test("reads never change the state", () => {
    assert.equal(ask("GET", "/api/board?view=sandbox").next, undefined);
  });
});

describe("invoices", () => {
  test("the detail by view and state", () => {
    assert.equal(served(ask("GET", "/api/invoices/OCT-01?view=canonical")), "invoices/OCT-01/canonical.json");
    assert.equal(served(ask("GET", "/api/invoices/OCT-01?view=sandbox")), "invoices/OCT-01/inbox.json");
    assert.equal(served(ask("GET", "/api/invoices/OCT-01?view=sandbox", { state: "decided" })), "invoices/OCT-01/decided.json");
  });

  test("an unknown invoice is the API's 404", () => {
    assert.equal(detailOf(ask("GET", "/api/invoices/OCT-99?view=canonical")), "No existe la factura OCT-99.");
  });

  test("a Probar invoice exists in the sandbox in every state, never in the canonical run", () => {
    assert.equal(served(ask("GET", "/api/invoices/TRY-GEN-084-1-1?view=sandbox", { state: "decided" })), "invoices/TRY-GEN-084-1-1/sandbox.json");
    assert.equal(detailOf(ask("GET", "/api/invoices/TRY-GEN-084-1-1?view=canonical")), "No existe la factura TRY-GEN-084-1-1.");
    assert.equal(detailOf(ask("GET", "/api/invoices/TRY-GEN-084-1-1/pages/1?view=canonical")), "No existe la factura TRY-GEN-084-1-1.");
  });

  test("the trace before the decision is the recorded 404", () => {
    const a = ask("GET", "/api/invoices/OCT-01/trace?view=sandbox");
    assert.equal(a.kind === "file" && a.entry.status, 404);
    assert.equal(served(ask("GET", "/api/invoices/OCT-01/trace?view=sandbox", { state: "decided" })), "invoices/OCT-01/trace-decided.json");
    assert.equal(served(ask("GET", "/api/invoices/TRY-GEN-084-1-1/trace?view=sandbox")), "invoices/TRY-GEN-084-1-1/trace-sandbox.json");
  });

  test("a missing trace says whether the invoice exists in that view", () => {
    assert.equal(detailOf(ask("GET", "/api/invoices/OCT-02/trace?view=canonical")), "La factura OCT-02 aún no tiene decisión.");
    assert.equal(detailOf(ask("GET", "/api/invoices/TRY-GEN-084-1-1/trace?view=canonical")), "No existe la factura TRY-GEN-084-1-1.");
  });

  test("page images ignore the view and default to scale 1", () => {
    const a = ask("GET", "/api/invoices/OCT-01/pages/1?view=sandbox");
    assert.equal(served(a), "pages/OCT-01/1@1x.png");
    assert.equal(a.kind === "file" && a.entry.content_type, "image/png");
    assert.equal(served(ask("GET", "/api/invoices/OCT-01/pages/1?view=canonical&scale=2")), "pages/OCT-01/1@2x.png");
  });

  test("scale 3 falls back to the largest scale recorded", () => {
    assert.equal(served(ask("GET", "/api/invoices/OCT-01/pages/1?view=canonical&scale=3")), "pages/OCT-01/1@2x.png");
  });

  test("a scale outside 1-3 is a 422, a page past the end the API's 404", () => {
    const bad = ask("GET", "/api/invoices/OCT-01/pages/1?scale=4");
    assert.equal(bad.kind === "json" && bad.status, 422);
    assert.equal(detailOf(ask("GET", "/api/invoices/OCT-01/pages/2?view=canonical")), "La factura OCT-01 no tiene página 2.");
  });
});

describe("writes the recording cannot answer", () => {
  const writes: [string, string, string?][] = [
    ["PUT", "/api/rules"],
    ["POST", "/api/beneficiaries"],
    ["POST", "/api/invoices/OCT-08/approve"],
    ["POST", "/api/invoices/OCT-08/reject"],
    ["PUT", "/api/admin/settings"],
    ["POST", "/api/try", "multipart/form-data; boundary=x"],
  ];
  for (const [method, path, contentType] of writes) {
    test(`${method} ${path}${contentType ? " (upload)" : ""} is a 403 that says why`, () => {
      const a = ask(method, path, { contentType, state: "decided" });
      assert.equal(a.kind === "json" && a.status, 403);
      assert.equal(detailOf(a), FROZEN_ES);
      assert.equal(a.next, undefined);
    });
  }
});

describe("Probar", () => {
  test("the samples list is the recorded one with uploads off", () => {
    const a = ask("GET", "/api/try/samples");
    assert.equal(a.kind === "file" && a.entry.file, "try/samples.json");
    assert.deepEqual(a.kind === "file" && a.patch, { live_uploads: false });
  });

  test("patched() replaces only the given fields and keeps the rest as recorded", () => {
    const recorded = '{"live_uploads":true,"upload_limits":{"types":["pdf","png","jpg"],"max_mb":4},"samples":[{"id":"GEN-084-1","title_es":"Factura de rutina en PDF","pages":1,"preview_url":null}]}';
    assert.equal(patched(recorded, { live_uploads: false }), recorded.replace('"live_uploads":true', '"live_uploads":false'));
  });

  test("an upload is still refused while the samples list says uploads are off", () => {
    const a = ask("POST", "/api/try", { contentType: "multipart/form-data; boundary=x" });
    assert.equal(a.kind === "json" && a.status, 403);
  });

  test("a sample starts a job whose events URL names the sample", () => {
    const a = ask("POST", "/api/try", { body: '{"sample_id":"GEN-084-1"}', contentType: "application/json" });
    assert.deepEqual(a, {
      kind: "json",
      status: 202,
      body: { job_id: "GEN-084-1.n0nce123", events_url: "/api/try/GEN-084-1.n0nce123/events" },
      headers: undefined,
    });
  });

  test("an unknown sample is a 404, a body without one a 422", () => {
    assert.equal(detailOf(ask("POST", "/api/try", { body: '{"sample_id":"NOPE"}' })), "No existe la muestra NOPE.");
    const bad = ask("POST", "/api/try", { body: "not json" });
    assert.equal(bad.kind === "json" && bad.status, 422);
    const empty = ask("POST", "/api/try", { body: "{}" });
    assert.equal(empty.kind === "json" && empty.status, 422);
  });

  test("the events URL replays the sample's recorded stream", () => {
    assert.equal(served(ask("GET", "/api/try/GEN-084-1.n0nce123/events")), "stream try/GEN-084-1/events.json");
    assert.equal(served(ask("GET", "/api/try/GEN-084-1/events")), "stream try/GEN-084-1/events.json");
    assert.equal(detailOf(ask("GET", "/api/try/GEN-999-1.x/events")), "No existe la prueba GEN-999-1.x.");
  });

  test("a job id names its sample", () => {
    assert.equal(sampleOf("DUP-GEN-084-1.ab12cd34"), "DUP-GEN-084-1");
    assert.equal(sampleOf("ATK-01-1"), "ATK-01-1");
  });
});

describe("paths and methods the API never had", () => {
  test("an unknown path is a 404 with a detail", () => {
    assert.equal(detailOf(ask("GET", "/api/nada")), "No existe la ruta /api/nada.");
    assert.equal(detailOf(ask("GET", "/api")), "No existe la ruta /api.");
    assert.equal(detailOf(ask("GET", "/api/board/")), "No existe la ruta /api/board/.");
  });

  test("a known path with another method is a 405 listing the allowed ones", () => {
    const a = ask("DELETE", "/api/rules");
    assert.equal(a.kind === "json" && a.status, 405);
    assert.equal(a.kind === "json" && a.headers?.allow, "GET, PUT");
  });

  test("a malformed escape in a path is a 404, not an exception", () => {
    assert.equal(detailOf(ask("GET", "/api/invoices/%E0%A4%A?view=canonical")), "No existe la ruta /api/invoices/%E0%A4%A.");
  });
});

describe("the state cookie", () => {
  test("only alinka_frozen=decided means decided", () => {
    assert.equal(readState(null), "inbox");
    assert.equal(readState("alinka_frozen=decided"), "decided");
    assert.equal(readState("alinka_sandbox=abc; alinka_frozen=decided"), "decided");
    assert.equal(readState("alinka_frozen=other; x=decided"), "inbox");
  });

  test("decided is stored for a day on /api; the inbox clears the cookie", () => {
    assert.equal(stateCookie("decided"), "alinka_frozen=decided; Max-Age=86400; Path=/api; HttpOnly; Secure; SameSite=Lax");
    assert.equal(stateCookie("inbox"), "alinka_frozen=; Max-Age=0; Path=/api; HttpOnly; Secure; SameSite=Lax");
  });
});

describe("the stream replay", () => {
  test("an event is written as FastAPI wrote it", () => {
    assert.equal(sseFrame({ event: "step", data: '{"a":1}', delay_ms: 0 }), 'event: step\ndata: {"a":1}\n\n');
    assert.equal(sseFrame({ event: "done", data: "a\nb", delay_ms: 0, id: "7" }), "event: done\ndata: a\ndata: b\nid: 7\n\n");
  });

  test("the waits keep the recorded pacing and are never negative", () => {
    const at = (...ms: number[]) => ms.map((delay_ms) => ({ event: "step", data: "{}", delay_ms }));
    assert.deepEqual(gaps(at(0, 0, 120, 450, 450, 1000)), [0, 0, 120, 330, 0, 550]);
    assert.deepEqual(gaps(at(30, 10, 40)), [30, 0, 10]);
    assert.deepEqual(gaps([]), []);
  });
});
