# Player vs original singer: Last Christmas (36 s, partly clipped)

9 lyric lines the recording covers, lined up by melody (register +0, agreement 0.52 vs 0.34). Each player line is compared with every original-singer line; the right line should be nearest. Different voices, so recognising the singer cannot help.

| Features | all lines: AUC / top-1 | length-matched: AUC / top-1 | tune-and-length-matched: AUC / top-1 |
|---|---|---|---|
| wav2vec2 layer 6 | 0.99 / 100% | 0.99 / 100% | nan / 0% |
| wav2vec2 layer 12 | 1.00 / 100% | 0.98 / 100% | nan / 0% |
| MFCC (acoustic baseline) | 0.93 / 89% | 0.97 / 100% | nan / 0% |
| player's melody alone (no words) | 0.80 / 33% | 0.59 / 43% | nan / 0% |

Chance top-1 (one right line among the allowed candidates): all lines ~16%, length-matched ~53%, tune-and-length-matched ~100%.
**Limits:** one singer, one song, a phone recording, an unreviewed reference. The right line always shares the player's tune and length; the matched controls reduce that advantage but cannot remove it completely.
