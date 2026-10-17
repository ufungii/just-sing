# Just Sing - Project Brief for AI Agents

You are helping a 4-person team at **SwampHacks XII** (University of Florida hackathon) build a Smule-style, just-dance like, K-pop karaoke web app. The user you are talking to is on the ML side. Read this whole file before doing anything.

## What we are building

A **website** where a user picks a K-pop song, sings along with the instrumental, sees their live pitch drawn over the target notes with synced lyrics (Korean + romanization + English), and gets a score with per-line feedback and a short AI coaching blurb.

Core loop: pick song -> sing -> live pitch lane + highlighted lyrics -> post-song score and feedback -> leaderboard.

## Goals (in priority order)

1. **Win the UF Data Science & Informatics "Most Creative Use of AI" track.** Judges want: AI/ML central to the project (non-trivial implementation, evals, custom models), a public repo with a README linked on Devpost, clean readable documented code, and the ability to explain design choices and tradeoffs. They said depth beats polish and that they will read the code and commit history.
2. Also target: Entertainment & Creative Technology (Swamp Studios), Easy On The Eyes (UI/UX), MLH Gemini API, MLH Tiger Data, MLH Auth0, MLH Vultr, MLH GoDaddy Registry. We are NOT targeting Least Vibe Coded, Solana, Roblox, or hardware.
3. A reliable live demo. One song working end to end beats five half-working songs.

## Team and ownership

| Role | Owns |
|---|---|
| Frontend | React/Vite UI, pitch lane, lyric highlighting, results screen, `web/` |
| Full-stack/infra | FastAPI, Tiger Data (Postgres), Auth0, Vultr deploy, domain, `api/` |
| ML A (pipeline) | Offline per-song processing, `ml/pipeline/`. After the demo `song.json` is done, also owns the pronunciation scorer, `ml/scoring/pronunciation.py` (see ML split below). |
| ML B (scoring + evals) | Scoring engine and evaluation harness, `ml/scoring/` (except `pronunciation.py`), `ml/evals/`. Also owns `ml/scoring/pitch.py`. |

Stay inside the folder of the role you are helping unless asked. Do not edit other roles' folders without saying so.

### ML split and shared pieces

ML B has the larger workload (pitch, DTW timing, blend, evals), so pronunciation scoring goes to ML A once the pipeline works. Pronunciation only needs text and word timings, so it shares almost no code with pitch scoring and the two can proceed in parallel.

Shared pieces where ML A and ML B can collide:

1. **One `pitch_contour()`.** It lives in `ml/scoring/pitch.py` (owned by ML B). ML A's pipeline imports it to build the reference contour; it must not be reimplemented in `ml/pipeline/`. If reference and user contours use different settings, every score is biased. Settings: 16 kHz audio, 0.02 s hop (`hop_length=320`), `fmin=65`, `fmax=1000`, periodicity below ~0.5 counts as unvoiced (`null`), median-filter smoothing.
2. **Cents convention (decided, do not change without telling the team):** cents are absolute, MIDI note number x 100, so A4 (440 Hz) = 6900 and middle C = 6000.
   `cents = 1200 * log2(hz / 440) + 6900`. Singing falls roughly in 4500-7500. The `1250.5` in `contracts/song.example.json` is only a placeholder. The frontend's `pitchy` output must be converted with the same formula.
3. **Early rough `song.json`.** ML A should hand ML B a rough `song.json` (even with unpolished lyrics) as soon as Demucs + CREPE work, so ML B can test per-line scoring on real data.
4. **Pipeline must be song-agnostic.** ML A's entry point takes arguments (e.g. `python -m ml.pipeline.run --id <song_id> --clip <path> --lyrics <path>`), not a hardcoded song. Outputs go to `ml/data/<song_id>/` (gitignored). Per-song hand corrections (lyric timing fixes) live in a small JSON next to the outputs so reruns reuse them. Plan is ONE polished demo song first; a second or third only after the vertical slice works.
5. **Lyric timing uses forced alignment, not transcription.** Lyrics are known, so align the official text with `whisperx.align()` rather than transcribing and fixing errors. When transcribing the *user* for pronunciation scoring, never pass the true lyrics to Whisper as a prompt (it would echo them and make the score meaningless).

## Git workflow

- `main` always works. Never push directly to it after the initial skeleton; merge via GitHub PR (self-approval is fine).
- Short-lived branches off an up-to-date `main`, named `<role>/<task>`, deleted after merging. Examples: `web/scaffold-pitch-lane`, `api/scaffold-endpoints`, `ml/pipeline-demo-song`, `ml/pitch-score`, `ml/evals-degradation`, `ml/dtw-timing`.
- Merge back to `main` often (several times a day) and `git pull origin main` into your branch often. Avoid long-lived per-person branches.
- Changes to `contracts/` or this file get their own small PR and the whole team is told.
- AI agents: never run `git commit` or `git push` unless the user explicitly asks. The user commits and pushes themselves.

## Architecture

**Offline pipeline (once per song, run on a laptop or Colab/Kaggle GPU, never on the production server):**
1. Demucs (`--two-stems=vocals`) splits the song into vocals and instrumental stems.
2. WhisperX (fallback: faster-whisper) runs on the *isolated vocals* with `language="ko"` to get word-level timestamps. Lyrics are hand-corrected afterwards.
3. torchcrepe extracts the reference pitch contour from the isolated vocals (~50 frames/sec, stored in cents).
4. Gemini adds romanization and English translation per line.
5. Output is one `song.json` plus audio files.

**Live (browser):** Web Audio plays the instrumental; `AudioContext.currentTime` is the master clock. A pitch detector (`pitchy`) draws the user's pitch in real time. Mic must use `echoCancellation: false` (and users wear headphones). The browser records mic audio and logs pitch frames.

**Scoring (backend, after the song):** the browser POSTs the recording and pitch trace. The scoring engine compares user vs. reference:
- Pitch: compare contours in cents, with **octave folding** and **key-shift tolerance** (subtract the median offset), counting frames within a tolerance (default 50 cents), multiplied by a voiced-coverage factor.
- Timing: DTW alignment (`librosa.sequence.dtw`) plus latency calibration.
- Pronunciation: transcribe/forced-align the user's vocals and compare with true lyrics (wav2vec2 CTC alignment confidence per word). Computed asynchronously, since it is the slowest part.
- Final score: weighted blend, per-line breakdown, Gemini-written coaching blurb.

Pitch and timing scores return immediately. Pronunciation fills in later via polling.

## Data contracts (source of truth lives in `contracts/`)

Song JSON:
```json
{
  "id": "string",
  "title": "string",
  "artist": "string",
  "audio": { "instrumental": "path", "vocals": "path" },
  "offset_ms": 0,
  "lines": [
    {
      "start": 12.3, "end": 15.8,
      "text": "Korean text", "romanized": "...", "translation": "...",
      "words": [{ "text": "...", "start": 12.3, "end": 12.9 }]
    }
  ],
  "pitch_contour": { "hop_seconds": 0.02, "cents": [null, 1250.5, 1262.1] }
}
```
Unvoiced frames are `null`. All times are in seconds.

Score JSON:
```json
{
  "total": 0,
  "pitch": 0, "timing": 0, "pronunciation": null,
  "per_line": [{ "line_index": 0, "pitch": 0, "timing": 0, "pronunciation": null }],
  "coach_blurb": "string"
}
```
`pronunciation` is `null` until the async pass completes. Do not change either contract without telling the whole team; update `contracts/` and the example files together.

## Repo layout

```
ml/pipeline/   offline song processing (Demucs, WhisperX, CREPE, Gemini)
ml/scoring/    scoring engine (pure Python functions, importable by api/)
ml/evals/      evaluation harness and results
ml/data/       LOCAL ONLY, gitignored (audio, stems, model outputs)
api/           FastAPI backend
web/           React + Vite frontend
contracts/     JSON schemas, Pydantic models, example files
```

## Hard rules

- **The repo is public.** Never commit copyrighted audio (no mp3/wav/flac), model weights, or secrets. `ml/data/` is gitignored. Demo songs stay local; the public repo ships a download/processing script and royalty-free or CC test audio.
- Never commit API keys. Use `.env` (gitignored) and keep `.env.example` with fake values.
- Judges read the code and the git history. Write clear, commented, well-named code. Make small, frequent commits with meaningful messages. Never create filler commits.
- Do the heavy ML offline. Runtime scoring must be fast enough for a live demo.
- Do not train models from scratch. We have no labeled data and no time. Use pretrained models and engineer the scoring around them.
- Use a short 60-90 second chorus clip for iteration, not full songs.
- Python 3.11. Keep dependencies in `ml/requirements.txt`. Ask before adding heavy new dependencies.

## ML evaluation plan (this is what wins the AI track)

We have no human-labeled singing data, so we create labeled data synthetically: take the reference vocals and degrade them in known, controllable ways (pitch shift by N cents, time stretch, additive noise, wrong/missing words). Then verify the scoring engine:
- scores a clip against itself at about 1.0
- ignores a full octave shift and small key shifts
- gives silence about 0 and noise low scores
- is monotonic in degradation severity (report Spearman correlation)
- tolerates realistic timing offsets

Results go in a table in the README. Weights of the final score blend are tuned against this synthetic data, and that tuning is our honest "custom model" story. The README must have a "Design decisions and tradeoffs" section covering why pitch contours over learned embeddings, why octave folding, why offline preprocessing, what failed, and what we would do next.

## Current status and immediate next steps

- Repo skeleton exists (folders, contracts, `.gitignore`, `.env.example`, `ml/requirements.txt`); no feature code yet.
- ML A (branch `ml/pipeline-demo-song`): get Demucs + CREPE working on one chosen demo clip and hand ML B a rough `song.json` early; then add WhisperX forced alignment of the known lyrics, Gemini romanization/translation, and validate against `contracts/`. Then the pronunciation scorer (RapidFuzz-on-jamo baseline first, wav2vec2 confidence second).
- ML B (branch `ml/pitch-score`): implement `pitch_contour()` and `pitch_score()` in `ml/scoring/pitch.py` with synthetic-audio pytest tests, then the synthetic-degradation eval script in `ml/evals/`, then DTW timing.
- Eval trap: a *global* pitch shift is exactly what key-shift tolerance ignores, so it will not lower the score. Test monotonicity with *local* degradations (per-note detuning, dropped segments, falling SNR, time stretch).
- Two score modes are planned as weight presets only (Karaoke: pitch-heavy; Language Learning: pronunciation-heavy). When `pronunciation` is still `null`, redistribute its weight over the other scores. Adding a `mode` field to the score contract needs a team heads-up first.
- First milestone: one song working end to end (vertical slice). Add more songs and polish only after that.
- If time gets short, cut Gemini coaching and pronunciation scoring first. Never cut pitch scoring or the UI.

## How to work with me

- Briefly state your plan before large changes, then do the work.
- Keep changes scoped to the task. Prefer simple, readable solutions over clever ones.
- Run code and tests when you can instead of assuming they pass. Tell me plainly what you verified and what you did not.
- If a request conflicts with the rules above (especially copyrighted audio or secrets in the repo), say so and suggest the safe alternative.
