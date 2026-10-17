# Comparing two singers' audio directly: does it know which words were sung?

Test set: 73 lyric lines from one full K-pop vocal stem (Demucs output, local only). 46 lines have the same lyric sung elsewhere in the song (often by another member), giving 69 same-lyric pairs vs 2559 different-lyric pairs. No repeat is a copy-pasted recording (waveform correlation of repeats: median 0.04). Each line is turned into features and compared by DTW.

| Features | Same vs different lyric (AUC, 0.5 = chance) | Nearest line has the same lyric (top-1) |
|---|---|---|
| line length only (trivial baseline) | 0.683 | 28% (chance 4%) |
| wav2vec2 layer 6 | 0.795 | 85% (chance 4%) |
| wav2vec2 layer 12 | 0.770 | 80% (chance 4%) |
| wav2vec2 layer 18 | 0.741 | 80% (chance 4%) |
| wav2vec2 posteriorgram | 0.546 | 22% (chance 4%) |
| MFCC (acoustic baseline) | 0.895 | 80% (chance 4%) |

## The control that matters: same tune, different words

In the game the player always sings the same tune as the reference, so the real question is whether a method can tell the words apart **when the melody is the same**. Here only pairs whose melodies are as similar as most same-lyric repeats are kept (key-independent pitch-contour DTW at or below the 75th percentile of same-lyric pairs): 52 same-lyric vs 1913 different-lyric pairs.

| Features | Same vs different lyric, same-tune pairs only (AUC) |
|---|---|
| line length only (trivial baseline) | 0.695 |
| melody itself (pitch-contour DTW) | 0.724 |
| wav2vec2 layer 6 | 0.804 |
| wav2vec2 layer 12 | 0.779 |
| wav2vec2 layer 18 | 0.768 |
| wav2vec2 posteriorgram | 0.556 |
| MFCC (acoustic baseline) | 0.914 |

**Limits:** one song, professional singers, stems from Demucs; repeated chorus lines are the easiest case (often sung in the same melody). This tests whether the features carry lyric content across different takes, not whether they can grade a learner's pronunciation. Real player takes are the next test.
