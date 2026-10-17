# Making the reference with the same tracker as the live game

**For:** the frontend owner (Pitchy, Electron/browser) and ML A (manifests). **Why this exists:** a perfect singer scores 40-70 today, because the reference pitch and the live pitch come from different trackers that disagree on real singing.

## 1. The evidence (three real 30 s clips, ML A's demo manifests)

The "take" is the clip's own vocal, so a perfect score is the correct answer. Totals, 0-100:

| Clip | CREPE live vs CREPE reference | Browser-style tracker (MPM), clarity 0.5 | 0.65 | 0.8 | 0.65 + 0.1 s pitch tolerance | **Same tracker for reference and live** |
|---|---|---|---|---|---|---|
| Clip 1 | 96.7 | 68.6 | 59.0 | 39.1 | 74.8 | **100** |
| Clip 2 | 96.3 | 78.7 | 70.9 | 52.9 | 82.0 | **100** |
| Clip 3 | 96.3 | 79.6 | 65.8 | 37.8 | 79.3 | **100** |

(`python -m ml.evals.score_take take clip.json --tracker mpm --clarity 0.65`, with `--ref-audio` for the last column.) "MPM" is our Python emulation of Pitchy's algorithm. The last column is a ceiling: the take is the reference audio itself, so tracker errors are perfectly correlated. A different human performance will land lower, but the gap to the other columns shows the problem is the tracker mismatch, not the singer. The fix is to produce `reference.hz` with the tracker the browser runs.

## 2. What to build

1. **One shared tracker config** that both the live path and the offline script read (do not duplicate the numbers):
```json
{
  "library": "pitchy",
  "version": "<pin the exact npm version the app uses>",
  "sampleRate": 48000,
  "windowSamples": 4096,
  "hopSeconds": 0.02,
  "clarityThreshold": 0.65,
  "minHz": 65,
  "maxHz": 1000,
  "silenceGateRms": 0.005
}
```
   The starting values above are a recommendation. For reference, APR's existing live demo (`web/live/` on branch `ml/pipeline`) runs Pitchy with **`windowSamples` 4096, clarity >= 0.8, RMS gate 0.008**, and timestamps each estimate at the window *center* (the convention this spec requires). Tested against the demo clips with our emulation, that exact setting scores a perfect take **22-40**; 0.65 with a 0.005 gate scores about 47-54; 0.5 with a 0.003 gate about 63-69 (all against a CREPE-made reference). With a reference made by the same tracker these all reach about 100, which is the point of this spec.
   `clarityThreshold` is the one knob to tune (0.5-0.7 on real voices; 0.8 is too strict). `sampleRate` and `windowSamples` must be what the live `AudioContext` and detector actually use; confirm them and update this block. If the live rate varies by device, resample the mic to `sampleRate` before detecting, or the offline reference will not match.
2. **An offline Node script** (suggested: `web/tools/extract-reference.mjs`, plain Node, no browser) that runs the *same detector function the live code calls* over a vocals file:
   `node extract-reference.mjs vocals.clip.mp3 > reference.json` → `{ "hop_seconds": 0.02, "hz": [null, 261.6, ...], "tracker": { ...config } }`.
   Share one `detectPitch(frame, config)` function between the live path and this script; that is what guarantees they agree.
3. **ML A pastes the result into `reference.hz`, then reviews it by ear** (octave errors, backing vocals, held-note ends) and recomputes `reference.notes` from that same contour. `python -m ml.evals.inspect_reference song.json` checks it.

## 3. Conventions that must match (these cause silent mismatches)

- **Frame timing:** frame `i` is centered at `t = i * hopSeconds`; its window covers `t ± windowSamples / (2 * sampleRate)`, zero-padded at the clip edges. The scorer assumes this.
- **Live timestamps:** when the last `windowSamples` of mic audio end at time `T_end`, label that estimate `T_end - windowSamples / (2 * sampleRate)`. Then the one-time latency calibration only has to absorb the device's real delay, not a half-window shift.
- **Unvoiced:** `null` when clarity < `clarityThreshold`, RMS of the window < `silenceGateRms`, or the frequency is outside `[minHz, maxHz]`. Never emit 0.
- **Hop:** emit exactly one value per 0.02 s so `len(hz) * 0.02 == duration` (the inspector fails otherwise).
- **Audio prep:** mono; the same resampling as live; no loudness normalization unless the live path does it too.

## 4. Acceptance tests

1. **Perfect-take test:** feed a clip's vocals through the live detector path (offline harness is fine), score it against the new reference with the TypeScript scorer. **Expect >= 95** on every demo clip. (Python equivalent: `score_take --ref-audio`.)
2. **Silence and noise-only both score 0** against the new reference.
3. **Parity with the Python emulation:** run the Node script and `ml/evals/mpm.py` on the same clip and compare voiced share and the share of frames within 1 semitone. If they disagree materially, tell ML B: the evals' absolute numbers need re-checking against real Pitchy output.
4. `inspect_reference.py` on the resulting manifest: 0 failures.

## 5. Proposed contract addition (needs team sign-off)

An optional `reference.tracker` object in the manifest recording what produced `hz` (the config block above), so a manifest made with a different tracker than the live app is detectable. The API's `Song` model ignores unknown fields today, so adding it is backward compatible.

## 6. Electron vs the browser

Same thing for this purpose. Electron runs Chromium and the same JavaScript engine, and `getUserMedia` / Web Audio behave as in Chrome, so Pitchy produces the same numbers in both. One config covers both, and the offline script is plain Node, so Electron neither helps nor hurts it. Things to check: `echoCancellation`, `noiseSuppression` and `autoGainControl` must be off in the Electron window too, and the `AudioContext` sample rate on the demo laptop must match `sampleRate` above.
