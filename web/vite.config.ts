import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // `@/` for anything under src. Relative paths across a component tree become
    // `../../../` quickly, and those are the imports that break silently when a file moves.
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    // The API in development. Same-origin in the browser, so the refresh cookie's
    // SameSite=Strict is honoured — a cross-origin frontend would not receive it at all.
    //
    // The target is overridable so the browser tests can point this at their own API — one
    // running scripted models against a throwaway database — without disturbing a dev
    // server somebody has open.
    proxy: {
      "/api": {
        target: process.env.PLANTOPIA_API_ORIGIN ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    // `src` only. The browser tests under `e2e/` are Playwright's, and vitest collecting
    // them fails the run with an error about two copies of @playwright/test — which is not
    // what is wrong.
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
