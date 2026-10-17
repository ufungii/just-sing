# Rating-band calibration: love-scenario-daniel

Take lined up by melody: register -12, agreement 0.64 (next best 0.41). 222 s of the song, 54 phrases. Current bands: perfect >= 90, great >= 75, okay >= 50; miss under 25% coverage. Phrase scores below are the 10th / 50th / 90th percentile over phrases that were not a miss.

## live (Pitchy, clarity 0.65, RMS 0.005)

| Condition | Total | Phrase p10 / p50 / p90 | Ratings, current bands | Ratings, proposed 80 / 65 / 40 |
|---|---|---|---|---|
| original singer (stem) | 76.9 | 66 / 78 / 89 | great 30, okay 18, perfect 5, bad 1 | great 25, perfect 24, okay 5 |
| real take | 59.8 | 46 / 64 / 79 | okay 37, bad 9, great 8 | okay 27, great 21, perfect 4, bad 2 |
| off-key 50 cents | 56.6 | 42 / 59 / 75 | okay 33, bad 15, great 6 | okay 36, great 12, bad 4, perfect 2 |
| off-key 100 cents | 47.5 | 34 / 50 / 63 | bad 29, okay 23, great 2 | okay 36, bad 13, great 5 |
| off-key 200 cents | 25.2 | 17 / 25 / 36 | bad 54 | bad 52, okay 2 |
| off-key 300 cents | 14.7 | 10 / 14 / 23 | bad 54 | bad 54 |
| late 0.2 s | 48.3 | 38 / 49 / 62 | bad 29, okay 25 | okay 43, bad 7, great 4 |
| late 0.4 s | 34.3 | 26 / 35 / 44 | bad 51, okay 3 | bad 37, okay 16, great 1 |
| 25% of phrases silent | 47.2 | 48 / 66 / 78 | okay 29, miss 14, great 6, bad 5 | okay 20, great 17, miss 14, perfect 3 |
| 50% of phrases silent | 32.9 | 48 / 62 / 77 | miss 27, okay 19, great 4, bad 4 | miss 27, okay 16, great 9, perfect 2 |
| noise only | 0.0 | n/a | miss 54 | miss 54 |
| silence | 0.0 | n/a | miss 54 | miss 54 |

## CREPE

| Condition | Total | Phrase p10 / p50 / p90 | Ratings, current bands | Ratings, proposed 80 / 65 / 40 |
|---|---|---|---|---|
| original singer (stem) | 97.3 | 92 / 99 / 100 | perfect 53, great 1 | perfect 54 |
| real take | 61.4 | 46 / 67 / 81 | okay 35, great 10, bad 8, perfect 1 | okay 23, great 22, perfect 6, bad 3 |
| off-key 50 cents | 58.1 | 45 / 62 / 76 | okay 35, bad 11, great 8 | okay 33, great 14, perfect 4, bad 3 |
| off-key 100 cents | 48.1 | 34 / 50 / 64 | okay 29, bad 24, great 1 | okay 35, bad 13, great 6 |
| off-key 200 cents | 24.7 | 15 / 26 / 34 | bad 54 | bad 51, okay 3 |
| off-key 300 cents | 14.3 | 8 / 14 / 22 | bad 54 | bad 54 |
| late 0.2 s | 50.8 | 42 / 52 / 64 | okay 31, bad 23 | okay 44, great 5, bad 5 |
| late 0.4 s | 35.1 | 24 / 35 / 48 | bad 49, okay 5 | bad 37, okay 17 |
| 25% of phrases silent | 48.6 | 51 / 67 / 80 | okay 30, miss 14, great 5, bad 4, perfect 1 | great 19, okay 16, miss 14, perfect 4, bad 1 |
| 50% of phrases silent | 33.3 | 50 / 62 / 75 | miss 27, okay 21, great 3, bad 3 | miss 27, okay 14, great 10, perfect 2, bad 1 |
| noise only | 0.0 | n/a | miss 54 | miss 54 |
| silence | 0.0 | n/a | miss 54 | miss 54 |

## Reading it

- Through the live tracker the original singer is the realistic ceiling (CREPE scoring the stem is the same tracker that made the reference, so it is near 100 by construction and says nothing).
- Proposed cutoffs, all on the live path: **perfect >= 80** (about the original singer's typical phrase), **great >= 65** (about a decent amateur's typical phrase), **okay >= 40** (a phrase a semitone off still lands here; two semitones off or 0.4 s late falls below). These are choices read off one singer and one song, not validated thresholds. Changing them is a scoring-version bump: fixtures and the TypeScript port change too.

