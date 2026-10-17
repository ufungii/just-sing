# Just Sing! desktop shell

A thin Electron client: one window that loads the Just Sing! web app from the
server's URL. All app logic lives in `web/` (and `api/`); this folder only
provides the window, a small preload bridge, and a friendly offline page.
No Python is bundled. The browser version keeps working on its own.

## Run it (development)

1. Start the web dev server (it proxies `/api` to FastAPI on `127.0.0.1:8000`):

   ```bash
   cd web
   npm run dev
   ```

2. In another terminal, start the desktop shell:

   ```bash
   cd desktop
   npm install
   npm start
   ```

By default the window loads `http://localhost:5173`. To point it somewhere
else (another port, or the shared server's public HTTPS URL for the demo), set
`JUST_SING_URL`:

```bash
JUST_SING_URL=https://example.invalid npm start      # macOS / Linux / Git Bash
$env:JUST_SING_URL="https://example.invalid"; npm start   # PowerShell
```

If the URL can't be reached, the window shows a small offline page with a
Retry button instead of a blank screen. While running from source,
`Ctrl/Cmd+R` reloads the app and `Ctrl/Cmd+Shift+I` opens DevTools.

## Linux AppImage (x86-64)

From `desktop/`, install dependencies and build:

```bash
npm ci
JUST_SING_URL=https://your-server.example npm run build:appimage
chmod +x dist/Just-Sing-0.1.0-x86_64.AppImage
./dist/Just-Sing-0.1.0-x86_64.AppImage
```

The build remembers that server URL, so double-clicking the AppImage opens it.
Without a build-time URL, the packaged app defaults to `http://localhost:8000`.
The API and built frontend must already be running on the chosen server; the
AppImage contains only the desktop shell, not Python, song assets, or credentials.
The output stays in gitignored `desktop/dist/`.

To use a different server without rebuilding:

```bash
JUST_SING_URL=https://another-server.example ./dist/Just-Sing-0.1.0-x86_64.AppImage
```

A Quick Tunnel hostname changes when the tunnel restarts; rebuild with the new
URL or use this environment override. If your Linux distribution cannot mount
AppImages through FUSE, run with `--appimage-extract-and-run`.

## What the web app sees

The preload script exposes `window.electronAPI = { isDesktop: true, platform }`
(typed in `web/src/electron.d.ts`). It is absent in a normal browser, so web
code must feature-check it: `if (window.electronAPI) { ... }`.

## Security choices

- **Isolated, sandboxed renderer:** `contextIsolation: true`, `sandbox: true`,
  `nodeIntegration: false`. The page has no Node access; it only gets the two
  read-only fields above through `contextBridge`.
- **Stays on its own origin:** navigation and `window.open` to any other origin
  are blocked. `https:` links open in the system browser; other schemes are
  ignored.
- **Microphone only:** the permission handlers grant `media` (audio, not video)
  to the app's origin and deny every other permission and origin.
- **Mic needs a secure context:** use `http://localhost` in development and the
  server's HTTPS URL everywhere else.
