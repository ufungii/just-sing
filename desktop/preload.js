// Runs in the page before the app loads, in an isolated, sandboxed context.
// It exposes one small, read-only object to the web app. That shape is the
// contract typed in web/src/electron.d.ts; change both together.
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isDesktop: true,
  platform: process.platform,
});
