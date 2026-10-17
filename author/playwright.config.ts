import { defineConfig } from '@playwright/test';
export default defineConfig({testDir: './tests', workers: 1, use: {baseURL:'http://127.0.0.1:8011'},
  webServer: {command: `${process.env.AUTHOR_PYTHON || 'python'} -m author.e2e_server`, cwd:'..',
    url:'http://127.0.0.1:8011/api/songs', reuseExistingServer:false}});
