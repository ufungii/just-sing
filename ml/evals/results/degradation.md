# Singing score: degradation evals

Scoring version `0.2.0`. Synthetic voice-like melody (10.25 s, 14 notes, 3 phrases), rendered to audio, tracked with pyin, scored with `score_turn`. 3 seeds per level.
Totals are 0-100. **Limits:** clean synthetic voices only; says nothing yet about real singers.

## Sanity checks

| Check | Score | Expected |
|---|---|---|
| Reference-like take (through tracker) | 99.4 | >= 90 |
| Same take, octave up, +12 register chosen | 97.5 | >= 90 |
| Same take, octave up, register NOT chosen | 20.0 | <= 30 |
| Silence | 0.0 | == 0 |
| Noise only (no voice) | 3.5 | <= 10 |
| Identical input scored twice, equal? | 1.0 | == 1 |

## Detuning (every note off by +/- N cents)

Spearman rho (severity vs total): **-0.954**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0 | 99.7 +/- 0.2 | 99.6 | 100.0 |
| 25 | 99.5 +/- 0.1 | 99.3 | 100.0 |
| 50 | 97.5 +/- 0.1 | 96.8 | 100.0 |
| 100 | 70.7 +/- 1.7 | 65.7 | 90.7 |
| 150 | 43.6 +/- 1.9 | 33.5 | 83.9 |
| 200 | 22.0 +/- 2.5 | 7.3 | 80.5 |
| 300 | 24.3 +/- 1.1 | 6.3 | 96.6 |

## Skipped notes (fraction replaced by rests)

Spearman rho (severity vs total): **-0.991**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 99.7 +/- 0.2 | 99.6 | 100.0 |
| 0.1 | 91.9 +/- 0.8 | 94.2 | 83.0 |
| 0.25 | 70.6 +/- 1.8 | 70.9 | 69.2 |
| 0.5 | 49.7 +/- 4.5 | 53.8 | 33.3 |
| 0.75 | 25.5 +/- 2.3 | 28.0 | 15.7 |
| 1.0 | 0.0 +/- 0.0 | 0.0 | 0.0 |

## Background noise (white, lower SNR = worse)

Spearman rho (severity vs total): **-0.921**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| -40 | 99.7 +/- 0.2 | 99.6 | 100.0 |
| -30 | 99.6 +/- 0.2 | 99.6 | 100.0 |
| -20 | 99.7 +/- 0.2 | 99.6 | 100.0 |
| -10 | 99.2 +/- 0.0 | 99.1 | 100.0 |
| -5 | 98.0 +/- 0.1 | 97.5 | 100.0 |
| 0 | 25.3 +/- 18.0 | 25.4 | 25.1 |
| 5 | 0.3 +/- 0.4 | 0.0 | 1.4 |

## Late entrance, uncalibrated (seconds)

Spearman rho (severity vs total): **-0.977**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 99.7 +/- 0.2 | 99.6 | 100.0 |
| 0.1 | 99.5 +/- 0.2 | 99.6 | 99.3 |
| 0.2 | 85.5 +/- 0.2 | 88.5 | 73.7 |
| 0.3 | 66.8 +/- 0.2 | 73.4 | 40.4 |
| 0.4 | 48.2 +/- 0.2 | 58.3 | 7.8 |
| 0.5 | 36.6 +/- 0.1 | 43.2 | 10.0 |

## Tempo drift (singer slower; 1 - rate)

Spearman rho (severity vs total): **-0.819**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 99.7 +/- 0.2 | 99.6 | 100.0 |
| 0.05 | 76.2 +/- 0.5 | 81.2 | 56.3 |
| 0.1 | 49.3 +/- 0.3 | 48.1 | 53.9 |
| 0.2 | 28.0 +/- 0.1 | 27.9 | 28.2 |
| 0.3 | 22.4 +/- 0.2 | 22.3 | 22.6 |
| 0.4 | 31.7 +/- 0.1 | 31.7 | 31.9 |
