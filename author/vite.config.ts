import { defineConfig } from 'vite';
import path from 'node:path';
// Shared source resolves React from this app, including in a clean checkout.
export default defineConfig({ resolve: { alias: {
  'react/jsx-runtime': path.resolve('node_modules/react/jsx-runtime.js'),
  'react': path.resolve('node_modules/react'),
  'react-dom': path.resolve('node_modules/react-dom'),
} } });
