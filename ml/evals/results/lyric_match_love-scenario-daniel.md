# Lyric match (shipped scorer): love-scenario-daniel

Lines fingerprinted: 54 (lines >= 0.8 s with text). Take offset from melody alignment: 4.54 s, register -12, margin 0.23.

| condition | graded | match | match rate | median gain over own hum | not sung | not covered |
|---|---|---|---|---|---|---|
| take | 54 | 52 | 96% | +0.177 | 0 | 0 |
| original | 54 | 54 | 100% | +0.784 | 0 | 0 |
| aah | 54 | 0 | 0% | +0.002 | 0 | 0 |
| misaligned | 53 | 4 | 8% | +0.029 | 1 | 0 |
| quiet | 0 | 0 | 0% | n/a | 54 | 0 |

Time: fingerprints 5.5 s for 230 s of vocals; scoring the take 28.9 s for 226 s of audio (device as run; the first call includes model loading).

gain = how much closer (cosine distance) the line is to the original than a wordless hum of the same melody; 'match' means gain >= 0.06 and closer than >= 80% of the song's other lines. The 0.06 margin was picked on these takes, so this table is not an independent test of it. Controls are built from the same take, so they are cleaner than real mistakes; this is evidence, not validation.
