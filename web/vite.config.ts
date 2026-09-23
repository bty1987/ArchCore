import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 内网管理台：dev 代理到本机 server；构建产物由 server 或 Nginx 静态托管
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", chunkSizeWarningLimit: 1500 },
});
