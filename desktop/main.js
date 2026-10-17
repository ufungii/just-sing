// Just Sing! desktop shell.
//
// This is a thin client: one window that loads the shared server's URL (the
// React app served next to FastAPI). No app logic and no Python live here, so
// the browser version and the desktop version run exactly the same code.

const path = require('node:path');
const { app, BrowserWindow, Menu, session, shell } = require('electron');

// Where the app lives.
// Development default: the Vite dev server in web/ (it proxies /api to FastAPI
// on :8000). For the demo, set JUST_SING_URL to the shared server's public
// HTTPS URL; the mic only works in a secure context (HTTPS or localhost).
function getAppUrl() {
  return process.env.JUST_SING_URL || 'http://localhost:5173';
}

const APP_URL = getAppUrl();
const APP_ORIGIN = new URL(APP_URL).origin;

// The bundled "can't reach the server" page. It is a local file, so it gets
// its own small allowance in the navigation guard below.
const OFFLINE_PAGE = path.join(__dirname, 'offline.html');

function isAppUrl(url) {
  try {
    return new URL(url).origin === APP_ORIGIN;
  } catch {
    return false;
  }
}

// Links that leave the app open in the system browser, but only https: ones.
// Anything else (file:, javascript:, custom protocols, plain http) is ignored.
function openExternally(url) {
  try {
    if (new URL(url).protocol === 'https:') shell.openExternal(url);
  } catch {
    // Not a valid URL: ignore it.
  }
}

// Microphone access is the only permission the app needs, and only the app's
// own origin may have it. Everything else (camera, geolocation, notifications,
// clipboard, ...) is denied.
function lockDownPermissions() {
  const ses = session.defaultSession;

  ses.setPermissionRequestHandler((_webContents, permission, callback, details) => {
    const audioOnly = (details.mediaTypes || []).every((type) => type === 'audio');
    callback(permission === 'media' && audioOnly && isAppUrl(details.requestingUrl));
  });

  // requestingOrigin arrives as "http://host:port/", so compare parsed origins.
  ses.setPermissionCheckHandler((_webContents, permission, requestingOrigin, details) => {
    return permission === 'media' && details.mediaType !== 'video' && isAppUrl(requestingOrigin);
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: '#FFE4F1',
    title: 'Just Sing!',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });

  win.once('ready-to-show', () => win.show());

  // Keep the window on the app's origin. The offline page may navigate back to
  // the app (its Retry button); nothing else may navigate anywhere else.
  win.webContents.on('will-navigate', (event, url) => {
    if (isAppUrl(url)) return;
    event.preventDefault();
    openExternally(url);
  });

  // No pop-up windows: same-origin links open in this window, https: links in
  // the system browser, everything else is dropped.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isAppUrl(url)) win.loadURL(url).catch(() => {});
    else openExternally(url);
    return { action: 'deny' };
  });

  // If the server can't be reached, show a friendly page with a Retry button
  // instead of a blank window. -3 (ERR_ABORTED) is a cancelled load, not a failure.
  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    if (!isMainFrame || errorCode === -3 || !isAppUrl(validatedURL)) return;
    console.warn(`[just-sing] could not load ${validatedURL}: ${errorDescription} (${errorCode})`);
    win.loadFile(OFFLINE_PAGE, { query: { url: APP_URL, reason: errorDescription } });
  });

  // Dev conveniences while running from source: Ctrl/Cmd+R reloads,
  // Ctrl/Cmd+Shift+I opens DevTools (the menu bar that normally provides them is off).
  if (!app.isPackaged) {
    win.webContents.on('before-input-event', (event, input) => {
      if (input.type !== 'keyDown' || !(input.control || input.meta)) return;
      const key = input.key.toLowerCase();
      if (key === 'r' && !input.shift) {
        event.preventDefault();
        win.loadURL(APP_URL).catch(() => {});
      } else if (key === 'i' && input.shift) {
        event.preventDefault();
        win.webContents.toggleDevTools();
      }
    });
  }

  // A failed load is handled by did-fail-load above; catch the rejection so it
  // isn't also reported as an unhandled error.
  win.loadURL(APP_URL).catch(() => {});
}

app.whenReady().then(() => {
  // No menu bar on Windows/Linux. macOS keeps its default app menu so standard
  // shortcuts (copy, paste, quit) still work.
  if (process.platform !== 'darwin') Menu.setApplicationMenu(null);

  lockDownPermissions();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
