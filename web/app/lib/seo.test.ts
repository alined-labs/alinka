import { readFileSync, statSync } from "node:fs";

import { describe, expect, it } from "vitest";

import routes from "~/routes";

import { JSON_LD, OG_IMAGE, PUBLIC_PATHS, SITE, seo } from "./seo";

const read = (path: string) => readFileSync(new URL(`../../public/${path}`, import.meta.url), "utf8");

/** The paths routes.ts defines without parameters: what the build can prerender. */
const staticPaths = routes.filter((r) => !r.path?.includes(":")).map((r) => (r.index ? "/" : `/${r.path}`));

describe("seo", () => {
  it("returns the full set of tags for a page", () => {
    const tags = seo({ path: "/registro", title: "Registro", description: "Texto." });
    const by = (key: string, value: string) => tags.find((t) => (t as Record<string, unknown>)[key] === value);
    expect(tags).toContainEqual({ title: "Registro · Alinka" });
    expect(by("rel", "canonical")).toMatchObject({ href: `${SITE}/registro` });
    expect(by("property", "og:url")).toMatchObject({ content: `${SITE}/registro` });
    expect(by("property", "og:locale")).toMatchObject({ content: "es_CO" });
    expect(by("property", "og:image")).toMatchObject({ content: OG_IMAGE.url });
    expect(OG_IMAGE.url).toMatch(/^https:\/\//);
    expect(by("property", "og:image:alt")).toBeDefined();
    expect(by("name", "twitter:card")).toMatchObject({ content: "summary_large_image" });
    expect(JSON.parse(JSON_LD)).toMatchObject({ "@type": "SoftwareApplication", url: `${SITE}/` });
  });

  it("links the two showcase pages to each other and localizes the English one", () => {
    const tags = seo({ path: "/en", lang: "en", alternates: true });
    const alternates = tags.filter((t) => (t as Record<string, unknown>).rel === "alternate");
    expect(alternates).toEqual([
      { tagName: "link", rel: "alternate", hrefLang: "es", href: `${SITE}/` },
      { tagName: "link", rel: "alternate", hrefLang: "en", href: `${SITE}/en` },
      { tagName: "link", rel: "alternate", hrefLang: "x-default", href: `${SITE}/` },
    ]);
    expect(tags).toContainEqual({ property: "og:locale", content: "en_US" });
    expect(tags).toContainEqual({ property: "og:locale:alternate", content: "es_CO" });
    expect(tags).toContainEqual({ title: "Alinka · Accounts payable with rules and a log" });
    // The app screens stay Spanish and carry no alternates.
    expect(seo({ path: "/tablero", title: "Tablero" }).some((t) => (t as Record<string, unknown>).rel === "alternate")).toBe(false);
  });

  it("lists every prerendered route in the sitemap, and nothing else", () => {
    const listed = [...read("sitemap.xml").matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]!.replace(SITE, ""));
    const prerendered = PUBLIC_PATHS.filter((p) => staticPaths.includes(p));
    expect(listed.sort()).toEqual([...prerendered].sort());
  });

  it("points robots.txt at the sitemap", () => {
    expect(read("robots.txt")).toContain(`Sitemap: ${SITE}/sitemap.xml`);
  });

  it("keeps og.png under 300 KB, the WhatsApp limit", () => {
    expect(statSync(new URL("../../public/og.png", import.meta.url)).size).toBeLessThan(300 * 1024);
  });
});
