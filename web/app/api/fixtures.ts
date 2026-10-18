/*
 * Fixture mode (VITE_FIXTURES=1): answers /api calls from Lane D's sample responses in
 * alinka/api/fixtures/samples/, so the screens work with no API running.
 * The sandbox is kept in memory: "Ejecutar agente" moves the inbox to the decided board,
 * and "Restablecer sandbox" brings the inbox back.
 */

export type Samples = Record<string, unknown>;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

const notFound = (detail: string) => json({ detail }, 404);

export function createFixtureFetch(samples: Samples) {
  const pick = (name: string) => {
    const body = samples[name];
    if (body === undefined) throw new Error(`fixture sample "${name}" is missing`);
    return structuredClone(body) as Record<string, any>;
  };
  let decided = false;

  const sandboxBoard = () => (decided ? pick("run").board : pick("board_inbox"));

  return async function fixtureFetch(input: Request | string | URL): Promise<Response> {
    const req = input instanceof Request ? input : new Request(input);
    const url = new URL(req.url);
    const view = url.searchParams.get("view") === "canonical" ? "canonical" : "sandbox";
    const path = url.pathname.replace(/\/+$/, "");
    const route = `${req.method} ${path}`;

    if (route === "GET /api/health") return json(pick("health"));
    if (route === "GET /api/board")
      return json(view === "canonical" ? pick("board_canonical") : sandboxBoard());
    if (route === "POST /api/run") {
      decided = true;
      return json(pick("run"));
    }
    if (route === "POST /api/sandbox/reset") {
      decided = false;
      return json(pick("board_inbox"));
    }
    if (route === "GET /api/rules") return json(pick("rules"));
    if (route === "PUT /api/rules") {
      decided = true;
      return json({ rules: pick("rules"), board: sandboxBoard() });
    }
    if (route === "GET /api/log") return json(pick("log"));
    if (route === "GET /api/log/verify") return json(pick("log_verify"));
    if (route === "GET /api/eval") return json(pick("eval"));

    const invoice = path.match(/^\/api\/invoices\/([^/]+)(\/.*)?$/);
    if (invoice) {
      const id = decodeURIComponent(invoice[1] ?? "");
      const rest = invoice[2] ?? "";
      if (req.method === "GET" && rest === "") {
        const detail = pick("invoice_OCT-05");
        return detail.card?.invoice_id === id ? json(detail) : notFound(`Sin muestra para ${id}`);
      }
      if (req.method === "POST" && rest === "/approve") {
        const detail = pick("approve_OCT-03");
        return detail.card?.invoice_id === id ? json(detail) : notFound(`Sin muestra para ${id}`);
      }
      if (req.method === "GET" && rest.startsWith("/pages/"))
        return notFound("Las imágenes de página no están en modo de muestras");
    }
    return notFound(`Sin muestra para ${route}`);
  };
}

/** The samples, loaded only in fixture mode so they never ship in a normal build. */
export async function loadSamples(): Promise<Samples> {
  const modules = import.meta.glob<{ default: unknown }>(
    "../../../alinka/api/fixtures/samples/*.json",
  );
  const entries = await Promise.all(
    Object.entries(modules).map(async ([file, load]) => {
      const name = file.split("/").pop()!.replace(/\.json$/, "");
      return [name, (await load()).default] as const;
    }),
  );
  return Object.fromEntries(entries);
}
