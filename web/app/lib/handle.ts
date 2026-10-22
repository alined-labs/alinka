import { useMatches } from "react-router";

/**
 * What a route module can tell root.tsx about the page around it, through its `handle` export.
 * `lang` sets <html lang> (Spanish unless a route says otherwise); `bare` leaves out the app's
 * shell (header, demo banner and footer), which the showcase pages replace with their own.
 */
export interface RouteHandle {
  lang?: "es" | "en";
  bare?: boolean;
}

/** The handles of every matched route merged, the deepest winning. */
export function useRouteHandle(): RouteHandle {
  const matches = useMatches();
  return Object.assign({}, ...matches.map((m) => (m.handle ?? {}) as RouteHandle));
}
