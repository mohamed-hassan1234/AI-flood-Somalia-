/// <reference types="node" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { configDefaults } from 'vitest/config';

// Honour a PORT supplied by the environment so tooling that assigns a free
// port (preview harnesses, container orchestrators) is respected, while
// keeping Vite's 5173 default for a plain `npm run dev`.
const port = process.env.PORT ? Number(process.env.PORT) : 5173;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port,
    strictPort: false,
  },
  preview: { host: '0.0.0.0', port },
  build: {
    // The map renderer and the charting library are each large and are only
    // needed on the routes that use them. They already load through dynamic
    // imports; naming the chunks keeps them cacheable across deployments.
    rollupOptions: {
      output: {
        manualChunks: {
          maplibre: ['maplibre-gl'],
          charts: ['recharts'],
        },
      },
    },
    chunkSizeWarningLimit: 1200,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/tests/setup.ts',
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
});
