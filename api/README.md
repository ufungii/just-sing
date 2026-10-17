# API

FastAPI backend for the karaoke app: song catalog, guest and Auth0 sessions, solo / local / online matches,
spoken-practice uploads, and online rooms. The server schedules continuous multiplayer starts; each browser
uses its WebAudio clock for playback, pitch tracking and phrase ratings, then submits only its assigned phrases.

Data shapes (song manifest, score, practice result, error) are defined in [`../contracts/`](../contracts/).
The Pydantic models in `models.py` mirror them, and `tests/test_contracts.py` fails if they drift.
Change a contract in its own small PR and tell the team.

## Run it

Python 3.11 per CLAUDE.md (tested on 3.12). FFmpeg and `ffprobe` must be installed for practice uploads.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt
cp .env.example .env          # then fill in real values; .env is gitignored

alembic -c api/alembic.ini upgrade head   # create/upgrade tables
python -m api.seed                        # insert clip metadata (safe to repeat)
uvicorn api.main:app --reload             # run from the repo root
pytest api                                # tests; the DB tests need DATABASE_URL
```

Interactive docs: `http://localhost:8000/docs`. Without `DATABASE_URL`, the catalog endpoints still work and
the database tests are skipped. Without Auth0 values, guests still work and bearer tokens get `auth_unavailable`.
Without a pronunciation scorer (the default), `/api/practice` and `/api/lyric-check` answer `status: "unavailable"`.

## Environment

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...` (SQLAlchemy needs that scheme, not `postgres://`). Server-side only. |
| `PRONUNCIATION_SCORER` | `1` loads `ml.pronunciation.api_scorer.PronunciationScorer` at startup and warms it (about 30 s, needs the speech environment). Anything else: practice is `unavailable`. If loading fails, the error is logged and practice stays `unavailable`. The same flag starts the lyric check (same model, loaded once); it also needs `ml/data/<clip>/lyric_fingerprints.npz` for each clip, made by ML A's pipeline step, and answers `unavailable` for clips without one. |
| `AUTH0_DOMAIN` | Tenant domain, no `https://`. |
| `AUTH0_AUDIENCE` | The Auth0 API identifier. Login requests must pass the same `audience`, or Auth0 issues an opaque token we cannot verify. |
| `COOKIE_SECURE` | `1` on public HTTPS so the guest cookie is Secure. Leave `0` on `http://localhost`. |
| `GUEST_TTL_DAYS` | Guest session lifetime, default 7. Expired guests and their data are deleted hourly. |
| `ALLOWED_ORIGINS` | Extra browser origins allowed to open WebSockets. The server's own host is always allowed. |
| `SONG_DIRS` | Folders to load songs from (`:`-separated on Linux/macOS), each containing `<id>/song.json`. Default: `api/catalog` and `ml/data`. |
| `GEMINI_API_KEY` | Server-side only. Enables coaching blurbs; without it they answer `unavailable`. |
| `GEMINI_MODEL` | Model for blurbs, default `gemini-3.5-flash-lite`. Google retires older models for new accounts, so if blurbs go `unavailable`, check this first. |
| `WEB_DIST` | Folder with the built frontend. Default `web/dist`. |
| `RECONNECT_GRACE_SECONDS` | Extra time after a clip ends before a started turn is treated as lost, default 60. |

## Frontend: one origin

The server also serves the built frontend, so the browser (and Electron, which loads the server's URL) talks to one
origin: the guest cookie works and no CORS setup is needed.

```bash
cd web && npm run build        # produces web/dist
uvicorn api.main:app           # now http://localhost:8000/ is the app, /api and /ws are the backend
```

Rules: a real file in `web/dist` is served as is; any other non-API path returns `index.html` so client-side routes
survive a reload; unknown `/api/...` paths return the normal JSON error. If `web/dist` does not exist, `/` answers
`frontend_not_built`.

For hot-reload development, run `npm run dev` and proxy the backend so the page is still same-origin (otherwise the
cookie will not be sent). In `web/vite.config.ts`:

```ts
server: { proxy: { "/api": "http://localhost:8000", "/ws": { target: "ws://localhost:8000", ws: true } } }
```

## Public demo through a Cloudflare tunnel

Microphones need HTTPS, and remote players need a public URL. A Quick Tunnel gives both from a laptop, no account needed.

```bash
sudo pacman -S cloudflared                                   # Arch; other OS: developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads
COOKIE_SECURE=1 .venv/bin/uvicorn api.main:app --port 8000   # terminal 1: Secure cookie, because the public URL is HTTPS
cloudflared tunnel --protocol http2 --url http://localhost:8000   # terminal 2: prints https://<random>.trycloudflare.com
python -m api.scripts.smoke_public https://<random>.trycloudflare.com   # terminal 3: end-to-end check
```

`--protocol http2` matters on campus or corporate Wi-Fi, which often blocks the UDP that `cloudflared` tries first (the log shows `Failed to dial a quic connection` and the public URL answers error 1033). Look for `Registered tunnel connection` in its output.

The smoke script plays a full two-player room over the public URL and checks the cookie flags, WebSockets, the
origin check, live progress, turns and the winner. The URL changes every time the tunnel restarts, and it is
public: do not put it in the README or Devpost. Real copyrighted clips are served from this laptop only.
The script leaves `smoke-*` guests in the database; they expire with the 7-day cleanup.

## Conventions

- **Times** are seconds from clip start. **Scores** are 0-100, rounded to 2 decimals. **Pitch** is Hz in manifests.
- **Ratings** are lowercase slugs: `perfect`, `great`, `okay`, `bad`, `miss`. The UI maps them to labels.
- **Register** is `-12`, `0` or `12` semitones, chosen before the turn.
- **Identity:** either the `guest_token` cookie (set by `POST /api/guests`) or `Authorization: Bearer <Auth0 access token>`.
  A bearer token wins if both are sent.
- **Errors** always use one envelope; show `message`, branch on `code`, retry only when `retryable` is true:

```json
{"error": {"code": "room_full", "message": "That room is full.", "retryable": false, "request_id": "..."}}
```

| Status | Codes |
|---|---|
| 401 | `not_authenticated`, `invalid_token` |
| 403 | `host_only`, `not_your_seat` |
| 404 | `clip_not_found`, `phrase_not_found`, `match_not_found`, `attempt_not_found`, `room_not_found`, `audio_missing` |
| 409 | `not_your_turn`, `attempt_not_started`, `attempt_closed`, `attempt_invalidated`, `already_submitted`, `cannot_retry`, `use_room_rematch`, `room_full`, `room_started`, `not_ready`, `not_finished`, `use_duet_ready`, `duet_closed`, `missed_start`, `restart_duet`, `duet_not_started` |
| 410 | `room_expired` |
| 411 | `length_required` (practice uploads must send a `Content-Length`; browsers do this for `FormData`) |
| 413 / 422 | `audio_too_large`, `audio_too_long`, `unsupported_audio`, `phrase_mismatch`, `practice_unavailable`, `invalid_result`, `invalid_register`, `invalid_request`, `invalid_duet`, `invalid_duet_range` |
| 429 | `pronunciation_busy` (retryable), `too_many_joins` (retryable) |
| 503 | `catalog_not_seeded`, `auth_unavailable`, `room_code_unavailable` |

## Endpoints

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health`, `/api/ready` | Liveness; readiness (`catalog`, `database`, `pronunciation`) |
| GET | `/api/clips`, `/api/clips/{id}/manifest` | Prepared catalog (each clip has `synthetic` and `reviewed` flags); full manifest |
| GET | `/api/clips/{id}/audio` | Instrumental only, supports `Range` |
| POST | `/api/guests` | Create guest `{display_name}`; sets the cookie |
| POST | `/api/auth/claim` | After login, send bearer token + guest cookie to move guest history to the account |
| POST | `/api/matches` | `{clip_id}` for solo; add `players: ["A","B"], duet: true` for continuous local multiplayer |
| GET | `/api/time` | Current server epoch seconds, for monotonic client clock estimation |
| POST | `/api/matches/{id}/duet/ready` | Loaded microphone/audio barrier; `{players: [{slot, register, calibration_offset?}]}` |
| POST | `/api/matches/{id}/duet/stop` | Stop the shared duet; restart the whole match together |
| POST | `/api/turns/{attempt_id}/begin` | `{register, calibration_offset?, range?: {start,end}}` |
| POST | `/api/turns/{attempt_id}/result` | Final phrase results; needs an `Idempotency-Key` header |
| GET | `/api/matches/{id}` | Match, players, attempts, scores, `winner_slot` |
| POST | `/api/matches/{id}/retry` | Replace a lost or abandoned turn with a fresh attempt |
| POST | `/api/matches/{id}/rematch` | New local/solo match with the same players (online: use the room) |
| GET | `/api/history`, `/api/leaderboard?clip_id=` | One row per match: `total` is your own score (null in a local battle; see `players`). Leaderboard: best solo totals of logged-in players on the current clip version |
| POST | `/api/turns/{attempt_id}/coach` | Coaching blurb for a finished turn: `{status: ok\|unavailable, coach_blurb}`. Generated once, then cached. |
| POST | `/api/practice` | Multipart: `clip_id`, `phrase_id`, `audio` (WAV/MP3/WebM/Ogg, max 5 MB and 15 s) |
| POST | `/api/lyric-check` | Multipart: `clip_id`, `offset_s` (time in the recording of clip time 0, latency already removed), `audio` (the solo take, max 12 MB and 330 s). Returns `contracts/lyric_check.example.json`: per lyric line `match` / `unclear` / `not_sung` / `not_covered`. Display only, never part of a score; nothing is stored. Shares the practice model and its busy lock (429 `pronunciation_busy`). Takes about 10 s per 35 s of audio on CPU. |
| POST | `/api/rooms`, `/api/rooms/join` | Create `{clip_id, duet: true}`; join `{code}` |
| GET | `/api/rooms/{id}` | Snapshot (members only) |
| POST | `/api/rooms/{id}/ready`, `/clip`, `/range`, `/start`, `/rematch`, `/abort` | Lobby and lifecycle (`clip`, `range`, `start`, `rematch`, `abort` are host-only) |
| WS | `/ws/rooms/{id}` | Presence, snapshots, provisional progress |

## Example: a solo game

```bash
curl -c jar -X POST localhost:8000/api/guests -H 'content-type: application/json' -d '{"display_name":"Ann"}'
# {"id":"c2b5...","display_name":"Ann"}

curl -b jar -X POST localhost:8000/api/matches -H 'content-type: application/json' -d '{"clip_id":"synthetic-demo"}'
# {"match_id":"e4cd...","attempt_id":"88a2...","scoring_version":"0.1.0"}

curl -b jar -X POST localhost:8000/api/turns/88a2.../begin -H 'content-type: application/json' \
  -d '{"register":0,"calibration_offset":0.12}'
# {"attempt_id":"88a2...","state":"started"}

# ...the client plays, rates each phrase locally, then submits once:
curl -b jar -X POST localhost:8000/api/turns/88a2.../result -H 'content-type: application/json' \
  -H 'Idempotency-Key: abc-1' \
  -d '{"phrases":[{"phrase_id":"p1","pitch":82,"timing":70,"coverage":0.9}]}'
# {"mode":"solo","clip_id":"synthetic-demo","clip_version":1,"scoring_version":"0.1.0","register":0,
#  "total":79.6,"pitch":82.0,"timing":70.0,"phrases":[...],"coach_blurb":null}
```

Rules worth knowing:
- Send per phrase `{phrase_id, pitch, timing, coverage}` (`timing` may be `null` when no note starts inside the phrase; it is then
  scored on pitch alone). The response phrases are `{phrase_id, pitch, timing|null, score, coverage, rating}`, all server-computed.
- The result must contain **every phrase of the clip exactly once** (`phrase_mismatch` otherwise), or, for a practice
  section, exactly the phrases of the range.
- **Practice section** (solo, or a host-selected online section): `POST /api/turns/{id}/begin` with `{"register":0,"range":{"start":12.0,"end":30.5}}`.
  The scored phrases are those with `start >= range.start - 0.05` and `end <= range.end + 0.05` (seconds from clip start);
  none or no scoreable reference frames -> 422 `invalid_range` (also for non-finite/out-of-clip values, or any range in a local battle). The range is
  normalized to first-phrase start .. last-phrase end, fixed for the attempt (repeat begin with another range -> 409
  `attempt_already_started`), and the result must contain exactly those phrase IDs; totals are weighted over them only.
  Responses (`Score`, `GET /api/matches/{id}`, `/api/history` rows) carry `range: {start,end} | null` (null = full clip).
  Practice runs are excluded from the leaderboard. No migration: while started the range sits in `phrase_results` as
  `{"range":...}`; once accepted it is derived from the scored phrase IDs.
- **Guide vocals:** `POST /api/turns/{id}/result` takes an optional `guide_used: bool` (the guide vocals were audible at
  any time during the turn). It is client-reported, so not cheat-proof. `Score`, the `GET /api/matches/{id}` attempts and
  `/api/history` rows carry `guided: bool` (false for old rows), and guided runs are excluded from the leaderboard. No
  migration: the flag is stored on each saved phrase dict inside `phrase_results`. Winners in battle/online are unchanged.
- Sending the **same** `Idempotency-Key` again returns the same result and changes nothing, so retry freely after a
  lost response. A **different** key on a finished attempt gets `already_submitted`.
- Continuous local multiplayer (`players` with two names and `duet: true`) creates both attempts immediately. Each
  score aggregates only that player's assigned phrases. `winner_slot` compares totals at one decimal, or is `null` for a tie.
  Legacy API clients omitting `duet` retain sequential full-song turns; the current web UI always requests continuous duets.

## Continuous multiplayer: local or online

The web UI plays the song once, with automatic singer changes. Authored `duet_sections` contain section IDs,
explicit slots `0|1`, and existing phrase IDs. Timings and lyrics come from the original phrases/lines. See
[`../contracts/duet-sections.md`](../contracts/duet-sections.md) for validation and the three-line legacy fallback.

1. Local: create `/api/matches` with `{clip_id, players: ["A","B"], duet: true}`. Online: create `/api/rooms`
   with `{clip_id, duet: true}`, join by code, ready in the lobby, then let the host call `/start`.
2. Both attempts exist in a `preparing` match. Load instrumental/vocals and open microphones before calling
   `/api/matches/{id}/duet/ready`. Online each browser sends only its own slot; local sends both players with
   their chosen registers, using the same microphone and one playback.
3. After **both** loaded acknowledgments, the server freezes `duet.start_at` to a future epoch time (five-second
   scheduling lead, including the three-second count-in). Repeated ready calls preserve it and the voice settings.
   Clients sample `/api/time`, choose the shortest round trip, and estimate server time from the midpoint and
   monotonic `performance.now()`. The local wall-clock setting does not control synchronization.
4. Schedule one WebAudio playback at the shared timestamp, with instrumental/guide offsets aligned to the full
   clip or selected practice range. Singer cues change on the clip clock; the music and microphone never restart
   at a handoff. Each client rates only assigned phrases (local rates both players with their separate targets).
5. Submit `/api/turns/{id}/result` with exactly the slot's frozen phrase IDs and a stable idempotency key. Either
   player may finish first; the match becomes `finished` only when both results are accepted. There is no second
   full-song turn. Both clients read the same winner from the match/room snapshot.

`GET /api/matches/{id}` returns `duet: {sections, range, start_at}` with derived section times and `server_time`.
`Score` and history carry `duet: true`; their `range` is the shared practice range, **not** the bounds of a player's
assigned subset. Full-song duets have `range: null`. Multiplayer stays off the solo leaderboard.

Online host `/api/rooms/{id}/range` edits clear both lobby ready flags, persist across reconnects/rematches, and
retain the authored slot of each phrase. Reject a range without scoreable assigned phrases for either player
with `422 invalid_duet_range`. Local multiplayer stays on the full clip.

No migration: lobby/loaded attempts freeze arrangement, range and schedule inside JSON `phrase_results.duet`.
Accepted rows retain that metadata under `_duet` on their first phrase. This keeps history independent of later
manifest timing changes. Draft matches remain hidden from lobby `match` and from history until results exist.

**Recovery:** an existing page can continue scheduled WebAudio through a temporary network outage and retry a
failed save using the same key. Reloading after the shared start must never replay the song for just that player:
it shows `missed_start`. A stopped mic/audio context or explicit `/duet/stop` marks the shared match
`retry_required`. Individual `/retry` returns `restart_duet`. Local rematch or host room `/rematch` creates a
fresh, unscheduled duet and requires both loaded acknowledgments again. Accepted results are never overwritten.

Legacy clients without `duet: true` keep the original `/begin` and sequential turn API. The public smoke script
still exercises that compatibility path. New multiplayer clients use the shared barrier, not `/begin`.

WebSocket snapshots retain `state_version` ordering and presence. `heartbeat`, `progress` and `phrase_rating`
remain supported; duet participants may both relay provisional updates while active. Only committed results
count. Send a heartbeat every ~15 seconds; foreign origins, messages over 2 KB, and more than 30 messages per
second are refused. After reconnecting, trust the fresh durable snapshot.

## Where things live

| File | Role |
|---|---|
| `main.py` | App, health/ready, catalog and audio routes, error handlers |
| `play.py` | Guests, Auth0 identity, matches, turns, history, leaderboard, claim |
| `rooms.py` | Rooms, WebSocket hub, snapshots |
| `duets.py`, `duet_play.py` | Authored/fallback ownership, loaded barrier, shared schedule and stop |
| `practice.py` | Spoken-practice upload and the pluggable scorer |
| `models.py`, `tables.py` | Pydantic contracts; SQLAlchemy tables |
| `retention.py` | Hourly guest cleanup; lost-turn recovery every 15 s |
| `clip_catalog.py`, `catalog/<id>/song.json` | Song loading and validation; the synthetic fixture lives in `catalog/` |
| `migrations/` | Alembic migrations (committed) |

## Songs from the ML pipeline

`python -m ml.pipeline.run` writes `ml/data/<id>/song.json` (the `contracts/song.example.json` shape) with its audio
beside it, plus `song.review.json`. The API reads those folders directly, with no copying:

```bash
python -m api.seed                      # records each song's metadata and checksum in the database
uvicorn api.main:app                    # restart to pick up new songs
```

- **Draft vs reviewed:** `GET /api/clips` returns `reviewed: true` only when `song.review.json` says `"reviewed": true`.
  Drafts are served too, so they can be played and tried, and the UI should label them. A song with no review file counts as
  not reviewed.
- **`practice_text`:** a line cut off at the clip edge has `practice_text: ""` and no phrase, and that is fine. A line that
  has a singing phrase may still have empty `practice_text` (English/mixed-language lyrics).
  Spoken practice separately requires Korean-only `practice_text`; unsupported phrases return
  `422 practice_unavailable` before decoding or calling the model.
- **Errors name the folder:** an invalid `song.json`, or two songs with the same `id`, stop the server at startup with the path.
- **Audio:** instrumental and vocal paths are relative to the song's folder and served through their respective endpoints.

## Coaching blurb

After a turn is scored, call `POST /api/turns/{attempt_id}/coach`. Gemini gets only the measured numbers (totals,
per-phrase rating, pitch, timing, coverage, register) and writes 2-3 friendly sentences. It never changes a score,
rating or winner. If there is no key, or Gemini fails or times out (10 s), the answer is
`{"status": "unavailable", "coach_blurb": null}`: show the results without it and retry later. A successful blurb is
saved and also appears as `coach_blurb` on the attempt's score in `GET /api/matches/{id}`.

## Hooks for other roles

- **Pronunciation:** with `PRONUNCIATION_SCORER=1`, startup sets `api.practice.scorer` (see `practice.attach_scorer`).
  Any scorer is an object with a `provider` string and
  `assess(wav_path, expected_text) -> [{"text": ..., "score": 0-100}]`; it may also expose `last_overall` (0-100),
  read right after `assess` and returned as the nullable `overall` on the practice response (automated, not validated
  by a fluent reviewer). It receives 16 kHz mono WAV. Raise on failure;
  the API reports `status: "error"` (never a score). Only one assessment runs at a time.
- **ML B (scoring):** `play.py` scores through `ml.scoring.score.finalize_turn`. The version, weights (80/20) and rating
  bands live only in [`ml/scoring/config.py`](../ml/scoring/config.py); the API imports them (needs `numpy`, and the
  repo root on the path). Phrase weights come from the server's own manifest (scoreable reference frames), the client's
  `rating`/`score` are ignored and recomputed, and the total is the weighted mean of the phrase scores. A bad value is a
  422 `invalid_result`. Battle `tie_decimals` is an API constant in `play.py`. Change scoring values only in
  `ml/scoring/config.py` and bump `SCORING_VERSION`; `web/src/scoring/config.ts` and `/api/scoring-config` of the demo
  app are separate copies that the shared fixtures must keep honest.
- **Real clips:** see "Songs from the ML pipeline" below. Audio is gitignored; never commit copyrighted audio.

## Known limits

- Scoring uses the reference engine but is not validated on real recordings; weights and bands are unvalidated defaults.
- Result rows saved before the engine was wired in lack the phrase `score`; reads fall back to the phrase `pitch`.
- Client-submitted phrase results are validated, not cheat-proof.
- One Uvicorn worker only: socket handles and the join rate limiter are in memory. More workers need shared event delivery.
- Not yet verified: Python 3.11, two real computers over HTTPS, an Electron PKCE login, restart mid-turn recovery.
- `connected` in a snapshot only counts sockets open on this server process; after any reconnect, fetch `GET /api/rooms/{id}` for the truth.

## Local lyric and audio preview

The main backend mounts the offline ML preview at `/karaoke/live/`.
Set `JUST_SING_LOCAL_DEMO_AUDIO=1` on the team machine to enable prepared-song
audio and provisional scoring. The home screen's SOLO SING button opens it.
It can also run separately with `uvicorn api.local_demo:app`.
See [LOCAL_DEMO.md](LOCAL_DEMO.md) for the local song picker, vocal guide and
lyric-timing workflow. This entry point does not replace the backend above.
