# Local song author

Review prepared songs without changing the production server. This app binds
only to `127.0.0.1`; host/origin checks reject remote and cross-origin access.
Do not expose this port through a tunnel.

From the repository root (Python 3.11+, Node and FFmpeg installed), on Linux/macOS:

```sh
python3 -m venv author/.venv
author/.venv/bin/python -m pip install -r author/requirements.txt
cd author
npm ci
npm run build
cd ..
author/.venv/bin/python -m author.server
```

On Windows, using an existing API environment:

```powershell
uv --cache-dir ml/data/.uv-cache pip install --python api/.venv/Scripts/python.exe -r author/requirements.txt
cd author
npm ci
npm run build
cd ..
api/.venv/Scripts/python.exe -m author.server
```

Open http://127.0.0.1:8010. Override the data root with
`--data-dir <folder>` and port with `--port 8010`. The author server needs no
database and does not load ML models itself. Songs need `song.json` and both referenced audio files. Full pipeline
folders and portable handoff folders are supported.

## Add a recording

**Add song** accepts a raw audio file, title, artist, a new song ID, language
(Korean or English), and supplied lyrics with one sung line per line. Supported
files are MP3, WAV, FLAC, M4A, OGG and AAC, up to 250 MB. Lyrics are required;
the tool does not download songs or look up their words.

Configure existing offline model environments before starting the author server:

```sh
AUTHOR_PIPELINE_PYTHON=/absolute/path/to/pipeline/.venv/bin/python \
AUTHOR_SEPARATION_PYTHON=/absolute/path/to/demucs/.venv/bin/python \
author/.venv/bin/python -m author.server
```

Use `Scripts/python.exe` paths on Windows. Defaults are `ml/pipeline/.venv`
and `ml/pipeline/separation/.venv`. Follow the [pipeline setup](../ml/pipeline/docs/SETUP.md)
for model dependencies; installing the author requirements does not install them.
The two settings can point to the same compatible environment. FFmpeg must be on
PATH. Models may need an initial download; full songs can take several minutes.

**Process song** runs separation, synchronized encoding, lyric alignment and pitch
extraction in a separate process. Progress survives a page reload. Cancel stops
the processing job; failed/canceled jobs offer Retry and a local processing log.
Interrupted jobs become retryable failures after a server restart. Inputs and
job records stay under the data root's hidden `.imports/` directory. Completed
drafts appear only after validation; existing song IDs are never overwritten.

## Review and crop

Choose a song. Original/romanized lines, waveform and reference pitch share the
same timeline. Choose vocals, instrumental or both; click a line to seek.
Ctrl/Shift-click selects multiple lines. Assign Player 1/2 to all phrases in
the selected lines. The full list shows the distribution before playback.
Drag a timeline lyric block to move it: it follows the pointer, leaves a ghost
at its old position, and shows the proposed times before release. Invalid
placements turn red; Escape cancels the drag. Selected-line fields edit precise
line and phrase boundaries (including held endings). Voiced-onset snapping
uses a 150 ms window and can be disabled. Tap-to-sync starts at the selected
line: play vocals, then press Space at each entrance. Inputs keep normal Space
behavior. Invalid overlaps are rejected; edit a previous line's end first.

**Open timing / crop workspace** opens a full-screen editor with a whole-song
overview, zoom controls, searchable original/romanized lyrics, precise start/end
fields, playhead boundary buttons and selection preview. Use **Fit selection**
for detailed timing work. The selected-line editor and player assignment remain
available inside this workspace.

**Save as new short clip** creates a separate catalog folder with cropped stems
and rebased lyrics, phrases, pitch, exclusions and duet assignments. Save and
Rebuild source edits first. The source song stays intact; boundary lines cut
partway through are display-only, and the selection must include at least one
complete scored line. New clips always start unreviewed. Players have the same
large workspace for temporary whole-phrase practice selections; only the local
author tool can save clips into the catalog.

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
reviewed. Source downloads, note/octave editing and automated
judgment of timing accuracy remain outside this editor's scope. Lyrics, media,
corrections, backups and outputs remain in gitignored `ml/data/`.

The running karaoke API caches its catalog. To publish local edits/new songs to
your demo, run `python -m api.seed` in the API environment with its intended
database configured, then restart the single API worker. The author tool does
not change that database or restart the server automatically.

Checks (synthetic assets, no database or existing song changes):

```powershell
api/.venv/Scripts/python.exe -m pytest author -q --basetemp=ml/data/test-runs/author-tests
$env:AUTHOR_PYTHON = (Resolve-Path api/.venv/Scripts/python.exe).Path
cd author
npx playwright install chromium
npm run test:e2e
```

Playwright builds on the existing `dist/`; run `npm run build` first. The fixture
server uses a disposable directory under `ml/data/test-runs/`. Tests check
editing/persistence, not sync accuracy, reference quality or pronunciation.
