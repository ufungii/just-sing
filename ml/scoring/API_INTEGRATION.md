# Plugging ml/scoring and ml/pronunciation into the API

`api/README.md` leaves two hooks for ML: the scoring stand-in in `api/play.py` and the pronunciation `scorer` in `api/practice.py`. This page says how to fill both. `api_integration.patch` (same folder) is the tested change for the first; it applies cleanly to `origin/main` with `git apply -p1 ml/scoring/api_integration.patch`.

## 1. Scoring: replace the stand-in in `play.py`

What the stand-in does today and how the engine differs:

| | Stand-in | `finalize_turn` |
|---|---|---|
| Phrase weights | phrase duration (`end - start`) | **scoreable reference frames** (rests and excluded regions earn no weight) |
| Total | `0.8 * mean(pitch) + 0.2 * mean(timing)` | weighted mean of the **phrase scores** (so the total always agrees with the badges) |
| Ratings | stored as the client sent them | **recomputed** from the measured pitch, timing and coverage |
| Validation | phrase ids only | ids, ranges, finite numbers, register, a clip with nothing scoreable |
| `timing: null` (phrase starts mid-note) | crashes (`None * float`) | handled: the phrase is scored on pitch alone |

The patch:
- imports `SCORING_VERSION` from `ml.scoring.config`, so the version has one source of truth (delete the constant in `play.py`);
- caches `phrase_weights(...)` per clip, computed from the **server's own** manifest, never from the client;
- calls `finalize_turn(...)` and maps its `ValueError` to a 422 `invalid_result`;
- makes `PhraseScore.timing` nullable and adds `PhraseScore.score` (the contract's phrase `score`);
- adds `numpy` to `api/requirements.txt` (`ml/scoring` needs it; without it the import fails).

`ml` must be importable: run from the repo root, as the README already says.

**Not tested here:** the DB-backed `submit_result` path (no Postgres on the machine that built the patch). Verified instead, against the real catalog objects and models: weights computed from the manifest, a null-timing phrase, the result validating as `api.models.Score`, and the existing non-DB API tests still passing. Run `pytest api` with `DATABASE_URL` set before merging.

## 2. Pronunciation: attach the scorer at startup

```python
from ml.pronunciation.api_scorer import PronunciationScorer
import api.practice
api.practice.scorer = PronunciationScorer()   # needs the speech env (PyTorch); do it at startup, not import
```
- It returns `[{"text", "score"}]` (0-100) and **raises** when the assessment fails, which the API turns into `status: "error"`. Words the model can't score (English letters) are omitted rather than faked.
- Run it in the speech environment (`ml/pronunciation/requirements.txt`); the rest of the API stays PyTorch-free.
- Scores are raw model confidence: correct speech averages 60-70, not 100. The UI should highlight the lowest-scoring words instead of showing the number as a grade.
- The first call loads the models (~30 s on the first run). Warm it up at startup with a short silent clip, or the first learner waits.

## 3. A real demo clip

`contracts/fixtures/synthetic-demo.manifest.json` is a complete synthetic clip (30 s, 6 phrases, a real reference contour, original generic practice lines). It passes `ml/evals/inspect_reference.py` with no warnings and the API's `Song` model, and works as `api/catalog/synthetic-demo/manifest.json` (the current one has a 3-frame contour, so every phrase has weight 0). Regenerate with `python -m ml.evals.make_demo_manifest`. It has no audio; the frontend can play any placeholder track, or a real instrumental from ML A, over it.
