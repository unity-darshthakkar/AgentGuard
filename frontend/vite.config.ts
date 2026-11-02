import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const rootDir = path.resolve(__dirname, '..');
  const env = loadEnv(mode, rootDir, '');
  const adminKey = env.ADMIN_API_KEY;
  const adminProtectedPrefixes = [
    '/api/agents', '/api/transactions', '/api/dashboard',
    '/api/security-events', '/api/authorize', '/api/policies',
    '/api/attack-simulator',
  ];
  return {
  plugins: [react()],
  envDir: rootDir,
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            const requestPath = proxyReq.path || '';
            if (adminKey && adminProtectedPrefixes.some((prefix) => requestPath.startsWith(prefix))) {
              proxyReq.setHeader('X-Admin-API-Key', adminKey);
            }
          });
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
    },
  },
  };
});
