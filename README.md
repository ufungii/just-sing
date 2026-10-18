# ♪ Just Sing! ♪

**A (mostly K-pop) karaoke game that actually listens to you.** (ﾉ≧▽≦)ﾉ

Pick a song, sing along with the instrumental, and watch your voice draw a live line over the
melody while the lyrics scroll by in Hangul, romanization and English. Every phrase gets a
rating the moment you finish it (**PERFECT! / GREAT / OKAY / BAD / MISS**). At the end you get
a pitch and timing score, an overall **pronunciation report** (did you sing the right words?),
and a little pep talk from Mic-chan.

Built in 36 hours at **SwampHacks XII** by a team of four, none of us fluent in Korean (yet!).

https://youtu.be/QFOFoudTSPE

---

## ✦ What you can do

| Mode | What happens |
|---|---|
| **SING** ♪(^▽^)♪ | Pick a clip and a register (original, an octave down, or an octave up), then sing. Your pitch traces over the target notes, and each phrase is rated live, in the browser, with no waiting on a server. When the song ends you get your score plus an overall pronunciation report. Solo, or **1P vs 2P** on one laptop (player 2's lines in blue), with the same scoring rules for both. |
| **ONLINE** (＾▽＾)ﾉ ⇄ ヽ(＾▽＾) | Make a room, send the code to a friend, and sing against each other from two computers. |
| **SAY IT RIGHT** (・ω・) | Read one lyric line out loud at speaking pace, then see which words came through and which ones to practise. Separate from singing; it never touches your score. |

It runs in the browser or as a desktop app (Electron), both talking to the same server.

---

## ✦ How it works (the short version)

```
 ONCE PER SONG, OFFLINE                         EVERY TIME YOU SING
 ──────────────────────                         ───────────────────
 song clip                                      instrumental plays on the Web Audio clock
   │ Demucs: split vocals from the music          │
   ▼                                              ▼
 vocal stem ──► CREPE: reference melody (Hz)   your mic ──► Pitchy: your pitch, every 20 ms
   │            + lyric & phrase timing            │
   │                                               ▼
   └──► wav2vec2: "fingerprints"               scoring engine rates each phrase on the spot
        (how the original singer sounds)           │   (pitch in cents + note-start timing)
                                                   ▼
                                               results: score · phrase ratings · pronunciation report
                                                       · Gemini coaching blurb (words only)
```

The heavy models run **once per song, offline**. While you sing, the browser runs a light
pitch tracker and plain arithmetic. That keeps the game responsive and lets the score be
explained phrase by phrase.

---

## ✦ Where the AI is (and where it deliberately isn't)

We use **pretrained models only**. We had no labelled singing data and no fluent Korean
reviewer, so training or fine-tuning would have produced numbers nobody could check. The
"custom model" work is the engineering around those models, plus measuring whether it works:

- **Scoring engine** (`ml/scoring/`): pitch is compared in cents against a reviewed reference
  melody, with soft credit near the note. Timing comes from stable note starts after one fixed
  latency correction. Rests, backing-vocal regions and mic noise earn nothing. The engine is
  written twice, once in Python (the reference the evals test) and once in TypeScript (what the
  game runs live). Both pass the same shared test cases in `contracts/fixtures/`.
- **Pronunciation report after you sing** (`ml/pronunciation/lyric_match.py`): speech recognisers
  fail on singing (we measured it), so we don't transcribe. Instead your take is compared with
  *the original singer's recording of the same song*, using speech-model features (wav2vec2)
  aligned by DTW. It also has to sound clearly more like the original than a wordless hum of your
  own melody does, so getting the tune right is not enough to pass. The result is one overall
  **pronunciation score (0–100)**, the share of the song whose words matched the original, plus a
  plain verdict: **CLEAR / MIXED / UNCLEAR**. It's built during and right after the song: a couple
  of seconds on a fast machine, noticeably longer on our small CPU-only server.
- **Your score vs your pronunciation:** the total is **pitch and timing only**. The pronunciation
  report sits right next to it on the results screen as its own bar, so you can see both at a glance.
- **Spoken pronunciation** (`ml/pronunciation/`): the expected Korean text is force-aligned to
  your speech with a Korean wav2vec2 CTC model, and the weakest words in the phrase are
  highlighted.
- **Calibration** (`ml/evals/`): rating cutoffs, tolerances and the pronunciation-check margin were set
  from real takes and controlled damage, and the numbers are below.
- **Gemini** writes translations and the coaching blurb from the measured numbers. **No language
  model ever decides a score or a winner.**

---

## ✦ Does it actually work? (evaluation)

Unit tests passing doesn't mean the scoring is right, so we measured it. Everything below can be
rerun from `ml/evals/`. The real takes are teammates singing (few takes, one or two singers), so
read them as first evidence, not validation.

### Singing score under controlled damage (synthetic voice)

A voice-like melody is damaged on purpose at increasing severity. The score should fall
steadily; Spearman ρ near −1 means it does.

| Damage | Score trend | ρ |
|---|---|---|
| Every note detuned ±N cents | 99.7 → 71 at 100 cents → 22 at 200 | −0.95 |
| Notes skipped | steady fall to 0 | −0.99 |
| Late entrance | ~99 → 86 at 0.2 s → 48 at 0.4 s | −0.98 |
| White noise | ~97 down to 5 dB SNR, then collapses | −0.92 |

Sanity checks: silence scores 0 and noise alone 3.5. An octave up scores 97 with the right
register selected and 20 without it. The same input always gives the same score.

### Real takes, and where the rating cutoffs come from

Teammates singing along to real songs, scored through the **live path** (the browser's pitch
tracker, Pitchy). We also scored the song's own **original vocal**, which shows the realistic
ceiling. Typical phrase score:

| Who / what | Love Scenario | Last Christmas |
|---|---|---|
| Original singer (isolated vocal) | 78 | 80 |
| Teammate, real take | 64 | 59 |
| That take pushed a semitone off-key | 50 | 43 |
| That take pushed two semitones off | 25 | 18 |
| That take 0.4 s late | 35 | 37 |
| Silence / noise | Miss | Miss |

Even the original artist only reaches ~78 through a browser pitch tracker, so our first cutoffs
(Perfect ≥ 90) were unreachable. **Scoring 0.3.0 sets Perfect 80 / Great 65 / Okay 40.** With
those, the original singer gets mostly Perfect and Great, a decent amateur mostly Great and Okay,
and two semitones off is all Bad. The same take read 7 s off its correct timing drops from ~60
to 15–22.

### Pronunciation report after singing

Each number is the share of the song's lyric lines whose words matched the original singer, which
is what the overall pronunciation score is built from.

| | Love Scenario (54 lines) | Last Christmas (9 lines) |
|---|---|---|
| Real take, sung with the words | **89%** | **89%** |
| A teammate **humming** the song along with the music, no words | **0%** (6 lines) | – |
| Same take, words replaced by a synthetic "aah" on the same melody | 0% | 0% |
| Real take compared against the wrong part of the song | 4% | 0% |
| Quiet | 0% (nothing sung) | 0% |

Draft lyric timings off by up to 1 s barely matter (96% → 93–96%). The report is computed on the
server and takes a while: about a minute for a full song on a laptop CPU, and longer on our small
server (we haven't timed a full song there).

**How we got there (honestly):** our synthetic "aah" made the check look perfect, but a *real*
hum is harder to reject. Hummed along with the music, it still passed 3 of 6 lines at our first
margin, with gains of +0.04 to +0.09 against +0.19 to +0.36 for the same lines sung with words.
Raising the margin to 0.10 rejects the hum on every line and keeps 89% of the real take. We picked
that margin on these same few recordings, so more singers (and more hums) are the next test.

### Spoken pronunciation (SAY IT RIGHT)

Test speech was generated with a Korean text-to-speech voice.

| | Whisper + spelling comparison | wav2vec2 forced alignment (shipped) |
|---|---|---|
| Right sentence vs a different one (AUC) | 1.000 | 0.998 |
| Same, in heavy noise (0 dB) | 1.000 | 0.793 |
| One sound changed: finds the right word (chance 0.31) | 0.33 | **0.54** |

Whisper "autocorrects": on 25 of 39 clips where we changed one sound, its transcript contained
the *correct* word anyway. That's why we ship forced alignment, which scores the expected text
against your audio and can't autocorrect. Raw word scores aren't grades (correct speech has a
median score of ~48), so the screen highlights your *weakest* words instead of passing or failing
each one.

**On a real voice** (a teammate reading the Love Scenario chorus aloud, 16 words):

| Reading | Overall score |
|---|---|
| Medium-bad pronunciation | **78** |
| Deliberately mangled pronunciation | **14** |
| Scored against completely different lyrics | 5–6 |

With one word swapped in the expected text (as if the speaker had said a different word), the
swapped word came out as the lowest-scoring word in **14 of 16** cases (guessing: 1 in 16). We
don't have a genuinely *good* reading yet, so we can't say what "correct" scores. One speaker.

### Browser tracker vs reference tracker

The reference melody is extracted with CREPE, and the browser listens with Pitchy. We ran the
real Pitchy library on the same audio to measure the gap. At the default clarity setting (0.85)
a real take loses ~7 points. At our recommended setting (clarity 0.65, RMS gate 0.005, 48 kHz,
2048-sample window) a real take lands within ~2–4 points of CREPE (59.8 vs 61.6).

---

## ✦ Design decisions and tradeoffs

- **Pitch contours, not learned embeddings, for the score.** A contour compared in cents can be
  explained ("you were 80 cents flat here"), needs no training data, and runs in the browser.
  A learned similarity would need labelled performances we don't have.
- **A fixed register, not octave folding or key-shift forgiveness.** You choose original, an
  octave down or an octave up once per turn. Folding every frame to the nearest octave, or
  subtracting your average key offset, would reward a melody that jumps around or is sung in the
  wrong key against a fixed-key backing track.
- **No unrestricted time-warping (DTW) in the score.** Warping would align away exactly the rhythm
  mistakes the game should catch. Timing is measured against note starts after **one** device
  latency correction. We allow one small shift of up to 0.1 s per phrase. A per-frame
  "best match nearby" rule let random pitches score 42, so we dropped it. The pronunciation report *does*
  use DTW, because there it only removes tempo so the words can be compared. It never touches
  the score.
- **Scoring in the browser, with a Python reference and shared test cases.** Ratings have to pop
  up instantly, so the browser scores live. The Python engine is what the evals test, and the
  shared test cases keep the two in step. They caught real bugs: latency not applied to pitch,
  and excluded regions still costing timing points.
- **Heavy work offline.** Vocal separation, CREPE and the per-song fingerprints run once per song.
  The live path is a light tracker plus arithmetic.
- **Free, local, pretrained speech models instead of a paid API.** They cost nothing, work
  offline, and we can evaluate them ourselves. We chose forced alignment over transcription
  after measuring Whisper's autocorrection.
- **Spoken practice is separate from singing, and the pronunciation report compares sound with sound.**
  Recognisers can't read sung Korean (they told right from wrong lyrics at AUC 0.62–0.65, barely
  above chance), so we stopped asking them to.
- **Pronunciation is reported next to the score, not inside it.** We built and tested a rule that
  folds the pronunciation score into the total as a "humming guard" (it's in both scoring engines,
  with shared test cases), but we left it switched off. It rests on one or two singers, and an
  honest take that the check is unsure about could lose a big chunk of its total.

## ✦ What failed or surprised us (；へ；)

- Our first rating cutoffs came from synthetic voices and were impossible for real ones, even
  for the original artist.
- Our first pronunciation check passed a wordless "aah" on 76% of the song: the tune was doing all
  the work. The hum control fixed that. Then a real human hum still passed about half, so we
  raised the margin until it failed every time.
- Whisper's transcripts looked perfect while silently hiding the mistakes we wanted to find.
- Tempo drift is punished hard (5% slower costs ~30 points). That's the price of not warping
  time.
- We once quoted a ceiling of "74–81" for a perfect take. It came from the rejected per-frame
  rule; the real number was ~63 at the time.

## ✦ Limitations (please read!)

- **Few real singers.** The real-take numbers come from one or two teammates and two songs.
  The thresholds are a starting point.
- **No fluent Korean reviewer.** All pronunciation feedback is automated: one overall score for
  singing, word by word for spoken practice. It doesn't judge accent or individual sounds. The Hangul lyrics come from **TODO: source**,
  not from our own transcription.
- **Song timings are drafts** until someone has checked them by ear (`song.review.json` marks
  the reviewed ones).
- The text-to-speech voice used for test speech (Meta MMS-TTS) is CC-BY-NC. We use it only to
  generate evaluation audio; it isn't part of the app.
- One register per turn can't follow a group song whose lead jumps between very low and very
  high parts.

## ✦ Next

1. More singers and more hums, to recalibrate the cutoffs and the pronunciation-check margin on people
   other than us. Then decide whether the humming guard should count toward the total.
2. A good spoken reading (and more speakers) for SAY IT RIGHT, to learn what "correct" scores.
3. Per-word feedback while singing: today the singing report is one overall score, because
   per-word evidence on singing isn't reliable yet.
4. Extract the reference melody with the browser's own tracker, to close the remaining tracker
   gap.

---

## ✦ Run it yourself

You need Python 3.11, Node (we use v24), FFmpeg and a Postgres database (we use Tiger Data). Secrets go in
`.env`, never in git; copy `.env.example` to start.

```bash
# API (from the repo root)
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt
cp .env.example .env                        # fill in DATABASE_URL etc.
alembic -c api/alembic.ini upgrade head
python -m api.seed
uvicorn api.main:app --reload

# web app (second terminal)
cd web && npm install && npm run dev

# desktop app (optional; loads the server's URL)
cd desktop && npm install && npm start
# or download an installer from the GitHub Releases tab (see desktop/README.md)
```

Spoken practice and the pronunciation report need the speech environment
(`pip install -r ml/pronunciation/requirements.txt`) and `PRONUNCIATION_SCORER=1`. Without them
both features show as "offline", and the singing game still works. Setting up songs is covered in
[`ml/pipeline/README.md`](ml/pipeline/README.md), and the evals in [`ml/README.md`](ml/README.md).

**Songs and copyright:** this repo contains no copyrighted audio, lyrics or model weights. Song
preparations stay on our own machines (`ml/data/` is gitignored), and the public build ships
only royalty-free test audio.

## ✦ Server update

Server `app@just-sing.ink`, checkout `/home/app/just-sing`, systemd service `just-sing`. Production uses `.venv-new` and a single Uvicorn worker; restarting disconnects active games.

```bash
cd /home/app/just-sing
(
  set -e
  git pull --ff-only origin main
  .venv-new/bin/python -m pip install -r api/requirements.txt
  (cd web && npm ci && npm run build)
  .venv-new/bin/alembic -c api/alembic.ini upgrade head
  .venv-new/bin/python -m api.seed
  sudo systemctl restart just-sing
)
```

## ✦ Repo map

```
web/               the game: React + TypeScript + Vite, Canvas pitch lane, live scoring
desktop/           Electron shell that opens the server's URL
api/               FastAPI: songs, sessions (Auth0 / guest), matches, practice, pronunciation report
ml/scoring/        Python reference scoring engine + spec
ml/pronunciation/  spoken-practice scorer and pronunciation report (local pretrained models)
ml/pipeline/       offline song preparation: Demucs, CREPE, lyric timing, Gemini translations
ml/evals/          every number in this README, and the scripts that produce it
contracts/         shared data shapes and test cases (Python and TypeScript both pass them)
```

## ✦ The team ★(＾▽＾)★

| | |
|---|---|
| **Frontend** | Daniel (superepic): the game UI, pitch lane, live scoring port, Electron |
| **Backend / infra** | Donald (waychlate): FastAPI, Tiger Data, Auth0, deploy |
| **ML A, song pipeline** | APR (DrewV2): separation, reference melody, lyric timing |
| **ML B, scoring + pronunciation + evals** | Corina (ufungii): scoring engine, speech models, evaluation |
| **Claude is not part of the team** |

Built with: React, Vite, Pitchy, FastAPI, Tiger Data (Postgres), Auth0, Gemini, Electron,
Demucs, torchcrepe, wav2vec2 (`kresnik/wav2vec2-large-xlsr-korean`, Apache-2.0), faster-whisper.
