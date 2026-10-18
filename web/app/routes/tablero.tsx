import { Progress } from "@base-ui/react/progress";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Columns3, Play, Table2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import { api, type Board, type Card, unwrap, type View } from "~/api/client";
import { DECISION_STYLE } from "~/components/badges";
import { BoardTable } from "~/components/board-table";
import { InvoiceCard } from "~/components/invoice-card";
import { Segmented } from "~/components/segmented";
import { allCards, COLUMN_TITLE, type CardState, projectRun, type RunResult, stepDelay } from "~/lib/board";
import { prefersReducedMotion, useTransitionedValue } from "~/lib/motion";
import { seo } from "~/lib/seo";
import { useView } from "~/lib/view";

export function meta() {
  return seo({ path: "/" });
}

export const boardKey = (view: View) => ["board", view] as const;

const boardSignature = (b: Board | undefined) =>
  b ? allCards(b).map((c) => `${c.invoice_id}:${c.state}:${c.approver ?? ""}`).join("|") : "";

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

/** "Octubre 2026", from the invoices on the board. */
function monthTitle(board: Board | undefined): string {
  const first = board && allCards(board)[0];
  if (!first) return "Tablero";
  const label = new Intl.DateTimeFormat("es", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(first.received_at),
  );
  return label.charAt(0).toUpperCase() + label.slice(1).replace(" de ", " ");
}

const COUNT_LABEL: Record<CardState, string> = {
  inbox: "Bandeja",
  PAY: COLUMN_TITLE.PAY,
  HOLD: COLUMN_TITLE.HOLD,
  ESCALATE: COLUMN_TITLE.ESCALATE,
};

/** ak-counts: one tile per state; pressing one shows only that state, pressing it again shows all. */
function Counts({ board, focus, onFocus }: { board: Board; focus: CardState | null; onFocus: (s: CardState | null) => void }) {
  const tiles: { state: CardState; count: number }[] = [
    { state: "inbox", count: board.inbox.length },
    ...board.columns.map((c) => ({ state: c.decision as CardState, count: c.count })),
  ];
  return (
    <div className="ak-counts" role="group" aria-label="Filtrar por estado">
      {tiles.map(({ state, count }) => (
        <button
          key={state}
          type="button"
          className="ak-count"
          aria-pressed={focus === state}
          onClick={() => onFocus(focus === state ? null : state)}
        >
          <span className={`ak-count__label ${state === "inbox" ? "" : DECISION_STYLE[state].text}`}>
            {COUNT_LABEL[state]}
          </span>
          <strong data-testid={`count-${state}`}>{count}</strong>
        </button>
      ))}
    </div>
  );
}

function EmptyBoard() {
  return (
    <div className="ak-empty">
      <div className="ak-schema" aria-hidden>
        {["bg-pagada", "bg-frenada", "bg-pendiente"].map((dot) => (
          <div key={dot}>
            <i className={dot} />
            <span />
            <span />
          </div>
        ))}
      </div>
      <strong>No hay facturas en este tablero</strong>
      <p>Cuando lleguen facturas por correo, PDF, imagen o chat, aparecerán en la bandeja de entrada.</p>
    </div>
  );
}

export default function Tablero() {
  const [view] = useView();
  const [params, setParams] = useSearchParams();
  const mode = params.get("modo") === "tabla" ? "tabla" : "columnas";
  const setMode = (m: string) =>
    setParams(
      (p) => {
        if (m === "tabla") p.set("modo", "tabla");
        else p.delete("modo");
        return p;
      },
      { replace: true },
    );
  const [focus, setFocus] = useState<CardState | null>(null);

  const qc = useQueryClient();
  const board = useQuery({
    queryKey: boardKey(view),
    queryFn: () => unwrap(api.GET("/api/board", { params: { query: { view } } })),
  });
  const onDone = useRef((b: Board) => qc.setQueryData(boardKey("sandbox"), b)).current;
  const { mutation: run, progress, shownBoard } = useRun(onDone);

  // Every new board (a run step, a re-decision, the view switch) morphs its cards into place.
  const data = useTransitionedValue(shownBoard ?? board.data, boardSignature);
  const running = run.isPending || progress !== null;
  const empty = data !== undefined && allCards(data).length === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="ak-h1">{monthTitle(data)}</h1>
        {view === "sandbox" && (
          <button
            type="button"
            className="ak-btn ak-btn--primary"
            onClick={() => board.data && run.mutate(board.data)}
            disabled={running || !board.data || board.data.inbox.length === 0}
          >
            <Play aria-hidden className="ak-icon" />
            Ejecutar agente
          </button>
        )}
      </div>

      {running && (
        <Progress.Root
          value={progress?.shown ?? null}
          max={progress?.result.steps.length ?? 100}
          className="space-y-1"
          aria-label="Progreso del agente"
        >
          <div className="ak-progress">
            <i />
          </div>
          <Progress.Label className="text-small text-ink-muted">
            {progress
              ? `Decidiendo ${progress.shown} de ${progress.result.steps.length} facturas…`
              : "Leyendo y verificando las facturas…"}
          </Progress.Label>
        </Progress.Root>
      )}
      {run.isError && (
        <p role="alert" className="ak-banner ak-banner--error">
          No se pudo ejecutar el agente: {run.error.message}
        </p>
      )}
      {board.isPending && (
        <div className="ak-skel" aria-label="Cargando el tablero">
          <span />
          <span />
          <span />
        </div>
      )}
      {board.isError && (
        <p role="alert" className="ak-banner ak-banner--error">
          No se pudo cargar el tablero: {board.error.message}
        </p>
      )}

      {data && !empty && (
        <>
          <Counts board={data} focus={focus} onFocus={setFocus} />
          <div className="flex justify-end">
            <Segmented
              label="Vista"
              value={mode}
              onChange={setMode}
              options={[
                { value: "columnas", label: "Columnas", icon: <Columns3 aria-hidden className="ak-icon" /> },
                { value: "tabla", label: "Tabla", icon: <Table2 aria-hidden className="ak-icon" /> },
              ]}
            />
          </div>
          {mode === "tabla" ? (
            <BoardTable cards={allCards(data).filter((c) => focus === null || c.state === focus)} />
          ) : (
            <Columns board={data} focus={focus} moving={progress !== null} />
          )}
        </>
      )}
      {empty && <EmptyBoard />}
    </div>
  );
}

function CardList({ cards, moved }: { cards: Card[]; moved: boolean }) {
  if (cards.length === 0) return <p className="px-1 text-small text-ink-muted">Ninguna factura.</p>;
  return (
    <ul className="ak-column" aria-live="polite">
      {cards.map((card) => (
        <InvoiceCard key={card.invoice_id} card={card} moved={moved} />
      ))}
    </ul>
  );
}

function Columns({ board, focus, moving }: { board: Board; focus: CardState | null; moving: boolean }) {
  const showInbox = board.inbox.length > 0 && (focus === null || focus === "inbox");
  const columns = board.columns.filter((c) => focus === null || focus === c.decision);
  return (
    <>
      {showInbox && (
        <section aria-labelledby="col-inbox" className="ak-column">
          <h2 id="col-inbox" className="ak-column__head">
            <span>Bandeja de entrada</span>
            <span>{board.inbox.length}</span>
          </h2>
          <ul className="ak-board">
            {board.inbox.map((card) => (
              <InvoiceCard key={card.invoice_id} card={card} />
            ))}
          </ul>
        </section>
      )}
      {columns.length > 0 && (
        <div className="ak-board">
          {columns.map((col) => (
            <section key={col.decision} aria-labelledby={`col-${col.decision}`} className="ak-column">
              <h2 id={`col-${col.decision}`} className="ak-column__head">
                <span>{COLUMN_TITLE[col.decision]}</span>
                <span>{col.count}</span>
              </h2>
              <CardList cards={col.cards} moved={moving} />
            </section>
          ))}
        </div>
      )}
    </>
  );
}
