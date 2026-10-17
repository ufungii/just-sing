# Emulation vs the real Pitchy

Same audio, same settings: `ml/evals/mpm.py` (our emulation) vs pitchy@4.1.0 run in Node (`ml/evals/node/pitchy_track.mjs`). 'Perfect take' = the clip's own vocal scored against its manifest reference (CREPE-made), so it measures tracker disagreement, not singing.

| Clip | Setting | Voiced (real / emulated) | Voicing agreement | Pitch within 1 semitone | Perfect take: real / emulated |
|---|---|---|---|---|---|
| Clip 1 | live demo setting: 48 kHz, 4096, clarity 0.8, gate 0.008 | 30% / 31% | 97% | 100% | 41.6 / 43.0 |
| Clip 1 | 48 kHz, 4096, clarity 0.65, gate 0.005 | 46% / 50% | 91% | 100% | 63.0 / 69.6 |
| Clip 1 | 16 kHz, 2048, clarity 0.8, gate 0.001 | 28% / 29% | 97% | 100% | 37.3 / 37.8 |
| Clip 2 | live demo setting: 48 kHz, 4096, clarity 0.8, gate 0.008 | 53% / 53% | 100% | 100% | 55.1 / 55.2 |
| Clip 2 | 48 kHz, 4096, clarity 0.65, gate 0.005 | 66% / 67% | 98% | 100% | 67.0 / 68.5 |
| Clip 2 | 16 kHz, 2048, clarity 0.8, gate 0.001 | 52% / 52% | 100% | 100% | 52.9 / 52.9 |
| Clip 3 | live demo setting: 48 kHz, 4096, clarity 0.8, gate 0.008 | 20% / 21% | 95% | 99% | 35.3 / 36.6 |
| Clip 3 | 48 kHz, 4096, clarity 0.65, gate 0.005 | 38% / 43% | 89% | 99% | 50.8 / 55.9 |
| Clip 3 | 16 kHz, 2048, clarity 0.8, gate 0.001 | 23% / 24% | 97% | 100% | 39.0 / 39.1 |
