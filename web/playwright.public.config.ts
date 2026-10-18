import { defineConfig } from "@playwright/test";

import local from "./playwright.config";

/*
 * The same suites against the deployed site: the Worker on alinka.alinedlabs.co, which forwards
 * /api to Azure. No local servers start. Not part of make check.
 * Run from web/: pnpm exec playwright test -c playwright.public.config.ts
 */
export default defineConfig({
  ...local,
  use: { ...local.use, baseURL: "https://alinka.alinedlabs.co" },
  webServer: undefined,
});
