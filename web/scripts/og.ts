/*
 * Render og/og.html to public/og.png (1200x630) with the system Chrome through Playwright.
 *   pnpm --filter ./web run og
 * WhatsApp drops link previews over about 300 KB, so this fails above that.
 */
import { statSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const template = new URL("../og/og.html", import.meta.url);
const out = fileURLToPath(new URL("../public/og.png", import.meta.url));
const MAX_BYTES = 300 * 1024;

const browser = await chromium.launch({ channel: "chrome" });
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.goto(template.href, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: out, type: "png" });
} finally {
  await browser.close();
}
const size = statSync(out).size;
console.log(`${out}: ${(size / 1024).toFixed(0)} KB`);
if (size > MAX_BYTES) {
  console.error(`og.png is over ${MAX_BYTES / 1024} KB`);
  process.exit(1);
}
