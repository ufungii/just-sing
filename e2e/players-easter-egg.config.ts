import { defineConfig } from '@playwright/test';

/** UI-only regression: mocked API, isolated browser storage, no database or microphone. */
export default defineConfig({
  testDir: '.',
  testMatch: 'players-easter-egg.spec.ts',
  timeout: 30_000,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5189',
    launchOptions: { executablePath: process.env.E2E_CHROMIUM },
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5189',
    cwd: '../web',
    env: { VITE_AUTH0_CLIENT_ID: '' },
    url: 'http://127.0.0.1:5189',
    reuseExistingServer: false,
  },
});
