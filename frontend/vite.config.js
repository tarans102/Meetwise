import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI backend runs separately (uvicorn on :8000). In development the
// Vite dev server forwards /api so the frontend uses relative URLs everywhere.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
