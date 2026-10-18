import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// "npm run dev" starts the website on http://127.0.0.1:5173
// and forwards every /api request to the Flask server on port 5000.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:5000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
  },
});
