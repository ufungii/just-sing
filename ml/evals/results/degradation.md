# Singing score: degradation evals

Scoring version `0.1.0`. Synthetic voice-like melody (10.25 s, 14 notes, 3 phrases), rendered to audio, tracked with pyin, scored with `score_turn`. 3 seeds per level.
Totals are 0-100. **Limits:** clean synthetic voices only; says nothing yet about real singers.

## Sanity checks

| Check | Score | Expected |
|---|---|---|
| Reference-like take (through tracker) | 98.1 | >= 90 |
| Same take, octave up, +12 register chosen | 96.1 | >= 90 |
| Same take, octave up, register NOT chosen | 20.0 | <= 30 |
| Silence | 0.0 | == 0 |
| Noise only (no voice) | 3.5 | <= 10 |
| Identical input scored twice, equal? | 1.0 | == 1 |

## Detuning (every note off by +/- N cents)

Spearman rho (severity vs total): **-0.960**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0 | 98.3 +/- 0.1 | 97.9 | 100.0 |
| 25 | 98.1 +/- 0.1 | 97.7 | 100.0 |
| 50 | 96.3 +/- 0.1 | 95.3 | 100.0 |
| 100 | 70.1 +/- 1.9 | 65.0 | 90.7 |
| 150 | 42.8 +/- 1.9 | 32.6 | 83.9 |
| 200 | 18.3 +/- 2.3 | 2.8 | 80.5 |
| 300 | 19.7 +/- 1.0 | 0.4 | 96.6 |

## Skipped notes (fraction replaced by rests)

Spearman rho (severity vs total): **-0.990**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 98.3 +/- 0.1 | 97.9 | 100.0 |
| 0.1 | 91.1 +/- 0.7 | 93.2 | 83.0 |
| 0.25 | 69.8 +/- 1.8 | 69.9 | 69.2 |
| 0.5 | 49.2 +/- 4.2 | 53.1 | 33.3 |
| 0.75 | 25.6 +/- 2.4 | 28.0 | 15.7 |
| 1.0 | 0.0 +/- 0.0 | 0.0 | 0.0 |

## Background noise (white, lower SNR = worse)

Spearman rho (severity vs total): **-0.860**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| -40 | 98.3 +/- 0.1 | 97.9 | 100.0 |
| -30 | 98.3 +/- 0.1 | 97.9 | 100.0 |
| -20 | 98.3 +/- 0.1 | 97.9 | 100.0 |
| -10 | 98.2 +/- 0.0 | 97.7 | 100.0 |
| -5 | 97.3 +/- 0.2 | 96.7 | 100.0 |
| 0 | 25.2 +/- 17.8 | 25.2 | 25.1 |
| 5 | 0.3 +/- 0.4 | 0.0 | 1.4 |

## Late entrance, uncalibrated (seconds)

Spearman rho (severity vs total): **-0.988**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 98.3 +/- 0.1 | 97.9 | 100.0 |
| 0.1 | 91.2 +/- 0.1 | 89.2 | 99.3 |
| 0.2 | 74.3 +/- 0.2 | 74.1 | 75.2 |
| 0.3 | 55.6 +/- 0.2 | 59.1 | 41.9 |
| 0.4 | 37.0 +/- 0.2 | 43.9 | 9.3 |
| 0.5 | 25.2 +/- 0.1 | 29.0 | 10.0 |

## Tempo drift (singer slower; 1 - rate)

Spearman rho (severity vs total): **-0.819**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 97.7 +/- 0.1 | 97.9 | 96.9 |
| 0.05 | 69.7 +/- 0.8 | 72.5 | 58.8 |
| 0.1 | 43.4 +/- 0.4 | 39.8 | 57.9 |
| 0.2 | 24.2 +/- 0.2 | 22.7 | 30.3 |
| 0.3 | 21.3 +/- 0.2 | 20.4 | 24.7 |
| 0.4 | 29.1 +/- 0.2 | 28.1 | 32.9 |
