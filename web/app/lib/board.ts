import type { Board, Card, RunResult, Schemas } from "~/api/client";

export type { RunResult };

export type Decision = Schemas["Column"]["decision"];
export type CardState = Card["state"];

export const DECISIONS: readonly Decision[] = ["PAY", "HOLD", "ESCALATE"];

/** Column titles use the brief's words. */
export const COLUMN_TITLE: Record<Decision, string> = {
  PAY: "Pagadas",
  HOLD: "Frenadas",
  ESCALATE: "Pendientes de aprobación",
};

export const STATE_LABEL: Record<CardState, string> = {
  inbox: "Bandeja de entrada",
  PAY: "Pagada",
  HOLD: "Frenada",
  ESCALATE: "Pendiente de aprobación",
};

/** Every card on the board: the inbox first, then the columns in order. */
export function allCards(board: Board): Card[] {
  return [...board.inbox, ...board.columns.flatMap((c) => c.cards)];
}

/**
 * The board part-way through "Ejecutar agente": the first `shown` steps have left the inbox
 * and appear in their columns; cards decided before the run stay where they were.
 */
export function projectRun(before: Board, result: RunResult, shown: number): Board {
  const moved = new Set(result.steps.slice(0, shown).map((s) => s.invoice_id));
  const decidedBefore = new Set(before.columns.flatMap((c) => c.cards.map((card) => card.invoice_id)));
  const columns = result.board.columns.map((col) => {
    const cards = col.cards.filter((c) => moved.has(c.invoice_id) || decidedBefore.has(c.invoice_id));
    return { ...col, cards, count: cards.length };
  });
  return {
    ...result.board,
    inbox: before.inbox.filter((c) => !moved.has(c.invoice_id)),
    columns,
  };
}

/** Milliseconds between two steps of the run animation: about 3 s in total. */
export function stepDelay(steps: number): number {
  if (steps <= 0) return 0;
  return Math.min(250, Math.max(60, Math.round(3000 / steps)));
}
