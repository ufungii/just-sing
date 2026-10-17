# Singing score: degradation evals

Scoring version `0.3.0`. Synthetic voice-like melody (10.25 s, 14 notes, 3 phrases), rendered to audio, tracked with pyin, scored with `score_turn`. 3 seeds per level.
Totals are 0-100. **Limits:** clean synthetic voices only; says nothing yet about real singers.

## Sanity checks

| Check | Score | Expected |
|---|---|---|
| Reference-like take (through tracker) | 99.5 | >= 90 |
| Same take, octave up, +12 register chosen | 99.0 | >= 90 |
| Same take, octave up, register NOT chosen | 20.0 | <= 30 |
| Silence | 0.0 | == 0 |
| Noise only (no voice) | 3.5 | <= 10 |
| Identical input scored twice, equal? | 1.0 | == 1 |

## Phrase ratings (count of phrases over all seeds)

| Take | Perfect | Great | Okay | Bad | Miss |
|---|---|---|---|---|---|
| Reference-like take | 9 | 0 | 0 | 0 | 0 |
| Mildly off (every note off by up to 50 cents) | 9 | 0 | 0 | 0 | 0 |
| Off (every note off by up to 100 cents) | 1 | 8 | 0 | 0 | 0 |
| Wrong notes (every note off by up to 200 cents) | 0 | 0 | 0 | 9 | 0 |
| Wrong notes (every note off by up to 300 cents) | 0 | 0 | 0 | 9 | 0 |
| Silence | 0 | 0 | 0 | 0 | 9 |

## Detuning (every note off by +/- N cents)

Spearman rho (severity vs total): **-0.958**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0 | 99.8 +/- 0.2 | 99.8 | 100.0 |
| 25 | 99.7 +/- 0.1 | 99.6 | 100.0 |
| 50 | 99.1 +/- 0.1 | 98.9 | 100.0 |
| 100 | 78.6 +/- 1.7 | 75.6 | 90.7 |
| 150 | 47.6 +/- 1.9 | 38.5 | 83.9 |
| 200 | 22.6 +/- 2.6 | 8.1 | 80.5 |
| 300 | 24.5 +/- 1.1 | 6.5 | 96.6 |

## Skipped notes (fraction replaced by rests)

Spearman rho (severity vs total): **-0.990**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 99.8 +/- 0.2 | 99.8 | 100.0 |
| 0.1 | 92.1 +/- 0.7 | 94.4 | 83.0 |
| 0.25 | 70.6 +/- 1.8 | 71.0 | 69.2 |
| 0.5 | 49.7 +/- 4.5 | 53.8 | 33.3 |
| 0.75 | 25.6 +/- 2.3 | 28.0 | 15.7 |
| 1.0 | 0.0 +/- 0.0 | 0.0 | 0.0 |

## Background noise (white, lower SNR = worse)

Spearman rho (severity vs total): **-0.920**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| -40 | 99.8 +/- 0.2 | 99.8 | 100.0 |
| -30 | 99.8 +/- 0.2 | 99.8 | 100.0 |
| -20 | 99.8 +/- 0.1 | 99.8 | 100.0 |
| -10 | 99.4 +/- 0.0 | 99.2 | 100.0 |
| -5 | 98.1 +/- 0.1 | 97.7 | 100.0 |
| 0 | 25.4 +/- 18.0 | 25.4 | 25.1 |
| 5 | 0.3 +/- 0.4 | 0.0 | 1.4 |

## Late entrance, uncalibrated (seconds)

Spearman rho (severity vs total): **-0.971**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 99.8 +/- 0.2 | 99.8 | 100.0 |
| 0.1 | 99.7 +/- 0.2 | 99.8 | 99.3 |
| 0.2 | 85.7 +/- 0.2 | 88.7 | 73.7 |
| 0.3 | 67.0 +/- 0.2 | 73.6 | 40.4 |
| 0.4 | 48.5 +/- 0.2 | 58.6 | 7.8 |
| 0.5 | 36.8 +/- 0.1 | 43.5 | 10.0 |

## Tempo drift (singer slower; 1 - rate)

Spearman rho (severity vs total): **-0.819**

| Severity | Total (mean +/- sd) | Pitch | Timing |
|---|---|---|---|
| 0.0 | 99.8 +/- 0.2 | 99.8 | 100.0 |
| 0.05 | 76.4 +/- 0.5 | 81.4 | 56.3 |
| 0.1 | 49.5 +/- 0.3 | 48.4 | 53.9 |
| 0.2 | 28.2 +/- 0.1 | 28.2 | 28.2 |
| 0.3 | 23.2 +/- 0.3 | 23.3 | 22.6 |
| 0.4 | 32.3 +/- 0.1 | 32.5 | 31.9 |
