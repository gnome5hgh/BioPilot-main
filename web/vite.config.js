import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期 /api 原样代理到 SpringBoot（8080）：服务端自己拥有 /api/v1 路径，
// 代理不再剥前缀；Python 适配层经 SpringBoot 内网转发
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8080', changeOrigin: true, ws: true },
    },
  },
})
