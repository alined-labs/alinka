import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import type { Board } from "~/api/client";
import { allCards, projectRun, type RunResult, stepDelay } from "./board";

const DIR = join(import.meta.dirname, "../../../alinka/api/fixtures/samples");
const load = <T>(name: string): T => JSON.parse(readFileSync(join(DIR, `${name}.json`), "utf8")) as T;
const inbox = load<Board>("board_inbox");
const run = load<RunResult>("run");

describe("projectRun", () => {
  it("starts as the inbox and ends as the decided board", () => {
    const start = projectRun(inbox, run, 0);
    expect(start.inbox.length).toBe(inbox.inbox.length);
    expect(start.columns.map((c) => c.count)).toEqual([0, 0, 0]);

    const end = projectRun(inbox, run, run.steps.length);
    expect(end.inbox).toEqual([]);
    expect(end.columns.map((c) => c.count)).toEqual(run.board.columns.map((c) => c.count));
  });

  it("moves one card per step and never loses one", () => {
    for (let i = 0; i <= run.steps.length; i++) {
      const b = projectRun(inbox, run, i);
      expect(b.inbox.length).toBe(inbox.inbox.length - i);
      expect(allCards(b).length).toBe(inbox.inbox.length);
    }
  });

  it("puts each moved card in the column of its decision", () => {
    const b = projectRun(inbox, run, 3);
    for (const step of run.steps.slice(0, 3)) {
      const col = b.columns.find((c) => c.decision === step.decision);
      expect(col?.cards.map((c) => c.invoice_id)).toContain(step.invoice_id);
    }
  });
});

describe("stepDelay", () => {
  it("keeps the animation near 3 seconds within bounds", () => {
    expect(stepDelay(0)).toBe(0);
    expect(stepDelay(6)).toBe(250);
    expect(stepDelay(30)).toBe(100);
    expect(stepDelay(175)).toBe(60);
  });
});
