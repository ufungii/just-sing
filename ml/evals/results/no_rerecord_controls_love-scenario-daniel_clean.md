# Controls without re-recording: Love Scenario (Daniel)

54 sung lines (register -12). Features: wav2vec2 layer 6 + DTW against the original vocal stem.

## 1. Same tune, no words

| Player audio | All lines: AUC / top-1 | Length-matched: AUC / top-1 |
|---|---|---|
| real singing | 0.98 / 96% | 0.98 / 98% |
| resynthesised "aah" (same pitch + loudness, no words) | 0.84 / 31% | 0.86 / 56% |

If the "aah" version still finds the right line, tune and rhythm explain the result; a large drop means the words matter.

## 2. One wrong word

36 lines with one word replaced by a pitch- and length-matched word from elsewhere in the same take.

- The replaced word has the highest alignment cost (flagged) in **29/36 = 81%** of lines; the same word is flagged in the unedited line 14/36 = 39% of the time; chance ~35%.
- **Artifact-only control** (the line's own word put through the same pitch-shift/stretch/crossfade, right words): flagged 30/36 = 83%. The gap between this and the wrong-word rate is the part explained by the words, not the edit.
- The line's overall cost rises by 0.0611 on average (median 0.0492).
- **Fair control (clean mode):** on the 19 lines where the same word was also sung elsewhere at the same note and length, splicing in a WRONG word gets it flagged 16/19, splicing in the RIGHT word (same kind of cut) 10/19. Only this gap is evidence that the words, not the cut, are detected.

**Limits:** artificial edits on one take; a spliced word can carry splice artifacts that a real mistake would not. Real wrong-word takes remain the true test.
