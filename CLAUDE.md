# K-Pop Karaoke (working title) - Project Brief for AI Agents

You are helping a 4-person team at **SwampHacks XII** (University of Florida hackathon, 36 hours) build a Smule-style K-pop karaoke web app. The user you are talking to may be on any role; check which one before editing. Read this whole file before doing anything.

## What we are building

A **website** where a user picks a K-pop clip, sings along with the instrumental, sees their live pitch drawn over scrolling target notes with synced lyrics (Korean + romanization + English), and gets a rating after every lyric phrase plus a final pitch/timing score with a short AI coaching blurb.

Three modes, in priority order:

1. **Solo karaoke (core MVP).** Pick clip -> pick register -> sing -> live pitch lane + phrase ratings (Perfect! / Great / Okay / Bad / Miss) -> final score -> coaching blurb.
2. **Spoken Korean pronunciation practice (core, separate mode).** The player reads a short lyric phrase aloud at normal speaking pace and gets word-level feedback. It never affects the singing score.
3. **Battle (deferred, stretch).** Two players take turns on the same clip under identical scoring rules; higher total wins, equal totals tie. **Do not start battle work (UI, schema, rooms) until solo karaoke and spoken practice work end to end.** Keep the scoring engine mode-agnostic so battle is just two turns of it. Local shared-laptop first; online two-computer rooms are a further stretch and cut first.

Platform: a **desktop app built with Electron**, a thin client that opens the shared server's own URL (React + Vite frontend served alongside FastAPI). The **browser version keeps working** next to it as the dev path and for judges; Electron-only code is feature-checked (`if (window.electronAPI)`) so the web path never breaks. No game engine, and no Python is bundled in the app. **Current focus: solo only.**

Planned demo clips (~30 s each, chosen by the team): Girls' Generation "Kissing You" and TWICE "What Is Love?". Get **one** working end to end before touching the second.

The singing screen is rhythm-game first: target notes and the live trace dominate, lyrics sit underneath. Do not turn it into an analytics dashboard.

## Goals (in priority order)

1. **Win the UF Data Science & Informatics "Most Creative Use of AI" track.** Judges want: AI/ML central to the project (non-trivial implementation, evals, custom models), a public repo with a README linked on Devpost, clean readable documented code, and the ability to explain design choices and tradeoffs. They said depth beats polish and that they will read the code and commit history.
2. Also target: Entertainment & Creative Technology (Swamp Studios), Easy On The Eyes (UI/UX), MLH Gemini API, MLH Tiger Data, MLH Auth0, MLH Vultr, MLH GoDaddy Registry. We are NOT targeting Least Vibe Coded, Solana, Roblox, or hardware.
3. A reliable live demo. One clip working end to end beats five half-working clips.

**Cut order if time runs short:** online rooms -> battle mode -> leaderboard -> Gemini coaching -> second song -> pronunciation practice. **Never cut** pitch/timing scoring, the singing UI, or the eval harness.

## Team and ownership

| Role | Owns |
|---|---|
| Frontend | React + TypeScript + Vite UI, Canvas pitch lane, audio clock, mic capture, live pitch (Pitchy), **the TypeScript port of the scoring engine**, lyrics, results, practice screen, the Electron shell (a window plus the Auth0 login helper), `web/`, `desktop/` |
| Full-stack/infra | FastAPI, Tiger Data (Postgres), Auth0, Vultr deploy, domain, FFmpeg audio normalization, practice-upload endpoint, `api/` |
| ML A (pipeline, then pronunciation) | Offline per-song processing in `ml/pipeline/`. After the first reviewed `song.json` exists, owns the local pronunciation scorer in `ml/pronunciation/`. |
| ML B (scoring + evals) | The Python **reference scoring engine** `ml/scoring/`, shared test fixtures, the evaluation harness `ml/evals/`, and calibration of thresholds/weights. Owns `ml/scoring/pitch.py`. |

Stay inside the folder of the role you are helping unless asked. Do not edit other roles' folders without saying so.

### ML split and shared pieces

1. **One `pitch_contour()`.** It lives in `ml/scoring/pitch.py` (ML B). ML A's pipeline imports it to build the reference; it must not be reimplemented in `ml/pipeline/`. Settings: 16 kHz audio, 0.02 s hop, `fmin=65`, `fmax=1000`, low-periodicity frames (~<0.5) are unvoiced (`null`), median-filter smoothing. Backend is selectable (`crepe` for the reference, `pyin` for CPU-only evals) with `torch`/`torchcrepe` imported lazily so `ml/scoring` stays importable without PyTorch.
2. **Pitch units: Hz everywhere in data.** Manifests and pitch tracks store Hz (`null` = unvoiced). Cents appear only as an *error* measure: `1200 * log2(user_hz / target_hz)`. MIDI/semitones are for display only. This matches what Pitchy outputs natively.
3. **Time: seconds relative to the prepared clip start**, everywhere (manifest, scoring, UI).
4. **Scoring exists twice, on purpose.** Live phrase ratings run in the browser (TypeScript, ported by Frontend). The Python engine in `ml/scoring/` is the **reference implementation and the thing the evals test**. Both must pass the same **shared fixtures** in `contracts/fixtures/` (JSON inputs -> expected outputs). Never change scoring math in only one language. Frontend must not invent a second rubric.
5. **Early rough `song.json`.** ML A hands ML B a rough manifest as soon as separation + pitch extraction work, so ML B can test on real data.
6. **Pipeline is song-agnostic.** Entry point takes arguments (e.g. `python -m ml.pipeline.run --id <song_id> --clip <path> --lyrics <path>`), not a hardcoded song. Outputs go to `ml/data/<song_id>/` (gitignored). Per-song human corrections (phrase boundaries, excluded regions, octave fixes) live in a small JSON next to the outputs so reruns reuse them.
7. **Reference review is manual.** Listen to the vocal stem and inspect the plotted contour; fix octave errors; mark unusable regions (backing vocals, harmonies) as `excluded` in the manifest. Exclusions are fixed per clip and identical for every player. Lyric/phrase timing is verified by ear; automatic alignment is only an assist. Nobody on the team is fluent in Korean, so take the Hangul text from a reliable source and say so in the README.
8. **Dependency environments are split** (see Hard rules). Demucs pins an old torchaudio, and RTX 5070 GPUs need a Blackwell-compatible PyTorch build. Verify a real separation run on the actual machine before promising anything.

## Architecture

**Offline preparation (once per clip, laptop or Colab/Kaggle GPU, never on the production server):**
1. Crop the source to one clip; keep a clean WAV analysis copy. Record the source URL/version and crop boundaries as provenance.
2. Demucs (`--two-stems=vocals`) -> vocals + instrumental. Vocals and instrumental must share one timeline; verify equal duration/alignment after resampling and encoding.
3. `pitch_contour()` (torchcrepe) on the isolated vocals -> reference Hz contour -> human review -> derive display notes.
4. Lyrics: hand-checked line + phrase timing (include sustained final notes in the phrase boundary). Romanization from a deterministic Revised Romanization library (verify the package before adding) so it can be checked; Gemini produces English translations and may cross-check romanization.
5. Output: one `song.json` manifest plus audio files.

**Live singing (browser, offline-capable with cached assets):** Web Audio plays the instrumental; `AudioContext.currentTime` is the single master clock for audio, notes, lyrics, and scoring. Mic capture uses `echoCancellation: false`, `noiseSuppression: false`, `autoGainControl: false` where supported (inspect what the browser actually applies); users wear wired headphones. An AudioWorklet timestamps samples; Pitchy gives live Hz. Each completed phrase is rated locally with no network wait; the final result aggregates the *same* phrase scores.

**Scoring (starting defaults, validate with the evals; thresholds live in config, not code):**
- **Register:** the player picks original / one octave lower / one octave higher before the turn. The target and scoring reference shift together for the whole turn; the instrumental stays in key. Do **not** forgive octave jumps per frame, and do **not** subtract a per-performance median "key shift". Both reward a broken melody.
- **Pitch:** per voiced, non-excluded reference frame, compare user Hz to target Hz in cents; soft credit (full within ~50 cents, falling to zero by ~150-200). Duration-weighted. Reference rests and excluded regions are not in the denominator. Missing/unvoiced user frames during a target note earn zero but stay in the denominator.
- **Timing:** compare the user's onsets with reviewed phrase entrances and note changes, after correcting **one** device latency offset measured in the setup step. Never optimize a separate offset per performance. Avoid unrestricted DTW; it aligns away the mistakes we want to measure (a bounded alignment may be used offline for analysis only and must be reported).
- **Total:** default 80% pitch / 20% timing (a default, not a validated weighting). Phrase rating bands (Perfect!/Great/Okay/Bad/Miss) are config, calibrated on recordings. `Miss` means insufficient sung coverage; a mic failure is an input error with a recovery state, never a poor score.
- Silence scores 0 overall. Mic noise must not earn points just because the tracker returns a frequency. Same reference, config, and math for every player. Deterministic: identical input -> identical score.
- Never use an LLM to decide scores or a winner.

**Pronunciation practice (separate mode, spoken not sung):**
The player reads a short Korean lyric phrase aloud. Sung audio is out of scope because ASR on singing is unreliable. We build this on **free, local, pretrained models**, not a paid API, and evaluate it ourselves:
- *Baseline A:* transcribe with faster-whisper (`language="ko"`, **no lyric prompt**, or the model will echo the answer) -> compare to the expected text at jamo level with RapidFuzz -> word-level highlights.
- *Baseline B:* CTC forced alignment of the expected text with a pretrained Korean wav2vec2 CTC model (`torchaudio` forced alignment; verify model license/size first) -> per-word posterior/confidence (goodness-of-pronunciation style) -> word-level highlights.
- Compare A vs B in the evals and ship whichever separates better. No paid or cloud speech APIs: everything runs locally on pretrained open models to keep cost at zero.
- Report word-level feedback only. Do not claim exact phoneme/consonant diagnosis, and label it automated and not validated by a fluent reviewer. API/model failure is an `unavailable` state with retry, never a low score.

**Backend (after the song):** the browser submits the structured phrase results (not raw audio) to FastAPI, which validates ranges and phrase IDs, recomputes the aggregate with the same config, and stores it. Results save in Tiger Data (Postgres). Gemini writes the coaching blurb from the *measured* numbers only.

## Data contracts (source of truth lives in `contracts/`)

`contracts/song.example.json`, `score.example.json`, and `practice.example.json` are the agreed shapes; fixtures live in `contracts/fixtures/`. Highlights:
- **Song manifest:** id, version, language, duration, provenance, audio paths (instrumental/vocals share a timeline), `lines` (text, romanized, translation, `practice_text`, word times), `phrases` (gradeable boundaries incl. sustained final notes), and `reference` (`hop_seconds`, `hz` contour with `null` for unvoiced, reviewed `notes`, `excluded` regions).
- **Score:** mode (`solo` | `battle`), clip + scoring versions, register in semitones (`-12`, `0`, `12`), total/pitch/timing (0-100), per-phrase scores with rating and coverage, coach blurb. **Pronunciation is not part of the score.**
- **Practice result:** locale, provider, `status` (`ok` | `unavailable` | `error`), per-word scores. `unavailable` is not a score.

Do not change a contract without telling the whole team; update `contracts/`, the examples, and the fixtures together.

## Infra

- **FastAPI** (Python 3.11), single Uvicorn worker. Keep the API importable without PyTorch/Demucs; model-backed endpoints (pronunciation) load lazily and run blocking inference outside the async event loop, one request at a time with an explicit busy/retry response.
- **Tiger Data (Postgres)** via SQLAlchemy 2 + psycopg 3 + Alembic migrations committed to the repo, plus an idempotent seed for the prepared clips. Browsers never touch the database. Store structured results and versions, **not** raw recordings; recordings stay session-local and temp uploads are deleted after assessment or failure.
- **Auth0** for login (saved history, leaderboard); guests can play without an account. The Electron app is an Auth0 **Native application** that logs in through the system browser with PKCE. The API's token check (signature, issuer, audience) does not change.
- **Hosting:** one shared FastAPI server and one Tiger Data database for every client. For the demo a team laptop runs the server behind a Cloudflare tunnel, and each Electron app loads that URL, so the guest cookie stays same-origin and no CORS work is needed (CORS and `SameSite=None; Secure` cookies are only needed if an app ever loads from a different origin than the server). Mic needs HTTPS in a secure context, so remote players use the HTTPS URL. **Vultr** VM plus a GoDaddy domain is a stretch goal. An offline fallback is a local Postgres on the demo laptop only, using the same migrations and `DATABASE_URL`; SQLite is not an option without changing `api/tables.py`.
- **Gemini** (MLH): translations, optional romanization cross-check, and the coaching blurb. Never scoring decisions.
- Online battle rooms (if reached): WebSocket events + HTTP durable actions, state machine in Postgres, idempotent result saves, reconnect via snapshot. Time-box it; if flaky, demo local battle and label online incomplete.

## Repo layout

```
ml/pipeline/       offline song processing (Demucs, CREPE, manifest assembly, Gemini)
ml/scoring/        Python reference scoring engine (pure functions, importable by api/)
ml/pronunciation/  local spoken-Korean scorer (faster-whisper, wav2vec2 CTC, RapidFuzz)
ml/evals/          evaluation harness and results
ml/data/           LOCAL ONLY, gitignored (audio, stems, model outputs)
api/               FastAPI backend
web/               React + Vite frontend
desktop/           Electron shell (window + Auth0 login helper); loads the server URL
contracts/         example files, schemas/Pydantic models, shared test fixtures
```

## Git workflow

- `main` always works. Never push directly to it after the initial skeleton; merge via GitHub PR (self-approval is fine).
- Short-lived branches off an up-to-date `main`, named `<role>/<task>`, deleted after merging (e.g. `web/scaffold-pitch-lane`, `api/scaffold-endpoints`, `ml/pipeline-demo-song`, `ml/pitch-score`, `ml/evals-degradation`, `ml/pronunciation-baselines`).
- Merge back often (several times a day) and `git pull origin main` into your branch often. Avoid long-lived per-person branches.
- Changes to `contracts/` or this file get their own small PR and the whole team is told.
- AI agents: never run `git commit` or `git push` unless the user explicitly asks. The user commits and pushes themselves.

## Hard rules

- **The repo is public.** Never commit copyrighted audio or video (no mp3/wav/flac/mp4/webm), model weights, or secrets. `ml/data/` is gitignored. Demo songs stay local; the public repo ships the processing scripts and royalty-free/CC test audio. The **deployed public instance must not serve copyrighted audio**; copyrighted demo clips run only from a team machine, and the public deployment ships a CC/royalty-free clip. A tunnel from a team laptop is a public URL: keep it out of the README and Devpost, and make the royalty-free clip the always-on default.
- Never commit API keys. Use `.env` (gitignored) and keep `.env.example` with fake values. Keep `DATABASE_URL` and API keys server-side only.
- Judges read the code and the git history. Write clear, commented, well-named code. Make small, frequent commits with meaningful messages. Never create filler commits.
- Do the heavy ML offline. Runtime scoring must be fast enough for a live demo.
- **No training from scratch and no fine-tuning of ASR/pitch models.** We have no labeled data and no fluent reviewer to validate it. Use pretrained models and engineer the scoring around them. The honest "custom model" work is the scoring/feedback engines plus **calibration** (weights, tolerance bands, rating thresholds, a small calibration model if useful) fit on synthetic degradations and team recordings.
- Use a short ~30 s clip for iteration, not full songs.
- Python 3.11. **Separate environments and requirements files:** `ml/requirements.txt` (scoring + evals, light), `ml/pipeline/requirements.txt` (Demucs/CREPE prep stack), `ml/pronunciation/requirements.txt` (speech models). Ask before adding heavy new dependencies.

## ML evaluation plan (this is what wins the AI track)

We have no human-labeled singing data, so we generate labeled data synthetically and with team recordings. Do not call the scoring "validated" because unit tests pass; keep an evaluation log of recordings used, observed rankings, latency, and limitations.

**Singing score** (run on pitch tracks extracted from degraded audio and, separately, on raw tracks):
- a clip scored against itself ~ 100; a reference-like take beats wrong notes and an intentionally late take
- original-register and correctly selected octave-shifted takes score comparably; a *wrong* register does not
- silence ~ 0; noise low; singing a small easy section does not give a near-perfect total
- rests, excluded regions, and mic noise earn no free points
- a known simulated capture offset is corrected; deliberate lateness stays penalized
- monotonic in severity under **local** degradations (per-note detuning, dropped segments, falling SNR, time stretch); report Spearman correlation. A *global* pitch shift is just a register change, so it is not a severity axis
- identical input -> identical output; Python and TypeScript agree on the shared fixtures
- tracker robustness: compare Pitchy-style browser tracks against torchcrepe tracks on the same audio and report the score difference
- tune weights, tolerance bands, and rating thresholds against this data and report the tuning honestly

**Pronunciation:** with TTS-generated Korean speech and teammate recordings, measure (a) matched-text vs mismatched-text separation (AUC) for Baseline A vs B, (b) whether an injected substituted/missing word is the word flagged (top-1 hit rate), (c) robustness to speed and noise. This shows the scorer detects wrong words; it does not validate accent quality, and the README must say so.

Results go in a table in the README. The README must have a "Design decisions and tradeoffs" section covering: why pitch contours over learned embeddings, why a fixed register instead of octave folding/key-shift tolerance, why no unrestricted DTW, why scoring in the browser with a Python reference and shared fixtures, why offline preprocessing, why local pronunciation models instead of a paid API, what failed, and what we would do next.

## Current status and immediate next steps

- Repo skeleton exists; no feature code yet. Direction reconciled from two planning docs: solo karaoke + spoken practice are core, battle is stretch, infra from the original brief (Tiger Data, Auth0, Vultr, Gemini).
- **Team, today:** agree on the manifest/score/practice contracts and pick the first clip; confirm the pronunciation handoff to ML A.
- ML A (`ml/pipeline-demo-song`): prove one real Demucs separation on the actual machine, extract the reference contour, hand ML B a rough manifest, then hand-review notes/phrases/exclusions and finalize `song.json`. Then `ml/pronunciation-baselines`.
- ML B (`ml/pitch-score`): `pitch_contour()` + pitch/timing scoring + shared fixtures + pytest on synthetic melodies; then `ml/evals-degradation`; then calibration. Share the scoring spec/fixtures with Frontend early.
- Frontend: Vite + React + TS, Web Audio clock, mic + Pitchy, pitch lane from the example manifest, TS scoring port against the fixtures.
- Full-stack: FastAPI scaffold, catalog + manifest endpoints, practice-upload endpoint with FFmpeg normalization, Tiger Data schema/migrations, a hello-world tunnel deploy early (Vultr is a stretch goal).
- First milestone: one clip, one singer, correctly synchronized pitch trace, and a good take reliably beating a bad take. Then spoken practice end to end. Battle and extras come after.

## How to work with me

- Briefly state your plan before large changes, then do the work.
- Keep changes scoped to the task. Prefer simple, readable solutions over clever ones.
- Run code and tests when you can instead of assuming they pass. Tell me plainly what you verified and what you did not; separate measured facts, chosen defaults, and unverified assumptions.
- If a request conflicts with the rules above (especially copyrighted audio or secrets in the repo), say so and suggest the safe alternative.
