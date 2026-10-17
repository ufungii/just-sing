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

`E2E_CLIP` (default `synthetic-demo`) selects the clip for both scripts; `E2E_GOOD_FLOOR` (default 60) the minimum
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
