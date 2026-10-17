import type { Song } from './types';

/** Mirror ml/pronunciation/eligibility.py: don't grade only the Korean part of a mixed line. */
export function isSpokenKorean(text: string): boolean {
  return /[가-힣]/u.test(text)
    && [...text].every(ch => !/[\p{L}\p{N}]/u.test(ch) || /[가-힣]/u.test(ch));
}

export function practicePhrases(song: Pick<Song, 'phrases' | 'lines'>) {
  return song.phrases.filter(p => isSpokenKorean(song.lines[p.line_index]?.practice_text ?? ''));
}
