# Rating-band calibration: last-christmas

Take lined up by melody: register +0, agreement 0.52 (next best 0.34). 36 s of the song, 9 phrases. Current bands: perfect >= 90, great >= 75, okay >= 50; miss under 25% coverage. Phrase scores below are the 10th / 50th / 90th percentile over phrases that were not a miss.

## live (Pitchy, clarity 0.65, RMS 0.005)

| Condition | Total | Phrase p10 / p50 / p90 | Ratings, current bands | Ratings, proposed 80 / 65 / 40 |
|---|---|---|---|---|
| original singer (stem) | 79.4 | 70 / 80 / 86 | great 6, okay 2, perfect 1 | perfect 5, great 3, okay 1 |
| real take | 55.9 | 44 / 59 / 73 | okay 6, bad 3 | okay 5, great 3, bad 1 |
| off-key 50 cents | 55.4 | 42 / 63 / 71 | okay 7, bad 2 | okay 5, great 3, bad 1 |
| off-key 100 cents | 47.1 | 38 / 43 / 67 | bad 5, okay 3, great 1 | okay 7, bad 1, perfect 1 |
| off-key 200 cents | 23.2 | 13 / 18 / 39 | bad 9 | bad 8, okay 1 |
| off-key 300 cents | 12.1 | 5 / 9 / 23 | bad 9 | bad 9 |
| late 0.2 s | 48.8 | 37 / 53 / 61 | okay 5, bad 4 | okay 7, bad 2 |
| late 0.4 s | 33.6 | 24 / 37 / 42 | bad 9 | bad 6, okay 3 |
| 25% of phrases silent | 45.8 | 43 / 59 / 73 | okay 5, bad 2, miss 2 | okay 4, great 2, miss 2, bad 1 |
| 50% of phrases silent | 34.4 | 45 / 59 / 73 | okay 4, miss 4, bad 1 | miss 4, great 2, okay 2, bad 1 |
| noise only | 0.0 | n/a | miss 9 | miss 9 |
| silence | 0.0 | n/a | miss 9 | miss 9 |

## CREPE

| Condition | Total | Phrase p10 / p50 / p90 | Ratings, current bands | Ratings, proposed 80 / 65 / 40 |
|---|---|---|---|---|
| original singer (stem) | 88.7 | 84 / 88 / 95 | great 6, perfect 3 | perfect 9 |
| real take | 59.5 | 50 / 65 / 73 | okay 7, bad 1, great 1 | great 5, okay 3, bad 1 |
| off-key 50 cents | 59.6 | 51 / 64 / 76 | okay 6, great 2, bad 1 | okay 4, great 3, bad 1, perfect 1 |
| off-key 100 cents | 51.7 | 41 / 53 / 74 | bad 4, okay 4, great 1 | okay 6, great 2, bad 1 |
| off-key 200 cents | 25.1 | 16 / 21 / 42 | bad 8, okay 1 | bad 8, okay 1 |
| off-key 300 cents | 12.4 | 7 / 9 / 23 | bad 9 | bad 9 |
| late 0.2 s | 52.6 | 41 / 55 / 64 | okay 5, bad 4 | okay 7, bad 1, great 1 |
| late 0.4 s | 36.0 | 24 / 37 / 48 | bad 8, okay 1 | bad 5, okay 4 |
| 25% of phrases silent | 49.3 | 47 / 67 / 73 | okay 6, miss 2, bad 1 | great 4, okay 2, miss 2, bad 1 |
| 50% of phrases silent | 37.1 | 49 / 71 / 74 | miss 4, okay 3, bad 1, great 1 | great 4, miss 4, bad 1 |
| noise only | 0.0 | n/a | miss 9 | miss 9 |
| silence | 0.0 | n/a | miss 9 | miss 9 |

## Reading it

- Through the live tracker the original singer is the realistic ceiling (CREPE scoring the stem is the same tracker that made the reference, so it is near 100 by construction and says nothing).
- Proposed cutoffs, all on the live path: **perfect >= 80** (about the original singer's typical phrase), **great >= 65** (about a decent amateur's typical phrase), **okay >= 40** (a phrase a semitone off still lands here; two semitones off or 0.4 s late falls below). These are choices read off one singer and one song, not validated thresholds. Changing them is a scoring-version bump: fixtures and the TypeScript port change too.

