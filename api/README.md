# API

FastAPI backend for the karaoke app: song catalog, guest and Auth0 sessions, solo / local / online matches,
spoken-practice uploads, and online rooms. It never touches the singing clock: pitch tracking and phrase
ratings happen in the client, which submits the finished phrase results once.

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
Without a pronunciation scorer, `/api/practice` answers `status: "unavailable"`.

## Environment

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...` (SQLAlchemy needs that scheme, not `postgres://`). Server-side only. |
| `AUTH0_DOMAIN` | Tenant domain, no `https://`. |
| `AUTH0_AUDIENCE` | The Auth0 API identifier. Login requests must pass the same `audience`, or Auth0 issues an opaque token we cannot verify. |
| `COOKIE_SECURE` | `1` on public HTTPS so the guest cookie is Secure. Leave `0` on `http://localhost`. |
| `GUEST_TTL_DAYS` | Guest session lifetime, default 7. Expired guests and their data are deleted hourly. |
| `ALLOWED_ORIGINS` | Extra browser origins allowed to open WebSockets. The server's own host is always allowed. |
| `RECONNECT_GRACE_SECONDS` | Extra time after a clip ends before a started turn is treated as lost, default 60. |

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
| 409 | `not_your_turn`, `attempt_not_started`, `attempt_closed`, `attempt_invalidated`, `already_submitted`, `cannot_retry`, `use_room_rematch`, `room_full`, `room_started`, `not_ready`, `not_finished` |
| 410 | `room_expired` |
| 413 / 422 | `audio_too_large`, `audio_too_long`, `unsupported_audio`, `phrase_mismatch`, `invalid_register`, `invalid_request` |
| 429 | `pronunciation_busy` (retryable), `too_many_joins` (retryable) |
| 503 | `catalog_not_seeded`, `auth_unavailable`, `room_code_unavailable` |

## Endpoints

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health`, `/api/ready` | Liveness; readiness (`catalog`, `database`, `pronunciation`) |
| GET | `/api/clips`, `/api/clips/{id}/manifest` | Prepared catalog; full manifest |
| GET | `/api/clips/{id}/audio` | Instrumental only, supports `Range` |
| POST | `/api/guests` | Create guest `{display_name}`; sets the cookie |
| POST | `/api/auth/claim` | After login, send bearer token + guest cookie to move guest history to the account |
| POST | `/api/matches` | `{clip_id}` for solo, plus `players: ["A","B"]` for local battle |
| POST | `/api/turns/{attempt_id}/begin` | `{register, calibration_offset?}` |
| POST | `/api/turns/{attempt_id}/result` | Final phrase results; needs an `Idempotency-Key` header |
| GET | `/api/matches/{id}` | Match, players, attempts, scores, `winner_slot` |
| POST | `/api/matches/{id}/retry` | Replace a lost or abandoned turn with a fresh attempt |
| POST | `/api/matches/{id}/rematch` | New local/solo match with the same players (online: use the room) |
| GET | `/api/history`, `/api/leaderboard?clip_id=` | Your saved results; best totals of logged-in players |
| POST | `/api/practice` | Multipart: `clip_id`, `phrase_id`, `audio` (WAV/MP3/WebM/Ogg, max 5 MB and 15 s) |
| POST | `/api/rooms`, `/api/rooms/join` | Create `{clip_id}`; join `{code}` |
| GET | `/api/rooms/{id}` | Snapshot (members only) |
| POST | `/api/rooms/{id}/ready`, `/clip`, `/start`, `/rematch`, `/abort` | Lobby and lifecycle (`clip`, `start`, `rematch`, `abort` are host-only) |
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
  -d '{"phrases":[{"phrase_id":"p1","rating":"great","pitch":82,"timing":70,"coverage":0.9}]}'
# {"mode":"solo","clip_id":"synthetic-demo","clip_version":1,"scoring_version":"0.1.0","register":0,
#  "total":79.6,"pitch":82.0,"timing":70.0,"phrases":[...],"coach_blurb":null}
```

Rules worth knowing:
- The result must contain **every phrase of the clip exactly once** (`phrase_mismatch` otherwise).
- Sending the **same** `Idempotency-Key` again returns the same result and changes nothing, so retry freely after a
  lost response. A **different** key on a finished attempt gets `already_submitted`.
- Local battle (`players` with two names): the second player's attempt appears in `GET /api/matches/{id}` after the
  first result is saved. `winner_slot` is the higher total at one decimal, or `null` for a tie.

## Example: an online room

1. Host `POST /api/rooms {clip_id}` and shares the returned `code`; the friend `POST /api/rooms/join {code}`.
2. Each calls `POST /api/rooms/{id}/ready {ready: true}`; the host calls `/start` (returns `match_id`, `attempt_id`).
3. Both open `ws://host/ws/rooms/{id}` (guest cookie, or `?access_token=` for Auth0). The server sends `room_snapshot`
   immediately and after every durable change.
4. The singer runs `begin` then `result` exactly as in solo. Only the active seat may call them (`not_your_seat` otherwise).
5. The other player sees `result_saved`, then their own turn opens; after the last result, `match_finished`. Both read the
   same winner from `GET /api/rooms/{id}` (`match.winner_slot`).

WebSocket messages (all JSON with a `type` and an `id`):

| Direction | Types |
|---|---|
| Client → server | `heartbeat`, `progress` (`data`), `phrase_rating` (`data`). Progress and ratings are accepted only from the active singer. |
| Server → client | `room_snapshot` (includes `state_version`; ignore older versions), `heartbeat_ack`, `turn_progress`, `phrase_rating`, `result_saved`, `match_finished`, `error` |

Limits: messages over 2 KB or more than 30 per second get an `error`; a socket silent for 45 s is closed (send a
`heartbeat` every ~15 s); browsers sending a foreign `Origin` are refused. **Live progress and badges are provisional;
only a committed `result` counts.** After a reconnect, trust the fresh snapshot, not what you buffered.

**Lost turns:** a started turn that is not finished within the clip length + grace period is invalidated and the match
becomes `retry_required`. Call `POST /api/matches/{id}/retry` for a fresh `attempt_id`. A tab that is still open after a
network blip can submit the same attempt with the same `Idempotency-Key` as long as the deadline has not passed.

## Where things live

| File | Role |
|---|---|
| `main.py` | App, health/ready, catalog and audio routes, error handlers |
| `play.py` | Guests, Auth0 identity, matches, turns, history, leaderboard, claim |
| `rooms.py` | Rooms, WebSocket hub, snapshots |
| `practice.py` | Spoken-practice upload and the pluggable scorer |
| `models.py`, `tables.py` | Pydantic contracts; SQLAlchemy tables |
| `retention.py` | Hourly guest cleanup; lost-turn recovery every 15 s |
| `clip_catalog.py`, `catalog/<id>/manifest.json` | Validated manifests (audio files go next to them, gitignored) |
| `migrations/` | Alembic migrations (committed) |

## Hooks for other roles

- **ML A (pronunciation):** set `api.practice.scorer` to an object with a `provider` string and
  `assess(wav_path, expected_text) -> [{"text": ..., "score": 0-100}]`. It receives 16 kHz mono WAV. Raise on failure;
  the API reports `status: "error"` (never a score). Only one assessment runs at a time.
- **ML B (scoring):** `play.py` recomputes totals with a **stand-in** (duration-weighted mean of phrase pitch and timing,
  80/20). Replace it with a call into `ml/scoring` once that exists, and keep `scoring_version` in step.
- **Real clips:** put `manifest.json` and the instrumental in `api/catalog/<id>/`, then run `python -m api.seed`.
  Audio is gitignored; never commit copyrighted audio.

## Known limits

- Scoring is a placeholder; ratings are stored as the client submitted them, not recomputed.
- Client-submitted phrase results are validated, not cheat-proof.
- One Uvicorn worker only: socket handles and the join rate limiter are in memory. More workers need shared event delivery.
- Not yet verified: Python 3.11, two real computers over HTTPS, an Electron PKCE login, restart mid-turn recovery.
- `connected` in a snapshot only counts sockets open on this server process; after any reconnect, fetch `GET /api/rooms/{id}` for the truth.
