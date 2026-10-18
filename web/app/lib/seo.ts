import type { MetaDescriptor } from "react-router";

/** The public site. Prerendered pages, the sitemap and Open Graph all use this origin. */
export const SITE = "https://alinka.alinedlabs.co";
export const SITE_NAME = "Alinka";
export const DESCRIPTION =
  "Agente de cuentas por pagar: lee facturas, pagos y chats, paga solo lo que las reglas permiten, frena o escala el resto con su motivo y deja un registro encadenado. Datos ficticios.";
export const OG_IMAGE = {
  url: `${SITE}/og.png`,
  width: 1200,
  height: 630,
  alt: "Alinka: La IA lee. Las reglas deciden. El registro explica. Con los estados Pagada, Frenada y Pendiente de aprobación.",
};

/** The public routes: prerendered at build time and listed in sitemap.xml. */
export const PUBLIC_PATHS = ["/", "/probar", "/como-funciona", "/evaluacion", "/registro", "/reglas"] as const;

const APP_LD = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: SITE_NAME,
  url: `${SITE}/`,
  description: DESCRIPTION,
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  inLanguage: "es",
  image: OG_IMAGE.url,
  license: "https://www.gnu.org/licenses/agpl-3.0.html",
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
};

type Page = { path: string; title?: string; description?: string };

/**
 * Every tag a page needs. A route's meta replaces its parent's, so each route returns the
 * full set from here: title, description, canonical, Open Graph, Twitter and JSON-LD.
 */
export function seo({ path, title, description = DESCRIPTION }: Page): MetaDescriptor[] {
  const fullTitle = title ? `${title} · ${SITE_NAME}` : `${SITE_NAME} · Cuentas por pagar con reglas y registro`;
  const url = `${SITE}${path}`;
  return [
    { title: fullTitle },
    { name: "description", content: description },
    { tagName: "link", rel: "canonical", href: url },
    { property: "og:type", content: "website" },
    { property: "og:site_name", content: SITE_NAME },
    { property: "og:title", content: fullTitle },
    { property: "og:description", content: description },
    { property: "og:url", content: url },
    { property: "og:locale", content: "es_CO" },
    { property: "og:image", content: OG_IMAGE.url },
    { property: "og:image:width", content: String(OG_IMAGE.width) },
    { property: "og:image:height", content: String(OG_IMAGE.height) },
    { property: "og:image:alt", content: OG_IMAGE.alt },
    { name: "twitter:card", content: "summary_large_image" },
    { name: "twitter:title", content: fullTitle },
    { name: "twitter:description", content: description },
    { name: "twitter:image", content: OG_IMAGE.url },
    { name: "twitter:image:alt", content: OG_IMAGE.alt },
    { "script:ld+json": APP_LD },
  ];
}
