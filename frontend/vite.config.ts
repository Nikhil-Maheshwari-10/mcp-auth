import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// When running inside Docker, use container names as proxy targets.
// When running locally (npm run dev), use localhost.
const inDocker = process.env.DOCKER === 'true'
const apiHost = inDocker ? 'http://api:8001' : 'http://localhost:8001'
const adkHost = inDocker ? 'http://adk:8000' : 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    allowedHosts: true,
    watch: {
      usePolling: true,   // Required inside Docker for file-change detection
      interval: 300,
    },
    proxy: {
      '/api': {
        target: apiHost,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/apps': {
        target: adkHost,
        changeOrigin: true,
        headers: { 'Origin': adkHost },
      },
      '/run_sse': {
        target: adkHost,
        changeOrigin: true,
        headers: { 'Origin': adkHost },
      },
    },
  },
})
