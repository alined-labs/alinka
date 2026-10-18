import type { Config } from "@react-router/dev/config";

import { PUBLIC_PATHS } from "./app/lib/seo";

export default {
  // No server: the API is a separate service behind /api.
  ssr: false,
  // The public routes are rendered to HTML at build time, so crawlers and link previews get
  // their tags without JavaScript. Because "/" is among them, every other path (an invoice
  // detail) is served build/client/__spa-fallback.html. A public route not yet in routes.ts
  // is skipped until it exists.
  async prerender({ getStaticPaths }) {
    const known = new Set(getStaticPaths());
    return PUBLIC_PATHS.filter((p) => known.has(p));
  },
} satisfies Config;
