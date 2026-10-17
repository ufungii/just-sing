import type { Song } from './types';

/** Singing eligibility does not imply a Korean pronunciation exercise. */
export function practicePhrases(song: Song) {
  return song.phrases.filter((phrase) => song.lines[phrase.line_index]?.practice_text.trim());
}
