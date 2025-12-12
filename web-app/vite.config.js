import { defineConfig } from 'vite';

export default defineConfig({
  define: {
    // 1. Polyfill the 'global' variable (Fixes "global is not defined")
    'global': 'window',
  },
  resolve: {
    alias: {
      // 2. Fix AWS SDK import issues
      './runtimeConfig': './runtimeConfig.browser',
    },
  },
  optimizeDeps: {
    // 3. Force Vite to bundle the Cognito library
    include: ['amazon-cognito-identity-js'],
  },
  build: {
    commonjsOptions: {
      include: [/amazon-cognito-identity-js/, /node_modules/],
    },
  },
});