# Pronunciation: near-miss (one-sound) eval

39 cases: in each, one word of a test phrase has ONE sound changed (initial consonant 21, vowel 13, final consonant 5). That changed phrase is synthesized with local TTS and scored against the CORRECT text.
**Limits:** TTS stands in for a learner (clean, single speaker, says the changed text perfectly). No fluent reviewer. This measures sensitivity to one-sound changes, not pronunciation quality.

| Method | Word AUC (changed word, correct vs mispronounced audio) | Flags the changed word (top-1) | Mean score drop on that word |
|---|---|---|---|
| A | 0.621 | 0.33 | 8.2 |
| B | 0.643 | 0.54 | 17.4 |
| B-norm | 0.662 | 0.46 | 22.6 |
| A+B | 0.662 | 0.46 | 12.8 |
| A+B-norm | 0.678 | 0.41 | 15.4 |

Chance for top-1 flagging is about 0.31. A = Whisper + jamo; B = wav2vec2 forced alignment; B-norm = B divided per word by B's score on a separate TTS rendition of the correct phrase (computable offline per practice line); A+B and A+B-norm = mean of the two word scores.

## Word AUC by kind of mistake

| Method | initial consonant | vowel | final consonant |
|---|---|---|---|
| A | 0.526 | 0.683 | 0.880 |
| B | 0.621 | 0.633 | 0.760 |
| B-norm | 0.626 | 0.698 | 0.700 |
| A+B | 0.611 | 0.669 | 0.800 |
| A+B-norm | 0.616 | 0.692 | 0.880 |

## Does Whisper autocorrect? (Baseline A)

On the 39 mispronounced clips, Whisper's transcript contained:

| the word actually said (faithful) | the correct word (autocorrected) | neither |
|---|---|---|
| 2 | 25 | 12 |

Autocorrection is the failure mode where a learner's mistake goes unnoticed because the recognizer's language prior 'fixes' it.
