# Pitch time tolerance: what it changes

Total score (pitch / timing in brackets) for the same takes at different `PitchConfig.time_tolerance_s`. 0 is the current default. Track-level synthetic takes.

| Take | tolerance 0.0 s | tolerance 0.05 s | tolerance 0.1 s | tolerance 0.15 s |
|---|---|---|---|---|
| perfect | 100.0 (100 / 100) | 100.0 (100 / 100) | 100.0 (100 / 100) | 100.0 (100 / 100) |
| late 0.05 s | 95.1 (94 / 100) | 100.0 (100 / 100) | 100.0 (100 / 100) | 100.0 (100 / 100) |
| late 0.1 s | 87.9 (85 / 100) | 92.8 (91 / 100) | 100.0 (100 / 100) | 100.0 (100 / 100) |
| late 0.2 s | 69.1 (70 / 67) | 73.9 (76 / 67) | 81.2 (85 / 67) | 88.5 (94 / 67) |
| late 0.3 s | 50.3 (54 / 33) | 55.2 (61 / 33) | 62.4 (70 / 33) | 69.7 (79 / 33) |
| detuned 100 cents | 73.3 (67 / 100) | 73.3 (67 / 100) | 73.3 (67 / 100) | 73.3 (67 / 100) |
| detuned 200 cents | 20.0 (0 / 100) | 21.9 (2 / 100) | 24.6 (6 / 100) | 27.4 (9 / 100) |
| half the notes skipped | 55.6 (56 / 52) | 55.6 (56 / 52) | 55.6 (56 / 52) | 55.6 (56 / 52) |

Reading: a tolerance should raise late takes' **pitch** (lateness then shows only in timing) while leaving detuned and skipped takes about where they were. If it also lifts wrong notes, it is too wide.
