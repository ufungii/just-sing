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
| 50 | 96.4 +/- 0.1 | 95.5 | 100.0 |
| 100 | 70.0 +/- 1.9 | 64.9 | 90.7 |
| 150 | 42.8 +/- 1.8 | 32.6 | 83.9 |
| 200 | 18.2 +/- 2.2 | 2.6 | 80.5 |
| 300 | 19.7 +/- 1.0 | 0.4 | 96.6 |

## Skipped notes (fraction replaced by rests)

Spearman rho (severity vs total): **-0.990**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 98.3 +/- 0.1 | 97.9 | 100.0 |
| 0.1 | 91.1 +/- 0.7 | 93.1 | 83.0 |
| 0.25 | 69.6 +/- 1.7 | 69.7 | 69.2 |
| 0.5 | 49.0 +/- 4.4 | 52.9 | 33.3 |
| 0.75 | 25.5 +/- 2.3 | 27.9 | 15.7 |
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
| 0.1 | 90.6 +/- 0.1 | 88.5 | 99.3 |
| 0.2 | 73.4 +/- 0.2 | 73.4 | 73.7 |
| 0.3 | 54.7 +/- 0.2 | 58.3 | 40.4 |
| 0.4 | 36.1 +/- 0.2 | 43.2 | 7.8 |
| 0.5 | 24.6 +/- 0.1 | 28.2 | 10.0 |

## Tempo drift (singer slower; 1 - rate)

Spearman rho (severity vs total): **-0.819**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 98.3 +/- 0.1 | 97.9 | 100.0 |
| 0.05 | 67.9 +/- 0.6 | 70.9 | 56.3 |
| 0.1 | 41.6 +/- 0.3 | 38.5 | 53.9 |
| 0.2 | 23.7 +/- 0.1 | 22.6 | 28.2 |
| 0.3 | 20.2 +/- 0.1 | 19.5 | 22.6 |
| 0.4 | 28.9 +/- 0.2 | 28.1 | 31.9 |
