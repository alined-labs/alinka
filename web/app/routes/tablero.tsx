import { Progress } from "@base-ui/react/progress";
import { Toggle } from "@base-ui/react/toggle";
import { ToggleGroup } from "@base-ui/react/toggle-group";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Columns3, Play, Table2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import { api, type Board, unwrap, type View } from "~/api/client";
import { STATE_STYLE } from "~/components/badges";
import { BoardTable } from "~/components/board-table";
import { InvoiceCard } from "~/components/invoice-card";
import { allCards, COLUMN_TITLE, projectRun, type RunResult, stepDelay } from "~/lib/board";

export function meta() {
  return [{ title: "Tablero · Alinka" }];
}

export const boardKey = (view: View) => ["board", view] as const;

function useBoard(view: View) {
  return useQuery({
    queryKey: boardKey(view),
    queryFn: () => unwrap(api.GET("/api/board", { params: { query: { view } } })),
  });
}

const toggleClass =
  "inline-flex items-center gap-1 px-3 py-1.5 text-sm first:rounded-l-md last:rounded-r-md border border-border bg-surface data-[pressed]:bg-primary data-[pressed]:text-primary-text";

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; icon?: React.ReactNode }[];
  onChange: (value: T) => void;
}) {
  return (
    <ToggleGroup
      aria-label={label}
      value={[value]}
      onValueChange={(v) => {
        const next = v[0] as T | undefined;
        if (next) onChange(next);
      }}
      className="inline-flex"
    >
      {options.map((o) => (
        <Toggle key={o.value} value={o.value} className={toggleClass} aria-label={o.label}>
          {o.icon}
          {o.label}
        </Toggle>
      ))}
    </ToggleGroup>
  );
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** "Ejecutar agente": POST /api/run, then replay its steps so invoices move one by one. */
function useRun(onDone: (board: Board) => void) {
  const [progress, setProgress] = useState<{ before: Board; result: RunResult; shown: number } | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const mutation = useMutation({
    mutationFn: (_before: Board) => unwrap(api.POST("/api/run")),
    onSuccess: (result, before) => {
      if (prefersReducedMotion() || result.steps.length === 0) return onDone(result.board);
      setProgress({ before, result, shown: 0 });
    },
  });

  useEffect(() => {
    if (!progress) return;
    const total = progress.result.steps.length;
    timer.current = setInterval(() => {
      setProgress((p) => (p ? { ...p, shown: Math.min(total, p.shown + 1) } : p));
    }, stepDelay(total));
    return () => clearInterval(timer.current);
  }, [progress?.result]);

  useEffect(() => {
    if (progress && progress.shown >= progress.result.steps.length) {
      clearInterval(timer.current);
      onDone(progress.result.board);
      setProgress(null);
    }
  }, [progress, onDone]);

  const shownBoard = progress ? projectRun(progress.before, progress.result, progress.shown) : undefined;
  return { mutation, progress, shownBoard };
}

export default function Tablero() {
  const [params, setParams] = useSearchParams();
  const view: View = params.get("vista") === "canonica" ? "canonical" : "sandbox";
  const mode = params.get("modo") === "tabla" ? "tabla" : "columnas";
  const setParam = (key: string, value: string | null) =>
    setParams(
      (p) => {
        if (value) p.set(key, value);
        else p.delete(key);
        return p;
      },
      { replace: true },
    );

  const qc = useQueryClient();
  const board = useBoard(view);
  const onDone = useRef((b: Board) => qc.setQueryData(boardKey("sandbox"), b)).current;
  const { mutation: run, progress, shownBoard } = useRun(onDone);

  const data = shownBoard ?? board.data;
  const running = run.isPending || progress !== null;

  return (
    <div className="mx-auto max-w-content space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Tablero</h1>
        <div className="flex flex-wrap items-center gap-3">
          <Segmented
            label="Ejecución"
            value={view}
            onChange={(v) => setParam("vista", v === "canonical" ? "canonica" : null)}
            options={[
              { value: "sandbox", label: "Mi sandbox" },
              { value: "canonical", label: "Ejecución canónica" },
            ]}
          />
          <Segmented
            label="Vista"
            value={mode}
            onChange={(v) => setParam("modo", v === "tabla" ? "tabla" : null)}
            options={[
              { value: "columnas", label: "Columnas", icon: <Columns3 aria-hidden size={16} /> },
              { value: "tabla", label: "Tabla", icon: <Table2 aria-hidden size={16} /> },
            ]}
          />
          {view === "sandbox" && (
            <button
              type="button"
              onClick={() => board.data && run.mutate(board.data)}
              disabled={running || !board.data || board.data.inbox.length === 0}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-text hover:bg-primary-hover disabled:opacity-50"
            >
              <Play aria-hidden size={16} /> Ejecutar agente
            </button>
          )}
        </div>
      </header>

      {view === "canonical" && (
        <p className="text-sm text-muted">
          La ejecución canónica es de solo lectura: es la misma para todos. Tus cambios viven en «Mi sandbox».
        </p>
      )}
      {run.isError && <p role="alert" className="text-hold">No se pudo ejecutar el agente: {run.error.message}</p>}
      {progress && (
        <Progress.Root value={progress.shown} max={progress.result.steps.length} className="space-y-1">
          <Progress.Label className="text-sm">
            Decidiendo {progress.shown} de {progress.result.steps.length} facturas…
          </Progress.Label>
          <Progress.Track className="h-2 overflow-hidden rounded-pill bg-surface-muted">
            <Progress.Indicator className="h-full bg-primary transition-all" />
          </Progress.Track>
        </Progress.Root>
      )}

      {board.isPending && <p className="text-muted">Cargando el tablero…</p>}
      {board.isError && <p role="alert">No se pudo cargar el tablero: {board.error.message}</p>}
      {data && (mode === "tabla" ? <BoardTable cards={allCards(data)} /> : <Columns board={data} />)}
    </div>
  );
}

function Columns({ board }: { board: Board }) {
  return (
    <>
      <section aria-labelledby="bandeja">
        <h2 id="bandeja" className="mb-2 text-lg font-semibold">
          Bandeja de entrada <span className="text-muted">({board.inbox.length})</span>
        </h2>
        {board.inbox.length === 0 ? (
          <p className="text-sm text-muted">La bandeja está vacía.</p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {board.inbox.map((card) => (
              <InvoiceCard key={card.invoice_id} card={card} />
            ))}
          </ul>
        )}
      </section>
      <div className="grid gap-4 lg:grid-cols-3">
        {board.columns.map((col) => {
          const s = STATE_STYLE[col.decision];
          const Icon = s.icon;
          return (
            <section
              key={col.decision}
              aria-labelledby={`col-${col.decision}`}
              className={`min-w-0 rounded-lg border-t-4 p-3 ${s.border} ${s.bg}`}
            >
              <h2 id={`col-${col.decision}`} className={`mb-2 flex items-center gap-2 font-semibold ${s.text}`}>
                <Icon aria-hidden size={18} />
                {COLUMN_TITLE[col.decision]}
                <span data-testid={`count-${col.decision}`} className="ml-auto rounded-pill bg-surface px-2 text-sm">
                  {col.count}
                </span>
              </h2>
              <ul className="space-y-2" aria-live="polite">
                {col.cards.map((card) => (
                  <InvoiceCard key={card.invoice_id} card={card} />
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </>
  );
}
