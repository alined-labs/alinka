import { useSyncExternalStore } from "react";
import { useSearchParams } from "react-router";

import type { View } from "~/api/client";

/** The Tablero's path. It was "/" until the showcase page took that path on 22 Oct 2026. */
export const BOARD_PATH = "/tablero";

/** The run on screen: the visitor's sandbox (default) or the read-only canonical run (?vista=canonica). */
export function useView(): [View, (view: View) => void] {
  const [params, setParams] = useSearchParams();
  // Prerendered pages are the sandbox view; reading ?vista during hydration would not match them.
  const hydrated = useSyncExternalStore(noop, () => true, () => false);
  const view: View = hydrated && params.get("vista") === "canonica" ? "canonical" : "sandbox";
  const setView = (next: View) =>
    setParams(
      (p) => {
        if (next === "canonical") p.set("vista", "canonica");
        else p.delete("vista");
        return p;
      },
      { replace: true },
    );
  return [view, setView];
}

const noop = () => () => {};
