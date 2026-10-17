# Grading lyrics in sung audio: it does not work yet

14 Korean-only lyric lines cut from isolated professional vocal stems (best case: clean voice, correct timing). Each line is scored against its own lyric and against the other lines' lyrics.

| Method | Right vs wrong lyric (AUC, 0.5 = chance) | Score with the right lyric (median) | with a wrong lyric (median) | Swapped word found |
|---|---|---|---|---|
| wav2vec2 forced alignment (spoken-mode scorer) | 0.65 | 2 | 0 | 7/14 (chance ~31%) |
| Whisper-small transcription + jamo comparison | 0.62 | 20 | 0 | 6/14 (chance ~31%) |

Whisper returned no text at all for 7 of 14 lines. The swapped-word column is NOT reliable for either method: scores are collapsed near zero, so the count swings (2 to 7 of 14 in repeated runs) with which word is swapped and how ties break. Only the right-vs-wrong AUC is a usable signal, and it is near chance.

Reading: both methods sit near chance on singing. The spoken-mode scorer's posteriors collapse on sung audio (stretched vowels, vibrato), and Whisper often hears nothing. Small sample (one best-case set), small models; larger models or a different approach (comparing against the original singer's vocal) may do better. Spoken practice remains the validated path for pronunciation feedback.
