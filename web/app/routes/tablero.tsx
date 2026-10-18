import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";

import { api, type Card, type Column, unwrap } from "~/api/client";
import { formatMoney } from "~/lib/format";

export function meta() {
  return [{ title: "Tablero · Alinka" }];
}

const TONE: Record<Column["decision"], string> = {
  PAY: "border-pay bg-pay-bg",
  HOLD: "border-hold bg-hold-bg",
  ESCALATE: "border-escalate bg-escalate-bg",
};

function CardItem({ card }: { card: Card }) {
  return (
    <li className="rounded-md border border-border bg-surface p-3 shadow-card">
      <p className="flex justify-between text-sm font-medium">
        <span>{card.invoice_id}</span>
        <span>{formatMoney(card.amount_minor, card.currency)}</span>
      </p>
      <p className="text-sm text-muted">{card.beneficiary_name ?? "Beneficiario no identificado"}</p>
      {card.reason_es && <p className="mt-1 text-sm">{card.reason_es}</p>}
    </li>
  );
}

export default function Tablero() {
  const qc = useQueryClient();
  const board = useQuery({ queryKey: ["board", "sandbox"], queryFn: () => unwrap(api.GET("/api/board")) });
  const run = useMutation({
    mutationFn: () => unwrap(api.POST("/api/run")),
    onSuccess: (result) => qc.setQueryData(["board", "sandbox"], result.board),
  });

  if (board.isPending) return <p className="text-muted">Cargando el tablero…</p>;
  if (board.isError) return <p role="alert">No se pudo cargar el tablero: {board.error.message}</p>;
  const data = board.data;

  return (
    <div className="mx-auto max-w-content space-y-6">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Tablero</h1>
        <button
          type="button"
          onClick={() => run.mutate()}
          disabled={run.isPending || data.inbox.length === 0}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-text hover:bg-primary-hover disabled:opacity-50"
        >
          <Play aria-hidden size={16} /> Ejecutar agente
        </button>
      </header>
      <section aria-labelledby="bandeja">
        <h2 id="bandeja" className="mb-2 text-lg font-semibold">
          Bandeja de entrada ({data.inbox.length})
        </h2>
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {data.inbox.map((card) => (
            <CardItem key={card.invoice_id} card={card} />
          ))}
        </ul>
      </section>
      <div className="grid gap-4 lg:grid-cols-3">
        {data.columns.map((col) => (
          <section key={col.decision} aria-labelledby={`col-${col.decision}`} className={`rounded-lg border-t-4 p-3 ${TONE[col.decision]}`}>
            <h2 id={`col-${col.decision}`} className="mb-2 font-semibold">
              {col.label_es} ({col.count})
            </h2>
            <ul className="space-y-2">
              {col.cards.map((card) => (
                <CardItem key={card.invoice_id} card={card} />
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
