import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In development the Vite server forwards /api (HTTP and WebSocket) to FastAPI,
// so the page and the API share one origin, just as they will when FastAPI
// serves the built app. The Electron shell loads this same URL.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/karaoke': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
});
