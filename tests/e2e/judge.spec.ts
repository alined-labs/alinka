import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { BOARD, card, COLUMN_DECISION, count, counts, fixture, open, runAgent, uv } from "./helpers";

/*
 * PLAN section 9, the judge tests at the Playwright layer. Every expectation comes from the
 * fixture in tests/judge/fixtures, written from each trap's intent, never from the engine.
 */

test("1 · la Bandeja muestra las 30 facturas y Ejecutar agente las reparte en tres columnas", async ({ page }) => {
  const f = fixture("01");
  await open(page, BOARD);
  await expect(count(page, "inbox")).toHaveText(String(f.expected.inbox_before_run));
  await runAgent(page);
  const c = await counts(page);
  expect(c.PAY + c.HOLD + c.ESCALATE).toBe(f.expected.sum);
  for (const [title, n] of Object.entries<number>(f.expected.columns)) {
    expect.soft(c[COLUMN_DECISION[title]!], title).toBe(n);
  }
});

test("2 · cada motivo nombra su regla en palabras y el valor usado", async ({ page }) => {
  const f = fixture("02");
  await runAgent(page);
  const reasons = page.locator("section[aria-labelledby^='col-'] .ak-card");
  const n = await reasons.count();
  expect(n).toBe(f.input.invoices);
  for (let i = 0; i < n; i++) {
    const text = await reasons.nth(i).locator(".ak-card__reason").allInnerTexts();
    const reason = text.join(" ");
    expect.soft(reason, `card ${i}`).toMatch(/\(R\d{2}\)/);
    expect.soft(reason, `card ${i}`).toMatch(/\d/);
  }
  for (const e of f.expected.non_pay as { invoice_id: string; decision: string; rule: string; rule_name_es: string }[]) {
    const c = card(page, e.decision, e.invoice_id);
    await expect.soft(c, e.invoice_id).toHaveCount(1);
    await expect.soft(c.locator(".ak-rule").first(), e.invoice_id).toContainText(`${e.rule}${e.rule_name_es}`);
    // A reason that quotes the document is split around its ak-slip: read every part.
    expect.soft((await c.locator(".ak-card__reason").allInnerTexts()).join(" "), e.invoice_id).toContain(`(${e.rule})`);
  }
});

test("4 · un beneficiario fuera de la lista queda Pendiente (R01) sin aprobar; agregarlo en Reglas lo re-decide", async ({ page }) => {
  const f = fixture("04");
  const before = f.expected.before;
  const body = f.expected.action["POST /api/beneficiaries"];
  await runAgent(page);

  await open(page, `/facturas/${before.invoice_id}`);
  const head = page.locator(".ak-detail__head");
  await expect(head.locator(".ak-chip")).toHaveText(before.state_es);
  for (const r of before.rules) await expect(head.locator(".ak-rule").first()).toContainText(r);
  await expect(page.getByRole("button", { name: "Aprobar" })).toHaveCount(before.approve_button ? 1 : 0);

  await open(page, "/reglas");
  const form = page.locator("form", { has: page.getByRole("button", { name: "Añadir y volver a decidir" }) });
  await form.getByLabel("Partir de una factura pendiente").selectOption(before.invoice_id);
  await expect(form.getByLabel("Nombre", { exact: true })).toHaveValue(body.name);
  await form.getByLabel("Nombre", { exact: true }).fill(body.name);
  await form.getByLabel("Identificación tributaria").fill(body.tax_id);
  await form.getByLabel("País (ISO, dos letras)").fill(body.country);
  await form.getByLabel("Moneda (ISO, tres letras)").fill(body.currency);
  await form.getByLabel(/^Cuenta registrada/).fill(body.account_on_file);
  await form.getByLabel(/^Alcance del contrato/).fill(body.contract.scope_es.join(", "));
  await form.getByLabel(/^Tarifa por periodo/).fill(String(body.contract.rate_minor / 100).replace(".", ","));
  await form.getByLabel("Tolerancia (%)").fill(String(body.contract.tolerance_pct));
  await form.getByLabel("Frecuencia").selectOption(body.contract.frequency);
  await form.getByLabel("Centro de costo").selectOption(body.contract.cost_center);
  await form.getByLabel("Contrato desde").fill(body.contract.valid_from);
  await form.getByLabel("Contrato hasta").fill(body.contract.valid_to);
  for (const [value, label] of [
    ["factura", "Factura"],
    ["cuenta_de_cobro", "Cuenta de cobro"],
    ["invoice", "Invoice"],
  ]) {
    await form.getByLabel(label!, { exact: true }).setChecked(body.doc_types.includes(value));
  }
  await form.getByRole("button", { name: "Añadir y volver a decidir" }).click();
  await expect(page.getByRole("status")).toContainText(`${body.name} quedó en la lista`);

  await open(page, `/facturas/${f.expected.after.invoice_id}`);
  await expect(page.locator(".ak-detail__head .ak-chip")).toHaveText(f.expected.after.state_es);
});

test("5 · un monto sobre el umbral queda Pendiente (R06); aprobarlo con nombre lo deja Pagada y escribe el log", async ({ page }) => {
  const f = fixture("05");
  const before = f.expected.before;
  const approver = f.expected.action[`POST /api/invoices/${before.invoice_id}/approve`].approver;
  await runAgent(page);

  await open(page, `/facturas/${before.invoice_id}`);
  await expect(page.locator(".ak-detail__head .ak-chip")).toHaveText(before.state_es);
  await expect(page.locator(".ak-detail__head .ak-rule").first()).toContainText(before.rules[0]);
  await page.getByRole("button", { name: "Aprobar" }).click();
  const dialog = page.getByRole("dialog", { name: "Aprobar el pago" });
  await dialog.getByLabel("Nombre de quien aprueba").fill(approver);
  await dialog.getByRole("button", { name: "Aprobar" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.locator(".ak-detail__head .ak-chip")).toHaveText(f.expected.after.state_es);
  await expect(page.locator(".ak-timeline")).toContainText(`Aprobada por ${approver}`);

  await open(page, "/registro");
  const last = page.locator(".ak-log tbody tr").last();
  await expect(last).toContainText(before.invoice_id);
  await expect(last).toContainText(approver);
  await expect(last.locator(".ak-chip")).toHaveText(f.expected.after.state_es);
});

test("11 · una cuenta distinta a la de la lista levanta alerta (R12), sin aprobar y con la cuenta de la lista", async ({
  page,
  request,
}) => {
  const [e] = fixture<{ expected: any[] }>("11").expected;
  const loaded = await request.get(`/api/invoices/${e.invoice_id}?view=canonical`);
  test.skip(!loaded.ok(), `${e.invoice_id} no está en la ejecución canónica: carga el run de ataques (load_run attack)`);
  await runAgent(page);

  await open(page, `/facturas/${e.invoice_id}`);
  await expect.soft(page.locator(".ak-detail__head .ak-chip")).toHaveText(e.state_es);
  for (const r of e.rules) await expect(page.locator(".ak-sec-box", { hasText: r })).toHaveCount(1);
  await expect(page.locator(".ak-detail__head .ak-sec")).toHaveCount(e.security_alert ? 1 : 0);
  await expect(page.getByRole("button", { name: "Aprobar" })).toHaveCount(e.approve_button ? 1 : 0);
  const account = page.locator(".ak-account");
  await expect(account).toContainText(e.preview_account_ends);
  await expect(account).not.toContainText(e.printed_account_ends);
});

test("17 · bajar el umbral mueve facturas a Pendientes; restablecer las restaura; la canónica no cambia", async ({
  page,
  request,
}) => {
  const f = fixture("17");
  const canonical = async () => (await (await request.get("/api/board?view=canonical")).json()).columns.map((c: any) => c.count);
  const canonicalBefore = await canonical();
  await runAgent(page);

  await open(page, "/reglas");
  // The impact sentence compares with the sandbox board, which loads beside the rules.
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Umbral de aprobación en USD").fill(String(f.setup["PUT /api/rules"].approval_threshold_usd));
  await page.getByRole("button", { name: "Guardar y volver a decidir" }).click();
  await expect(page.getByRole("status")).toContainText("Con este cambio");

  await open(page, BOARD);
  for (const id of f.expected.moves_to_pending as string[]) {
    await expect.soft(card(page, "ESCALATE", id), id).toHaveCount(1);
  }

  await open(page, "/reglas");
  await page.getByRole("button", { name: "Restablecer sandbox" }).click();
  await expect(page.getByRole("status")).toContainText("Sandbox restablecido");
  await expect(page.getByLabel("Umbral de aprobación en USD")).toHaveValue("2000");
  await runAgent(page);
  const c = await counts(page);
  for (const [title, n] of Object.entries<number>(f.expected.after_reset.columns)) {
    expect.soft(c[COLUMN_DECISION[title]!], title).toBe(n);
  }
  expect(await canonical()).toEqual(canonicalBefore);
});

test("18 · Verificar cadena dice OK; cambiar un byte almacenado hace fallar alinka verify", async ({ page }) => {
  await runAgent(page);
  await open(page, "/registro");
  // As a reader would: a check started before the log loads is reset when it arrives.
  await expect(page.getByText(/^\d+ registros/)).toBeVisible();
  await page.getByRole("button", { name: "Verificar cadena" }).click();
  await expect(page.locator(".ak-verify--ok")).toContainText("Cadena verificada");

  // The CLI half: the same chain written by `alinka batch`, then one byte flipped.
  const records = join(tmpdir(), `alinka-e2e-${Date.now()}.jsonl`);
  const batch = uv(["alinka", "batch", "data/runs/showcase", "--out", records]);
  expect(batch.code, batch.out).toBe(0);
  const ok = uv(["alinka", "verify", records]);
  expect(ok.code, ok.out).toBe(0);
  expect(ok.out).toMatch(/^OK/m);

  const bad = `${records}.bad`;
  copyFileSync(records, bad);
  const lines = readFileSync(bad, "utf8").split("\n");
  const at = lines[4]!.indexOf('"reason_es":"') + '"reason_es":"'.length;
  lines[4] = lines[4]!.slice(0, at) + (lines[4]![at] === "X" ? "Y" : "X") + lines[4]!.slice(at + 1);
  writeFileSync(bad, lines.join("\n"));
  const broken = uv(["alinka", "verify", bad]);
  expect(broken.code).not.toBe(0);
  expect(broken.out).toContain("registro 5");
});

test("20 · Evaluación muestra 0 de K aprobaciones indebidas con su cota y la autonomía como X% de un posible Y%", async ({
  page,
}) => {
  const f = fixture("20");
  await open(page, "/evaluacion");
  await expect(page.getByTestId("improper")).toHaveText(`${f.expected.improper_approvals} de ${f.expected.K}`);
  await expect(page.getByText(/cota superior del 95%: \d+(,\d+)?%/)).toBeVisible();
  await expect(page.getByTestId("autonomy")).toHaveText(/^\d+(,\d+)?% de un máximo posible de \d+(,\d+)?%$/);
});
