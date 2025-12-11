// vite.config.js
import { defineConfig } from 'vite';

export default defineConfig({
  define: {
    // Polyfill 'global' for the Amazon Cognito library
    global: 'window',
  },
});