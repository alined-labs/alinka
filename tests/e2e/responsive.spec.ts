import { expect, type Page, test } from "@playwright/test";

import { BOARD, counts, runAgent } from "./helpers";

/*
 * Every route at phone, tablet and desktop widths, with the board decided so the cards carry
 * their reasons: the page itself must never scroll sideways (wide tables scroll in their own
 * container). Then one pass with document.startViewTransition removed, as in browsers without
 * the API: navigation and "Ejecutar agente" still work, with no errors.
 */

const WIDTHS = [360, 768, 1280];
// Detail pages: a plain payment, and the longest reason on the board (a quote from the document).
const DETAILS = ["/facturas/OCT-01", "/facturas/OCT-22"];
// The showcase page in both languages: outside the app's navigation, so listed by hand.
const SHOWCASE = ["/", "/en"];

/** The routes in the main navigation, so a new screen is covered as soon as it is linked. */
async function routes(page: Page): Promise<string[]> {
  const nav = page.getByRole("navigation", { name: "Principal" }).getByRole("link");
  await expect(nav.first()).toBeVisible();
  const hrefs = await nav.evaluateAll((links) => links.map((a) => new URL((a as HTMLAnchorElement).href).pathname));
  return [...new Set([...SHOWCASE, ...hrefs, ...DETAILS])];
}

/** How far the page itself scrolls sideways, in CSS pixels (0 when it doesn't). */
const sideways = (page: Page) =>
  page.evaluate(() => {
    const root = document.scrollingElement ?? document.documentElement;
    return root.scrollWidth - root.clientWidth;
  });

for (const width of WIDTHS) {
  test.describe(`${width} px`, () => {
    test.use({ viewport: { width, height: 900 } });

    test(`ninguna ruta se desplaza en horizontal a ${width} px`, async ({ page }) => {
      await runAgent(page);
      for (const path of await routes(page)) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await expect(page.locator("h1").first(), path).toBeVisible();
        expect.soft(await sideways(page), `${path} a ${width} px`).toBeLessThanOrEqual(0);
      }
    });
  });
}

test.describe("sin View Transitions", () => {
  test("la navegación y Ejecutar agente funcionan sin document.startViewTransition", async ({ page }) => {
    await page.addInitScript(() => {
      delete (Document.prototype as { startViewTransition?: unknown }).startViewTransition;
    });
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });

    await runAgent(page);
    expect(await page.evaluate(() => "startViewTransition" in document)).toBe(false);
    const c = await counts(page);
    expect(c.PAY + c.HOLD + c.ESCALATE).toBe(30);

    const nav = page.getByRole("navigation", { name: "Principal" });
    for (const path of await routes(page)) {
      if (DETAILS.includes(path) || SHOWCASE.includes(path)) continue;
      await nav.locator(`a[href="${path}"]`).click();
      await expect(page).toHaveURL(new RegExp(`${path}$`));
      await expect(page.locator("h1").first(), path).toBeVisible();
    }
    await page.goto(BOARD);
    await page.getByRole("link", { name: /^Factura OCT-01:/ }).click();
    await expect(page).toHaveURL(/\/facturas\/OCT-01$/);
    await expect(page.locator("h1").first()).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/tablero$/);
    expect(errors).toEqual([]);
  });
});
