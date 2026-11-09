/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev server proxies the versioned API to the Django backend (same-origin in the browser, no CORS needed).
// Backend address is configurable for the E2E runner; default = local Django runserver.
const backend = process.env.ALEEKHAN_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      // changeOrigin false: Django sees the browser's Host (127.0.0.1:5173), so the CSRF Origin check of the
      // PHASE_01 session writes matches the page origin (same as behind the production reverse proxy).
      "/api": { target: backend, changeOrigin: false },
    },
  },
  preview: { host: "127.0.0.1", port: 4173, strictPort: true },
  build: { sourcemap: false, target: "es2022" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
