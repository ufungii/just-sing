# Browser-style tracker vs CREPE reference, real voice (clip-b)

A real 30 s vocal clip (local only). CREPE reference voiced 73% of frames. MPM = our emulation of Pitchy's McLeod Pitch Method. Totals 0-100.
**Limits:** one singer; the 'near-perfect take' is the same stem with mild noise, so same-tracker numbers are an upper bound; phrases are rough; the stem may contain backing vocals.

## 1. MPM clarity threshold (live tracker vs CREPE reference)

| Clarity | Frames voiced | Within 1 semitone (of frames both voiced) | About an octave off | Near-perfect take total |
|---|---|---|---|---|
| 0.9 | 44% | 97% | 3% | 53.6 |
| 0.8 | 62% | 91% | 7% | 68.7 |
| 0.7 | 75% | 87% | 9% | 80.0 |
| 0.6 | 85% | 84% | 11% | 82.6 |
| 0.5 | 91% | 83% | 11% | 83.6 |

## 2. Reference from CREPE vs from the same tracker family as the live one

| Live tracker / reference | near-perfect (30 dB noise) | near-perfect (20 dB noise) | detuned 200 cents | late 0.3 s | noise only | silence |
|---|---|---|---|---|---|---|
| MPM 0.6 vs CREPE reference | 82.6 | 78.9 | 55.5 | 49.9 | 0.0 | 0.0 |
| MPM 0.6 vs MPM 0.6 reference | 96.8 | 91.0 | 61.8 | 44.8 | 0.0 | 0.0 |
| MPM 0.7 vs CREPE reference | 80.0 | 73.9 | 51.5 | 44.5 | 0.0 | 0.0 |
| MPM 0.7 vs MPM 0.7 reference | 96.8 | 87.0 | 59.1 | 43.4 | 0.0 | 0.0 |
| MPM 0.8 vs CREPE reference | 68.7 | 62.6 | 43.5 | 36.5 | 0.0 | 0.0 |
| MPM 0.8 vs MPM 0.8 reference | 98.1 | 87.0 | 57.9 | 41.6 | 0.0 | 0.0 |

## 3. Cleaning the live track (MPM clarity 0.7, CREPE reference)

| Cleanup | Near-perfect (30 dB) | Near-perfect (20 dB) | Detuned 200 cents | Late 0.3 s |
|---|---|---|---|---|
| none | 80.0 | 73.9 | 51.5 | 44.5 |
| fill gaps <= 0.1 s | 79.3 | 73.6 | 51.2 | 45.5 |
| fill gaps <= 0.2 s | 76.9 | 73.1 | 50.9 | 45.6 |
| octave correction | 78.5 | 71.6 | 49.2 | 45.4 |
| octave + gaps 0.1 s | 77.6 | 71.5 | 49.9 | 45.8 |
