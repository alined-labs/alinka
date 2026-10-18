import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import createClient from "openapi-fetch";
import { describe, expect, it } from "vitest";

import { errorDetail } from "./client";
import { createFixtureFetch } from "./fixtures";
import type { paths } from "./schema";

const DIR = join(import.meta.dirname, "../../../alinka/api/fixtures/samples");
const samples = Object.fromEntries(
  readdirSync(DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => [f.replace(/\.json$/, ""), JSON.parse(readFileSync(join(DIR, f), "utf8"))]),
);

const client = () =>
  createClient<paths>({ baseUrl: "http://fixtures.invalid", fetch: createFixtureFetch(samples) });

describe("fixture mode", () => {
  it("starts with the inbox and decides it on run", async () => {
    const api = client();
    const before = await api.GET("/api/board");
    expect(before.data?.inbox.length).toBeGreaterThan(0);
    expect(before.data?.columns.map((c) => c.count)).toEqual([0, 0, 0]);

    const run = await api.POST("/api/run");
    expect(run.data?.decided).toBe(before.data?.inbox.length);

    const after = await api.GET("/api/board");
    const counts = after.data?.columns.reduce((n, c) => n + c.count, 0);
    expect(after.data?.inbox).toEqual([]);
    expect(counts).toBe(before.data?.total);
  });

  it("serves the canonical view and resets the sandbox", async () => {
    const api = client();
    await api.POST("/api/run");
    const canonical = await api.GET("/api/board", { params: { query: { view: "canonical" } } });
    expect(canonical.data?.view).toBe("canonical");
    const reset = await api.POST("/api/sandbox/reset");
    expect(reset.data?.inbox.length).toBeGreaterThan(0);
  });

  it("answers 404 with a detail for an unknown route or invoice", async () => {
    const api = client();
    const res = await api.GET("/api/invoices/{invoice_id}", { params: { path: { invoice_id: "NOPE" } } });
    expect(res.response.status).toBe(404);
    expect(res.error).toMatchObject({ detail: expect.any(String) });
  });

  it("covers every sample the API writes", () => {
    for (const name of ["health", "board_inbox", "board_canonical", "run", "rules", "log", "log_verify", "eval"])
      expect(samples).toHaveProperty(name);
  });
});

describe("errorDetail", () => {
  it("reads a string detail and a validation list", () => {
    expect(errorDetail({ detail: "No se puede aprobar" }, 409)).toBe("No se puede aprobar");
    expect(errorDetail({ detail: [{ msg: "a" }, { msg: "b" }] }, 422)).toBe("a; b");
    expect(errorDetail(undefined, 500)).toBe("Error 500");
  });
});
