import { describe, expect, it } from "vitest";

import { COPY, FACTS, formats, type Lang } from "./showcase-copy";

/*
 * The showcase page in two languages: the versions must say the same things in the same places,
 * and every figure must match EVAL_REPORT.md exactly as FACTS records it.
 */

const LANGS: Lang[] = ["es", "en"];

/** The copy's structure with every string blanked: what both languages must share. */
function shape(value: unknown): unknown {
  if (typeof value === "string") return "string";
  if (Array.isArray(value)) return value.map(shape);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, shape(v)]));
  }
  return value;
}

describe("showcase copy", () => {
  it("has the same shape in Spanish and English", () => {
    expect(shape(COPY.en)).toEqual(shape(COPY.es));
  });

  it("links each language to the other", () => {
    expect(COPY.es.nav.switchHref).toBe("/en");
    expect(COPY.es.nav.switchLang).toBe("en");
    expect(COPY.en.nav.switchHref).toBe("/");
    expect(COPY.en.nav.switchLang).toBe("es");
  });

  it.each(LANGS)("gives every spec row a label, a value and a note (%s)", (lang) => {
    for (const row of COPY[lang].spec.rows) {
      expect(row.label && row.value && row.note, row.label).toBeTruthy();
    }
  });

  it("quotes the evaluation's headline figures", () => {
    expect(COPY.es.hero.figure).toBe("0");
    expect(COPY.es.hero.headline).toContain(`${FACTS.mustNotPay} facturas`);
    expect(COPY.en.hero.headline).toContain(`${FACTS.mustNotPay} invoices`);
    const autonomy = COPY.en.spec.rows.find((r) => r.label === "Decided without a person");
    expect(autonomy?.value).toBe("124 of 175 (71%)");
    expect(COPY.en.spec.rows.find((r) => r.label === "Cost per invoice")?.value).toBe("US$0.023");
  });

  it("formats numbers the way each language writes them", () => {
    const es = formats("es");
    const en = formats("en");
    // Colombian Spanish writes no space before % (CLDR es-CO), like the rest of the site.
    expect(es.pct(0.035, 1)).toBe("3,5%");
    expect(en.pct(0.035, 1)).toBe("3.5%");
    expect(es.secs(11.44)).toBe("11,4\u00a0s");
    expect(en.usd(0.02348)).toBe("US$0.023");
  });

  it("states the frozen demo's scope in both languages", () => {
    expect(COPY.es.demo.text).toContain("22 de octubre de 2026");
    expect(COPY.en.demo.text).toContain("October 22, 2026");
    expect(COPY.es.demo.callouts).toHaveLength(3);
  });
});
