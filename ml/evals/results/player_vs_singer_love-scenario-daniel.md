# Player vs original singer: Love Scenario (Daniel)

54 lyric lines the recording covers, lined up by melody (register -12, agreement 0.63 vs 0.41). Each player line is compared with every original-singer line; the right line should be nearest. Different voices, so recognising the singer cannot help.

| Features | all lines: AUC / top-1 | length-matched: AUC / top-1 | tune-and-length-matched: AUC / top-1 |
|---|---|---|---|
| wav2vec2 layer 6 | 0.98 / 96% | 0.98 / 98% | 0.97 / 93% |
| wav2vec2 layer 12 | 0.99 / 96% | 0.98 / 98% | 0.96 / 93% |
| MFCC (acoustic baseline) | 0.81 / 41% | 0.88 / 74% | 0.91 / 79% |
| player's melody alone (no words) | 0.92 / 67% | 0.92 / 76% | 0.69 / 64% |

Chance top-1 (one right line among the allowed candidates): all lines ~4%, length-matched ~22%, tune-and-length-matched ~87%.
**Limits:** one singer, one song, a phone recording, an unreviewed reference. The right line always shares the player's tune and length; the matched controls reduce that advantage but cannot remove it completely.
