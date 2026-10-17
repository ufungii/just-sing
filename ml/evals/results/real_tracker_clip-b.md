# Browser-style tracker vs CREPE reference, real voice (clip-b)

A real 30 s vocal clip (local only). CREPE reference voiced 73% of frames. MPM = our emulation of Pitchy's McLeod Pitch Method. Totals 0-100.
**Limits:** one singer; the 'near-perfect take' is the same stem with mild noise, so same-tracker numbers are an upper bound; phrases are rough; the stem may contain backing vocals.

## 1. MPM clarity threshold (live tracker vs CREPE reference)

| Clarity | Frames voiced | Within 1 semitone (of frames both voiced) | About an octave off | Near-perfect take total |
|---|---|---|---|---|
| 0.9 | 44% | 96% | 3% | 53.4 |
| 0.8 | 62% | 91% | 7% | 68.6 |
| 0.7 | 75% | 87% | 9% | 79.8 |
| 0.6 | 85% | 84% | 11% | 82.7 |
| 0.5 | 91% | 83% | 11% | 83.8 |

## 2. Reference from CREPE vs from the same tracker family as the live one

| Live tracker / reference | near-perfect (30 dB noise) | near-perfect (20 dB noise) | detuned 200 cents | late 0.3 s | noise only | silence |
|---|---|---|---|---|---|---|
| MPM 0.6 vs CREPE reference | 82.7 | 79.1 | 55.7 | 58.2 | 0.0 | 0.0 |
| MPM 0.6 vs MPM 0.6 reference | 96.8 | 91.0 | 61.8 | 52.6 | 0.0 | 0.0 |
| MPM 0.7 vs CREPE reference | 79.8 | 73.9 | 51.5 | 52.7 | 0.0 | 0.0 |
| MPM 0.7 vs MPM 0.7 reference | 96.8 | 87.0 | 59.1 | 52.7 | 0.0 | 0.0 |
| MPM 0.8 vs CREPE reference | 68.6 | 62.7 | 43.4 | 44.4 | 0.0 | 0.0 |
| MPM 0.8 vs MPM 0.8 reference | 98.1 | 87.0 | 57.9 | 50.7 | 0.0 | 0.0 |

## 3. Cleaning the live track (MPM clarity 0.7, CREPE reference)

| Cleanup | Near-perfect (30 dB) | Near-perfect (20 dB) | Detuned 200 cents | Late 0.3 s |
|---|---|---|---|---|
| none | 79.8 | 73.9 | 51.5 | 52.7 |
| fill gaps <= 0.1 s | 79.3 | 73.8 | 51.3 | 54.2 |
| fill gaps <= 0.2 s | 77.0 | 73.4 | 51.0 | 54.3 |
| octave correction | 78.2 | 71.7 | 49.1 | 53.1 |
| octave + gaps 0.1 s | 77.5 | 71.8 | 49.9 | 53.7 |
