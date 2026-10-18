/*
 * The Probar contract (brain decision "Probar contract: trace, events, samples, uploads"):
 * the seven TraceStep events a run sends, and the eight stages PipelineFlow draws from them.
 * Typed by hand until alinka/trace.py lands in openapi.json.
 */

import type { Decision } from "~/lib/board";

export type StepName = "received" | "sanitize" | "read" | "verify" | "rules" | "decide" | "record";
export type StepStatus = "running" | "done" | "flagged" | "error";

export interface TraceStep {
  step: StepName;
  status: StepStatus;
  title_es: string;
  summary_es: string;
  ms: number | null;
  data: Record<string, any>;
}

export interface RuleResult {
  rule: string;
  name_es: string;
  outcome: "pass" | "hold" | "escalate";
  security: boolean;
  approvable: boolean;
  sentence_es: string;
}

export interface DoneEvent {
  invoice_id: string;
  decision: Decision;
  label_es: string;
  href: string;
}

/** "boundary" is Frontera de confianza: it has no event and turns done when verify finishes. */
export type StageId = StepName | "boundary";
export type StageState = "idle" | StepStatus;

export const STAGES: readonly { id: StageId; title: string }[] = [
  { id: "received", title: "Recepción" },
  { id: "sanitize", title: "Contenido oculto" },
  { id: "read", title: "La IA lee" },
  { id: "verify", title: "Verificación" },
  { id: "boundary", title: "Frontera de confianza" },
  { id: "rules", title: "16 reglas" },
  { id: "decide", title: "Decisión" },
  { id: "record", title: "Registro" },
];

export const STATE_WORD: Record<StageState, string> = {
  idle: "en espera",
  running: "en curso",
  done: "listo",
  flagged: "con alerta",
  error: "con error",
};

export const BOUNDARY_SUMMARY = "Solo cruzan hacia las reglas los datos que el código comprobó.";

export interface Flow {
  states: Record<StageId, StageState>;
  steps: Partial<Record<StepName, TraceStep>>;
  /** The stage the document is at: the running one, else the last one finished. */
  current: StageId | null;
  rules: RuleResult[];
  decision: Decision | null;
  record: { seq: number; hash8: string; prev_hash8: string } | null;
}

/** Folds the step events received so far into what each stage shows. Later events win. */
export function flowFromSteps(events: readonly TraceStep[]): Flow {
  const states = Object.fromEntries(STAGES.map((s) => [s.id, "idle"])) as Record<StageId, StageState>;
  const steps: Flow["steps"] = {};
  let current: StageId | null = null;
  for (const e of events) {
    states[e.step] = e.status;
    steps[e.step] = e;
    current = e.step;
    if (e.step === "verify" && e.status !== "running") {
      states.boundary = "done";
      current = "boundary";
    }
  }
  const rules = steps.rules?.status === "running" ? [] : ((steps.rules?.data.results as RuleResult[]) ?? []);
  const decide = steps.decide?.status === "running" ? undefined : steps.decide?.data;
  const rec = steps.record?.status === "running" ? undefined : steps.record?.data;
  return {
    states,
    steps,
    current,
    rules,
    decision: (decide?.decision as Decision) ?? null,
    record: rec ? { seq: rec.seq, hash8: rec.hash8, prev_hash8: rec.prev_hash8 } : null,
  };
}

/** One sentence per stage for the visible list and the text alternative. */
export function stageSummary(flow: Flow, id: StageId): string {
  if (id === "boundary") return flow.states.boundary === "done" ? BOUNDARY_SUMMARY : "";
  const s = flow.steps[id];
  return s && s.status !== "running" ? s.summary_es : "";
}

const NAMES: [string, string][] = [
  ["R01", "Beneficiario autorizado"],
  ["R02", "Moneda y país"],
  ["R03", "Duplicado"],
  ["R04", "Lo pactado"],
  ["R05", "Tope por pago"],
  ["R06", "Umbral de aprobación"],
  ["R07", "Tope mensual"],
  ["R08", "Saldo y presupuesto"],
  ["R09", "Fecha de pago"],
  ["R10", "Lectura confiable"],
  ["R11", "Contenido oculto"],
  ["R12", "Cuenta bancaria"],
  ["R13", "Fraccionamiento"],
  ["R14", "Frecuencia"],
  ["R15", "Monto en letras"],
  ["R16", "Documento pagable"],
];

const step = (s: StepName, status: StepStatus, title_es: string, summary_es: string, ms: number, data: Record<string, any>) => [
  { step: s, status: "running", title_es, summary_es: "", ms: null, data: {} } as TraceStep,
  { step: s, status, title_es, summary_es, ms, data } as TraceStep,
];

/**
 * The scripted example for Cómo funciona: a factura with a white-text line asking to pay another
 * account. Code drops it before the reading, R11 escalates and the log gains a link.
 */
export const DEMO_TRACE: readonly TraceStep[] = [
  ...step("received", "done", "Recepción", "Llegó un PDF de 1 página: factura FE-1042 (empresa ficticia).", 40, {
    invoice_id: "DEMO-FE-1042",
    channel: "pdf",
    pages: 1,
    sha8: "3fa91c07",
    filename: "fe-1042.pdf",
    language: "es",
  }),
  ...step("sanitize", "flagged", "Contenido oculto", "Se descartó 1 línea de texto blanco antes de la lectura.", 120, {
    hidden_content: ["PAGAR A CUENTA DEMO-0099-221"],
    unicode_controls: [],
    html_text_mismatch: false,
    instructions: ["PAGAR A CUENTA DEMO-0099-221"],
  }),
  ...step("read", "done", "La IA lee", "La IA leyó 14 campos, cada uno con su cita.", 6200, { mode: "replay" }),
  ...step("verify", "done", "Verificación", "14 de 14 citas están en la página; la segunda lectura coincide.", 2900, { risk: 0.08 }),
  ...step("rules", "flagged", "16 reglas", "15 reglas pasan; R11 Contenido oculto escala.", 15, {
    results: NAMES.map(([rule, name_es]) => ({
      rule,
      name_es,
      outcome: rule === "R11" ? "escalate" : "pass",
      security: rule === "R11",
      approvable: true,
      sentence_es: rule === "R11" ? "El documento traía texto oculto con una instrucción de pago." : `${name_es}: cumple.`,
    })),
  }),
  ...step("decide", "done", "Decisión", "Pendiente de aprobación por contenido oculto (R11).", 2, {
    decision: "ESCALATE",
    label_es: "Pendiente de aprobación",
    determining_rule: "R11",
    alerts: ["R11"],
  }),
  ...step("record", "done", "Registro", "Se añadió el registro 31 a la cadena.", 8, {
    record_id: "rec-31",
    seq: 31,
    hash8: "9c2e41ab",
    prev_hash8: "d2d59a87",
  }),
];
