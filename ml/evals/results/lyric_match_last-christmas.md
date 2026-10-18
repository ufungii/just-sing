# Lyric match (shipped scorer): last-christmas

Lines fingerprinted: 67 (lines >= 0.8 s with text). Take offset from melody alignment: -3.98 s, register +0, margin 0.18.

| condition | graded | match | match rate | median gain over own hum | not sung | not covered |
|---|---|---|---|---|---|---|
| take | 9 | 8 | 89% | +0.197 | 0 | 58 |
| original | 67 | 67 | 100% | +0.782 | 0 | 0 |
| aah | 9 | 0 | 0% | -0.004 | 0 | 58 |
| misaligned | 6 | 0 | 0% | +0.009 | 0 | 61 |
| quiet | 0 | 0 | 0% | n/a | 9 | 58 |

Time: fingerprints 6.4 s for 263 s of vocals; scoring the take 3.2 s for 36 s of audio (device as run; the first call includes model loading).

gain = how much closer (cosine distance) the line is to the original than a wordless hum of the same melody; 'match' means gain >= 0.1 and closer than >= 80% of the song's other lines. The margin was picked on these takes (and one real hum), so this table is not an independent test of it. Controls are built from the same take, so they are cleaner than real mistakes; this is evidence, not validation.
