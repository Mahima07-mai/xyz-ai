import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// XYZ AI frontend (Day 3). Talks to the FastAPI backend in ../backend
// (default http://localhost:8000, see src/api/client.js /
// VITE_API_BASE_URL) -- no proxy needed since the backend already ships
// wide-open CORS for local dev (see backend/app/main.py).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
