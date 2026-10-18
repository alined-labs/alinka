import { FIXTURES, type View } from "~/api/client";
import type { Decision } from "~/lib/board";
import type { RuleResult, StepName, TraceStep } from "~/lib/trace";

/*
 * The data of each finished TraceStep, as the "Probar contract" decision lists it, for the
 * Detalle's "Cómo se decidió". TraceStep itself is in ~/lib/trace (shared with Probar).
 */

type Box = { page: number; x0: number; y0: number; x1: number; y1: number };

export type Call = { role: "reader" | "checker" | "jev"; model: string; cached: boolean; cost_usd: number; latency_ms: number };
export type ReadField = { value: string | null; quote: string | null; confidence: "high" | "medium" | "low" };
export type CheckedField = { grounded: boolean; agreed: boolean | null; boxes: Box[] };
export type StepData = {
  received: { invoice_id: string; channel: string; pages: number; sha8: string; filename: string; language: "es" | "en" | null };
  sanitize: { hidden_content: string[]; unicode_controls: string[]; html_text_mismatch: boolean; instructions: string[] };
  read: {
    mode: "replay" | "live";
    calls: Call[];
    fields: Record<string, ReadField>;
    stamps: string[];
    instructions_seen: string[];
    error: string | null;
  };
  verify: {
    calls: Call[];
    fields: Record<string, CheckedField>;
    ungrounded: string[];
    disagreements: string[];
    amount_in_regex: boolean | null;
    totals_reconcile: boolean | null;
    jev: { question: string; answer: string; probability: number }[];
    risk: number;
    risk_max: number;
  };
  rules: { results: RuleResult[] };
  decide: {
    decision: Decision;
    label_es: string;
    determining_rule: string | null;
    alerts: string[];
    reason_es: string;
    payment: unknown;
  };
  record: { record_id: string; seq: number; hash8: string; prev_hash8: string };
};


export const STEP_ORDER: StepName[] = ["received", "sanitize", "read", "verify", "rules", "decide", "record"];

/** A finished step carries its data; a running one has {}. */
export const hasData = (s: TraceStep) => s.status !== "running" && Object.keys(s.data).length > 0;

/** The typed data of a finished step. */
export const dataOf = <S extends StepName>(s: TraceStep, _step: S) => s.data as StepData[S];

/**
 * The stored trace from GET /api/invoices/{id}/trace (Lane C, #79), or null when the invoice has
 * none yet. Fixture mode has no trace: the timeline keeps its summary entries.
 */
export async function fetchTrace(id: string, view: View): Promise<TraceStep[] | null> {
  if (FIXTURES) return null;
  const res = await fetch(`/api/invoices/${encodeURIComponent(id)}/trace?view=${view}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof body?.detail === "string" ? body.detail : `Error ${res.status}`);
  }
  return sortSteps((await res.json()) as TraceStep[]);
}

export function sortSteps(steps: TraceStep[]): TraceStep[] {
  return [...steps].sort((a, b) => STEP_ORDER.indexOf(a.step) - STEP_ORDER.indexOf(b.step));
}

export function formatMs(ms: number | null): string | null {
  if (ms === null) return null;
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}
