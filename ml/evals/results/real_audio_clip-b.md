# Real-voice degradation eval (clip-b)

A real 30 s vocal clip (local only, never committed) is damaged at increasing severity, tracked, and scored against its own clean CREPE contour. Two trackers for the damaged take: **CREPE** and **MPM** (our emulation of the browser's Pitchy, clarity 0.8). Totals 0-100, 2 seeds per level. Phrases are rough voiced stretches (5).
**Limits:** one singer, damage is still synthetic, the stem may contain backing vocals, no human take. Read the ORDER of scores, not the absolute values.

## Local detuning (every other second shifted +/- N cents)

| cents | CREPE total | MPM (browser-style) total |
|---|---|---|
| 0 | 98.9 | 69.0 |
| 50 | 93.2 | 68.0 |
| 100 | 84.0 | 61.2 |
| 200 | 62.8 | 43.5 |
| 300 | 60.8 | 41.9 |

Spearman rho (severity vs total): CREPE **-0.98**, MPM **-0.99**

## Late entrance, uncalibrated (seconds)

| seconds | CREPE total | MPM (browser-style) total |
|---|---|---|
| 0.0 | 99.5 | 69.0 |
| 0.1 | 99.8 | 68.9 |
| 0.2 | 74.7 | 58.1 |
| 0.3 | 56.2 | 44.4 |
| 0.4 | 42.2 | 37.1 |

Spearman rho (severity vs total): CREPE **-0.94**, MPM **-1.00**

## Dropped seconds (fraction silenced)

| fraction | CREPE total | MPM (browser-style) total |
|---|---|---|
| 0.0 | 99.2 | 69.0 |
| 0.1 | 88.8 | 62.9 |
| 0.25 | 71.0 | 49.4 |
| 0.5 | 49.7 | 33.7 |

Spearman rho (severity vs total): CREPE **-0.98**, MPM **-0.98**

## White noise (-SNR dB, lower SNR = worse)

| -SNR dB | CREPE total | MPM (browser-style) total |
|---|---|---|
| -30 | 98.2 | 68.5 |
| -20 | 97.8 | 62.5 |
| -10 | 86.8 | 28.6 |
| -5 | 76.5 | 10.4 |

Spearman rho (severity vs total): CREPE **-0.93**, MPM **-0.98**

