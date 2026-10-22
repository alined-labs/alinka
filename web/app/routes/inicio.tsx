import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router";

import { Showcase } from "~/components/showcase";
import type { RouteHandle } from "~/lib/handle";
import { seo } from "~/lib/seo";
import { COPY } from "~/lib/showcase-copy";
import { BOARD_PATH } from "~/lib/view";

/*
 * "/": the showcase page in Spanish. Until 22 Oct 2026 "/" was the Tablero, which now lives at
 * /tablero (BOARD_PATH); links shared before that, such as /?vista=canonica, are sent there.
 */

export const handle: RouteHandle = { lang: "es", bare: true };

export function meta() {
  return seo({ path: "/", lang: "es", description: COPY.es.meta.description, alternates: true });
}

/** Old board links carry ?vista or ?modo; the showcase never does, so they must mean the board. */
function useOldBoardLinks() {
  const { search } = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const params = new URLSearchParams(search);
    if (params.has("vista") || params.has("modo")) navigate({ pathname: BOARD_PATH, search }, { replace: true });
  }, [search, navigate]);
}

export default function Inicio() {
  useOldBoardLinks();
  return <Showcase lang="es" />;
}
