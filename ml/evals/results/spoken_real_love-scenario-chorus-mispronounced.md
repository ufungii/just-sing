# Spoken practice on a real voice: love-scenario-chorus-mispronounced

20.2 s of speech, 16 words, scored with the shipped scorer (wav2vec2 forced alignment).

| Check | Result |
|---|---|
| Overall, scored against the right text | 14.2 |
| Overall, scored against different text | 4.8 |
| One word swapped: the swapped word is the lowest in the phrase | 6/16 (chance 0.06) |
| One word swapped: median rank of the swapped word | 8 of 16 |
| One word swapped: median score drop of that word | 0 points |

Word scores against the right text: 0, 0, 33, 24, 41, 0, 28, 18, 0, 1, 3, 0, 0, 1, 0, 49.
Words scoring under 20: 11/16 (on a correct reading these are false highlights; on a deliberately mispronounced one they are the point, and the swap test above says little because most words are already low).

One speaker; a swapped word is easier to catch than a subtle mispronunciation. Not validated by a fluent speaker.
