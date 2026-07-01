import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    env: {
      NODE_ENV: 'development',
    },
    server: {
      deps: {
        inline: ['@jarvis/ui', '@jarvis/sdk'],
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@jarvis/sdk': path.resolve(__dirname, '../packages/sdk/src'),
      '@jarvis/ui': path.resolve(__dirname, '../packages/ui/src'),
    },
  },
});
