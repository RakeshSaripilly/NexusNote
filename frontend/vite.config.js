import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const BACKEND_ORIGIN = 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // Convenience proxy so the app also works when VITE_BACKEND_ORIGIN is blank.
    proxy: {
      '/api': { target: BACKEND_ORIGIN, changeOrigin: true },
      '/static': { target: BACKEND_ORIGIN, changeOrigin: true },
    },
  },
});
