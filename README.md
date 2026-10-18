# ♪ Just Sing! ♪

**A K-pop karaoke game that actually listens to you.** (ﾉ≧▽≦)ﾉ

Pick a song, sing along with the instrumental, and watch your voice draw a live line over the
melody while the lyrics scroll by in Hangul, romanization and English. Every phrase gets a
rating the moment you finish it (**PERFECT! / GREAT / OKAY / BAD / MISS**). At the end you get
a pitch and timing score, a check of whether you sang the right words, and a little pep talk
from Mic-chan.

Built in 36 hours at **SwampHacks XII** by a team of four, none of us fluent in Korean (yet!).

> **TODO before submitting:** Devpost link · demo video · a screenshot or GIF of the singing screen

---

## ✦ What you can do

| Mode | What happens |
|---|---|
| **SOLO SING** ♪(^▽^)♪ | Pick a clip and a register (original, an octave down, or an octave up), then sing. Your pitch traces over the target notes, and each phrase is rated live, in the browser, with no waiting on a server. Afterwards each lyric line is marked by whether it sounded like the right words. |
| **SAY IT RIGHT** (・ω・) | Read one lyric line out loud at speaking pace, then see which words came through and which ones to practise. Separate from singing; it never touches your score. |
| **1P VS 2P / DUET** (｀∀´)ﾉ☆ヽ(＾▽＾) | Two singers, one clip, the same scoring rules. *(Stretch goal: built in the backend, but solo and practice come first.)* |

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
   └──► wav2vec2: "lyric fingerprints"         scoring engine rates each phrase on the spot
        (how each original line sounds)            │   (pitch in cents + note-start timing)
                                                   ▼
                                               results: score · phrase ratings · lyric check
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
- **Lyric check while singing** (`ml/pronunciation/lyric_match.py`): speech recognisers fail on
  singing (we measured it), so we don't transcribe. Each sung line is compared with *the original
  singer's recording of the same line*, using speech-model features (wav2vec2) aligned by DTW.
  It also has to sound clearly more like the original than a wordless hum of the player's own
  melody does, so getting the tune right is not enough to pass.
- **Spoken pronunciation** (`ml/pronunciation/`): the expected Korean text is force-aligned to
  your speech with a Korean wav2vec2 CTC model, and the weakest words in the phrase are
  highlighted.
- **Calibration** (`ml/evals/`): rating cutoffs, tolerances and the lyric-check margin were set
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

### Lyric check while singing

| | Love Scenario (54 lines) | Last Christmas (9 lines) |
|---|---|---|
| Real take: lines marked "match" | **89%** | **89%** |
| A teammate **humming** the song along with the music, no words | **0%** (6 lines) | – |
| Same take, words replaced by a synthetic "aah" on the same melody | 0% | 0% |
| Real take compared against the wrong part of the song | 4% | 0% |
| Quiet | 0% (all "not sung") | 0% |

Draft lyric timings off by up to 1 s barely matter (96% → 93–96%).

**How we got there (honestly):** our synthetic "aah" made the check look perfect, but a *real*
hum is harder to reject. Hummed along with the music, it still passed 3 of 6 lines at our first
margin, with gains of +0.04 to +0.09 against +0.19 to +0.36 for the same lines sung with words.
Raising the margin to 0.10 rejects the hum on every line and keeps 89% of real lines. We picked
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
each one. **TODO: real-voice results.**

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
  "best match nearby" rule let random pitches score 42, so we dropped it. The lyric check *does*
  use DTW, because there it only removes tempo so the words can be compared. It never touches
  the score.
- **Scoring in the browser, with a Python reference and shared test cases.** Ratings have to pop
  up instantly, so the browser scores live. The Python engine is what the evals test, and the
  shared test cases keep the two in step. They caught real bugs: latency not applied to pitch,
  and excluded regions still costing timing points.
- **Heavy work offline.** Vocal separation, CREPE and the lyric fingerprints run once per song.
  The live path is a light tracker plus arithmetic.
- **Free, local, pretrained speech models instead of a paid API.** They cost nothing, work
  offline, and we can evaluate them ourselves. We chose forced alignment over transcription
  after measuring Whisper's autocorrection.
- **Spoken practice is separate from singing, and the lyric check compares sound with sound.**
  Recognisers can't read sung Korean (they told right from wrong lyrics at AUC 0.62–0.65, barely
  above chance), so we stopped asking them to.

## ✦ What failed or surprised us (；へ；)

- Our first rating cutoffs came from synthetic voices and were impossible for real ones, even
  for the original artist.
- Our first lyric-check rule passed a wordless "aah" on 76% of lines: the tune was doing all the
  work. The hum control fixed that. Then a real human hum still passed half its lines, so we
  raised the margin until it failed every line.
- Whisper's transcripts looked perfect while silently hiding the mistakes we wanted to find.
- Tempo drift is punished hard (5% slower costs ~30 points). That's the price of not warping
  time.
- We once quoted a ceiling of "74–81" for a perfect take. It came from the rejected per-frame
  rule; the real number was ~63 at the time.

## ✦ Limitations (please read!)

- **Few real singers.** The real-take numbers come from one or two teammates and two songs.
  The thresholds are a starting point.
- **No fluent Korean reviewer.** All pronunciation feedback is automated and word or line level.
  It doesn't judge accent or individual sounds. The Hangul lyrics come from **TODO: source**,
  not from our own transcription.
- **Song timings are drafts** until someone has checked them by ear (`song.review.json` marks
  the reviewed ones).
- The text-to-speech voice used for test speech (Meta MMS-TTS) is CC-BY-NC. We use it only to
  generate evaluation audio; it isn't part of the app.
- One register per turn can't follow a group song whose lead jumps between very low and very
  high parts.

## ✦ Next

1. Finish the humming-with-music test and the real-voice pronunciation clips.
2. More singers, to recalibrate the cutoffs and the lyric-check margin on people other than us.
3. Extract the reference melody with the browser's own tracker, to close the remaining tracker
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
```

Spoken practice and the lyric check need the speech environment
(`pip install -r ml/pronunciation/requirements.txt`) and `PRONUNCIATION_SCORER=1`. Without them
both features show as "offline", and the singing game still works. Setting up songs is covered in
[`ml/pipeline/README.md`](ml/pipeline/README.md), and the evals in [`ml/README.md`](ml/README.md).

**Songs and copyright:** this repo contains no copyrighted audio, lyrics or model weights. Song
preparations stay on our own machines (`ml/data/` is gitignored), and the public build ships
only royalty-free test audio.

## ✦ Ubuntu / Vultr server operations

These commands target the existing server: `app@just-sing.ink`, checkout
`/home/app/just-sing`, systemd service `just-sing`, and frontend `web/dist`.
**Production uses `.venv-new` (Python 3.11.17), not the old `.venv`.** Keep one
Uvicorn worker: online-room presence and WebSocket connections live in that process.
Restarting disconnects active games, so deploy between sessions.

Jump to [updates](#update-the-application), [songs and images](#upload-songs-covers-and-menu-audio),
[configuration](#change-server-configuration), [diagnostics](#service-health-and-logs),
[backups](#back-up-before-a-deploy), [rollback](#roll-back-code), or
[Ubuntu maintenance](#maintain-ubuntu).

### Connect and inspect

Run SSH from your computer; the remaining commands run on the server unless marked otherwise.

```bash
ssh app@just-sing.ink
cd /home/app/just-sing
git status --short --branch
git log -5 --oneline
.venv-new/bin/python --version
node --version
npm --version
ffmpeg -version
sudo systemctl show just-sing -p User -p WorkingDirectory -p ExecStart -p EnvironmentFiles
```

### Back up before a deploy

Keep a provider database backup/snapshot before schema changes. The following makes a
restricted local copy of configuration and installed song assets. Copy backups off the VM
too; a backup on the same disk does not survive losing that disk. Audio backups can be large.

```bash
cd /home/app/just-sing
(
  set -e
  umask 077
  BACKUP_DIR="$HOME/just-sing-backups/$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$BACKUP_DIR"
  git rev-parse HEAD > "$BACKUP_DIR/commit.txt"
  cp .env "$BACKUP_DIR/server.env"
  # Include each existing asset directory, without failing on an optional missing one.
  for ASSET_DIR in ml/data web/public/covers web/public/audio; do
    if [ -d "$ASSET_DIR" ]; then
      tar -czf "$BACKUP_DIR/$(echo "$ASSET_DIR" | tr / -).tar.gz" "$ASSET_DIR"
    fi
  done
  echo "Backup saved to $BACKUP_DIR"
)
```

For a logical Postgres backup, install `postgresql-client` (see Ubuntu maintenance) and
use `pg_dump` of the same major version as the hosted database, or newer. This helper reads
`.env`, converts the SQLAlchemy URL to a libpq URL, and passes credentials through the child
process environment rather than command arguments. Existing exported `DATABASE_URL` values
override `.env`, just as they do for API commands; use a fresh SSH session if unsure.

```bash
cd /home/app/just-sing
.venv-new/bin/python - <<'PYBACKUP'
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv('.env')
os.umask(0o077)
backup_dir = Path.home() / 'just-sing-backups'
backup_dir.mkdir(exist_ok=True)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
target = backup_dir / f'database-{stamp}.dump'
url = make_url(os.environ['DATABASE_URL']).set(drivername='postgresql')
env = dict(os.environ, PGDATABASE=url.render_as_string(hide_password=False))
subprocess.run(['pg_dump', '--format=custom', '--file', str(target)], env=env, check=True)
print(f'Database backup saved to {target}')
PYBACKUP
# Inspect an archive (replace the example path); verify restoration into a separate DB.
pg_restore --list "$HOME/just-sing-backups/database-YYYYMMDDTHHMMSSZ.dump"
```

Backups contain secrets and private data; keep them outside the public repo. Restore a
provider snapshot or a verified dump only as a planned database recovery, with the matching
code and schema version. A code rollback alone does not restore the database.

### Update the application

Merge the intended PRs into `main` first, take a backup above, and check `git status` for
server edits before pulling. Resolve local edits deliberately; do not discard them with a
hard reset. The subshell stops on the first failure, leaving the current service running
unless the restart has been reached. A migration can still affect the running old code;
schedule downtime for incompatible schema changes.

```bash
cd /home/app/just-sing
(
  set -e
  git switch main
  git pull --ff-only origin main
  uv pip install --python .venv-new/bin/python -r api/requirements.txt
  (cd web && npm ci && npm run build)
  .venv-new/bin/alembic -c api/alembic.ini current
  .venv-new/bin/alembic -c api/alembic.ini upgrade head
  .venv-new/bin/python -m api.seed
  sudo systemctl restart just-sing
)
sudo systemctl status just-sing --no-pager -l
curl -fsS http://127.0.0.1:8000/api/ready
curl -fsS https://just-sing.ink/api/ready
```

Run all Python/Alembic commands from the repo root; they load `.env` automatically.
`DATABASE_URL` must use `postgresql+psycopg://` for the API. Do not copy `.env.example`
over an existing production `.env`. The build copies `web/public/` assets into `web/dist/`;
keep those source assets installed before rebuilding.

`/api/ready` should report `"database":"ok"` and `"catalog":true`. It returns HTTP 200
even when a dependency is unavailable, so inspect the JSON. Speech features may report
`unavailable` when intentionally disabled. With speech enabled, allow time for model startup
(the current machine has taken about 31 seconds), and watch the logs before retrying.

To run **just the seed**, without activating a virtual environment:

```bash
cd /home/app/just-sing
.venv-new/bin/python -m api.seed
sudo systemctl restart just-sing
```

Seeding inserts or updates catalog metadata from installed `ml/data/*/song.json`; it does
not download songs, prepare audio, or migrate tables. Restart after changing manifests
because the API loads the catalog at startup. Run migrations before seeding a new database.

### Upload songs, covers, and menu audio

These files are gitignored and do not arrive with `git pull`. Prepare and review songs on
your own machine using [the pipeline guide](ml/pipeline/README.md), then upload the prepared
folder, including `song.json`, review metadata, referenced audio, and any lyric fingerprints.
The folder ID should match `id` in its manifest. Bump the manifest version when changing a
released scoring reference so existing results retain their meaning.

Run these commands **on your computer**, replacing the example ID and local paths:

```bash
SONG_ID='your-song-id'
ssh app@just-sing.ink "mkdir -p /home/app/just-sing/ml/data/$SONG_ID /home/app/just-sing/web/public/covers /home/app/just-sing/web/public/audio"
rsync -av --progress /path/to/prepared-song/ "app@just-sing.ink:/home/app/just-sing/ml/data/$SONG_ID/"
rsync -av --progress /path/to/covers/ app@just-sing.ink:/home/app/just-sing/web/public/covers/
rsync -av --progress /path/to/menu-bgm.mp3 app@just-sing.ink:/home/app/just-sing/web/public/audio/
```

Use the cover filenames referenced by the frontend. Upload complete song folders between
sessions; these commands overwrite matching files but do not delete other server assets.
Then **on the server**:

```bash
cd /home/app/just-sing
.venv-new/bin/python -m api.seed
(cd web && npm ci && npm run build)
sudo systemctl restart just-sing
curl -fsS http://127.0.0.1:8000/api/clips | .venv-new/bin/python -m json.tool
```

### Change server configuration

```bash
cd /home/app/just-sing
nano .env
chmod 600 .env
sudo systemctl restart just-sing
sudo journalctl -u just-sing -n 100 --no-pager
```

Set `PRONUNCIATION_SCORER=0` to disable both spoken practice and sung lyric checking;
set it to `1` to enable them using the speech dependencies/models already installed in
`.venv-new`. The singing game works with them disabled. Enabled speech has used about
1.2 GB peak RAM on this 4 GB server. Keep heavy song preparation off production; do not
replace the working environment with the pipeline's Demucs dependencies.

If changing the **systemd unit**, inspect its current command first and preserve the
`.venv-new/bin/uvicorn` path and single worker. Unit edits need `daemon-reload`; ordinary
code or `.env` edits only need a restart.

```bash
sudo systemctl edit just-sing
sudo systemctl daemon-reload
sudo systemctl restart just-sing
```

### Service health and logs

```bash
sudo systemctl status just-sing --no-pager -l
sudo systemctl is-enabled just-sing
sudo journalctl -u just-sing -n 100 --no-pager
sudo journalctl -u just-sing --since "30 minutes ago" --no-pager
sudo journalctl -u just-sing -f                 # Ctrl-C stops following logs
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/ready
curl -fsS https://just-sing.ink/api/ready
sudo ss -ltnp
free -h
df -h
du -sh ml/data web/dist .venv-new
```

Liveness (`/api/health`) only proves the API responds. If local readiness works but the
public URL fails, inspect the installed reverse proxy, its logs, DNS, and TLS. The proxy
must forward WebSocket upgrades for online rooms. Browser microphones require HTTPS.
Voice media uses peer-to-peer WebRTC; a healthy API does not prove two peers can connect
through every NAT/firewall, and the current STUN setup has no TURN fallback.

Service controls, when needed:

```bash
sudo systemctl stop just-sing                  # planned downtime
sudo systemctl start just-sing
sudo systemctl restart just-sing
sudo systemctl enable just-sing                # start automatically after reboot
```

Do not use the API test suite as a production health check. Database tests belong in a
separate test database on a development machine or CI.

### Roll back code

Find the previous SHA in your backup's `commit.txt` or `git log`. Check migration
compatibility first: the commands below leave the database schema and installed assets
unchanged. Do not blindly run `alembic downgrade -1`; review that migration's data loss and
compatibility implications before a database rollback.

```bash
cd /home/app/just-sing
git log -10 --oneline
# Replace this example with the known-good SHA recorded before deployment.
KNOWN_GOOD_COMMIT='replace-with-commit-sha'
(
  set -e
  git switch --detach "$KNOWN_GOOD_COMMIT"
  uv pip install --python .venv-new/bin/python -r api/requirements.txt
  (cd web && npm ci && npm run build)
  sudo systemctl restart just-sing
)
curl -fsS http://127.0.0.1:8000/api/ready
```

Reinstalling requirements does not reproduce an older Python environment exactly because
the API requirements are not locked. Keep a VM snapshot for recovery involving dependency
changes. Return to `git switch main` when ready for the next normal deployment.

### Maintain Ubuntu

Review available updates, then apply them during a maintenance window. The optional package
install provides FFmpeg, rsync, and Postgres backup tools; the API database itself is hosted
on Tiger Data, so there is no local Postgres service to restart.

```bash
sudo apt update
apt list --upgradable
sudo apt upgrade
sudo apt install ffmpeg rsync postgresql-client
sudo journalctl --disk-usage
# Optional: delete journal entries older than 14 days to reclaim space.
sudo journalctl --vacuum-time=14d
if [ -f /var/run/reboot-required ]; then cat /var/run/reboot-required; fi
```

If a reboot is required, finish backups and schedule the interruption, then:

```bash
sudo reboot
# Back on your computer, reconnect once the VM is available:
ssh app@just-sing.ink
sudo systemctl status just-sing --no-pager -l
curl -fsS https://just-sing.ink/api/ready
```

## ✦ Repo map

```
web/               the game: React + TypeScript + Vite, Canvas pitch lane, live scoring
desktop/           Electron shell that opens the server's URL
api/               FastAPI: songs, sessions (Auth0 / guest), matches, practice, lyric check
ml/scoring/        Python reference scoring engine + spec
ml/pronunciation/  spoken-practice scorer and lyric check (local pretrained models)
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

*Made with ♡ and a lot of off-key singing.* ♪
