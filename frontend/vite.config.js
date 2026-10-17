import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server binds to localhost only and proxies /api to the Flask
// backend, so the browser sees a single origin (cookies stay SameSite=Strict).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:5000", changeOrigin: false },
    },
  },
  preview: { host: "127.0.0.1", port: 4173 },
  build: { outDir: "dist", sourcemap: false },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
  },
});
