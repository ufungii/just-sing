# e2e: solo play in real Chromium with a fake microphone

Dev-only harness (own `package.json`; nothing here ships). It drives Home -> Solo setup (clip, name, mic check) ->
Sing -> Results -> History as a guest, three times: a **good** take, a **wrong-notes** take (alternate 0.5 s windows
+4 semitones, not a global shift) and **silence**. WAVs are synthetic tones built from the clip's reference
contour (`make_takes.py`), written to the gitignored `e2e/takes/`.

## Run (from the repo root; uses the dev DB from `.env`)

```sh
(cd web && npm ci && npm run build)          # FastAPI serves web/dist
cd e2e && npm install && npx playwright install chromium
../.venv/bin/python make_takes.py            # or: E2E_CLIP=russian-roulette ../.venv/bin/python make_takes.py
npx playwright test                          # starts uvicorn on :8765 itself; ~2.5 min
cd .. && PYTHONPATH=. .venv/bin/python e2e/cleanup_db.py   # deletes the "E2E-Bot-*" and "E2E-Rival-*" guest rows, prints counts
```

`E2E_CLIP` (default `synthetic-demo`) selects the clip for solo playback and take generation; `E2E_GOOD_FLOOR` (default 60) the minimum
good total; `E2E_LEAD` (default 6 s, same for both) the WAV prefix; `E2E_DEBUG=1` echoes page console.
The synthetic clip has no instrumental, so the app uses its click track (no audio is needed or committed).
Screenshots land in `e2e/artifacts/`.

## How alignment works, and what is asserted

Chromium restarts the fake file each time a mic stream opens. Each WAV is `LEAD` s (a 1 s hum so the mic check
passes) + the take from clip t=0. The test records when the Sing screen's stream opened and clicks START so clip
t=0 (START + 3.15 s count-in) meets stream time `LEAD`. Residual offset is click jitter plus device latency
(tens of ms); the timing check is skipped. Measured on synthetic-demo: timing score 100, so the offset is well
inside the timing tolerance.

Asserted: good > `E2E_GOOD_FLOOR`; good > wrong + 10; silence < 5; the match is in `/api/history` and the History
screen; a non-empty coach bubble; no console/page errors (401 guest bootstrap and the 404 for the missing
instrumental are expected and filtered). Absolute totals are not asserted beyond those margins.


## Practice-section ranges

`npx playwright test range.spec.ts` uses local `russian-roulette` assets and generated in-browser fake microphones (no take WAVs needed).
It checks pointer and keyboard snapping, full reset, synchronized instrumental/vocal preview (with instrumental fallback when vocals are missing), a count-in before a middle phrase, matching instrumental/guide offsets,
selected-only saved results and history, host-only room edits, save-failure recovery, readiness reset and reconnect recovery.
Both online singers use the same range and save disjoint phrase IDs according to the frozen duet ownership. The online range spans both singers; a one-singer-only section is invalid. This does not validate real-mic accuracy or lyric timing.

`E2E_PORT` overrides port 8765; `E2E_REUSE_SERVER=0` requires a fresh server rather than reusing one on that port.
Run with an isolated test database/schema when checking retention or server startup, so background cleanup never reaches hand-played rows.

## Continuous local and online duets

`npx playwright test battle.spec.ts online.spec.ts` uses the real local `russian-roulette` manifest/audio and
generated oscillator microphones. It checks one count-in/playback per client, automatic P1→P2→P1 handoffs,
one shared local singing stream, separate registers, complete disjoint saved ownership, and full-song results
remaining distinct from practice sections. A simulated failed save retries with the same idempotency key and no new playback. Online checks hold the start barrier until both clients load, compare
scheduled playback timestamps within 150 ms, and deliberately offset one browser's wall clock by one hour.
A reload after the shared start is refused without replaying one player; an explicit host restart creates a new unscheduled barrier. Screenshots mask the lyric display. These checks do not establish real microphone accuracy or physical-device
synchronization; test those with two computers/headphones. `E2E_CLIP` does not override these duet/range specs.

## Live duet voice

`npx playwright test voice.spec.ts` uses the built-in synthetic duet and two real Chromium clients with generated microphone tones. No song assets or take WAVs are needed. It checks decoded peer audio, silent preparation/count-in, section handoffs, mute without stopping local scoring, listening volume, socket recovery, reload/missed-start handling, shared restart and quit/peer teardown. Use a disposable database/schema so server startup and test cleanup never reach existing gameplay rows. See [live voice transport and physical-device checks](../docs/live-duet-voice.md).

These browser checks establish functional audio transport on one computer. They do not establish listening quality, Internet NAT traversal or total mic-to-ear latency. TURN remains unconfigured.

## Multiplayer lyrics bars

`npx playwright test lyrics.spec.ts` checks local and online duets with the built-in synthetic clip and
generated microphones. Each local singer uploads a recording; each online browser uploads only its own.
Both player panels show separate LYRICS bars, including the unavailable state when fingerprints are absent.
Use a disposable test database. A controlled checker returning alternating `match`/`unclear` lines can also
run with `E2E_REQUIRE_LYRICS=1` to require the fixture's distinct 4/6 and 1/3 results on both clients. This
checks recording, ownership, persistence and rendering; it does not measure pronunciation accuracy.

## Player-name Easter egg regression

These UI-only checks cover the Players dialog (add/rename by blur or Enter),
selection of an already-saved Zibran profile, the configured joke names, an
obfuscated slur, returning home, and ordinary longer names. They mock API requests and use isolated browser storage; no database or mic
is needed. Run from `e2e/`:

```sh
npx playwright test --config players-easter-egg.config.ts
# To use an existing system Chromium instead of Playwright's browser:
E2E_CHROMIUM=/usr/bin/chromium npx playwright test --config players-easter-egg.config.ts
```

The test runner starts a temporary Vite server on port 5189 and stops it afterward.

## Live pitch, score bars, and microphone input

From `e2e/`, run `npx playwright test online.spec.ts -g 'remote score|short local clip|recording errors'` against a disposable database and a built frontend. These three cases use the built-in `duet-demo`, so no copyrighted song assets are needed. They check different octave settings, original timestamped pitch delivery, matching live score-bar fills, local three-second recording playback, measured 3x amplitude at 300% input, and capture cleanup/retry on recorder errors. Use `npx playwright test voice.spec.ts` to check the existing voice gates, mute, capture reuse, reconnects, and teardown.
