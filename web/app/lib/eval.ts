/*
 * evals/report.json arrives untyped (EvalOut.report is a free dict that Lane A writes).
 * readReport checks the shape and returns only what the screen shows; every number is the
 * report's own, this file only reads and formats it.
 */

export type Point = { threshold: number; coverage: number; error: number };
export type SplitRow = { name: string; invoices: number; k: number; K: number; upper: number; rate: number; ceiling: number };
export type EvalView = {
  invoices: number;
  k: number;
  K: number;
  upper: number;
  rate: number;
  ceiling: number;
  autonomous: number | null;
  jevOn: Point[];
  jevOff: Point[];
  jevOffNote: string | null;
  /** verifier_risk_max in data/rules.yaml when the report ran: the threshold R10 uses. */
  inUse: number | null;
  /** The threshold the risk–coverage curve would pick; shown, not applied. */
  suggested: number | null;
  costUsd: number | null;
  p50: number | null;
  p95: number | null;
  securityRecall: { value: number; n: number } | null;
  splits: SplitRow[];
  source: string | null;
  generatedAt: string | null;
};

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

function points(v: unknown): Point[] {
  if (!Array.isArray(v)) return [];
  return v
    .map(obj)
    .filter((p): p is Obj => p !== null)
    .map((p) => ({ threshold: num(p.threshold), coverage: num(p.coverage), error: num(p.error) }))
    .filter((p): p is Point => p.threshold !== null && p.coverage !== null && p.error !== null)
    .sort((a, b) => a.coverage - b.coverage);
}

const SPLIT_LABEL: Record<string, string> = {
  showcase: "Mes típico (octubre)",
  generated: "Generadas",
  attack: "Ataques",
};

export function readReport(report: unknown): EvalView | null {
  const r = obj(report);
  const ia = obj(r?.improper_approvals);
  const au = obj(r?.autonomy);
  const k = num(ia?.k);
  const K = num(ia?.K);
  const upper = num(ia?.upper_95);
  const rate = num(au?.rate);
  const ceiling = num(au?.ceiling);
  const invoices = num(r?.invoices);
  if (!r || k === null || K === null || upper === null || rate === null || ceiling === null || invoices === null) return null;

  const rc = obj(r.risk_coverage);
  const lat = obj(r.latency_ms);
  const sec = obj(obj(obj(r.quality)?.security_recall));
  const splits: SplitRow[] = Object.entries(obj(r.by_split) ?? {}).flatMap(([name, v]) => {
    const s = obj(v);
    const si = obj(s?.improper_approvals);
    const sa = obj(s?.autonomy);
    const row = {
      name: SPLIT_LABEL[name] ?? name,
      invoices: num(s?.invoices),
      k: num(si?.k),
      K: num(si?.K),
      upper: num(si?.upper_95),
      rate: num(sa?.rate),
      ceiling: num(sa?.ceiling),
    };
    return Object.values(row).every((x) => x !== null) ? [row as SplitRow] : [];
  });

  return {
    invoices,
    k,
    K,
    upper,
    rate,
    ceiling,
    autonomous: num(au?.autonomous),
    jevOn: points(rc?.jev_on),
    jevOff: points(rc?.jev_off),
    jevOffNote: str(rc?.jev_off_note),
    inUse: num(obj(r.verifier_risk_max)?.default),
    suggested: num(obj(r.verifier_risk_max)?.chosen),
    costUsd: num(r.cost_usd_per_invoice),
    p50: num(lat?.p50),
    p95: num(lat?.p95),
    securityRecall: num(sec?.all) !== null && num(sec?.all_n) !== null ? { value: num(sec?.all)!, n: num(sec?.all_n)! } : null,
    splits,
    source: str(r.source),
    generatedAt: str(r.generated_at),
  };
}

/** 0.7 -> "0,70" */
export function threshold(x: number): string {
  return x.toFixed(2).replace(".", ",");
}

/** 0.0346 -> "3,5%"; 0.72 -> "72%" (the brief writes "X% de un máximo posible de Y%") */
export function pct(x: number, digits?: number): string {
  const v = x * 100;
  const d = digits ?? (v < 10 ? 1 : 0);
  return `${v.toFixed(d).replace(".", ",")}%`;
}

/** 0.02348 USD -> "2,3 centavos de dólar" */
export function cents(usd: number): string {
  return `${(usd * 100).toFixed(1).replace(".", ",")} centavos de dólar`;
}

/** 16379 ms -> "16,4 s" */
export function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}
