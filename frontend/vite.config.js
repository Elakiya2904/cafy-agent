import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  envDir: '..',  // VITE_SUPABASE_* come from the single project-root .env (only VITE_-prefixed keys reach the browser)
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
