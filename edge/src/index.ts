// alinka-edge: the front end on alinka.alinedlabs.co, and /api/* forwarded to the API on Azure
// Container Apps with the edge secret. Files and prerendered pages come straight from the assets
// layer; this code runs first for /api/* and otherwise only for paths that match no file.

interface Env {
  ASSETS: { fetch(request: Request): Promise<Response> };
  API_ORIGIN: string; // var in wrangler.jsonc: the Container Apps URL
  EDGE_SECRET?: string; // secret: deploy/edge.sh pipes it into wrangler secret put
}

// Headers a client must not choose: the Worker sets the secret and the client IP itself.
const DROPPED = ["host", "x-edge-secret", "x-client-ip", "connection", "keep-alive", "upgrade"];
// React Router writes __spa-fallback.html when "/" is prerendered, else index.html is the shell.
const FALLBACKS = ["/__spa-fallback", "/"];

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      return forward(request, url, env);
    }
    return page(request, url, env);
  },

  // Every 4 minutes (triggers in wrangler.jsonc): one query through the API's health check, so
  // Neon never suspends and the API's pooled connections stay alive between visitors.
  async scheduled(_controller: unknown, env: Env): Promise<void> {
    await fetch(new URL("/api/health", env.API_ORIGIN));
  },
};

async function forward(request: Request, url: URL, env: Env): Promise<Response> {
  if (!env.EDGE_SECRET) {
    return Response.json({ detail: "Servicio no disponible." }, { status: 503 });
  }
  const headers = new Headers(request.headers);
  for (const name of DROPPED) headers.delete(name);
  headers.set("X-Edge-Secret", env.EDGE_SECRET);
  headers.set("X-Client-IP", request.headers.get("CF-Connecting-IP") ?? "");
  const upstream = await fetch(new URL(url.pathname + url.search, env.API_ORIGIN), {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? null : request.body,
    redirect: "manual",
  });
  // The body passes through as a stream, so server-sent events (/api/try/*/events) reach the
  // browser as the API writes them.
  const response = new Response(upstream.body, upstream);
  const location = response.headers.get("Location");
  if (location?.startsWith(env.API_ORIGIN)) {
    // A redirect from the API (say, a trailing slash) must not send the browser to Azure.
    response.headers.set("Location", url.origin + location.slice(env.API_ORIGIN.length));
  }
  if (response.headers.get("Content-Type")?.startsWith("text/event-stream")) {
    response.headers.set("Cache-Control", "no-cache, no-transform");
  }
  return response;
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
