# ML: scoring, pronunciation, and evals

This folder holds everything that judges a performance: the singing score (pitch + timing), the spoken Korean pronunciation scorer, and the evaluations that check both behave sensibly. Song preparation (stem separation, reference extraction, manifest assembly) lives in `ml/pipeline/`.

We have no labeled singing or pronunciation data, and nobody on the team is fluent in Korean. So we do not train models. We build the scorers on pretrained models and signal processing, then **measure** them with synthetic data whose ground truth we control. Every number below comes from a script in `ml/evals/` and its output in `ml/evals/results/`.

## Layout

| Path | What it is |
|---|---|
| `scoring/pitch.py` | The shared pitch extractor (`pitch_contour` → array for evals; `reference_contour` → manifest-form dict for the pipeline) and pitch scoring |
| `scoring/timing.py` | Note-onset detection and timing scoring |
| `scoring/score.py` | Per-phrase scores, ratings, and totals (`score_turn`, `finalize_turn`, `phrase_weights`) |
| `scoring/config.py` | Every tunable threshold, plus `SCORING_VERSION` |
| `pronunciation/` | Spoken Korean scorer (`assess`) and the two baselines it was chosen from |
| `evals/` | Synthetic data, eval scripts, the manifest inspector, results |
| `../contracts/fixtures/` | Shared test cases the browser's TypeScript scorer must reproduce |

## Setup

Python 3.11, two environments (the speech stack is heavy and kept apart):

```bash
# light: scoring, evals, inspector (CPU only)
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r ml/requirements.txt

# speech + CREPE (GPU optional; RTX 50-series needs the cu128 build)
uv venv --python 3.11 ml/pronunciation/.venv
uv pip install --python ml/pronunciation/.venv/bin/python torch torchaudio --index-url https://download.pytorch.org/whl/cu128
uv pip install --python ml/pronunciation/.venv/bin/python -r ml/pronunciation/requirements.txt
```

Tests: `.venv/bin/python -m pytest ml` (speech tests skip themselves there) and `ml/pronunciation/.venv/bin/python -m pytest ml/pronunciation ml/scoring`.

## Entry points

- **API, after a song:** `phrase_weights(ref_hz, phrases, hop_seconds=..., excluded=...)` once per clip, then `finalize_turn(submitted_phrases, weights, expected_phrase_ids=..., register=...)`. It validates the browser's per-phrase results, ignores any client-claimed score or rating, recomputes everything, and raises `ValueError` on bad input. Needs only numpy.
- **API, pronunciation practice:** `ml.pronunciation.baselines.assess(audio, expected_text)`. Returns per-word scores (0-100) in the shape of `contracts/practice.example.json`. Needs PyTorch, so run it outside the main API process. Convert uploads first: `ffmpeg -i in -ac 1 -ar 16000 out.wav`.
- **Pipeline:** `pitch_contour(audio, sr, backend="crepe")` builds the reference, so the reference and the evals share one extractor.
- **Frontend's TypeScript port:** follow `scoring/SPEC.md` and test against `contracts/fixtures/`. `scoring/tests/test_spec.py` is an independent plain-Python implementation written only from the spec that passes the fixtures, so it can be translated line by line.
- **As soon as a vocals stem exists:** `ml/pronunciation/.venv/bin/python -m ml.evals.rough_reference vocals.wav --id <song>` extracts the reference, proposes rough phrases, runs the inspector, and checks the scorer on the real contour (all output under the gitignored `ml/data/<song>/`).
- **Before handing over a manifest:** `python -m ml.evals.inspect_reference song.json --plot contour.png` checks structure and flags octave jumps, heavy exclusions, notes too short to time, and phrases with nothing to grade.

## How the singing score works

- Pitch tracks are Hz every 20 ms (`null` = unvoiced). Error is measured in cents (100 cents = one semitone).
- **Pitch:** per reference frame, full credit within 50 cents, falling linearly to zero at 200. Only frames where the reference is voiced and not excluded count. A silent player earns zero on those frames, which stay in the denominator.
- **Register:** the player picks original, an octave down, or an octave up, once per turn.
- **Timing:** reference note starts vs the player's note starts, after subtracting one device-latency offset measured in setup. Full credit within 0.1 s, zero by 0.4 s. A player's note start only counts if the pitch is steady for ~80 ms, which keeps tracker noise from earning points.
- **Phrase score** = 80% pitch + 20% timing, rated perfect / great / okay / bad, or miss if under 25% of the phrase was sung. **Total** = phrase scores weighted by scoreable duration, so it always agrees with the badges the player saw.
- All of these are defaults in `config.py`, pending calibration on real recordings.

## Evaluation results

### Singing score under controlled damage (`run_evals.py` → `results/degradation.md`)
A synthetic voice-like melody is damaged at increasing severity, rendered to audio, tracked with pyin, and scored. Spearman ρ near −1 means the score falls steadily as damage rises.

| Damage | Score trend | ρ |
|---|---|---|
| Every note detuned ±N cents | 98 → 70 at 100 cents → ~18 at 200+ | −0.96 |
| Notes skipped | steady fall to 0 | −0.99 |
| Late entrance | 98 → 74 at 0.2 s → 37 at 0.4 s | −0.99 |
| White noise | ~97 down to 5 dB SNR, then collapses | −0.86 |
| Slower tempo | 70 at 5% slower; non-monotonic at extremes | −0.82 |

Sanity checks pass: silence 0, noise only 3.5, octave up 96 with the right register and 20 without, identical input gives identical output.

### Trackers: browser vs reference (`tracker_eval.py` → `results/trackers.md`)
The live game compares the browser's tracker (Pitchy, McLeod Pitch Method) with a CREPE reference. With our MPM reimplementation standing in for Pitchy:

| Take | Same tracker (CREPE vs CREPE) | Live pairing (CREPE vs MPM) |
|---|---|---|
| clean | 99.7 | 94.1 |
| 10 dB noise | 99.4 | 87.4 |
| 5 dB noise | 99.4 | **0.0** (MPM rejects every frame) |

That was a clean synthetic voice. On a **real vocal stem** the picture is different (`real_tracker_eval.py` → `results/real_tracker_<clip>.md`): a real voice is breathy, has vibrato and fast notes, so the browser tracker is much less sure than CREPE.

| MPM clarity | Frames voiced (CREPE: 82%) | About an octave off | Near-perfect take scores |
|---|---|---|---|
| 0.9 | 44% | 3% | 54 |
| 0.8 | 62% | 7% | 69 |
| 0.7 | 75% | 9% | 80 |
| 0.6 | 85% | 11% | 83 |

- **The threshold is the main lever, and 0.8 is too strict for real voices.** Use about **0.6-0.7**. Noise-only and silence still score 0 at every threshold, and bad takes stay well separated from good ones.
- **Gap filling and octave correction (`track_cleanup.py`) did not help** (within about 3 points, mostly slightly worse), so they are not adopted.
- **Tracker disagreement caps a perfect take at about 80-83 (clarity 0.6-0.7; only 69 at 0.8)** when the reference comes from CREPE and the live track from Pitchy-style MPM. If the reference is instead built with the same tracker family as the live one, the same near-perfect take scores about 97 and a detuned or late take still scores 43-62. This is an upper bound (our "perfect take" is the same audio plus noise, so tracker errors are more correlated than they would be for a different human performance), but it is a strong argument for either extracting the reference with the browser's own tracker (then reviewing it by hand) or recalibrating the rating bands against the live path. **Do not ship the 90/75/50 rating bands until they are calibrated on a real take**: with a CREPE reference, a perfect live take would never reach "perfect".

**Frontend:** use Pitchy clarity 0.6-0.7, and show a "we can't hear you" warning when almost no frames are voiced so a mic problem is never scored as bad singing.

### Real-voice degradation (`real_audio_eval.py` → `results/real_audio_<clip>.md`)
The same controlled damage as above, applied to a real vocal stem instead of a synthetic melody (local-only audio; only aggregated numbers are committed). With CREPE tracking, scores still fall in order for local detuning (100 → 84 → 63), lateness (100 → 81 → 61 → 37), dropped seconds, and noise (99 at 30 dB, 76 at 5 dB). The scorer is not an artifact of clean synthetic voices.

### Pronunciation (`pronunciation_eval.py`, `pronunciation_nearmiss.py`)
Test speech is generated locally with Meta's MMS-TTS Korean voice.

| | A: Whisper + jamo | B: wav2vec2 forced alignment |
|---|---|---|
| Right text vs a different sentence (AUC, clean) | 1.000 | 0.998 |
| Same at 0 dB noise | 1.000 | 0.793 |
| One sound changed in one word: word AUC | 0.62 | 0.64 |
| One sound changed: flags the right word (chance 0.31) | 0.33 | **0.54** |

**Whisper autocorrects.** On 25 of 39 clips where one sound was changed, Whisper's transcript contained the *correct* word; it reported the sound actually said only twice. So `assess()` uses B, which scores the expected text against the audio and cannot autocorrect. Both methods are weak on single-sound errors (n = 39, so the top-1 rates carry roughly ±0.15 uncertainty).

### Pitch time tolerance (`tolerance_eval.py` → `results/tolerance.md`)
Strict frame-by-frame pitch scoring counts lateness twice (pitch and timing). An optional `time_tolerance_s` (default 0, off) fixes that: at 0.1 s, a 0.1 s-late take goes from 87.9 to 100 and a 0.2 s-late take from 69.1 to 81.2, while a 100-cent-detuned take stays at 73.3. Not enabled yet; it is a team decision.

## Design decisions and tradeoffs

- **Pitch contours, not learned embeddings.** A contour compared in cents is explainable ("you were 80 cents flat on this note"), needs no training data, and can run in the browser. Learned similarity would need labeled performances we don't have.
- **Fixed register, not octave folding or key-shift removal.** Folding every frame to the nearest octave, or subtracting the player's median offset, both reward a melody that jumps around or is sung in the wrong key against a fixed-key instrumental. One explicit register per turn allows singing an octave away without that loophole.
- **No unrestricted DTW.** Time-warping would align away exactly the rhythm mistakes the game should catch. Timing is measured against note starts after one fixed latency correction.
- **Scoring in the browser, with a Python reference and shared fixtures.** Phrase ratings must appear instantly without a network round trip, so the browser scores live. The Python engine is the reference the evals test, and `contracts/fixtures/` keeps the TypeScript port from drifting. The fixtures found two real bugs (latency not applied to pitch; excluded regions still costing timing points).
- **Heavy work offline.** Separation and CREPE run once per song; the live path only needs a light tracker and arithmetic.
- **Local pretrained models for pronunciation, no paid API.** Free, offline, and something we can evaluate ourselves. We chose forced alignment over transcription after measuring Whisper's autocorrection.
- **Spoken, not sung, pronunciation.** Speech recognizers are unreliable on singing; practice uses spoken lines and never affects the singing score.
- **Noise robustness by stability, not thresholds alone.** Requiring ~80 ms of steady pitch before counting a note start is what stops random tracker output from earning timing points (noise-only timing: 0).

## What failed or surprised us

- Whisper's language prior silently fixed most single-sound mistakes, which made it unsuitable for pinpointing errors despite near-perfect transcription.
- Normalizing B's word scores against a second TTS rendition did not clearly help (AUC 0.643 → 0.662, top-1 0.54 → 0.46: within noise).
- The browser-style tracker costs a real singer 20+ points at the default 0.8-0.9 clarity thresholds, and our first recommendation (0.8, from clean synthetic voices) was wrong for real voices.
- Tempo drift is penalized harshly (5% slower costs ~30 points) and non-monotonically at extremes, a direct consequence of not time-warping.

## Limitations

- **All results are on synthetic audio.** No real singers or learners have been scored yet; thresholds are placeholders until then.
- No fluent Korean reviewer: pronunciation feedback is automated and word-level, and does not validate accent or phoneme quality.
- The MMS-TTS voice used to generate test speech is licensed CC-BY-NC-4.0. It is used only to create evaluation audio and is not part of the app.
- One register per turn can't fit a group song whose lead jumps between very low and very high parts.

## Next

1. Score ML A's finished manifest for the first real clip and check note-start detection on fast syllables.
2. Record real takes (good, late, off-key) and real spoken phrases (correct and deliberately wrong) to replace synthetic evidence and calibrate thresholds and rating bands.
3. Decide the pitch time tolerance and the 80/20 weighting with that data.
