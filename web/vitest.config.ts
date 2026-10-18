import { defineConfig } from "vitest/config";

// Kept apart from vite.config.ts: the React Router plugin is not meant to run under Vitest.
export default defineConfig({
  resolve: { tsconfigPaths: true },
  test: { include: ["app/**/*.test.ts", "app/**/*.test.tsx"], environment: "node" },
});
