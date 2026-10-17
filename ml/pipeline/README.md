# Music preparation

## Selected audio

Russian Roulette uses:

- `ml/data/russian-roulette/vocals.mp3`: original htdemucs vocal estimate, without enhancement filters.
- `ml/data/russian-roulette/instrumental.mp3`: the improved residual instrumental selected by the user.

Both decode to 9,332,736 stereo samples at 44.1 kHz (211.626667 seconds).
`preparation.json` contains the active paths, provenance, hashes, and review status.
Cleanup copies the selected exports without re-encoding, preserving their sound.

Downloaded source audio, intermediate WAVs, comparison clips, older exports,
and synthetic test audio are removed during cleanup. Historical JSON reports
remain as evidence; their old paths are historical, not active references.
Model caches, virtual environments, and reusable scripts remain installed.
Decode the selected MP3s to temporary PCM for analysis. Repeating separation
requires downloading the source again; its URL and hash remain in metadata.
All song audio, lyric files, and model caches stay in gitignored `ml/data/`.

How Sweet by NewJeans is also prepared in `ml/data/how-sweet/`, with its own
`vocals.mp3` (original htdemucs estimate) and `instrumental.mp3` (mastered
fine-tuned residual). Choose it in the song picker or open
**http://127.0.0.1:8000/live/?song=how-sweet**.

Its selected source is `https://www.youtube.com/watch?v=KNqn_WuV2bE`. The initial
TJ Karaoke link was superseded because the sample appeared instrumental-only;
it is not the selected vocal/reference source. All 46 supplied lines match the
[studio timing source](https://lrclib.net/api/get/37129358) after normalization.
Ten independent ASR entrance matches indicate a recording offset of about 12 s
(median 11.99 s), with no meaningful tempo change detected. Fixed line anchors
therefore add 12 s, and the lyric region ends at 231 s before the video outro.
There are 406 timed words and eight supplied sections. The 20 ms reference has
12,411 frames; estimated intro/outro regions are excluded from scoring.

These are unreviewed preparation outputs. Acoustic word timing, melodic octave
errors, harmonies and the estimated boundaries still need listening review.
`corrections.json` preserves line entrances and section breaks; provenance and
the recording-offset diagnostic are retained alongside the prepared timeline.

Blood Sweat & Tears by BTS is prepared in `ml/data/blood-sweat-tears/` from
`https://www.youtube.com/watch?v=QFcJOvp5Cw0`, using the same original-vocal and
enhanced-instrumental recipe. It contains 49 supplied lines / 246 timed words
in 12 sections. The [matched line source](https://lrclib.net/api/get/942277)
includes explicit instrumental-break cues. Acoustic entrance checks support
keeping its original timing without a global offset; the estimated last lyric
ends at 202.50 s, before the recording ends. All timing remains unreviewed.
Preview: **http://127.0.0.1:8000/live/?song=blood-sweat-tears**.

## Song manifests

### Short demo handoff and text quality

The app demo assets are separate, exactly 30-second preparations:

| ID | Parent source window | Scoreable phrases |
| --- | --- | --- |
| `russian-roulette-demo` | 45.00–75.00 s | 11 |
| `how-sweet-demo` | 56.42–86.42 s | 5 |
| `blood-sweat-tears-demo` | 66.00–96.00 s | 5 |

Full songs are preserved. Each demo directory contains matching MP3s, a rebased
manifest/reference and review sidecar. Partial boundary lines are for display
only; their translations retain parent-line context and their practice/grading
is disabled. The cropper verifies exactly 1,323,000 decoded frames per stem.

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.crop --song russian-roulette --id another-demo --start 45 --duration 30
```

`practice_text` keeps the original whole line only when it contains Hangul and
no Latin letters. Mixed Korean/English and English-only lines get an empty
string; partial crop-boundary lines are also ineligible. This is
spoken-practice eligibility, not a pronunciation score. Original singing lyrics
and romanization remain available unchanged in the full songs.

All current full-song lines have English reading drafts in `translations.json`
and the manifests. These were assistant-generated from supplied lyrics, not
Gemini output, and have not been checked by a fluent reviewer. The translation
cache is text-hashed and reused on alignment reruns without overwriting existing
nonempty corrections. Gemini is not configured in this checkout.

Phrases require at least 0.5 s of voiced, non-excluded reference frames. Short or
empty phrases are listed in `song.review.json` and dropped from `phrases` while
their lines stay visible. Browser and backend scoring both use this phrase list.
Full-song manifests are v3 and demo manifests v2 after the whole-line practice fix.

**Still pending:** the teammate supplied four candidate backing-vocal ranges
from the contour (45.8–48.4, 50.0–51.3, 51.8–55.6 and 67.5–73.1 seconds of
Russian Roulette). The user has not listened yet. They remain recorded in
`ml/data/russian-roulette/reference.review.json` for review and have not been
applied as exclusions. Russian Roulette's backing/harmony cleanup still needs
listening review. No asset is marked reviewed.
The teammate's branch tools were fetched and copied into the gitignored
`ml/data/peer-tools/pitch-score/` directory, preserving local scoring code.
All six manifests pass the teammate's structural inspector; detailed findings
and the source commit are in each song's `INSPECTOR_REPORT.json`. Warnings
remain about note duration and phrase coverage. These checks cannot confirm
the correct singer or pitch by ear.

The local-only `/api/demo-handoff` download contains the three demo packages
with manifests, audio and review notes. Do not confuse passing mechanical checks
with having completed the outstanding backing-vocal review.

Each prepared song now contains `song.json` with the exact top-level fields from
`contracts/song.example.json`: provenance, relative audio paths, timed lines and
romanization, phrases, reference Hz, display notes and excluded regions. The
reference is embedded, so this is the single-file ML handoff alongside its MP3s.
The existing shared contract is unchanged. Media and manifests remain gitignored.

`song.review.json` records review state and hashes separately. Current manifests
are drafts: phrases use lyric windows and notes are automatic pitch segments.
Neither those windows nor the imported timings establish reviewed held-note
boundaries. The API keeps generated draft manifests out of the reviewed-lyrics
endpoint; local preview still works. Hand-edited or reviewed manifests are not
overwritten. Existing human-reviewed lyric sidecars take priority when assembling.

New `ml.pipeline.run` preparations create manifests automatically. After changing
an existing song's timing corrections or reference, rebuild from cached data:

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.manifest --all
# Or: python -m ml.pipeline.manifest --id blood-sweat-tears
```

No separation or pitch inference is repeated by this command. Rebuilding is
allowed only for unchanged drafts created by this generator, protecting edits.
Explicit per-line `line_ends` in `corrections.json` preserve instrumental gaps;
the LRC exporter includes corresponding blank cues.

## Environments

Run commands from the repository root. This Intel-graphics workstation uses
Python 3.11 and two CPU environments because Demucs requires older torchaudio:

| Environment | Purpose | Requirements |
| --- | --- | --- |
| `ml/pipeline/.venv` | Downloader, pitch, transcription/alignment | `requirements-pitch.txt`, `requirements-alignment.txt` |
| `ml/pipeline/separation/.venv` | Demucs separation | `requirements-demucs.txt` |

```powershell
uv --cache-dir ml/data/.uv-cache venv --python 3.11 ml/pipeline/.venv
uv --cache-dir ml/data/.uv-cache pip install --python ml/pipeline/.venv/Scripts/python.exe torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
uv --cache-dir ml/data/.uv-cache pip install --python ml/pipeline/.venv/Scripts/python.exe -r ml/pipeline/requirements-pitch.txt -r ml/pipeline/requirements-alignment.txt "yt-dlp[default]==2026.8.19" imageio-ffmpeg==0.6.0
uv --cache-dir ml/data/.uv-cache venv --python 3.11 ml/pipeline/separation/.venv
uv --cache-dir ml/data/.uv-cache pip install --python ml/pipeline/separation/.venv/Scripts/python.exe torch==2.0.1 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu
uv --cache-dir ml/data/.uv-cache pip install --python ml/pipeline/separation/.venv/Scripts/python.exe -r ml/pipeline/requirements-demucs.txt
```

Choose and verify a compatible build separately for GPU workstations. Do not
install Demucs in the modern PyTorch environment. The backend has its own
lightweight environment and never imports the preparation stack.

## Reusable commands

### Add another song in one command

Use a local source with lead vocals and a UTF-8 lyrics file (one line per line).
Run from the repository root with the pipeline environment:

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.run --id next-song --title "Song title" --artist "Artist" --clip "C:/path/to/song.mp3" --lyrics "C:/path/to/lyrics.txt" --source-url "SOURCE_URL"
```

Optional `--start 45 --duration 30` prepares a short excerpt. Its lyrics file must
contain only the words sung in that excerpt, and times start at zero for the clip.
Without these options, the full supplied recording is prepared.

The command separates original htdemucs vocals and a vocal-specific fine-tuned
residual instrumental, masters only the instrumental, exports the two selected
MP3s, checks equal decoded lengths, aligns supplied text, generates deterministic
romanization, extracts the pitch reference, and writes preparation metadata.
It uses the installed separate Demucs environment for separation. CPU processing
can take time; quality still depends on the recording and separation result.

If stems are already selected, reuse them without another mastering pass:

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.run --id next-song --title "Song title" --artist "Artist" --vocals "C:/path/to/vocals.mp3" --instrumental "C:/path/to/instrumental.mp3" --lyrics "C:/path/to/lyrics.txt"
```

Only use stems cut to the same start and end. Equal decoded length is checked;
it cannot prove that independently sourced stems have matching musical timing.
MP3 inputs are copied unchanged; other stem formats are encoded to 320 kbps MP3.

Outputs appear in `ml/data/<id>/` after all jobs succeed. Temporary separation
audio is cleaned up, leaving only `vocals.mp3` and `instrumental.mp3` alongside
lyrics, reference and reports. Original input files outside the preparation
workspace are left alone. Existing song IDs are refused to preserve selected
audio, versions and hand corrections; use a new ID for a replacement preparation.

Refresh **http://127.0.0.1:8000/live/** and choose the new song, or open
`http://127.0.0.1:8000/live/?song=next-song`. No server restart is needed. This is
an explicit offline command, not a background folder watcher. Every new song
still needs listening review of stems, line/word boundaries, reference pitch,
held-note phrase ends and exclusions before its scores can be treated as judged.

Display romanization uses pinned
[korean-romanizer](https://github.com/osori/korean-romanizer) (GPL-3.0), a deterministic
Revised Romanization library. Mixed English and punctuation are preserved.
It is a reading aid, not pronunciation assessment or a fluent review. The preview
uses the same word times for Korean and romanized display. To add romanization
to an existing automatic timeline without rerunning ML:

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.romanize --input ml/data/russian-roulette/alignment/lyrics.aligned.json --output ml/data/russian-roulette/alignment/lyrics.aligned.json
```

Use fresh output directories. These commands regenerate preparation outputs;
they do not replace the selected karaoke assets automatically.

### Download a source

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.download_audio "VIDEO_URL"
```

Downloads one video to `ml/data/downloads/<video-id>.mp3`; playlists are disabled.
The downloader uses bundled FFmpeg. Deno is available on this workstation.

### Separate source audio

```powershell
ml/pipeline/separation/.venv/Scripts/python.exe -m ml.pipeline.separate --input "path/to/source.mp3" --output ml/data/work/baseline
ml/pipeline/separation/.venv/Scripts/python.exe -m ml.pipeline.separate --input "path/to/source.mp3" --output ml/data/work/improved --model 04573f0d --overlap 0.5 --instrumental-method residual
```

The first command uses baseline htdemucs. The second uses the vocal-specific
checkpoint from htdemucs_ft and computes the backing as source minus the vocal
estimate. This may preserve detail while retaining more vocal bleed. The user
preferred this instrumental but rejected its vocal output; keep baseline vocals.
`--start` and `--duration` select a diagnostic excerpt. `separation.json` records
source hash, settings, crop, and frame checks. Cached weights are under
`ml/data/model-cache/torch/`. Listen to stems; equal duration alone is insufficient.

### Optional playback mastering

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.enhance --input-dir ml/data/work/improved/stems/04573f0d --instrumental-name instrumental-residual.wav --output-dir ml/data/work/playback
```

Produces 320 kbps MP3s and 24-bit WAVs with gentle high-pass filtering and two-pass
loudness normalization. It checks decoded frame counts and encoded peak headroom.
It does not repair watery separation artifacts. Do not apply vocal enhancement
to the selected original vocal reference unless the user chooses that change.

### Lyrics and alignment

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.transcribe --audio ml/data/russian-roulette/vocals.mp3 --output ml/data/work/lyric-draft --model small
```

Whisper creates unverified JSON/text/VTT with word timestamps, not corrected-text
forced alignment. It failed on this song's earlier vocals and original mix;
rejected drafts are not served by the API. The user supplied lyric text in chat;
it is now saved as `ml/data/russian-roulette/lyrics.supplied.txt`. Never invent timestamps by evenly
dividing song or line durations. Preserve hand corrections across reruns.

Align the supplied text and extract the reference without creating more audio:

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.align_lyrics --audio ml/data/russian-roulette/vocals.mp3 --instrumental ml/data/russian-roulette/instrumental.mp3 --lyrics ml/data/russian-roulette/lyrics.supplied.txt --output ml/data/russian-roulette/alignment
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.reference --audio ml/data/russian-roulette/vocals.mp3 --output ml/data/russian-roulette/reference.pitch.json
```

The reference command refuses to overwrite an existing file; use a new output
path for a new extraction. The aligner reuses audio-hashed acoustic emissions
and writes an automatic JSON timeline, VTT, LRC, and a word-confidence report.
Keep hand-corrected timelines separately so reruns cannot erase review work.
MMS_FA weights are cached locally and use the upstream CC-BY-NC 4.0 license.

The current full-song alignment contains 73 lines / 231 words. These are acoustic
word estimates inside fixed line windows, not evenly distributed guesses. The
initial unconstrained alignment drifted within repeated choruses and is retained
under `alignment/history/`. The replacement uses normalized text matches to
[LRCLIB line timestamps](https://lrclib.net/api/get/33861377), with the four intro
entrances retained from the earlier acoustic draft. It remains unreviewed: 205
words have posterior below the diagnostic 0.2 threshold.
Speech alignment confidence is not a singing score. Listen and correct it.
The reference uses the shared `ml.scoring.pitch.pitch_contour()` (CREPE, 20 ms),
with unvoiced frames represented by null. Check octave errors/harmonies and add
excluded ranges before judging singers.

The [backend and local preview](../../api/README.md) expose this draft explicitly
for playback, word highlighting, mic pitch and provisional scoring. The canonical
reviewed lyric endpoint stays unavailable until review. Scoring also needs reviewed
phrase boundaries through held notes. Analysis decodes the two selected MP3s in
memory; it does not restore deleted intermediate stems or the source recording.

`corrections.json` preserves the chosen line entrances and the user's section
breaks, bound to the vocal hash and a hash of the nonblank lyric lines. The
aligner automatically reuses it on reruns (or use `--corrections PATH`). Each
line is aligned independently inside its entrance window so repeated phrases
cannot pull later lyrics forward or backward across the song. The display holds
a line until the next entrance; its end is a display boundary, not a reviewed
held-note scoring phrase. Blank lines in supplied text group sections and do
not specify silence durations. Corrections require matching text/audio and
ordered, finite anchors. Neither these imported line anchors nor the intro
have been manually verified against this karaoke recording.

### Environment smoke tests

```powershell
ml/pipeline/.venv/Scripts/python.exe -m ml.pipeline.preflight --component pitch --smoke-test --device cpu
ml/pipeline/separation/.venv/Scripts/python.exe -m ml.pipeline.preflight --component separation --smoke-test --device cpu
```

These regenerate synthetic audio in `ml/data/smoke-test/`. Pitch uses a 220 Hz
tone, the full model, 16 kHz audio, 320-sample hops, and 65-1000 Hz limits.
Separation checks ten-second stereo output lengths. Successful inference does
not establish real-song quality. Synthetic outputs can be removed after testing.
