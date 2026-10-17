# Controls without re-recording: Love Scenario (Daniel)

54 sung lines (register -12). Features: wav2vec2 layer 6 + DTW against the original vocal stem.

## 1. Same tune, no words

| Player audio | All lines: AUC / top-1 | Length-matched: AUC / top-1 |
|---|---|---|
| real singing | 0.98 / 96% | 0.98 / 98% |
| resynthesised "aah" (same pitch + loudness, no words) | 0.84 / 31% | 0.86 / 54% |

If the "aah" version still finds the right line, tune and rhythm explain the result; a large drop means the words matter.

## 2. One wrong word

48 lines with one word replaced by a pitch- and length-matched word from elsewhere in the same take.

- The replaced word has the highest alignment cost (flagged) in **42/48 = 88%** of lines; the same word is flagged in the unedited line 18/48 = 38% of the time; chance ~33%.
- **Artifact-only control** (the line's own word put through the same pitch-shift/stretch/crossfade, right words): flagged 40/48 = 83%. The gap between this and the wrong-word rate is the part explained by the words, not the edit.
- The line's overall cost rises by 0.0705 on average (median 0.0540).

**Limits:** artificial edits on one take; a spliced word can carry splice artifacts that a real mistake would not. Real wrong-word takes remain the true test.
