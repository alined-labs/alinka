import { describe, expect, it } from "vitest";

import { boxStyle, fieldChecks, type FieldView, jevCheck, orderRules, type RuleView } from "./detail";

const field = (over: Partial<FieldView> = {}): FieldView => ({
  name: "invoice_number",
  label_es: "Número de factura",
  value: "HLS-2026-09",
  quote: "Invoice # HLS-2026-09",
  confidence: "high",
  grounded: true,
  agreed: true,
  critical: true,
  boxes: [],
  ...over,
});

const rule = (id: RuleView["rule"], outcome: RuleView["outcome"], security = false): RuleView => ({
  rule: id,
  name_es: id,
  outcome,
  security,
  approvable: true,
  values: {},
  reason_es: "",
});

describe("fieldChecks", () => {
  it("lists the quote, the second reading and JEV", () => {
    const checks = fieldChecks(field(), [{ question: "J2.invoice_number", answer: "no", probability: 0.02 }]);
    expect(checks).toEqual([
      { label: "Cita en la página", ok: true },
      { label: "Segunda lectura coincide", ok: true },
      { label: "JEV", ok: true },
    ]);
  });

  it("warns when the quote is missing, the readings differ or JEV doubts", () => {
    const checks = fieldChecks(field({ grounded: false, agreed: false }), [
      { question: "J2.invoice_number", answer: "yes", probability: 0.31 },
    ]);
    expect(checks.every((c) => !c.ok)).toBe(true);
    expect(checks[2]?.label).toBe("JEV: duda (0,31)");
  });

  it("skips the second reading and JEV when they did not run", () => {
    expect(fieldChecks(field({ agreed: null }), [])).toEqual([{ label: "Cita en la página", ok: true }]);
  });
});

describe("jevCheck on the total", () => {
  it("warns when the two readings of the total differ", () => {
    const check = jevCheck(field({ name: "total" }), [
      { question: "J1a", answer: "2.400,00", probability: 1 },
      { question: "J1b", answer: "4.200,00", probability: 1 },
    ]);
    expect(check?.ok).toBe(false);
  });
});

describe("orderRules", () => {
  it("puts security alerts first and passes last", () => {
    const rules = [rule("R01", "pass"), rule("R06", "escalate"), rule("R11", "escalate", true), rule("R12", "pass", true)];
    const { fired, passed } = orderRules(rules, ["R11"]);
    expect(fired.map((r) => r.rule)).toEqual(["R11", "R06"]);
    expect(passed.map((r) => r.rule)).toEqual(["R01", "R12"]);
  });
});

describe("boxStyle", () => {
  it("turns a 0..1 box into percentages", () => {
    expect(boxStyle({ x0: 0.1, y0: 0.2, x1: 0.5, y1: 0.25 })).toEqual({ left: "10%", top: "20%", width: "40%", height: "5%" });
  });
});
