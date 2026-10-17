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

## For the API (proposal for waychlate)

`POST /matches/{match_id}/lyric-match` (multipart). Same handling rules as the practice upload:
FFmpeg to 16 kHz mono, run blocking outside the event loop, one at a time with busy/retry, and
delete the upload after scoring or on failure. Never store the recording.

Request fields:
- `audio`: the player's mic recording of the turn (WAV/WebM).
- `offset_s`: the time in the recording at which clip time 0 falls, **after** the latency
  correction. That is `(clip start on the AudioContext clock - recording start on the same clock)
  + latency_s`. The singer is late by the device latency, so adding it lines their voice up with
  the clip.
- optional `pitch_hz` plus `hop_s`: the Pitchy track the browser already measured. If it is
  missing, the server tracks pitch itself with pyin.

Server call:

```python
from ml.pronunciation.lyric_match import load_fingerprints, lyric_match
fp = load_fingerprints(f"ml/data/{song_id}/lyric_fingerprints.npz")   # cache per song
result = lyric_match(wav_16k, 16000, fp, offset_s=offset_s)          # take_hz=... if provided
```

Response (proposed `contracts/lyric_match.example.json`; it needs a team OK because it is a
contract change):

```json
{
  "match_id": "m_123",
  "clip_id": "love-scenario",
  "lyric_match_version": "0.1.0",
  "status": "ok",
  "lines": [
    { "line_index": 0, "status": "match" },
    { "line_index": 1, "status": "unclear" },
    { "line_index": 2, "status": "not_sung" },
    { "line_index": 5, "status": "not_covered" }
  ],
  "summary": { "graded": 2, "match": 1, "not_sung": 1, "not_covered": 1 }
}
```

- `status` is `ok`, `unavailable` (no fingerprints for this clip, model not loaded, or busy) or
  `error`. Just as with practice, `unavailable` is never a bad result.
- `line_index` indexes the manifest's `lines`.
- The function also returns `gain` and `share` per line. Log them for calibration, but do not
  send them to the UI.
- Store only this JSON next to the match, if anything. It is not part of the score or the
  leaderboard.

## For the UI (proposal for Daniel)

These go on the results screen after the song, never during singing. The check takes about
10 s, so show a small "checking lyrics..." state. Per lyric line:

| status | Show |
|---|---|
| `match` | a small check by the line ("lyrics ✓") |
| `unclear` | a soft hint: "words unclear on this line". Do not say "wrong" and do not highlight a word |
| `not_sung` | a muted "not sung" |
| `not_covered` | nothing |
| `status: unavailable` | hide the lyric column, or show "lyric check unavailable", with a retry |

Label the section as automated: "Compared with the original singer. Not checked by a fluent
speaker."
