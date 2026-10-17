# Detailed preparation workflow

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

Song-specific timing sources and earlier alignment failures are recorded in
[the song notes](SONGS.md). Word-confidence flags guide listening review; they
are not singing or pronunciation scores.

The reference uses ML B's shared `ml.scoring.pitch.reference_contour()` adapter
(CREPE, 20 ms). That upstream change must be present before running extraction;
the pipeline does not substitute a separate extractor when it is missing. The
manifest builder counts voiced, non-excluded frames for phrase eligibility
without importing the local demo scoring implementation. Keep the pipeline PR
limited to `ml/pipeline/`; API, browser demo and shared scoring changes belong
in their respective workstreams.

The shared reference adapter handles chunking, the RMS gate and smoothing,
with unvoiced frames represented by null. Check octave errors/harmonies and add
excluded ranges before judging singers.

The [backend and local preview](../../../api/README.md) expose this draft explicitly
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
