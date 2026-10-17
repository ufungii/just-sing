# Real-voice degradation eval (clip-b)

A real 30 s vocal clip (local only, never committed) is damaged at increasing severity, tracked, and scored against its own clean CREPE contour. Two trackers for the damaged take: **CREPE** and **MPM** (our emulation of the browser's Pitchy, clarity 0.8). Totals 0-100, 2 seeds per level. Phrases are rough voiced stretches (2).
**Limits:** one singer, damage is still synthetic, the stem may contain backing vocals, no human take. Read the ORDER of scores, not the absolute values.

## Local detuning (every other second shifted +/- N cents)

| cents | CREPE total | MPM (browser-style) total |
|---|---|---|
| 0 | 100.0 | 62.4 |
| 50 | 93.0 | 60.7 |
| 100 | 82.1 | 53.5 |
| 200 | 60.5 | 37.6 |
| 300 | 58.6 | 36.9 |

Spearman rho (severity vs total): CREPE **-0.99**, MPM **-0.98**

## Late entrance, uncalibrated (seconds)

| seconds | CREPE total | MPM (browser-style) total |
|---|---|---|
| 0.0 | 99.3 | 62.4 |
| 0.1 | 82.2 | 56.7 |
| 0.2 | 62.9 | 43.6 |
| 0.3 | 48.1 | 37.1 |
| 0.4 | 37.8 | 33.5 |

Spearman rho (severity vs total): CREPE **-0.99**, MPM **-1.00**

## Dropped seconds (fraction silenced)

| fraction | CREPE total | MPM (browser-style) total |
|---|---|---|
| 0.0 | 100.0 | 62.4 |
| 0.1 | 90.5 | 56.5 |
| 0.25 | 71.5 | 44.0 |
| 0.5 | 51.0 | 30.9 |

Spearman rho (severity vs total): CREPE **-0.98**, MPM **-0.98**

## White noise (-SNR dB, lower SNR = worse)

| -SNR dB | CREPE total | MPM (browser-style) total |
|---|---|---|
| -30 | 97.9 | 61.2 |
| -20 | 91.5 | 55.0 |
| -10 | 83.0 | 25.1 |
| -5 | 74.5 | 9.3 |

Spearman rho (severity vs total): CREPE **-0.98**, MPM **-0.98**

