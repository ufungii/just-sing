# Singing score: degradation evals

Scoring version `0.1.0`. Synthetic voice-like melody (9.5 s, 14 notes, 3 phrases), rendered to audio, tracked with pyin, scored with `score_turn`. 3 seeds per level.
Totals are 0-100. **Limits:** clean synthetic voices only; says nothing yet about real singers.

## Sanity checks

| Check | Score | Expected |
|---|---|---|
| Reference-like take (through tracker) | 97.9 | >= 90 |
| Same take, octave up, +12 register chosen | 97.2 | >= 90 |
| Same take, octave up, register NOT chosen | 20.0 | <= 30 |
| Silence | 0.0 | == 0 |
| Noise only (no voice) | 3.8 | <= 10 |
| Identical input scored twice, equal? | 1.0 | == 1 |

## Detuning (every note off by +/- N cents)

Spearman rho (severity vs total): **-0.959**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0 | 98.1 +/- 0.1 | 97.7 | 100.0 |
| 25 | 98.0 +/- 0.2 | 97.5 | 100.0 |
| 50 | 96.1 +/- 0.1 | 95.1 | 100.0 |
| 100 | 69.8 +/- 2.1 | 64.8 | 89.9 |
| 150 | 42.9 +/- 1.9 | 32.6 | 84.0 |
| 200 | 18.5 +/- 2.3 | 2.9 | 81.1 |
| 300 | 19.8 +/- 0.9 | 0.5 | 97.1 |

## Skipped notes (fraction replaced by rests)

Spearman rho (severity vs total): **-0.990**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 98.1 +/- 0.1 | 97.7 | 100.0 |
| 0.1 | 91.0 +/- 0.3 | 92.7 | 84.4 |
| 0.25 | 69.6 +/- 1.6 | 70.2 | 67.3 |
| 0.5 | 48.0 +/- 0.9 | 51.9 | 32.6 |
| 0.75 | 25.2 +/- 1.4 | 27.6 | 15.6 |
| 1.0 | 0.0 +/- 0.0 | 0.0 | 0.0 |

## Background noise (white, lower SNR = worse)

Spearman rho (severity vs total): **-0.870**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| -40 | 98.1 +/- 0.1 | 97.7 | 100.0 |
| -30 | 98.1 +/- 0.1 | 97.7 | 100.0 |
| -20 | 98.1 +/- 0.1 | 97.7 | 100.0 |
| -10 | 98.0 +/- 0.0 | 97.5 | 100.0 |
| -5 | 97.1 +/- 0.2 | 96.4 | 100.0 |
| 0 | 24.7 +/- 17.5 | 24.6 | 25.3 |
| 5 | 0.3 +/- 0.4 | 0.0 | 1.6 |

## Late entrance, uncalibrated (seconds)

Spearman rho (severity vs total): **-0.991**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 98.1 +/- 0.1 | 97.7 | 100.0 |
| 0.1 | 90.4 +/- 0.1 | 88.2 | 99.2 |
| 0.2 | 72.4 +/- 0.2 | 71.8 | 74.6 |
| 0.3 | 52.6 +/- 0.2 | 55.5 | 41.2 |
| 0.4 | 33.0 +/- 0.2 | 39.1 | 8.7 |
| 0.5 | 20.5 +/- 0.0 | 22.9 | 10.9 |

## Tempo drift (singer slower; 1 - rate)

Spearman rho (severity vs total): **-0.818**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 97.6 +/- 0.2 | 97.7 | 97.2 |
| 0.05 | 68.5 +/- 0.9 | 70.2 | 61.8 |
| 0.1 | 44.1 +/- 0.5 | 40.6 | 58.2 |
| 0.2 | 25.9 +/- 0.2 | 24.6 | 30.8 |
| 0.3 | 22.9 +/- 0.2 | 22.2 | 25.3 |
| 0.4 | 31.0 +/- 0.2 | 30.6 | 32.5 |
