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
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
