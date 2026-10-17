# Emulation vs the real Pitchy

Same audio, same settings: `ml/evals/mpm.py` (our emulation) vs pitchy@4.1.0 run in Node (`ml/evals/node/pitchy_track.mjs`). 'Perfect take' = the clip's own vocal scored against its manifest reference (CREPE-made), so it measures tracker disagreement, not singing.

| Clip | Setting | Voiced (real / emulated) | Voicing agreement | Pitch within 1 semitone | Perfect take: real / emulated | Real, browser-smoothed |
|---|---|---|---|---|---|---|
| Clip 1 | live demo setting: 48 kHz, 4096, clarity 0.8, gate 0.008 | 42% / 42% | 99% | 100% | 52.8 / 53.3 | 53.0 |
| Clip 1 | 48 kHz, 4096, clarity 0.65, gate 0.005 | 58% / 62% | 94% | 99% | 70.5 / 74.9 | 71.1 |
| Clip 1 | 16 kHz, 2048, clarity 0.8, gate 0.001 | 42% / 42% | 98% | 100% | 51.9 / 52.4 | 52.1 |
| Clip 2 | live demo setting: 48 kHz, 4096, clarity 0.8, gate 0.008 | 48% / 49% | 99% | 100% | 60.0 / 60.7 | 60.0 |
| Clip 2 | 48 kHz, 4096, clarity 0.65, gate 0.005 | 63% / 67% | 95% | 99% | 75.8 / 79.5 | 75.9 |
| Clip 2 | 16 kHz, 2048, clarity 0.8, gate 0.001 | 45% / 46% | 99% | 100% | 54.7 / 54.9 | 54.6 |
| Clip 3 | live demo setting: 48 kHz, 4096, clarity 0.8, gate 0.008 | 28% / 29% | 95% | 99% | 46.4 / 47.0 | 46.6 |
| Clip 3 | 48 kHz, 4096, clarity 0.65, gate 0.005 | 42% / 47% | 90% | 99% | 61.8 / 64.7 | 61.9 |
| Clip 3 | 16 kHz, 2048, clarity 0.8, gate 0.001 | 32% / 33% | 96% | 100% | 50.4 / 50.6 | 50.1 |
