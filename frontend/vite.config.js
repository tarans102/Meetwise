import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI backend runs separately (uvicorn on :8000). In development the
// Vite dev server forwards /api so the frontend uses relative URLs everywhere.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: env.VITE_APP_API_URL || "http://localhost:8000",
          changeOrigin: true,
        }
      },
    },
  }
});
