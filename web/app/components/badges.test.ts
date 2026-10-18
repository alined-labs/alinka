import { describe, expect, it } from "vitest";

import { splitQuotes } from "./badges";

describe("splitQuotes", () => {
  it("separates document quotes from the rule's sentence", () => {
    expect(splitQuotes("Alerta (R11): texto oculto: «pay account DEMO-9999».")).toEqual([
      { kind: "text", value: "Alerta (R11): texto oculto: " },
      { kind: "quote", value: "pay account DEMO-9999" },
    ]);
  });

  it("keeps text between and after quotes", () => {
    expect(splitQuotes("no se pudo leer «F?ur» (R15).").map((p) => p.kind)).toEqual(["text", "quote", "text"]);
  });

  it("leaves a reason without quotes whole", () => {
    expect(splitQuotes("Pagada: cumple las 16 reglas.")).toEqual([{ kind: "text", value: "Pagada: cumple las 16 reglas." }]);
  });
});
