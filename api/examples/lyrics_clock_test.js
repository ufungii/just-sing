import { activeIndices } from "./lyrics_clock.js";

Deno.test("clock boundaries, gaps, backward seeks, and invalid times", () => {
  const lines = [
    { start: 1, end: 3, words: [{ start: 1, end: 1.5 }, { start: 2, end: 3 }] },
    { start: 3, end: 4, words: [] },
  ];
  for (const [time, lineIndex, wordIndex] of [
    [0, null, null], [1, 0, 0], [1.5, 0, null], [2, 0, 1],
    [3, 1, null], [4, null, null], [8, null, null],
    [1.1, 0, 0], [3.5, 1, null], [3.5, 1, null], [NaN, null, null],
  ]) {
    const result = activeIndices(lines, time);
    if (result.lineIndex !== lineIndex || result.wordIndex !== wordIndex) {
      throw new Error(`Wrong active lyric at ${time}: ${JSON.stringify(result)}`);
    }
  }
});
