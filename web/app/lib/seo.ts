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
export const PUBLIC_PATHS = [
  "/",
  "/en",
  "/tablero",
  "/probar",
  "/como-funciona",
  "/evaluacion",
  "/registro",
  "/reglas",
] as const;

/** The showcase page in each language, linked to each other with hreflang alternates. */
const SHOWCASE_PATHS = { es: "/", en: "/en" } as const;

/** Per-language defaults: the title a page gets without one of its own, and the Open Graph locale. */
const LOCALES = {
  es: { title: `${SITE_NAME} · Cuentas por pagar con reglas y registro`, og: "es_CO" },
  en: { title: `${SITE_NAME} · Accounts payable with rules and a log`, og: "en_US" },
} as const;

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

/**
 * The SoftwareApplication JSON-LD, the same on every page. root.tsx writes it once in <head>:
 * as a route meta tag React would re-create the <script> on each navigation and warn.
 */
export const JSON_LD = JSON.stringify(APP_LD).replace(/</g, "\\u003c");

type Page = {
  path: string;
  title?: string;
  description?: string;
  /** The page's language; Spanish unless it says otherwise (only /en does). */
  lang?: keyof typeof LOCALES;
  /** True on the showcase pages: adds hreflang links to both language versions. */
  alternates?: boolean;
};

/**
 * Every tag a page needs. A route's meta replaces its parent's, so each route returns the
 * full set from here: title, description, canonical, Open Graph and Twitter, plus the hreflang
 * alternates on the two showcase pages.
 */
export function seo({ path, title, description = DESCRIPTION, lang = "es", alternates = false }: Page): MetaDescriptor[] {
  const locale = LOCALES[lang];
  const fullTitle = title ? `${title} · ${SITE_NAME}` : locale.title;
  const url = `${SITE}${path}`;
  const hreflang: MetaDescriptor[] = alternates
    ? [
        ...Object.entries(SHOWCASE_PATHS).map(([code, href]) => ({
          tagName: "link" as const,
          rel: "alternate",
          hrefLang: code,
          href: `${SITE}${href}`,
        })),
        { tagName: "link", rel: "alternate", hrefLang: "x-default", href: `${SITE}${SHOWCASE_PATHS.es}` },
        { property: "og:locale:alternate", content: LOCALES[lang === "es" ? "en" : "es"].og },
      ]
    : [];
  return [
    { title: fullTitle },
    { name: "description", content: description },
    { tagName: "link", rel: "canonical", href: url },
    ...hreflang,
    { property: "og:type", content: "website" },
    { property: "og:site_name", content: SITE_NAME },
    { property: "og:title", content: fullTitle },
    { property: "og:description", content: description },
    { property: "og:url", content: url },
    { property: "og:locale", content: locale.og },
    { property: "og:image", content: OG_IMAGE.url },
    { property: "og:image:width", content: String(OG_IMAGE.width) },
    { property: "og:image:height", content: String(OG_IMAGE.height) },
    { property: "og:image:alt", content: OG_IMAGE.alt },
    { name: "twitter:card", content: "summary_large_image" },
    { name: "twitter:title", content: fullTitle },
    { name: "twitter:description", content: description },
    { name: "twitter:image", content: OG_IMAGE.url },
    { name: "twitter:image:alt", content: OG_IMAGE.alt },
  ];
}
