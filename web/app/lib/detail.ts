import type { Schemas } from "~/api/client";

export type Detail = Schemas["InvoiceDetail"];
export type FieldView = Schemas["FieldView"];
export type RuleView = Schemas["RuleView"];
export type JevAnswer = Schemas["JevAnswer"];

export type Check = { label: string; ok: boolean };

const pct = (p: number) => p.toFixed(2).replace(".", ",");

/** The JEV verdict for one field: J2.<field> asks "was it misread?", J1a/J1b read the total twice. */
export function jevCheck(field: FieldView, jev: readonly JevAnswer[]): Check | null {
  const j2 = jev.find((j) => j.question === `J2.${field.name}`);
  if (field.name === "total") {
    const j1 = jev.filter((j) => j.question.startsWith("J1"));
    const split = j1.length >= 2 && new Set(j1.map((j) => j.answer)).size > 1;
    if (split) return { label: "JEV: las dos lecturas del total difieren", ok: false };
    if (!j2 && j1.length === 0) return null;
  } else if (!j2) {
    return null;
  }
  if (j2 && j2.answer === "yes") return { label: `JEV: duda (${pct(j2.probability)})`, ok: false };
  return { label: "JEV", ok: true };
}

/** Each field's evidence: its quote on the page, the second reading, and JEV when it ran. */
export function fieldChecks(field: FieldView, jev: readonly JevAnswer[]): Check[] {
  const checks: Check[] = [
    field.grounded ? { label: "Cita en la página", ok: true } : { label: "Cita no encontrada en la página", ok: false },
  ];
  if (field.agreed === true) checks.push({ label: "Segunda lectura coincide", ok: true });
  else if (field.agreed === false) checks.push({ label: "Segunda lectura difiere", ok: false });
  const j = jevCheck(field, jev);
  if (j) checks.push(j);
  return checks;
}

/** Rules for the detail: security alerts first, then the others that fired, then those that passed. */
export function orderRules(rules: readonly RuleView[], alerts: readonly string[]): {
  fired: RuleView[];
  passed: RuleView[];
} {
  const isAlert = (r: RuleView) => alerts.includes(r.rule) || (r.security && r.outcome !== "pass");
  const fired = rules.filter((r) => r.outcome !== "pass");
  return {
    fired: [...fired.filter(isAlert), ...fired.filter((r) => !isAlert(r))],
    passed: rules.filter((r) => r.outcome === "pass"),
  };
}

/** Field.boxes are 0..1 of the page; the kit places them with percentages. */
export function boxStyle(b: { x0: number; y0: number; x1: number; y1: number }) {
  const p = (v: number) => `${Math.round(v * 1e6) / 1e4}%`;
  return { left: p(b.x0), top: p(b.y0), width: p(b.x1 - b.x0), height: p(b.y1 - b.y0) };
}
