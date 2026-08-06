import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // FastAPI auth API
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // ADK agent API — override Origin so ADK's CSRF check passes
      '/apps': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        headers: { 'Origin': 'http://localhost:8000' },
      },
      '/run_sse': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        headers: { 'Origin': 'http://localhost:8000' },
      },
    },
  },
})
