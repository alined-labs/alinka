import { execFileSync } from "node:child_process";
import { join } from "node:path";

import { expect, type Page } from "@playwright/test";

// Playwright loads tests/e2e as CommonJS (no package.json here), so __dirname is defined.
export const ROOT = join(__dirname, "../..");

/** A judge fixture from tests/judge/fixtures, read through uv (the YAML reader lives in Python). */
export function fixture<T = Record<string, any>>(prefix: string): T {
  const out = execFileSync(
    "uv",
    [
      "run",
      "--frozen",
      "python",
      "-c",
      "import glob, json, sys, yaml; print(json.dumps(yaml.safe_load(open(glob.glob(sys.argv[1])[0], encoding='utf-8'))))",
      join(ROOT, `tests/judge/fixtures/${prefix}-*.yaml`),
    ],
    { cwd: ROOT, encoding: "utf8" },
  );
  return JSON.parse(out) as T;
}

/** Runs a command through uv from the repo root; returns its exit code and output. */
export function uv(args: string[]): { code: number; out: string } {
  try {
    return { code: 0, out: execFileSync("uv", ["run", "--frozen", ...args], { cwd: ROOT, encoding: "utf8" }) };
  } catch (e) {
    const err = e as { status?: number; stdout?: string; stderr?: string };
    return { code: err.status ?? 1, out: `${err.stdout ?? ""}${err.stderr ?? ""}` };
  }
}

export const COLUMN_DECISION: Record<string, "PAY" | "HOLD" | "ESCALATE"> = {
  Pagadas: "PAY",
  Frenadas: "HOLD",
  "Pendientes de aprobación": "ESCALATE",
};

export const count = (page: Page, state: string) => page.getByTestId(`count-${state}`);

export async function counts(page: Page) {
  const read = async (s: string) => Number(await count(page, s).innerText());
  return { inbox: await read("inbox"), PAY: await read("PAY"), HOLD: await read("HOLD"), ESCALATE: await read("ESCALATE") };
}

/**
 * Opens a page and waits for React to hydrate it. The public routes arrive prerendered, so their
 * buttons are on screen before they work: wait until <main> carries React's props.
 */
export async function open(page: Page, path: string) {
  await page.goto(path);
  await page.waitForFunction(() => {
    const main = document.querySelector("main");
    return main !== null && Object.keys(main).some((key) => key.startsWith("__reactProps$"));
  });
}

/** The sandbox board, decided: press "Ejecutar agente" and wait for the inbox to empty. */
export async function runAgent(page: Page) {
  await open(page, "/");
  const run = page.getByRole("button", { name: "Ejecutar agente" });
  await expect(run).toBeEnabled();
  await run.click();
  await expect(count(page, "inbox")).toHaveText("0", { timeout: 30_000 });
  await expect(page.getByText(/Decidiendo \d+ de \d+/)).toHaveCount(0, { timeout: 30_000 });
}

/** The card of one invoice on the board, inside the column of a decision. */
export const card = (page: Page, decision: string, invoiceId: string) =>
  page.locator(`section[aria-labelledby="col-${decision}"]`).getByRole("link", { name: new RegExp(`^Factura ${invoiceId}:`) });
