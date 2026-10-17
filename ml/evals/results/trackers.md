# Pitch trackers: do the browser and the reference agree?

Synthetic singer with known pitch (3 seeds per row). Reference = CREPE on a separate clean rendition, as the offline pipeline would build it. `mpm` is our Python reimplementation of the McLeod Pitch Method that Pitchy uses in the browser (an emulation, not Pitchy's exact code).
**Limits:** synthetic voices only.

## 1. Accuracy against the ground truth

| Take | Tracker | Score vs truth | Voicing recall | False voicing | Median error (cents) | Errors > 100 cents |
|---|---|---|---|---|---|---|
| clean | pyin | 98.1 | 1.00 | 0.12 | 9.2 | 0.021 |
| clean | crepe | 97.3 | 0.99 | 0.08 | 8.7 | 0.022 |
| clean | mpm | 91.6 | 0.92 | 0.20 | 5.8 | 0.007 |
| noise 20 dB | pyin | 98.1 | 1.00 | 0.20 | 9.2 | 0.021 |
| noise 20 dB | crepe | 97.3 | 0.99 | 0.06 | 7.9 | 0.023 |
| noise 20 dB | mpm | 90.7 | 0.92 | 0.12 | 5.8 | 0.007 |
| noise 10 dB | pyin | 97.7 | 0.99 | 0.20 | 9.2 | 0.017 |
| noise 10 dB | crepe | 97.1 | 0.99 | 0.06 | 8.3 | 0.020 |
| noise 10 dB | mpm | 84.0 | 0.84 | 0.00 | 5.5 | 0.000 |
| noise 5 dB | pyin | 96.7 | 0.98 | 0.19 | 9.2 | 0.013 |
| noise 5 dB | crepe | 97.2 | 0.99 | 0.06 | 7.8 | 0.023 |
| noise 5 dB | mpm | 0.0 | 0.00 | 0.00 | nan | nan |
| detuned 100 cents | pyin | 65.1 | 0.99 | 0.12 | 100.3 | 0.510 |
| detuned 100 cents | crepe | 65.0 | 0.99 | 0.09 | 100.2 | 0.507 |
| detuned 100 cents | mpm | 61.2 | 0.94 | 0.20 | 100.4 | 0.516 |
| late 0.2 s | pyin | 88.5 | 0.95 | 0.42 | 9.2 | 0.227 |
| late 0.2 s | crepe | 86.4 | 0.94 | 0.40 | 10.7 | 0.246 |
| late 0.2 s | mpm | 84.3 | 0.88 | 0.46 | 6.7 | 0.215 |

## 2. The live-game pairing (total score)

| Take | CREPE ref vs CREPE player | CREPE ref vs MPM player (live game) | Cost of mismatch |
|---|---|---|---|
| clean | 99.7 | 94.1 | +5.6 |
| noise 20 dB | 99.5 | 93.4 | +6.1 |
| noise 10 dB | 99.4 | 87.8 | +11.6 |
| noise 5 dB | 99.4 | 0.0 | +99.4 |
| detuned 100 cents | 73.0 | 68.3 | +4.7 |
| late 0.2 s | 81.2 | 78.8 | +2.4 |

## 3. MPM clarity threshold (frontend setting), total score

| Clarity threshold | Clean take | Take with 10 dB noise | Noise only, no voice |
|---|---|---|---|
| 0.7 | 97.9 | 97.3 | 0.0 |
| 0.8 | 96.9 | 94.2 | 0.0 |
| 0.9 | 94.1 | 87.8 | 0.0 |
| 0.95 | 91.9 | 0.0 | 0.0 |
