# Local song author

Review prepared songs without changing the production server. This app binds
only to `127.0.0.1`; host/origin checks reject remote and cross-origin access.
Do not expose this port through a tunnel.

From the repository root (Python 3.11 and Node installed):

```powershell
uv --cache-dir ml/data/.uv-cache pip install --python api/.venv/Scripts/python.exe -r author/requirements.txt
cd author
npm ci
npm run build
cd ..
api/.venv/Scripts/python.exe -m author.server
```

Open http://127.0.0.1:8010. Override the data root with
`--data-dir <folder>` and port with `--port 8010`. No database or ML models are
loaded. Songs need `song.json` and both referenced audio files. Full pipeline
folders and portable handoff folders are supported.

Choose a song. Original/romanized lines, waveform and reference pitch share the
same timeline. Choose vocals, instrumental or both; click a line to seek.
Ctrl/Shift-click selects multiple lines. Assign Player 1/2 to all phrases in
the selected lines. The full list shows the distribution before playback.
Drag a timeline lyric block to move it; selected-line fields edit precise
line and phrase boundaries (including held endings). Voiced-onset snapping
uses a 150 ms window and can be disabled. Tap-to-sync starts at the selected
line: play vocals, then press Space at each entrance. Inputs keep normal Space
behavior. Invalid overlaps are rejected; edit a previous line's end first.

Undo/redo is in memory. **Save** writes `corrections.json` under a namespaced
`author` key and invalidates review; existing aligner anchors, hashes, provenance,
and unrelated fields are preserved. Original text changes regenerate
romanization on Save and clear stale word timings; this tool does not realign
words automatically. **Rebuild** applies saved absolute edits through manifest
assembly, including phrases, translations, exclusions and `duet_sections`.
Portable folders rebuild from their embedded manifest. Unsaved edits disable
Rebuild. Every overwritten JSON gets a `.bak` of the immediately previous
version. Changed-on-disk revisions and audio hashes reject stale edits.

**Mark reviewed** requires a rebuilt manifest, current audio hashes and explicit
human confirmation of listening review. Save/Rebuild never claim a draft was
reviewed. Song ingestion, source downloads, note/octave editing and automated
judgment of timing accuracy are outside this editor's scope. Lyrics, media,
corrections, backups and outputs remain in gitignored `ml/data/`.

Checks (synthetic assets, no database or existing song changes):

```powershell
api/.venv/Scripts/python.exe -m pytest author/test_author.py --basetemp=ml/data/test-runs/author-tests
$env:AUTHOR_PYTHON = (Resolve-Path api/.venv/Scripts/python.exe).Path
cd author
npx playwright install chromium
npm run test:e2e
```

Playwright builds on the existing `dist/`; run `npm run build` first. The fixture
server uses a disposable directory under `ml/data/test-runs/`. Tests check
editing/persistence, not sync accuracy, reference quality or pronunciation.
