# Spoken practice on a real voice: love-scenario-chorus

12.2 s of speech, 16 words, scored with the shipped scorer (wav2vec2 forced alignment).

| Check | Result |
|---|---|
| Overall, scored against the right text | 78.2 |
| Overall, scored against different text | 5.9 |
| One word swapped: the swapped word is the lowest in the phrase | 14/16 (chance 0.06) |
| One word swapped: median rank of the swapped word | 1 of 16 |
| One word swapped: median score drop of that word | 76 points |

Word scores against the right text: 82, 100, 100, 100, 94, 100, 73, 52, 66, 79, 0, 98, 67, 71, 0, 100.
Words scoring under 20: 2/16 (on a correct reading these are false highlights; on a deliberately mispronounced one they are the point, and the swap test above says little because most words are already low).

One speaker; a swapped word is easier to catch than a subtle mispronunciation. Not validated by a fluent speaker.
