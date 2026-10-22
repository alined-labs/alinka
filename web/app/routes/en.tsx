import { Showcase } from "~/components/showcase";
import type { RouteHandle } from "~/lib/handle";
import { seo } from "~/lib/seo";
import { COPY } from "~/lib/showcase-copy";

/*
 * "/en": the showcase page in English, for readers who don't speak Spanish. The app screens it
 * links to stay in Spanish, as the hackathon built them; the page says so beside each link.
 */

export const handle: RouteHandle = { lang: "en", bare: true };

export function meta() {
  return seo({ path: "/en", lang: "en", description: COPY.en.meta.description, alternates: true });
}

export default function En() {
  return <Showcase lang="en" />;
}
