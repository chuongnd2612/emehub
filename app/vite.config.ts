import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// EmeHub frontend. Ports are chosen not to clash with QAgent (web 5174,
// api 8787) or DAgent (web 3000) so all three stacks can run on one host.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5180,
    proxy: {
      // Same-origin API access: the client calls `/api/*` and Vite forwards to
      // the FastAPI backend with the `/api` prefix stripped, mirroring nginx.
      "/api": {
        target: "http://127.0.0.1:8790",
        changeOrigin: true,
        ws: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
