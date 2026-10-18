# Singing score specification (for the TypeScript port)

The browser must rate phrases live with exactly the same math as the Python reference in `ml/scoring/`. This page is the language-neutral spec; `contracts/fixtures/` holds the test cases both implementations must pass. If this page and the Python code ever disagree, the code plus fixtures win: tell ML B.

Scoring version: `0.4.0` (`SCORING_VERSION` in `ml/scoring/config.py`). Any change that can change a score bumps it and regenerates the fixtures.

## 1. Inputs and conventions

- **Pitch track:** an array of Hz values, one per frame. Frame `i` is at time `i * hop` seconds from the clip start. `hop = 0.02`.
- **Unvoiced:** `null`, non-finite, or `<= 0` all mean unvoiced. Normalize these first.
- **Reference:** `ref_hz` from the manifest (`reference.hz`), plus `phrases` (`id`, `start`, `end`), `excluded` (`start`, `end`), and the reference note starts `ref_onsets` (seconds).
- **Player:** `user_hz` from Pitchy at the same hop (resample or bucket your tracker output to 20 ms frames).
- **Settings for a turn:** `register` in semitones (`-12`, `0`, or `12`) and `latency_offset_s` (measured once in the setup step).
- `round(x)` below means round to the nearest integer, **ties to the nearest even integer** (Python's `round`; implement a `roundHalfEven` helper, because JavaScript's `Math.round` rounds ties up). Ties do occur: a phrase boundary of `x.5` frames is common. The first TypeScript port shifted frame indices by one because of this.

## 2. Config (defaults)

| Name | Value | Meaning |
|---|---|---|
| `full_credit_cents` | 50 | pitch error with full credit |
| `zero_credit_cents` | 200 | pitch error where credit reaches 0 |
| `time_tolerance_s` | 0.1 | the player's track may be shifted up to this much, earlier or later, **once per phrase** (0 = strict). Section 4. |
| `full_credit_s` | 0.10 | timing offset with full credit |
| `zero_credit_s` | 0.40 | timing offset where credit reaches 0 |
| `match_window_s` | 0.50 | max distance to match a note start |
| `stable_frames` | 4 | frames of steady pitch needed for a note start |
| `stable_cents` | 60 | "steady" means within this of the window median |
| `min_onset_gap_s` | 0.12 | note starts closer than this are merged |
| `pitch_weight`, `timing_weight` | 0.8, 0.2 | phrase score blend |
| `perfect`, `great`, `okay` | 80, 65, 40 | rating bands on the phrase score (0.3.0, from `ml/evals/band_calibration.py`) |
| `min_coverage` | 0.25 | below this, the phrase is `miss` |

## 3. Preparing the player track

1. **Latency:** `n = round(latency_offset_s / hop)`. If `n > 0`, drop the first `n` frames of `user_hz` and append `n` unvoiced frames at the end. Do this **once**; both pitch and timing use the corrected track.
2. **Length (pitch only):** make a copy padded with unvoiced frames or truncated to `len(ref_hz) + k`, where `k = round(time_tolerance_s / hop)` (the `k` extra frames let a shift reach the tail of a late take). Timing uses the corrected track at its full length.

Keep recording about 0.5 s past the clip end, so step 1 doesn't cut off the last note.

## 4. Pitch

**Scoreable mask:** `mask[i] = ref voiced at i`. Then for each excluded `(start, end)`, set `mask[i] = false` for `i` in `[round(start / hop), round(end / hop))` (clamped at 0).

**Target:** `target[i] = ref_hz[i] * 2^(register / 12)`.

**Frame credit:** for a voiced user value `u` and target `t`:
```
err    = 1200 * log2(u / t)
credit = clamp((zero_credit_cents - |err|) / (zero_credit_cents - full_credit_cents), 0, 1)
```

**With time tolerance:** `k = round(time_tolerance_s / hop)`. For every shift `off` in `[-k, k]`, build the shifted user track `shifted_off[i] = user[i + off]` (outside the array = unvoiced) and compute `credit_off[i]` and `voiced_off[i]` for every frame as above.

**Choose ONE shift per span** (see "For a span of frames" below): the `off` that maximizes the sum of `credit_off[i]` over the span's scoreable frames; ties keep the smallest `|off|`, then the negative one. That span then uses `credit_off` and `voiced_off` for its `credit_sum` and `voiced`.

Why one shift and not the best frame at each position: picking the luckiest frame everywhere lets a jittery or sweeping pitch track earn credit by chance (random pitches scored 42 under that rule). One consistent shift forgives a consistent lateness of up to `time_tolerance_s`, which the timing score still measures, and nothing else.

With `k = 0` this is simply frame `i` against frame `i`.

**For a span of frames** (a phrase: `[round(start / hop), round(end / hop))`), counting only frames where `mask` is true:
- `credit_sum` = sum of `credit`
- `scoreable` = count of frames
- `voiced` = count of frames where `user_voiced`
- `pitch = 100 * credit_sum / scoreable` and `coverage = voiced / scoreable` (both 0 if `scoreable == 0`)

## 5. Note starts (onsets)

Used on the player's corrected track (full length). The reference note starts come from the manifest, or from the same function run on `ref_hz`.

```
L = stable_frames
stable[i] = frames i .. i+L-1 all voiced
            AND max over w in that window of |1200 * log2(w / median(window))| <= stable_cents
            (stable[i] = false for i > n - L)
```
**Median of 4 values is the mean of the two middle values** (sort, then average elements 1 and 2). This detail matters for parity.

```
gap = round(min_onset_gap_s / hop)
onsets = []
for i in 0 .. n-1:
    if stable[i] and (i == 0 or not stable[i-1]):
        if onsets is empty or i - last(onsets) >= gap:
            append i
onset times = onsets * hop
```

## 6. Timing

1. Drop reference onsets inside any excluded region (`start <= t < end`).
2. For a phrase, take the reference onsets with `start <= t < end`, in ascending order. `n_ref` = how many.
3. Player onsets `U` = onset times of the corrected player track.
4. Greedy matching, one player onset per reference onset:
```
used = all false
for each reference onset r (ascending):
    among unused U[j], pick the one with the smallest |U[j] - r| (ties: lowest j)
    if none, or that distance > match_window_s: no match, continue
    mark it used; d = U[j] - r   (+ is late)
    credit_sum += clamp((zero_credit_s - |d|) / (zero_credit_s - full_credit_s), 0, 1)
```
5. `timing = 100 * credit_sum / n_ref`. **If `n_ref == 0`, timing is `null`** for that phrase (it starts mid-note).

## 7. Phrase result and rating

```
score = pitch_weight * pitch + timing_weight * timing     (unrounded values)
      = pitch                                             if timing is null
rating = "miss"     if coverage < min_coverage
         "perfect"  if score >= perfect
         "great"    if score >= great
         "okay"     if score >= okay
         "bad"      otherwise
```
Rate with the **unrounded** score and coverage. Then report `pitch`, `timing`, and `score` rounded to 1 decimal, and `coverage` to 3 decimals. Rating ids are lowercase; the UI shows "Perfect!", "Great", and so on.

## 8. Totals

Weight of a phrase = its `scoreable` frame count from section 4.
```
total  = sum(w * score_rounded)  / sum(w)    over phrases with w > 0
pitch  = sum(w * pitch_rounded)  / sum(w)    over phrases with w > 0
timing = sum(w * timing_rounded) / sum(w)    over phrases with w > 0 and timing not null
```
Each is 0 if its weight sum is 0. Round to 1 decimal. Totals use the **rounded** phrase values, so the total always agrees with the badges the player saw.

## 8b. Lyric check in the turn total (0.4.0)

`pronunciation_score(statuses, line_weights)`: the lyric check gives each fingerprinted line a status. Credit is `match` 100, `unclear` 0, `not_sung` 0 (humming is graded `unclear`, so it earns nothing); `not_covered` and unknown statuses are left out. Line weight = sum of its phrases' scoreable frames (`line_weights`). The value is the weighted mean, rounded to 1 decimal, or `null` if nothing was checked.

`apply_pronunciation(score, p)`: with `p` not null, `total = round((0.7*pitch + 0.1*timing + 0.2*p) * (0.5 + 0.5*p/100), 1)` using the aggregate pitch and timing from section 8 (pitch stands in for timing when no phrase has an onset). With `p` null the section 8 total is kept (the check was unavailable; never a low score). Phrase scores and ratings are unchanged. All values live in `PronunciationConfig`; they are unvalidated starting defaults and the lyric check has not been measured on sung audio or reviewed by a fluent speaker. Fixtures: `contracts/fixtures/pronunciation_cases.json`.

## 9. Testing against the fixtures

- `contracts/fixtures/score_cases.json`: `{tolerance, cases: [{name, description, input, expected}]}`. The `input` has `hop_seconds`, `ref_hz`, `user_hz`, `ref_onsets`, `phrases` (`[id, start, end]`), `register`, `latency_offset_s`, `excluded`. The `expected` output has `total`, `pitch`, `timing`, and `phrases`, each with `phrase_id`, `pitch`, `timing`, `score`, `coverage`, and `rating`. Every number must match within `tolerance` (0.1), and ratings must match exactly.
- `contracts/fixtures/onset_cases.json`: `{tolerance_s, cases: [{name, input: {hop_seconds, hz}, expected_onsets}]}`.
- Regenerate after any scoring change: `python -m ml.evals.make_fixtures`.

## 10. What the server does

The browser submits each phrase's `phrase_id`, `pitch`, `timing` and `coverage`. The API calls `finalize_turn`, which ignores any client-claimed `score` or `rating` and recomputes sections 7 and 8 using weights from its own copy of the manifest. Recomputed phrase scores can differ from the browser's by about 0.1, because the submitted inputs are rounded.

## 11. Display-only word activity

See [WORD_FEEDBACK.md](WORD_FEEDBACK.md) for the independent word-activity contract,
version 1.0.0, and `contracts/fixtures/word_feedback.json` for shared Python/TypeScript
cases. This does not modify the scoring rubric above or scoring version 0.3.0.
