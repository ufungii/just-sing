/**
 * The bridge the Electron preload script exposes (desktop/preload.js).
 * It is absent in a normal browser, so always feature-check it:
 *   if (window.electronAPI) { ... }
 */
export interface ElectronAPI {
  isDesktop: true;
  platform: string; // process.platform, e.g. "win32" | "darwin" | "linux"
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}
