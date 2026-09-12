import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// api_port in config/settings.py defaults to 8420 — proxying to the real
// SAM API process during dev so the iQOO workspace can talk to it without
// a CORS dance. Adjust if your local settings override the port.
const SAM_API_PORT = 8420;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: `http://localhost:${SAM_API_PORT}`,
        changeOrigin: true,
      },
    },
  },
});
