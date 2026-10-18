# Lyric match: did the player sing the right words? (line level, while singing)

`ml/pronunciation/lyric_match.py`, version 0.1.0. This is feedback only. It never changes the
singing score, the phrase ratings or a battle winner.

## What it does

After a turn, the server compares each line the player sang with the **original singer's
recording of the same line**. It uses speech-model features (wav2vec2 layer 6, the same Korean
model as spoken practice) aligned by DTW. It does not transcribe: speech recognisers fail on
singing (AUC 0.62-0.65, `ml/evals/results/sung_lyrics.md`).

A line is a **match** when both hold:

1. **It beats its own hum.** We resynthesise the player's exact melody and loudness as a
   wordless "aah". The real line must sound clearly closer to the original line than that hum does
   (gain of at least `min_gain` = 0.06). The hum has the same tune, rhythm and length, so the only
   thing it lacks is the words. This is what stops a good tune from passing on its own.
2. **It is the right line.** The real line must be closer to the original's same line than to at
   least 80% of the song's other lines. This catches singing the wrong part of the song.

Lines the player did not sing (under 30% voiced frames) are `not_sung`. Lines outside the
recording are `not_covered`. Lines under 0.8 s are not graded. Neither test can be passed by
sounding like the original singer, because the player is a different voice compared with the same
original.

## Evidence (real takes, `ml/evals/lyric_match_eval.py`)

| Condition | Love Scenario (Daniel, 54 lines) | Last Christmas (9 lines sung) |
|---|---|---|
| Real take | **52/54 match (96%)** | **8/9 (89%)** |
| Original vocal scored against itself | 54/54 | 67/67 |
| Player's melody as a wordless "aah" | **0/54** | **0/9** |
| Real take read 6 s off (wrong lines) | 4/53 | 0/6 |
| Quiet noise | 0 (all `not_sung`) | 0 (all `not_sung`) |

Median gain over the player's own hum: +0.18 / +0.20 for real singing, about 0 for "aah".
Numbers are in `ml/evals/results/lyric_match_*.md`.

**How the rule was chosen (be honest about this):**
- The first version only used the second test, against similar-length lines. On it, "aah" passed
  41/54, so the tune was doing the work.
- Requiring the right line to be the single closest line cut "aah" to 15/54 on Love Scenario but
  still let 6/9 through on the short Last Christmas take.
- Comparing only against lines with a similar tune did not help (aah 30-36/54).
- The beat-your-own-hum test separated cleanly on both songs. The 0.06 margin was picked on these
  same two takes, so the table above is **not an independent test** of that number. It needs more
  takes from different singers.

**Draft line times are fine.** Moving every line's times in Daniel's take on purpose still left
96% of lines matching with times up to 1 s off. That held with each start and end off at random,
and with whole lines slid by 1 s it was 93%. "aah" stayed at 0-4%. The original and the player
are cut at the same wrong times, so they still line up with each other. Fingerprint draft
manifests now and rerun after the timing review.

**A singer who drifts off the beat loses lines.** A second Love Scenario take by the same
singer was sung from memory with no instrumental playing. It drifts from about 0.5 s off to about
3 s late over 57 s. At one fixed start time its first 8 lines are `unclear`
and its last 7 `match`. Yet at each line's own best time, every line beats its hum clearly
(gain +0.17 to +0.34), so the words were there; only the timing was off. In the app the
instrumental keeps players in time. But this check
assumes the player sings on the song's clock, so a line sung more than about a second late
is not credited.

**A real hum is harder to reject than our synthetic one (correction).** The "aah" control above is
resynthesised, and a real human hum passes the first test more easily. The test recording is Daniel
humming 34 s of Love Scenario with no words, from memory and without the music. It cannot be
placed on the song's clock, so we gave the check its best case: for each line, the start time in the
recording with the largest gain. Under that search, every one of the 54 lines cleared the hum test
(median gain +0.12, against +0.21 for his worded take under the same search). Both tests together
matched **32/54 lines for the hum, against 44/54 for words**. So the check separates humming from
words better than chance, but it does **not** reject real humming reliably. The search gives each
line about 140 tries, which favours both takes; the app uses one fixed start time. The fair test,
a hum sung along with the instrumental, is still to do. Until then, do not claim that humming
cannot pass.

## Not shown yet (limits)

- **Same tune, wrong words** is not directly tested. The controls show that the words matter
  (a hum fails), and that the wrong part of the song fails. A real wrong-lyric take sung in tune has
  not been tested; the closest is the splice test in `results/no_rerecord_controls_*_clean.md`
  (16/19 vs 10/19, word level, small).
- **Two singers, two songs.** No fluent Korean reviewer. It says "the words sounded like the
  original's words", not "your pronunciation is correct".
- **Word-level highlights are not reliable yet.** Show line results only. On an `unclear` line the
  UI may at most say "words unclear on this line", never point at a specific word.
- The original vocal stem must be clean lead vocal. Backing vocals or harmonies in the stem make
  their lines noisier.

## Cost

- **Fingerprints:** made once per song from the vocal stem, about 6 s on a GPU for a 4-minute
  song. The file is about 19 MB for a full song (float16, 1024 dims, 50 per second), so about
  2-3 MB for a 30 s clip.
- **Scoring:** on CPU only, a 35 s take takes about 10 s plus a 2.4 s model load. Peak RAM is
  2.8 GB, in the same process as the pronunciation model, which uses the same weights. Run it
  outside the event loop, one at a time, like the practice upload.

## For ML A (pipeline): one extra step per song

```bash
ml/pronunciation/.venv/bin/python -m ml.pronunciation.lyric_match fingerprint \
  --manifest ml/data/<song>/song.json --vocals ml/data/<song>/vocals.mp3 \
  --out ml/data/<song>/lyric_fingerprints.npz
```

Run it after the line timings are final. If line times change, rerun it, because the file
stores per-line slices. It is derived from the copyrighted vocal, so it stays in the gitignored
`ml/data/`. Like the audio, it is served only for the clips the deployment is allowed to serve.

## In the API (built: `api/lyric_check.py`)

`POST /api/lyric-check` (multipart). It's on when the server starts with `PRONUNCIATION_SCORER=1`, and it
shares that model and its busy lock. Same handling rules as the practice upload: FFmpeg to 16 kHz mono,
blocking work off the event loop, one model job at a time, and the upload deleted after the check or on
failure. Nothing is stored.

Request fields:
- `clip_id`
- `audio`: the solo take. The web app sends a 16 kHz mono WAV, at most 12 MB and 330 s.
- `offset_s`: the time in the recording at which clip time 0 falls, with the device latency already
  removed. The web app's recorder places every mic sample on the clip clock exactly like the pitch
  tracker does (`web/src/audio/takeRecorder.ts`), so `offset_s` is just minus the clip time where the
  recording starts.

The server finds `lyric_fingerprints.npz` next to the clip's `song.json`, caches it, and reloads it if
the file changes. The server tracks the hum's pitch itself with pyin. The browser's Pitchy track is
not sent.

Response (`contracts/lyric_check.example.json`):

```json
{
  "clip_id": "love-scenario",
  "status": "ok",
  "lyric_match_version": "0.1.0",
  "lines": [
    { "line_index": 0, "status": "match" },
    { "line_index": 1, "status": "unclear" },
    { "line_index": 2, "status": "not_sung" },
    { "line_index": 5, "status": "not_covered" }
  ]
}
```

- `status` is `ok`, `unavailable` (the checker isn't running, or this clip has no fingerprints) or
  `error` (the check failed). Neither `unavailable` nor `error` is a bad result.
- A busy model gets 429 `pronunciation_busy` (retryable), and the web app retries once.
- `line_index` indexes the manifest's `lines`.
- `gain` and `share` per line go to the server log for calibration, not to the UI.

Tests: `api/tests/test_lyric_check.py` (no database or model needed). It was also checked with the
real model through the endpoint on 40 s of a real take: 12/12 lines matched at the right offset,
2/9 when read 6 s off.

## Live path: one line at a time, during the song

Checking the whole take after the song took about a minute for a 4-minute song on the server's CPU. So
the singing screen now sends each lyric line as soon as it has been sung (`web/src/screens/Sing/liveLyrics.ts`):
a slice from 0.3 s before the line to 0.5 s after it, to `POST /api/lyric-check/line` (`clip_id`,
`line_index`, `offset_s`, `audio`). Requests go one at a time in line order. The server grades only that
line, but still compares it against **all** of the song's lines, so the rule is the same as for a
whole take. A small "LYRICS x/y" chip in the singing screen counts up as answers arrive. If the live
path is unavailable or loses a line, the results screen falls back to uploading the whole take.

Measured on CPU, end to end through the endpoint (Daniel's Love Scenario take, 54 lines):

| | Live, per line | Whole take after the song |
|---|---|---|
| Time per request | median 1.4 s, max 2.5 s | about 10 s per 35 s of audio |
| Results ready | about 1-2 s after the song ends | about 1 minute after a 4-minute song |
| Real singing matched | 45/54 (83%) | 48/54 (89%) |
| Real hum over the beat matched | 1/6 | 0/6 |

Lines in this song end every 3.9 s on average (the shortest gap is 1.0 s), so the server keeps up. A
slice gives the model less surrounding audio than the whole take, which costs a few lines. Wider
slices (1.0 or 1.5 s each side) did not help. Short slices exposed one bug, now fixed: the "is anyone
singing" noise floor came from the slice's quietest frames, which were singing, so sung lines read as
`not_sung`. The floor is now capped at -45 dBFS. The production server's CPU may be slower than the
laptop these timings come from.

## In the UI (built: results screen, solo only)

After the song the results screen uploads the take once and shows "checking your lyrics…". Each
phrase row then decorates its lyric line:

| status | Shown |
|---|---|
| `match` | a mint highlighter on the Korean line, plus a "LYRICS ♪" tag |
| `unclear` | a wavy pink underline plus a soft "words?" tag. It never says "wrong" and never points at a word |
| `not_sung` | a faded line plus a "not sung" tag |
| `not_covered` | nothing |
| `unavailable` or `error` | "lyric check is offline right now". Scores are unaffected |

A summary line says how many sung lines sounded like the original lyrics. It is labelled
"Compared with the original singer by a speech model. Automated, not checked by a fluent speaker,
and not part of your score." Battle and online turns don't run the check.
