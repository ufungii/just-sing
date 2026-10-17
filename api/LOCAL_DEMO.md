# Prepared songs and synchronized lyrics

This is the first backend slice: catalog, local audio playback, reviewed lyric
JSON, VTT subtitles, and a timestamp lookup for debugging. It does not load
PyTorch/Demucs, run inference, or generate lyrics during playback. No database
is required for these prepared file assets.

## Run locally (PowerShell, repository root)

```powershell
uv --cache-dir ml/data/.uv-cache venv --python 3.11 api/.venv
uv --cache-dir ml/data/.uv-cache pip install --python api/.venv/Scripts/python.exe -r api/requirements-dev.txt
$env:JUST_SING_LOCAL_DEMO_AUDIO = "1"
api/.venv/Scripts/python.exe -m uvicorn api.local_demo:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/live/** for the local karaoke preview, or
`http://127.0.0.1:8000/docs` for the API. The default data directory is `ml/data/`;
override it with `JUST_SING_DATA_DIR`. Localhost Vite origins on port 5173 are
allowed. The backend binds to loopback in the documented command.

Audio serving defaults to disabled. The explicit local-demo flag above is for
team-machine use: `CLAUDE.md` prohibits serving copyrighted demo audio from the
public deployment. Never mount the entire data directory: it also contains
model weights, drafts, and processing reports.

## HTTP endpoints

| GET path | Response |
| --- | --- |
| `/api/health` | Readiness and whether local audio is enabled |
| `/api/songs` | Available song metadata and lyric/audio URLs |
| `/api/songs/{id}/audio/instrumental` | Selected playback asset; supports byte ranges and HEAD for seeking |
| `/api/songs/{id}/audio/vocals` | Prepared raw vocal stem for review |
| `/api/songs/{id}/lyrics` | Status, song/version/duration, and timed `lines`/`words` |
| `/api/songs/{id}/lyrics.vtt` | Reviewed line-level WebVTT; 503 when unavailable |
| `/api/songs/{id}/lyrics/at?time_seconds=45.2` | Debug lookup of current line/word; no server timer |
| `/api/songs/{id}/lyrics/preview` | Local-only reviewed timeline or explicitly labeled supplied-text alignment draft |
| `/api/songs/{id}/reference` | Local-only cached reference Hz at 20 ms intervals |
| `/api/scoring-config` | Versioned provisional scoring configuration |

`POST /api/songs/{id}/score-preview` accepts `scoring_version`, fixed `register`
(-12, 0, or 12 semitones), `latency_seconds`, and `observations` containing
`{time, hz}` in clip seconds/Hz (`null` for unvoiced). It returns per-line feedback
and duration-weighted totals. This endpoint is local-demo only and stores nothing.
Scoring uses the manifest's filtered `phrases`, not every display line. The
preview response includes those same windows for browser scoring. A dropped
phrase remains visible as lyrics but contributes no score.

`GET /api/demo-handoff` downloads the locally generated 30-second demo package
when local-demo serving is enabled. It includes MP3s, manifests and review notes.

Times are seconds relative to the selected audio's start. Intervals include
their start and exclude their end. Before a line, between lines/words, and
after the end, the applicable active index is `null`.

The backend reads a final `song.json` using the existing `contracts/` shape,
or preparation metadata plus an explicitly reviewed `lyrics.reviewed.json`.
Generated drafts carry a separate `song.review.json`; they are not promoted to
reviewed lyrics merely because `song.json` exists. Their local preview remains
available. The manifest builder preserves the shared contract's field shape.
The response preserves the contract's line fields. No shared contract was
changed. It never reads `lyrics.draft.json`, and it rejects invalid timing,
overlapping lines, words outside their lines, non-finite timestamps, mismatched
versions, and reviewed sidecars bound to different audio bytes.

Russian Roulette has 73 supplied lyric lines and 231 whitespace words aligned
against the original vocal estimate using MMS_FA. The preview endpoint exposes
these real acoustic alignment timestamps with `status: "draft"`, `reviewed: false`.
The canonical reviewed endpoint remains unavailable until listening review.
Most words have low CTC posterior on this singing recording; inspect the alignment
report and correct timings by listening before using them for judged performance.
The selected audio files are `ml/data/russian-roulette/instrumental.mp3` and
`ml/data/russian-roulette/vocals.mp3` (the original vocal estimate).
`preparation.json` points both audio roles at these canonical filenames.

## Browser synchronization

Fetch lyrics once before playback, then select the line and word on each animation
frame using the same playback clock as the music. Do not poll `/lyrics/at`, use a
wall-clock timer, or stream a new lyric from the server every second.

The reference adapter is [examples/lyrics_clock.js](examples/lyrics_clock.js):

```javascript
const track = await loadLyrics("russian-roulette");
const stop = followPlayback(track, getPlaybackSeconds, updateLyricDisplay);
// Call stop() when leaving/resetting the screen.
```

The frontend owns `getPlaybackSeconds`, derived from its AudioContext schedule,
seek position, and paused state. For example, while playing:
`seekOffset + audioContext.currentTime - scheduledStartTime`; while paused,
return the frozen pause position. A countdown may yield negative time, which
shows no active lyric. Seeking jumps directly to the correct interval; pause
keeps the current line/word highlighted. Render lyric text using React's normal
text rendering or `textContent`, not `innerHTML`.

The runnable implementation is in `web/live/`; the adapter reexports its clock
helper. The preview shows active words, the next line, a seekable timestamp sheet,
the reference pitch and the user's trace. Play/Pause/seek use one AudioContext
clock. Enable the microphone explicitly, preferably with headphones; Pitchy runs
locally on sample-timestamped AudioWorklet windows. Only time/Hz observations are
sent to the local scoring endpoint, not microphone recordings.

The song picker lists prepared songs from the catalog; use the
[one-command preparation workflow](../ml/pipeline/README.md#add-another-song-in-one-command)
for new songs, then refresh the preview. **Vocal guide** mixes the selected original
vocal estimate over the instrumental. Both sources start at the same AudioContext
time and seek offset; toggling the guide fades its gain without restarting or
changing scores. The vocal volume slider adjusts the guide during playback
without restarting; the combined mix reduces backing gain to leave headroom.
Vocal guide and romanized lyrics are enabled by default, with vocal volume at 50%.
The slider is boosted: at 50% the guide matches the backing gain; at 100% its
gain is twice the backing. At 0% the guide is muted.
**Romanized lyrics** switches the current line, next line and timestamp sheet,
reusing word intervals when spacing matches. Missing romanization falls back to
original text. Both switches work during playback and pause.

The current Russian Roulette preview uses fixed line entrances to avoid drift
through repeated choruses. It keeps each line visible until the next entrance
and preserves the supplied section breaks in the timestamp sheet. Unreviewed
word timings can still be compressed by the speech aligner; word highlighting
is a normal, always-enabled lyric feature using those automatic estimates.
Music breaks display `♫⋆｡♪ ₊˚♬ﾟ.`.

The preview scores lyric intervals provisionally. Reviewed singing phrase ends
must extend through held notes and may differ from word-display timings. The
reference still needs octave/harmony corrections and excluded regions. Thresholds
are an uncalibrated baseline; timing offset is a fixed manual correction, not
device calibration. This scores melody/timing, not pronunciation or lyric accuracy.
Seeking or changing register/offset starts a fresh attempt. Browser and Python
scores use the same fixtures and version; a mismatch is displayed explicitly.

## Publish a corrected, reviewed timeline

First obtain correct Korean lyric text, align it to the vocal recording, then
check the line/word timings by listening. A text file alone does not establish
timing. Store this local JSON in the song's gitignored directory:

```json
{
  "reviewed": true,
  "lines": [
    {
      "start": 1.0,
      "end": 3.0,
      "text": "Your checked lyric line",
      "romanized": "",
      "translation": "",
      "practice_text": "Your checked lyric line",
      "words": [
        { "text": "Your", "start": 1.0, "end": 1.5 }
      ]
    }
  ]
}
```

This is illustrative text, not Russian Roulette lyrics or real timestamps.
Leave `words` empty if only line timings have been reviewed; do not invent word
times by splitting the line duration evenly.

```powershell
api/.venv/Scripts/python.exe -m api.publish_lyrics --song russian-roulette --input ml/data/russian-roulette/lyrics.corrected.json
```

The command validates timing against the prepared duration and writes
`lyrics.reviewed.json`, bound to a SHA-256 of the preferred instrumental.
It refuses to overwrite an existing reviewed track. Preserve the old track
and increment the song version when replacing a reviewed release. Publishing
here writes a local file only; it does not deploy or upload anything.

## Checks

```powershell
New-Item -ItemType Directory -Path ml/data/test-runs -Force | Out-Null
api/.venv/Scripts/python.exe -m pytest api/test_lyrics_api.py -q -p no:cacheprovider --basetemp ml/data/test-runs/lyrics-api
api/.venv/Scripts/python.exe -m pytest ml/scoring/test_live.py -q -p no:cacheprovider
deno test --allow-read=contracts/fixtures web/live/live_test.js api/examples/lyrics_clock_test.js
```

Tests use invented phrases and synthetic audio, not the rejected song drafts.
They cover boundaries, gaps, pause/backward seek, bad timing, stale audio/version,
draft rejection, path containment, VTT, range requests, and API/ML isolation.
Shared scoring fixtures cover correct/wrong pitch, fixed register, silence,
missing frames, early/late entry and note changes, fixed latency, exclusions,
rests and weighted aggregation. Browser hardware microphone testing is separate.
