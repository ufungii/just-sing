# Overnight notes (solo MVP)

Branch `overnight`. Everything below was run on this machine; "not verified" means exactly that.

## What works (verified)

- **Solo play end to end on the real clip** (`russian-roulette`, 30.5 s, Red Velvet): `e2e/` drives real Chromium with a
  fake mic through Home (guest) -> Solo setup -> Sing -> Results -> History. Server-saved totals: good take 85.8,
  wrong-notes take 50.7, silence 0. Run: see `e2e/README.md` (`E2E_CLIP=russian-roulette`).
- **Server-side scoring**: `api/play.py` scores with `ml.scoring.finalize_turn`; client ratings are ignored.
  `ml/scoring/config.py` is the single scoring config (`contracts/scoring.config.json` deleted).
- **TS scoring parity**: `web/src/scoring` follows `ml/scoring/SPEC.md`; `npm test` runs `score_cases` and
  `onset_cases` fixtures (12 pass). One real bug found: half-even vs JS rounding of frame indices.
- **Coach**: Gemini when `GEMINI_API_KEY` works, otherwise a deterministic template blurb (`source: "template"`).
- Tests: `pytest api` 88 passed (dev DB, no leftover rows); light ML env 89 passed, 4 skipped (need PyTorch);
  `web`: typecheck, vitest, build pass.

## Needs you (morning checklist)

1. **Sing it with a real mic and headphones.** Only a fake mic was tested. Check pitch tracking feels right and the
   timing check/latency offset behaves.
2. **Review the clip by ear** (`ml/data/russian-roulette/`, `reviewed: false`):
   - Korean text is an uncorrected Whisper draft; word alignment is weak (mean posterior 0.31, 16 flagged words).
     Fix it against a reliable lyric source and rerun the pipeline.
   - Translations are empty (no translation step ran).
   - Phrase ends / held notes are line-based; no `excluded` regions marked (harmonies/backing vocals unchecked).
   - Octaves were only sanity-checked from numbers (73.7% voiced, 232-527 Hz).
   - Stems are plain `htdemucs`, not the pipeline's fine-tuned/mastered recipe. Window: `WINDOW.txt` (`--start 90.2`).
   - 4 lines got hand-edited `practice_text` (Hangul-only words) in `song.json`; noted in `song.review.json`.
3. **Auth0** (live login not tested): create a Single Page Application; set Allowed Callback URLs, Allowed Logout
   URLs and Allowed Web Origins to `http://localhost:5173`, the server URL and the tunnel URL. The API with
   identifier `AUTH0_AUDIENCE` must exist. Put `VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_AUDIENCE`
   in `web/.env.local` (see `web/.env.example`). Without `VITE_AUTH0_CLIENT_ID` the app is guest-only.
4. **Production DB** is still two Alembic revisions behind: run `alembic -c api/alembic.ini upgrade head` with the
   production `DATABASE_URL` set as an environment variable before deploying this code. Tasks here needed no new
   migration. Run `python -m api.seed` there too (new clip).
5. **Rotate the keys** that were pasted into chat (Gemini key, database password).
6. The copyrighted song stays local: `ml/data/` is gitignored. The public deployment must ship a CC/royalty-free clip.

## Cross-folder edits (CLAUDE.md asks me to say so)

- `web/` (Frontend), `api/` + `contracts/` (Full-stack), `ml/data/` only (ML A). No `ml/` code changed.
- `CLAUDE.md`: only the two `scoring.config.json` references were removed (weights/bands/version now live in
  `ml/scoring/config.py`). Contracts: `contracts/scoring.config.json` deleted per `tasks.md` Task 2.
- Dev DB was seeded with `python -m api.seed` so the new clip exists there.

## Known gaps / copies

- `web/src/scoring/config.ts` and `/api/scoring-config` in `api/local_demo.py` are still separate copies of the numbers.
- `ml/scoring/api_integration.patch` and `API_INTEGRATION.md` are stale now.
- `live_scoring.json` fixture belongs to the older `ml/scoring/live.py` engine used by `web/live`; the TS port follows
  SPEC.md instead, so it is not tested against that file.
- `ml/pipeline/run.py` hardcodes a Windows separation-venv path (unused when `--vocals/--instrumental` are given).
- Pipeline venv lives outside the repo at `~/.cache/just-sing-pipeline/venv` (python 3.12, torch 2.8, demucs 4.0.1;
  `av` pinned to 15.1.0 because faster-whisper crashes on newer).
