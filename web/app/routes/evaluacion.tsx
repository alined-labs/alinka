import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "~/api/client";
import { cents, type EvalView, pct, type Point, readReport, seconds } from "~/lib/eval";
import { formatDateTime } from "~/lib/format";

export function meta() {
  return [{ title: "Evaluación · Alinka" }];
}

export default function Evaluacion() {
  const query = useQuery({ queryKey: ["eval"], queryFn: () => unwrap(api.GET("/api/eval")) });
  const view = query.data?.available ? readReport(query.data.report) : null;

  return (
    <div className="space-y-6">
      <h1 className="ak-h1">Evaluación</h1>
      {query.isPending && (
        <div className="ak-skel" aria-label="Cargando la evaluación">
          <span />
          <span />
        </div>
      )}
      {query.isError && (
        <p role="alert" className="ak-banner ak-banner--error">
          No se pudo cargar la evaluación: {query.error.message}
        </p>
      )}
      {query.data && !view && (
        <div className="ak-empty">
          <strong>La evaluación aún no está disponible</strong>
          <p>El informe se genera con make eval sobre las ejecuciones grabadas.</p>
        </div>
      )}
      {view && <Report v={view} />}
    </div>
  );
}

function Report({ v }: { v: EvalView }) {
  return (
    <>
      <p className="ak-muted">
        Medido sobre {v.invoices} facturas ficticias, con las respuestas del modelo grabadas y reproducidas. Una aprobación
        indebida es pagar una factura que, según su etiqueta, debía frenarse o escalarse.
      </p>
      <div className="ak-stats">
        <div className="ak-stat">
          Aprobaciones indebidas
          <strong data-testid="improper">
            {v.k} de {v.K}
          </strong>
          <small>cota superior del 95%: {pct(v.upper)}</small>
        </div>
        <div className="ak-stat">
          Autonomía
          <strong data-testid="autonomy">
            {pct(v.rate)} de un máximo posible de {pct(v.ceiling)}
          </strong>
          <small>
            {v.autonomous !== null ? `${v.autonomous} de ${v.invoices} facturas sin intervención humana` : "facturas decididas sin una persona"}
          </small>
        </div>
        {v.costUsd !== null && (
          <div className="ak-stat">
            Costo por factura
            <strong>{cents(v.costUsd)}</strong>
            <small>lectura, segunda lectura y JEV</small>
          </div>
        )}
        {v.p95 !== null && (
          <div className="ak-stat">
            Latencia p95 por factura
            <strong>{seconds(v.p95)}</strong>
            <small>{v.p50 !== null ? `mediana ${seconds(v.p50)}` : "tiempo del modelo"}</small>
          </div>
        )}
        {v.securityRecall && (
          <div className="ak-stat">
            Ataques con alerta de seguridad
            <strong>{pct(v.securityRecall.value)}</strong>
            <small>de {v.securityRecall.n} que debían alertar</small>
          </div>
        )}
      </div>

      <section aria-labelledby="curva" className="ak-stack">
        <h2 id="curva" className="ak-h2">
          Riesgo y cobertura
        </h2>
        <p className="ak-muted">
          Cada punto es un umbral de riesgo del verificador (R10): a la derecha, el agente decide más facturas solo; hacia arriba,
          se equivoca más. Con JEV, cada lectura dudosa se escala.
          {v.chosen !== null && ` Umbral elegido: ${v.chosen.toFixed(2).replace(".", ",")}.`}
        </p>
        <RiskCoverage on={v.jevOn} off={v.jevOff} chosen={v.chosen} />
        {v.jevOffNote && <p className="ak-note">{v.jevOffNote}</p>}
      </section>

      {v.splits.length > 0 && (
        <section aria-labelledby="por-conjunto" className="ak-stack">
          <h2 id="por-conjunto" className="ak-h2">
            Por conjunto
          </h2>
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="ak-log">
              <caption className="ak-sr">Resultados por conjunto de facturas</caption>
              <thead>
                <tr>
                  <th scope="col">Conjunto</th>
                  <th scope="col">Facturas</th>
                  <th scope="col">Aprobaciones indebidas</th>
                  <th scope="col">Autonomía</th>
                </tr>
              </thead>
              <tbody>
                {v.splits.map((s) => (
                  <tr key={s.name}>
                    <td className="font-semibold">{s.name}</td>
                    <td>{s.invoices}</td>
                    <td>
                      {s.k} de {s.K} <span className="ak-note">cota 95%: {pct(s.upper)}</span>
                    </td>
                    <td>
                      {pct(s.rate)} de un máximo posible de {pct(s.ceiling)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <p className="ak-footer">
        {v.source && `Fuente: ${v.source}. `}
        {v.generatedAt && `Generado el ${formatDateTime(v.generatedAt)}.`} Todos los números salen de evals/report.json.
      </p>
    </>
  );
}

const W = 640;
const H = 300;
const PAD = { l: 56, r: 16, t: 16, b: 44 };

function RiskCoverage({ on, off, chosen }: { on: Point[]; off: Point[]; chosen: number | null }) {
  const all = [...on, ...off];
  if (all.length === 0) return <p className="ak-muted">El informe no trae la curva.</p>;
  const step = 0.05;
  const x0 = Math.max(0, Math.floor(Math.min(...all.map((p) => p.coverage)) / step) * step - step);
  const x1 = Math.min(1, Math.ceil(Math.max(...all.map((p) => p.coverage)) / step) * step + step);
  // The error axis ends at the next whole percent, in quarter steps.
  const y1 = Math.max(0.01, Math.ceil(Math.max(...all.map((p) => p.error)) * 100) / 100);
  const sx = (c: number) => PAD.l + ((c - x0) / (x1 - x0)) * (W - PAD.l - PAD.r);
  const sy = (e: number) => H - PAD.b - (e / y1) * (H - PAD.t - PAD.b);
  const path = (ps: Point[]) => ps.map((p, i) => `${i ? "L" : "M"}${sx(p.coverage).toFixed(1)},${sy(p.error).toFixed(1)}`).join(" ");
  const xs = Array.from({ length: Math.round((x1 - x0) / step) + 1 }, (_, i) => x0 + i * step);
  const ys = Array.from({ length: 5 }, (_, i) => (y1 * i) / 4);
  const mark = chosen !== null ? on.find((p) => Math.abs(p.threshold - chosen) < 1e-9) : undefined;
  // Several thresholds can land on the same point; draw each distinct point once.
  const distinct = (ps: Point[]) => [...new Map(ps.map((p) => [`${p.coverage}|${p.error}`, p])).values()];
  const onPts = distinct(on);
  const offPts = distinct(off);

  return (
    <figure className="ak-stack m-0">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="ak-chart w-full max-w-3xl"
        role="img"
        aria-label="Curva de riesgo y cobertura con JEV y sin JEV"
      >
        {xs.map((x) => (
          <g key={`x${x}`}>
            <line className="grid" x1={sx(x)} x2={sx(x)} y1={PAD.t} y2={H - PAD.b} />
            <text x={sx(x)} y={H - PAD.b + 16} textAnchor="middle" fill="currentColor">
              {pct(x, 0)}
            </text>
          </g>
        ))}
        {ys.map((y) => (
          <g key={`y${y}`}>
            <line className="grid" x1={PAD.l} x2={W - PAD.r} y1={sy(y)} y2={sy(y)} />
            <text x={PAD.l - 8} y={sy(y) + 4} textAnchor="end" fill="currentColor">
              {pct(y, 1)}
            </text>
          </g>
        ))}
        <text x={(PAD.l + W - PAD.r) / 2} y={H - 6} textAnchor="middle" fill="currentColor">
          Cobertura: facturas decididas sin una persona
        </text>
        <text x={14} y={(PAD.t + H - PAD.b) / 2} textAnchor="middle" fill="currentColor" transform={`rotate(-90 14 ${(PAD.t + H - PAD.b) / 2})`}>
          Error
        </text>
        {off.length > 0 && <path className="series-b" d={path(off)} />}
        {on.length > 0 && <path className="series-a" d={path(on)} />}
        {offPts.map((p) => (
          <rect key={`b${p.coverage}${p.error}`} className="series-b" x={sx(p.coverage) - 4} y={sy(p.error) - 4} width={8} height={8} />
        ))}
        {onPts.map((p) => (
          <circle key={`a${p.coverage}${p.error}`} className="series-a" cx={sx(p.coverage)} cy={sy(p.error)} r={2.5} />
        ))}
        {mark && <circle className="series-a" cx={sx(mark.coverage)} cy={sy(mark.error)} r={6} />}
      </svg>
      <figcaption className="ak-row text-small text-ink-muted">
        <svg width="28" height="8" aria-hidden className="ak-chart">
          <line className="series-a" x1="0" x2="28" y1="4" y2="4" />
        </svg>
        Con JEV
        <svg width="28" height="8" aria-hidden className="ak-chart ml-4">
          <line className="series-b" x1="0" x2="28" y1="4" y2="4" />
        </svg>
        Sin JEV
        {mark && <span className="ml-4">○ umbral elegido</span>}
      </figcaption>
      {[
        { name: "Sin JEV", pts: offPts },
        { name: "Con JEV", pts: onPts },
      ]
        .filter((s) => s.pts.length === 1)
        .map((s) => (
          <p key={s.name} className="ak-note">
            {s.name}, todos los umbrales dan el mismo punto: cobertura {pct(s.pts[0]!.coverage, 1)}, error {pct(s.pts[0]!.error, 2)}.
          </p>
        ))}
      <details>
        <summary className="cursor-pointer text-small text-ink-muted">Ver los datos de la curva</summary>
        <div className="mt-2 overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="ak-log">
            <thead>
              <tr>
                <th scope="col">Umbral</th>
                <th scope="col">Cobertura con JEV</th>
                <th scope="col">Error con JEV</th>
                <th scope="col">Cobertura sin JEV</th>
                <th scope="col">Error sin JEV</th>
              </tr>
            </thead>
            <tbody>
              {[...new Set(all.map((p) => p.threshold))]
                .sort((a, b) => a - b)
                .map((t) => {
                  const a = on.find((p) => p.threshold === t);
                  const b = off.find((p) => p.threshold === t);
                  return (
                    <tr key={t}>
                      <td>{t.toFixed(2).replace(".", ",")}</td>
                      <td>{a ? pct(a.coverage, 1) : "—"}</td>
                      <td>{a ? pct(a.error, 2) : "—"}</td>
                      <td>{b ? pct(b.coverage, 1) : "—"}</td>
                      <td>{b ? pct(b.error, 2) : "—"}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
