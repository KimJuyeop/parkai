import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 빌드 결과는 FastAPI가 서빙하는 parkai/web/static 으로 나간다 (설치 번들에 그대로 포함).
// 개발 중에는 `npm run dev` (5173) + `python tools/dev.py` (8080) 를 함께 띄우면 /api 가 프록시된다.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../parkai/web/static",
    emptyOutDir: true,
    target: "es2019",
    chunkSizeWarningLimit: 400,
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8080" },
  },
});
