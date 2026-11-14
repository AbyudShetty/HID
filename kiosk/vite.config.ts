/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api (including the WebSocket upgrade) to the backend (plan T0.3).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", ws: true, changeOrigin: false },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
