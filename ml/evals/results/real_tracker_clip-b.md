# Browser-style tracker vs CREPE reference, real voice (clip-b)

A real 30 s vocal clip (local only). CREPE reference voiced 82% of frames. MPM = our emulation of Pitchy's McLeod Pitch Method. Totals 0-100.
**Limits:** one singer; the 'near-perfect take' is the same stem with mild noise, so same-tracker numbers are an upper bound; phrases are rough; the stem may contain backing vocals.

## 1. MPM clarity threshold (live tracker vs CREPE reference)

| Clarity | Frames voiced | Within 1 semitone (of frames both voiced) | About an octave off | Near-perfect take total |
|---|---|---|---|---|
| 0.9 | 44% | 96% | 3% | 46.9 |
| 0.8 | 62% | 90% | 7% | 61.1 |
| 0.7 | 75% | 86% | 10% | 72.7 |
| 0.6 | 85% | 83% | 11% | 77.3 |
| 0.5 | 91% | 82% | 12% | 81.8 |

## 2. Reference from CREPE vs from the same tracker family as the live one

| Live tracker / reference | near-perfect (30 dB noise) | near-perfect (20 dB noise) | detuned 200 cents | late 0.3 s | noise only | silence |
|---|---|---|---|---|---|---|
| MPM 0.6 vs CREPE reference | 77.3 | 72.7 | 54.1 | 45.9 | 0.0 | 0.0 |
| MPM 0.6 vs MPM 0.6 reference | 95.6 | 89.3 | 60.3 | 42.1 | 0.0 | 0.0 |
| MPM 0.7 vs CREPE reference | 72.7 | 66.2 | 49.3 | 43.3 | 0.0 | 0.0 |
| MPM 0.7 vs MPM 0.7 reference | 95.8 | 85.8 | 58.1 | 39.4 | 0.0 | 0.0 |
| MPM 0.8 vs CREPE reference | 61.1 | 54.9 | 37.9 | 37.0 | 0.0 | 0.0 |
| MPM 0.8 vs MPM 0.8 reference | 97.8 | 86.4 | 57.3 | 39.1 | 0.0 | 0.0 |

## 3. Cleaning the live track (MPM clarity 0.7, CREPE reference)

| Cleanup | Near-perfect (30 dB) | Near-perfect (20 dB) | Detuned 200 cents | Late 0.3 s |
|---|---|---|---|---|
| none | 72.7 | 66.2 | 49.3 | 43.3 |
| fill gaps <= 0.1 s | 74.3 | 67.4 | 50.3 | 43.8 |
| fill gaps <= 0.2 s | 72.9 | 66.7 | 50.2 | 44.0 |
| octave correction | 72.4 | 65.5 | 47.7 | 43.7 |
| octave + gaps 0.1 s | 74.1 | 67.2 | 48.6 | 43.6 |
