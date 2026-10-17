import { defineConfig } from '@playwright/test';

const PORT = Number(process.env.E2E_PORT ?? 8765);
export default defineConfig({
  testDir: '.',
  testMatch: ['sing.spec.ts', 'battle.spec.ts', 'online.spec.ts', 'range.spec.ts'],
  timeout: 120_000,
  workers: 1, // one fake mic file per browser; takes run one after another
  reporter: 'list',
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  // The real path: FastAPI serving the built web/dist (run `npm run build` in web/ first). Uses the dev DB from .env.
  webServer: {
    command: `.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port ${PORT}`,
    cwd: '..',
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: process.env.E2E_REUSE_SERVER !== '0',
    timeout: 60_000,
  },
});
