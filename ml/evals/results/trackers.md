# Pitch trackers: do the browser and the reference agree?

Synthetic singer with known pitch (3 seeds per row). Reference = CREPE on a separate clean rendition, as the offline pipeline would build it. `mpm` is our Python reimplementation of the McLeod Pitch Method that Pitchy uses in the browser (an emulation, not Pitchy's exact code).
**Limits:** synthetic voices only.

## 1. Accuracy against the ground truth

| Take | Tracker | Score vs truth | Voicing recall | False voicing | Median error (cents) | Errors > 100 cents |
|---|---|---|---|---|---|---|
| clean | pyin | 97.6 | 1.00 | 0.26 | 9.2 | 0.021 |
| clean | crepe | 97.6 | 1.00 | 0.14 | 7.3 | 0.025 |
| clean | mpm | 91.6 | 0.92 | 0.20 | 5.8 | 0.007 |
| noise 20 dB | pyin | 97.6 | 1.00 | 0.20 | 9.2 | 0.021 |
| noise 20 dB | crepe | 97.5 | 1.00 | 0.12 | 7.2 | 0.025 |
| noise 20 dB | mpm | 90.7 | 0.92 | 0.12 | 5.8 | 0.007 |
| noise 10 dB | pyin | 97.5 | 0.99 | 0.20 | 9.2 | 0.017 |
| noise 10 dB | crepe | 97.5 | 1.00 | 0.12 | 8.0 | 0.025 |
| noise 10 dB | mpm | 84.0 | 0.84 | 0.00 | 5.5 | 0.000 |
| noise 5 dB | pyin | 96.5 | 0.98 | 0.19 | 9.2 | 0.013 |
| noise 5 dB | crepe | 97.4 | 1.00 | 0.12 | 7.5 | 0.023 |
| noise 5 dB | mpm | 0.0 | 0.00 | 0.00 | nan | nan |
| detuned 100 cents | pyin | 64.8 | 0.99 | 0.28 | 100.3 | 0.510 |
| detuned 100 cents | crepe | 65.3 | 1.00 | 0.15 | 100.1 | 0.505 |
| detuned 100 cents | mpm | 61.2 | 0.94 | 0.20 | 100.4 | 0.516 |
| late 0.2 s | pyin | 74.2 | 0.96 | 0.50 | 9.2 | 0.229 |
| late 0.2 s | crepe | 72.5 | 0.95 | 0.44 | 9.8 | 0.245 |
| late 0.2 s | mpm | 69.2 | 0.88 | 0.46 | 6.7 | 0.215 |

## 2. The live-game pairing (total score)

| Take | CREPE ref vs CREPE player | CREPE ref vs MPM player (live game) | Cost of mismatch |
|---|---|---|---|
| clean | 99.6 | 93.4 | +6.1 |
| noise 20 dB | 99.3 | 92.5 | +6.8 |
| noise 10 dB | 99.3 | 86.3 | +13.0 |
| noise 5 dB | 99.2 | 0.0 | +99.2 |
| detuned 100 cents | 71.6 | 68.1 | +3.4 |
| late 0.2 s | 70.0 | 66.6 | +3.4 |

## 3. MPM clarity threshold (frontend setting), total score

| Clarity threshold | Clean take | Take with 10 dB noise | Noise only, no voice |
|---|---|---|---|
| 0.7 | 97.3 | 96.4 | 0.0 |
| 0.8 | 96.2 | 92.9 | 0.0 |
| 0.9 | 93.4 | 86.3 | 0.0 |
| 0.95 | 91.3 | 0.0 | 0.0 |
