# tasks.md

Live task list. Last cleaned 2026-10-17. Older material (the finished backend handoff and the original 36-hour backend checklist) was removed; a copy is in `ml/data/work/tasks.md.bak-2026-10-17` (gitignored).

## Rules for agents working here

- Treat `CLAUDE.md` as repository instructions for Codex too (explicit user preference). Current explicit user instructions take precedence where they conflict.

- Work on `overnight-extra` (a superset of `overnight`). Free to commit there. Do not touch the local `main` branch. Push or open a PR only with explicit user authorization. **The user authorized pushing this work and opening a PR to `main` on 2026-10-17 after vocals-preview completion and bug checks; that authorization overrides the earlier no-push/no-PR rule for this work.**
- No co-author line on commits, no "Generated with Claude Code" footer on PRs (the user's explicit preference).
- Never commit secrets, audio, model weights or `.env`. `.env` points at the **dev** database; tests never run against production. Do not delete database rows you did not create (the user has hand-played rows).
- Songs live in gitignored `ml/data/`. Copyrighted lyrics and audio never go in tracked files or chat output.
- Say plainly what was verified and what was not (no real mic, no real second computer, no live Auth0 login so far).

## Open tasks

### 1. Clip-range editor (practice section) for solo and online lobbies

Status: **implemented and verified (Codex, 2026-10-17).** Shared timeline and solo/online range wiring are complete on `overnight-extra`. The author tool (task 2) can import `web/src/components/timeline/ClipTimeline.tsx`.

Verification and implementation notes:
- Final typecheck/production build and all **24 Vitest tests passed**. The build retains its existing large-chunk warning.
- The complete API suite passed: **104 tests, 3 existing warnings**. This includes the regression preventing accepted host phrase IDs from being reinterpreted against a replacement manifest version.
- Both tests in `e2e/range.spec.ts` passed (**2 tests, 37.3 s**) against the real local `russian-roulette` manifest with fake mics (solo plus two browser contexts online). The final API and browser runs used separate temporary schemas in a disposable, localhost-only PostgreSQL container; both schemas were removed afterward. The final full-clip browser regression suite also passed: **5 tests, 4.8 min** (solo good/wrong/silence, local battle, online battle). Its isolated schema and disposable container were removed afterward. Earlier dev-DB retries hit connection timeouts; final local runs passed.
- Python score/fixture/spec/timing tests: **36 passed, 1 skipped**. Broader offline pitch extraction tests need unavailable `librosa`/`scipy` in the lean API environment (3 dependency failures); no ML dependencies were changed.
- Solo visual QA passed using a lyric-masked screenshot: keyboard selection keeps the handles and nearby phrases visible. Committed selection edges normalize to the selected phrases, matching the server even when only one handle moves.
- Preview plays instrumental plus available vocals with identical scheduled time, selected offset and duration. Missing vocals preserve instrumental preview; an early vocal ending does not stop the instrumental. Browser checks cover both cases.
- No migration: lobby range lives in a pending host attempt on a draft match, activated at room start. Original host attempts preserve the selection across retries; accepted phrase IDs preserve it after scoring. Failed room saves restore the last server selection. Clip/range changes reset both ready flags. All-zero-weight sections are rejected before playback.
- No real mic, real second computer or live Auth0 login tested here. Audio/lyric timing still needs listening review.
- Local isolated runner: `/tmp/just-sing-task1-tests.py` (loads dev `.env` unless `DATABASE_URL` is already set, never prints credentials, creates/removes only its own schema, seeds browser-test metadata and disables reuse of an existing e2e server). Commands: `.venv/bin/python /tmp/just-sing-task1-tests.py .venv/bin/python -m pytest api -q` and `.venv/bin/python /tmp/just-sing-task1-tests.py e2e/node_modules/.bin/playwright test -c e2e/playwright.config.ts range.spec.ts`.
- The user authorized a push and PR after these checks; publication is handled separately from this implementation handoff.

**Goal.** Before singing, the player chooses which part of the song to sing, like a video editor: the bottom half is a clip strip with two draggable ends, the top half shows the lyrics at their points in time so the player sees which line sits where. Both ends snap to phrase boundaries: start only at a phrase start, end only at a phrase end.

**Decided (do not re-ask).**
- Only phrases fully inside the range are scored, with the same rules. These are "practice section" runs, not comparable with full-clip scores, and never on the leaderboard (already enforced).
- Available in **solo** and in **online lobbies, where only the host picks the range** (it applies to both players). Local 1P vs 2P stays on the full clip (the server rejects a range there).

**Server side is done** (`bf7e97a`; `api/play.py`, tests in `api/tests/test_play.py`):
- `POST /api/turns/{attempt_id}/begin` takes an optional `range: {start, end}` in seconds, e.g. `{"register":0,"calibration_offset":0.0,"range":{"start":5.0,"end":15.0}}`. Omit it for the full clip. The server keeps phrases with `start >= start-0.05` and `end <= end+0.05` and stores the normalized range.
- 422 `invalid_range`: values not finite, `0 <= start < end <= duration` fails, no phrase fits, no scoreable frames remain, or the match is a local battle. A different range after begin gives 409 `attempt_already_started`.
- `POST /api/turns/{id}/result` must send exactly the included phrase IDs, otherwise 422 `phrase_mismatch`.
- `range` (`{start, end}` or `null`) appears on the Score response, `attempts[].score` in `GET /api/matches/{id}`, and each `/api/history` row.
- **Online rooms implemented** (`api/rooms.py`): host-only `/api/rooms/{id}/range`, durable lobby selection, guest read-only snapshots, both turns/retries/rematches use the same section, and clip/range changes reset readiness. Uses a draft match and pending host attempt; no Alembic migration.

**Web work.**
1. Reusable timeline component (phrase blocks or waveform of the clip, playhead, two draggable handles).
2. Solo setup: range picker with the lyric lines above the strip at their times, handles snapping to phrase boundaries, a Play-preview for the selected range, a "full clip" reset, and a count of selected phrases and seconds.
3. Sing: start the instrumental at the range start and stop at the end, with clip time still measured from clip start so notes, lyrics and scoring stay aligned; count-in before the start; only included phrases are rated live and submitted. The guide vocals must follow the same offset.
4. Online lobby: host-only picker; the guest sees the range read-only.
5. Results and history: label the run "practice section" with the range.

**Done when.** A solo run on `russian-roulette` over a middle range scores only those phrases, the saved result shows the range, and it is off the leaderboard. An online room with a host range scores both players on the same phrases. Typecheck, vitest, build, API tests and a Playwright range spec pass (fake mic only).

### 2. Song author tool, review-only v1 (queued after task 1)

Decided: a **standalone app** in `author/` with its own build and its own small local Python server bound to `127.0.0.1` only (nothing in `api/` changes, a tunnel can never reach it). It imports the timeline component straight from `web/src/`. Review only; adding songs (YouTube link, Demucs, alignment as a job) is a teammate's later task.
- Shows the vocals waveform with the reference pitch contour drawn over it, lyric lines as draggable blocks, and playback of vocals, instrumental or both with a playhead; click a line to jump to it.
- Edits lyric text, line times, phrase boundaries (including held-note ends), excluded regions and a translation box per line. Octave and note editing are later.
- Syncing: tap-to-sync (play the vocals, press a key at each line start) plus drag to fine-tune with snapping to voiced onsets in the reference contour.
- Saving: explicit Save writes `corrections.json` and `song.review.json` next to the song (a `.bak` of the previous file each time); in-memory undo and redo; no autosave; never edits `song.json` directly. A Rebuild button reruns the manifest step; Mark reviewed flips the flag.
- Tests: unit tests for reading and writing corrections, a check that a saved correction survives a pipeline rebuild, one Playwright smoke test (load a song, drag a line, save). No test claims anything about sync accuracy; that is judged by ear.

### 3. Known rough edges (from the lobby work and the Opus review)

- Online: a singer who quits mid-turn leaves the attempt "started"; the retry button exists but has no UI e2e. A failed save returns the singer to the room with an error and no retry button for the save itself.
- Online: a guest cookie that already has a name ignores the name typed in the form; the Sing title does not show the player name for online turns.
- Battle hand-off picks the first slot-1 attempt (`BattleTurn.tsx`), which could be an invalidated one.
- Server `_weights` (`api/play.py`) always uses the `reference.hz` contour while the TS scoring falls back to the notes: they can disagree for a manifest with a stub contour. No current clip triggers it.
- `/api/clips/{id}/vocals` serves stems without auth (same as the instrumental). The public deployment must not have copyrighted stems installed.
- `web/src/scoring/config.ts` and `/api/scoring-config` in `api/local_demo.py` are still separate copies of the scoring numbers; `ml/scoring/api_integration.patch` and `API_INTEGRATION.md` are stale.
- ML B: add an exact-half rounding case to `contracts/fixtures` (TS now rounds half-even like Python; covered only by `web/src/scoring/rounding.test.ts`).

### 4. Docs

- `CLAUDE.md` "Current status" is stale (it still says totals use a stand-in and that battle UI is not started). Refresh it after the user confirms; CLAUDE.md edits go in their own small PR.
- Message to DrewV2 about the stale `origin/ml/pipeline` branch (not merged; 27 commits behind, conflicts in 11 files). Draft for the user to send:
  > The `ml/pipeline` branch is 27 commits behind `main` and conflicts in 11 files, mostly older copies of code that already merged via PRs #9 and #11. We are not merging it. Anything you still want from it? I can see a `/catalog` endpoint and the `reference_unavailable` error on the demo app. Tell me what to port, and then we delete the branch.

## The user does these (remind at the right time)

- **Listen to the clips and review them**: `russian-roulette` and `how-sweet` are both `reviewed: false`. `how-sweet` lyrics are the user's pasted text; line timing is hand-anchored and unverified (check the line 8/9 split near 21-22 s, the 18-34 s stretch, phrase p8's end and the long hold in p7).
- **Sing it with a real mic and headphones**; the real-mic path is only tested with a fake mic.
- **Auth0**: login works in the browser; the Auth0 SPA must keep its callback, logout and web-origin URLs in sync with wherever the app is served (localhost, the server URL, the tunnel).
- **Production database**: two Alembic revisions behind (`3e6c60a577fd` coach blurb, `2822a2cbf379` unique Auth0 account). Run `alembic -c api/alembic.ini upgrade head` with the production `DATABASE_URL` set as an environment variable (never in `.env`) **before** deploying, then `python -m api.seed` there. No new migration has been added since.
- **Rotate the Gemini key and database password** that were pasted into chat.
- Two-computer room test and the final demo setup. The Cloudflare tunnel (`--protocol http2` on campus Wi-Fi) is stopped and must stay stopped when unattended.
- Open PRs and merge. `overnight-extra` is 0 commits behind `main` and merges cleanly as of the last check.

## Done recently (for orientation)

- Solo MVP verified end to end with a fake mic on the real clip: server-side scoring through the reference engine, TS scoring parity (`web` tests), Auth0 login, coach with template fallback (`overnight`, `12ef3be`).
- `overnight-extra`: opt-in pronunciation hook with nullable `overall` (`d4956dd`); local battle (`a2d4e3a`); guide-vocals toggle and slider (`165de3f`); online lobbies (`816af36`); server-side practice-section range (`bf7e97a`); review fixes (`188eefb`).
- Prepared clips (local only, gitignored): `russian-roulette` (30.5 s) and `how-sweet` (80 s).
