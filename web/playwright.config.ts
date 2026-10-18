import { defineConfig } from "@playwright/test";

/*
 * Judge tests (PLAN section 9) against the local stack: `make api` on :8000 and the web dev
 * server on :5175. Each test gets a fresh browser context, so a fresh sandbox cookie.
 * Run from web/: pnpm exec playwright test   (or pnpm --filter ./web exec playwright test)
 */
export default defineConfig({
  testDir: "../tests/e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5175",
    // The Google Chrome installed on this machine; no Playwright browser download.
    channel: "chrome",
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "make -C .. api",
      url: "http://localhost:8000/api/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "pnpm run dev --port 5175 --strictPort",
      url: "http://localhost:5175",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
