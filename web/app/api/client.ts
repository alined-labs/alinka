import createClient from "openapi-fetch";

import { createFixtureFetch, loadSamples } from "./fixtures";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Board = Schemas["Board"];
export type Card = Schemas["Card"];
export type Column = Schemas["Column"];
export type View = Board["view"];

export const FIXTURES = import.meta.env.VITE_FIXTURES === "1";

let fixtureFetch: Promise<(req: Request) => Promise<Response>> | undefined;

function send(req: Request): Promise<Response> {
  if (!FIXTURES) return globalThis.fetch(req);
  fixtureFetch ??= loadSamples().then(createFixtureFetch);
  return fixtureFetch.then((f) => f(req));
}

/** The typed API client. Paths in openapi.json already start with /api. */
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "http://localhost",
  credentials: "same-origin",
  fetch: send,
});

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Turns an openapi-fetch result into its data, or throws an ApiError with the API's detail. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (data !== undefined && response.ok) return data;
  throw new ApiError(response.status, errorDetail(error, response.status));
}

/** FastAPI sends `detail` as a string, or as a list of validation errors with a `msg` each. */
export function errorDetail(error: unknown, status: number): string {
  const detail =
    error && typeof error === "object" && "detail" in error
      ? (error as { detail: unknown }).detail
      : undefined;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
  return `Error ${status}`;
}
