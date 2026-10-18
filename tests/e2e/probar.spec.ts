import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { card, open, ROOT } from "./helpers";

/*
 * Probar: a sample runs through the real pipeline in the visitor's sandbox, its seven steps
 * appear, and the run ends on its card on the board. The expected decision and rules are the
 * sample's gold label in data/labels (the trap's intent), never the engine's output.
 */

type Gold = { invoice_id: string; gold_decision: "PAY" | "HOLD" | "ESCALATE"; gold_rules: string[] };

function gold(invoiceId: string): Gold {
  for (const split of ["generated", "attack", "showcase"]) {
    for (const line of readFileSync(join(ROOT, "data/labels", `${split}.jsonl`), "utf8").split("\n")) {
      if (!line.includes(`"${invoiceId}"`)) continue;
      const label = JSON.parse(line) as Gold;
      if (label.invoice_id === invoiceId) return label;
    }
  }
  throw new Error(`no gold label for ${invoiceId}`);
}

const STEPS = ["Recepción", "Contenido oculto", "La IA lee", "Verificación", "16 reglas", "Decisión", "Registro"];
const STATE_ES = { PAY: "Pagada", HOLD: "Frenada", ESCALATE: "Pendiente de aprobación" };

for (const [sample, title] of [
  ["GEN-084-1", "Factura de rutina en PDF"],
  ["ATK-01-1", "Texto blanco oculto"],
] as const) {
  test(`Probar · «${title}» recorre los siete pasos y termina en su tarjeta del tablero`, async ({ page }) => {
    const label = gold(sample);
    await open(page, "/probar");
    await page
      .locator("ul.probar-gallery > li")
      .filter({ has: page.getByText(title, { exact: true }) })
      .getByRole("button", { name: "Probar esta factura" })
      .click();

    const toBoard = page.getByRole("link", { name: "Ver en el tablero" });
    await expect(toBoard).toBeVisible({ timeout: 45_000 });
    for (const step of STEPS) await expect(page.getByRole("heading", { name: step, exact: true })).toBeVisible();
    await expect(page.getByText(`Registro: listo · ${STATE_ES[label.gold_decision]}`)).toBeVisible();

    const href = await page.getByRole("link", { name: "Ver el detalle" }).getAttribute("href");
    expect(href).toMatch(new RegExp(`^/facturas/TRY-${sample}-\\d+$`));
    await toBoard.click();
    const onBoard = card(page, label.gold_decision, href!.split("/").pop()!);
    await expect(onBoard).toHaveCount(1);
    for (const rule of label.gold_rules) await expect(onBoard).toContainText(`(${rule})`);
  });
}
