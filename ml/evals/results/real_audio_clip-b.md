# Real-voice degradation eval (clip-b)

A real 30 s vocal clip (local only, never committed) is damaged at increasing severity, tracked, and scored against its own clean CREPE contour. Two trackers for the damaged take: **CREPE** and **MPM** (our emulation of the browser's Pitchy, clarity 0.8). Totals 0-100, 2 seeds per level. Phrases are rough voiced stretches (5).
**Limits:** one singer, damage is still synthetic, the stem may contain backing vocals, no human take. Read the ORDER of scores, not the absolute values.

## Local detuning (every other second shifted +/- N cents)

| cents | CREPE total | MPM (browser-style) total |
|---|---|---|
| 0 | 100.0 | 69.5 |
| 50 | 93.3 | 68.0 |
| 100 | 83.7 | 61.1 |
| 200 | 62.8 | 43.4 |
| 300 | 60.6 | 42.0 |

Spearman rho (severity vs total): CREPE **-0.99**, MPM **-0.99**

## Late entrance, uncalibrated (seconds)

| seconds | CREPE total | MPM (browser-style) total |
|---|---|---|
| 0.0 | 100.0 | 69.5 |
| 0.1 | 80.8 | 62.1 |
| 0.2 | 61.2 | 47.4 |
| 0.3 | 47.7 | 36.3 |
| 0.4 | 37.1 | 32.6 |

Spearman rho (severity vs total): CREPE **-0.99**, MPM **-1.00**

## Dropped seconds (fraction silenced)

| fraction | CREPE total | MPM (browser-style) total |
|---|---|---|
| 0.0 | 99.5 | 69.5 |
| 0.1 | 88.7 | 63.3 |
| 0.25 | 71.8 | 49.6 |
| 0.5 | 50.2 | 33.8 |

Spearman rho (severity vs total): CREPE **-0.98**, MPM **-0.98**

## White noise (-SNR dB, lower SNR = worse)

| -SNR dB | CREPE total | MPM (browser-style) total |
|---|---|---|
| -30 | 99.0 | 68.8 |
| -20 | 98.1 | 62.6 |
| -10 | 87.5 | 28.8 |
| -5 | 76.0 | 10.6 |

Spearman rho (severity vs total): CREPE **-0.98**, MPM **-0.98**

