# Per-word singing activity, version 1.0.0

ML implementation: `ml.scoring.words.word_feedback`. This is display-only feedback for
option 1. It does not alter phrase ratings, total scores, API submissions, or scoring
version 0.2.0. It uses no speech model, extra dependency, or raw audio upload.

It measures detected singing during a word's scheduled window. It cannot tell whether
the player said that word, pronounced it correctly, or hummed. Never label it word
accuracy or pronunciation. Thresholds are provisional, not validated on player takes.

## Inputs and algorithm

Pass the raw player track and **unshifted** reference track in Hz at the same hop
(default 0.02 s), plus manifest `lines`. Track frames must already be gated for pitch
confidence and microphone level. Null, nonfinite and nonpositive values are unvoiced.
Do not pass a register-shifted target or an already latency-corrected track.

1. Subtract the single measured device latency: drop `round(latency / hop)` player
   frames, pad with unvoiced, then truncate/pad to the reference length. No take-fitted
   offset or search through neighboring frames. Register is -12, 0, or 12.
2. Scoreable frames have positive finite reference Hz and lie outside every excluded
   interval. Quantize word/exclusion boundaries using Python round (ties to even),
   use half-open `[start, end)` frame spans, clamp to track bounds.
3. Coverage = voiced player frames / scoreable reference frames **inside that word**.
   Default status is `sung` at >= 0.5, `partly` at >= 0.2, otherwise `missed`. Classify
   before rounding. These names are activity bands, not recognized-word judgments.
4. Pitch = mean frame credit * 100 over those same frames, silence included as zero.
   Shift the reference by the chosen register. Full credit within 50 cents, linear
   drop to zero at 200 cents (the shared `PitchConfig` defaults). Pitch time tolerance
   is deliberately unused: a neighboring voiced frame cannot fill a dropped word.
5. `onset_delay_s` = (first voiced scoreable frame - first scoreable frame) * hop.
   `late` is true when delay > 0.12 s (comparison epsilon 1e-12 s). It is independent
   of coverage status, so a partly sung word can also have a late detected start.
   Without any player voice, both fields are null. During continuous singing, these
   values cannot detect a word boundary, consonant onset, or a delayed syllable.
6. A word with no scoreable frames is `not_graded`; all measurements are null.
   Missing `words` yields an empty row, not manufactured word timing. Preserve line
   and word order. Coverage/delay use 3 decimal places; pitch uses 1.

Example output (one row per manifest line):

```json
[[{"text":"hello","start":0,"end":1,"status":"sung","coverage":0.8,
   "pitch":80.0,"onset_delay_s":0.2,"late":true}]]
```

Version this display feedback separately through `WORD_FEEDBACK_VERSION`. Do not
add it to the persisted score contract without team agreement. The additive shared
fixture is `contracts/fixtures/word_feedback.json`; regenerate with
`python -m ml.evals.make_word_fixtures`.

## Frontend handoff

From the repo root, apply the additive patch (only adds `web/src/scoring/words.ts`):

```sh
git apply --check ml/scoring/ts_word_feedback.patch
git apply ml/scoring/ts_word_feedback.patch
node ml/evals/node/word_feedback_parity.mjs web/src/scoring/words.ts contracts/fixtures/word_feedback.json
```

The TS implementation is independent of the older browser scoring port and has no
imports or model dependencies. It accepts one object with the Python parameter names
(`user_hz`, `ref_hz`, `lines`, `hop_seconds`, `register`, `excluded` as `[start,end]`
pairs, `latency_offset_s`). `wordFeedback(input)` returns the same nested rows.
Parity runner requires Node 24+ (native TypeScript stripping).

Frontend wiring remains frontend-owned and is not included in this patch:

- At turn completion, while raw frames and the manifest are available, compute
  feedback once and carry the derived rows through `SingResult` to Results. Keep
  audio/tracks session-local; server score submission remains unchanged.
- Highlight missed/partial word windows, mark late detected starts, and show pitch
  separately. Use text labels as well as color. Render ungraded words neutrally.
- Label the panel **Singing activity** and explain: “Detected singing during each
  word's timing window; doesn't check which words you said.” Avoid “you dropped
  this word”; use “little/no singing detected here.”
- If the mic failed or no reliable track was captured, show a capture recovery state
  instead of treating this as bad singing. The pure function cannot diagnose mic
  failure from an all-null track. Omit the panel for historical/demo results without
  derived word feedback; don't manufacture misses.

Do not apply the older `ts_port_0.2.0.patch` blindly to this checkout: browser files
here differ from the branches that patch was prepared for. That port is separate
work and isn't a prerequisite for this standalone word helper.

## Testing and recordings

`python -m pytest ml/scoring/tests/test_words.py` checks targeted behavior and applies
the TS patch in a temporary directory to run all 21 shared fixtures with Node.
These are controlled track tests, not validation on singers or audio models.

`python -m ml.evals.score_take take.wav clip.json --latency 0.16` now prints word
activity in addition to scores, and `score_take()` returns `word_feedback` and
`word_feedback_version`. Use reviewed word timings and the measured device offset;
don't fit latency to each take. Check good singing, one skipped window, deliberately
late entrances, wrong notes, humming, and silence. Record observed false flags before
calibrating thresholds. Humming is expected to register as singing activity.

## Option 2: research gate

Reference-vs-player speech embeddings are not implemented here. Existing sung-lyric
evaluations (`ml/evals/results/sung_lyrics.md`) tested ASR/forced alignment, not this
embedding method; they cannot establish whether embedding similarity will work.
A metric could reward matching pitch, timing, singer identity, or recording conditions
rather than words. Reliable development needs actual player takes with matched,
wrong/skipped-word and hummed controls, a specific pretrained feature extractor with
checked license/runtime, and an eval that separates those controls while allowing
legitimate register/voice differences. Until then there is no evidence-backed model
choice or threshold to ship. This feature makes no embedding-based claims.
