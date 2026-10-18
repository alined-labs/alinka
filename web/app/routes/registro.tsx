import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, Link2, ShieldCheck, ShieldX } from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router";

import { api, FIXTURES, type Schemas, unwrap } from "~/api/client";
import { DecisionChip, ReasonText, RuleChip } from "~/components/badges";
import { formatDateTime } from "~/lib/format";
import { useMotionOK } from "~/lib/motion";
import { seo } from "~/lib/seo";
import { useView } from "~/lib/view";

export function meta() {
  return seo({
    path: "/registro",
    title: "Registro",
    description:
      "El registro encadenado de cada decisión, con su regla, su motivo y su hash. Verifica la cadena y exporta el CSV para conciliar.",
  });
}

type ChainCheck = Schemas["ChainCheck"];

function Hash({ value, label }: { value: string | null | undefined; label: string }) {
  if (!value) return <span className="ak-muted">—</span>;
  return (
    <span className="ak-hash" title={`${label}: ${value}`}>
      <Link2 aria-hidden className="ak-icon" />
      <span aria-hidden className="lg:hidden">{value.slice(0, 6)}…</span>
      <span aria-hidden className="max-lg:hidden">{value.slice(0, 10)}</span>
      <span className="ak-sr">
        {label}: {value}
      </span>
    </span>
  );
}

function Verdict({ check }: { check: ChainCheck }) {
  return (
    <p className={`ak-verify ${check.ok ? "ak-verify--ok" : "ak-verify--roto"}`} role="status">
      {check.ok ? <ShieldCheck aria-hidden className="ak-icon" /> : <ShieldX aria-hidden className="ak-icon" />}
      {check.message_es}
      {!check.ok && check.first_bad_seq != null && ` Primer registro roto: n.º ${check.first_bad_seq}.`}
    </p>
  );
}

export default function Registro() {
  const [view] = useView();
  const motion = useMotionOK();
  const log = useQuery({
    queryKey: ["log", view],
    queryFn: () => unwrap(api.GET("/api/log", { params: { query: { view } } })),
  });
  const verify = useMutation({
    mutationFn: () => unwrap(api.GET("/api/log/verify", { params: { query: { view } } })),
  });
  // A verdict belongs to one chain: forget it when the view or the head changes.
  useEffect(() => verify.reset(), [view, log.data?.head_hash]);
  const search = view === "canonical" ? "?vista=canonica" : "";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="ak-h1">Registro</h1>
        <div className="ak-row">
          <button type="button" className="ak-btn ak-btn--primary" onClick={() => verify.mutate()} disabled={verify.isPending || !log.data}>
            <ShieldCheck aria-hidden className="ak-icon" />
            Verificar cadena
          </button>
          <a
            className="ak-btn ak-btn--secondary"
            href={`/api/log/export.csv?view=${view}`}
            download
            aria-disabled={FIXTURES || undefined}
            onClick={(e) => FIXTURES && e.preventDefault()}
            title={FIXTURES ? "No disponible en modo de muestras" : undefined}
          >
            <Download aria-hidden className="ak-icon" />
            Exportar CSV
          </a>
        </div>
      </div>
      <p className="ak-muted">
        Cada decisión queda encadenada a la anterior con su hash: cambiar un solo byte de un registro rompe la cadena desde ahí.
        El CSV sirve para conciliar.
      </p>
      {verify.data && <Verdict check={verify.data} />}
      {verify.isError && (
        <p role="alert" className="ak-banner ak-banner--error">
          No se pudo verificar la cadena: {verify.error.message}
        </p>
      )}
      {log.isPending && (
        <div className="ak-skel" aria-label="Cargando el registro">
          <span />
          <span />
          <span />
        </div>
      )}
      {log.isError && (
        <p role="alert" className="ak-banner ak-banner--error">
          No se pudo cargar el registro: {log.error.message}
        </p>
      )}
      {log.data && log.data.entries.length === 0 && (
        <div className="ak-empty">
          <strong>Todavía no hay decisiones</strong>
          <p>Ejecuta el agente en el tablero y cada decisión aparecerá aquí, en orden.</p>
        </div>
      )}
      {log.data && log.data.entries.length > 0 && (
        <>
          <p className="text-small text-ink-muted">
            {log.data.entries.length} registros · último hash <Hash value={log.data.head_hash} label="Hash del último registro" />
          </p>
          {/* Below 768 px each record is a card, so the reason gets the full width. */}
          <ol className="grid gap-3 md:hidden" aria-label="Registro encadenado">
            {log.data.entries.map((e) => (
              <li key={e.record_id} className="grid gap-1.5 rounded-xl border border-line bg-surface p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <Link
                    to={{ pathname: `/facturas/${encodeURIComponent(e.invoice_id)}`, search }}
                    className="font-mono underline underline-offset-2"
                    viewTransition={motion}
                  >
                    n.º {e.seq} · {e.invoice_id}
                  </Link>
                  <span className="text-small text-ink-muted">{formatDateTime(e.created_at)}</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  <DecisionChip decision={e.decision} />
                  {e.determining_rule && <RuleChip rule={e.determining_rule} decision={e.decision} />}
                </div>
                {/* Three lines here; the invoice's page has the full reason. */}
                <p className="ak-muted line-clamp-3 text-small">{e.reason_es}</p>
                {e.approver && <p className="text-small">Aprobó: {e.approver}</p>}
                <p className="ak-note">
                  <Hash value={e.hash} label="Hash" /> · anterior <Hash value={e.prev_hash} label="Hash anterior" />
                </p>
              </li>
            ))}
          </ol>
          {/* Below 1024 px the log scrolls in its own box; relative keeps the sr-only text inside it. */}
          <div
            className="relative overflow-x-auto max-md:hidden rounded-xl border border-line bg-surface max-lg:max-h-[70vh] max-lg:overflow-y-auto"
            tabIndex={0}
            role="region"
            aria-label="Registro encadenado"
          >
            <table className="ak-log">
              <caption className="ak-sr">Registro encadenado de decisiones, en orden</caption>
              <thead className="sticky top-0 z-[1] bg-surface">
                <tr>
                  <th scope="col">N.º</th>
                  <th scope="col">Factura</th>
                  <th scope="col">Decisión</th>
                  <th scope="col">Motivo</th>
                  <th scope="col">Aprobó</th>
                  <th scope="col">Fecha</th>
                  <th scope="col">Hash</th>
                </tr>
              </thead>
              <tbody>
                {log.data.entries.map((e) => (
                  <tr key={e.record_id}>
                    <td className="font-mono">{e.seq}</td>
                    <td>
                      <Link
                        to={{ pathname: `/facturas/${encodeURIComponent(e.invoice_id)}`, search }}
                        className="font-mono whitespace-nowrap underline underline-offset-2"
                        viewTransition={motion}
                      >
                        {e.invoice_id}
                      </Link>
                    </td>
                    <td>
                      <span className="grid justify-items-start gap-1">
                        <DecisionChip decision={e.decision} />
                        {e.determining_rule && <RuleChip rule={e.determining_rule} decision={e.decision} />}
                      </span>
                    </td>
                    <td className="min-w-64">
                      <ReasonText text={e.reason_es} className="ak-muted" />
                    </td>
                    <td>{e.approver ?? <span className="ak-muted">—</span>}</td>
                    <td className="whitespace-nowrap">{formatDateTime(e.created_at)}</td>
                    <td>
                      <span className="grid gap-1">
                        <Hash value={e.hash} label="Hash" />
                        <span className="ak-note">
                          anterior <Hash value={e.prev_hash} label="Hash anterior" />
                        </span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
