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

## Install a release (players)

Download the file for your OS from the repo's **Releases** tab. The app opens
`https://just-sing.ink` (the shared server), so it needs internet and a microphone.

| OS | File | Run |
|---|---|---|
| Windows | `Just-Sing-<version>-win-x64.exe` | Run the installer. SmartScreen may warn ("unknown publisher"): **More info → Run anyway**. |
| macOS | `Just-Sing-<version>-mac-<arch>.dmg` | Drag to Applications. First launch: right-click the app → **Open** (the build is unsigned). |
| Linux | `Just-Sing-<version>-linux-x86_64.AppImage` | `chmod +x` the file, then run it. Without FUSE, add `--appimage-extract-and-run`. |

The first time you sing, allow the microphone when asked. The builds are
**unsigned** (no paid certificates for a hackathon), hence the OS warnings.

## Build and publish (maintainers)

Local build for your own OS, from `desktop/`. The server URL is baked in at
build time; without `JUST_SING_URL` the packaged app defaults to
`http://localhost:8000`:

```bash
npm ci
JUST_SING_URL=https://just-sing.ink npm run dist   # installer lands in gitignored desktop/dist/
```

Windows and macOS installers can only be built on those systems, so releases
are built by `.github/workflows/release.yml`. Push a version tag and it builds
all three OSes and attaches the files to a GitHub Release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

To use a different server without rebuilding, set the variable at launch, e.g.
`JUST_SING_URL=https://another-server.example ./Just-Sing-0.1.0-linux-x86_64.AppImage`.
A Quick Tunnel hostname changes whenever the tunnel restarts, so use this
override (or rebuild) for tunnel demos. The app contains only the desktop
shell: no Python, song assets or credentials.

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
