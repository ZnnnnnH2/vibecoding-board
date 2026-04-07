import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/admin/',
  server: {
    port: 5173,
    proxy: {
      '/admin/api': 'http://127.0.0.1:9000',
      '/healthz': 'http://127.0.0.1:9000',
      '/v1': 'http://127.0.0.1:9000',
    },
  },
  build: {
    outDir: '../vibecoding_board/static/admin',
    emptyOutDir: true,
  },
})
