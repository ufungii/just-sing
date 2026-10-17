# TypeScript port: updating to scoring version 0.2.0

`ts_port_0.2.0.patch` (this folder) brings the `web/src/scoring/` port to scoring version 0.2.0. It applies cleanly to both `origin/overnight` and `origin/overnight-extra` (their scoring files are identical; verified on each: `tsc -b` clean, 14 of 14 tests pass):

```bash
git apply -p1 ml/scoring/ts_port_0.2.0.patch      # from the repo root, on the overnight-extra (or overnight) branch
cd web && npm test && npx tsc -b                   # 14 tests pass, typecheck clean
```

What it changes (3 files):
- `config.ts`: `SCORING_VERSION` -> `'0.2.0'`; `timeToleranceS` 0 -> **0.1**; live tracker thresholds `minClarity` 0.85 -> **0.65** and `minRms` 0.01 -> **0.005** (real-Pitchy numbers in `ml/README.md`, "Trackers"); `ScoringConfig` is widened to plain `number`s so tests can override a single value.
- `score.ts`: `scorePhraseSpan` now picks **one shift of the user's track per phrase** (SPEC section 4) instead of the best frame at every position, and reads the track up to `k` frames beyond the reference length so a shift can reach a late take's tail.
- `fixtures.test.ts`: every fixture case records its own `time_tolerance_s`, and the test builds its config from it. This exercises both the strict (0 s) and the forgiving (0.1 s) path.

Verified against the regenerated `contracts/fixtures/` (`python -m ml.evals.make_fixtures`): before the patch 12 of 14 pass (only the two tolerance cases fail); after it 14 of 14 pass, `tsc -b` is clean, and `vite build` succeeds. Not verified: the Playwright e2e and the live Electron/browser app, since those need the full stack and a microphone.

Also needed on the server side when this lands: nothing in `api/` changes, because `api/play.py` takes `SCORING_VERSION` from `ml/scoring/config.py`. If `contracts/scoring.config.json` still exists on the branch being merged, its `scoring_version` must be set to `0.2.0` too.
