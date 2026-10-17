# Offline music preparation

Prepare synchronized vocal/instrumental MP3s, timed lyrics, romanization and a
reference pitch track, then assemble the shared `song.json` contract. Heavy
processing runs offline; audio, lyrics, models and generated outputs stay in
gitignored `ml/data/`.

## Start here

1. Follow [environment setup](docs/SETUP.md). The main pipeline and Demucs use
   separate Python 3.11 environments.
2. Pitch extraction uses `ml.scoring.pitch.reference_contour()`, which owns
   chunking, RMS gating and smoothing. Install its offline dependencies using
   the setup instructions; the runtime API does not load those models.
3. Provide a recording with lead vocals and a UTF-8 lyric file. Each nonblank
   line is a display line; blank lines separate sections.

Run commands from the repository root:

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.run --id next-song --title "Song title" --artist "Artist" --clip "C:/path/song.mp3" --lyrics "C:/path/lyrics.txt" --source-url "SOURCE_URL"
```

Use `--start 45 --duration 30` to prepare a short excerpt directly; supply only
its lyrics. Existing song IDs are never overwritten. The recipe keeps original
htdemucs vocals and masters only the fine-tuned residual instrumental. To reuse
selected stems, supply `--vocals PATH --instrumental PATH` instead of `--clip`.

## Code layout

| Module | Responsibility |
| --- | --- |
| `run.py` | Validate inputs, select stems, run stages, publish a complete preparation |
| `download_audio.py` | Download one recording locally |
| `separate.py`, `enhance.py` | Isolated Demucs separation and instrumental mastering |
| `align_lyrics.py` | Acoustic word alignment, fixed line corrections and subtitles |
| `reference.py` | Call ML B's shared pitch adapter and save its output |
| `romanize.py`, `text.py` | Romanization, practice eligibility and translation-cache checks |
| `manifest.py` | Contract assembly, phrase eligibility and review/edit protection |
| `crop.py` | Matching audio crops and rebased lyrics/reference |
| `audio.py`, `common.py` | Shared decoding, paths, file hashing and JSON reads |
| `preflight.py`, `transcribe.py` | Environment checks and optional independent ASR drafts |
| `tests/` | Tests with expensive model inference mocked |
| `docs/` | Setup, detailed commands, song provenance and review notes |

CLI names remain stable: use `python -m ml.pipeline.<module>`. Model libraries
load when their stages run. The manifest builder has no dependency on the local
demo scorer, API or browser implementation.

## Outputs and review

Each `ml/data/<id>/` preparation contains:

```text
vocals.mp3                   instrumental.mp3
preparation.json             lyrics.supplied.txt
alignment/                   reference.pitch.json
song.json                    song.review.json
```

Corrections belong in `corrections.json`; cached translation drafts use
`translations.json`. Both are bound to their source text/audio. Alignment reruns
reuse matching acoustic emissions. See [detailed workflow](docs/WORKFLOW.md).

Rebuild a generated manifest from cached data, or create a new short demo:

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.manifest --id next-song
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.crop --song next-song --id next-song-demo --start 45 --duration 30
```

Manually edited or reviewed manifests are protected from replacement. Display
lines stay visible when their phrases have less than 0.5 seconds of voiced,
non-excluded reference. Partial crop-boundary lines are display-only.
`practice_text` keeps a whole line only if it contains Hangul and no Latin
letters. English translations are reading drafts until reviewed.

Passing structural checks does not verify the correct singer, lyric entrances,
held endings, harmonies or pitch octaves. Listen before judging singers. See
[prepared songs and outstanding review](docs/SONGS.md).

## Tests and integration

```powershell
ml/pipeline/.venv/Scripts/python.exe -m unittest discover -s ml/pipeline/tests -t . -q
```

Tests use temporary fixtures and mock model inference. The adapter test does not
replace integration testing against ML B's real implementation.

Keep the pipeline PR limited to `ml/pipeline/`. Local demo URLs in the song notes
refer to a separate API/browser workstream. Integrate `song.json` through the
shared contracts; share local audio/manifest packages outside Git.
