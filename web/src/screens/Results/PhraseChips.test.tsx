import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import type { PhraseScore, Song } from '../../lib/types';
import { PhraseChips } from './PhraseChips';

const song = {
  lines: [{ text: '첫 줄', romanized: 'cheot jul' }, { text: '둘째 줄', romanized: 'duljjae jul' }, { text: '셋째', romanized: 'setjjae' }],
  phrases: [{ id: 'p1', line_index: 0 }, { id: 'p2', line_index: 1 }, { id: 'p3', line_index: 2 }],
} as unknown as Song;
const phrase = (id: string): PhraseScore => ({ phrase_id: id, pitch: 70, timing: 60, coverage: 0.9, rating: 'great' } as PhraseScore);
const phrases = ['p1', 'p2', 'p3'].map(phrase);

it('marks each lyric line by its lyric-check status without touching the rating', () => {
  const html = renderToStaticMarkup(<PhraseChips phrases={phrases} song={song} lyrics={new Map([[0, 'match'], [1, 'unclear'], [2, 'not_covered']])} />);
  expect(html).toContain('results-lyric--match');
  expect(html).toContain('LYRICS ♪');
  expect(html).toContain('results-lyric--unclear');
  expect(html).toContain('words?');
  expect(html).not.toContain('results-lyric-tag--not_covered'); // nothing shown for lines outside the take
  expect(html.match(/GREAT/g)).toHaveLength(3); // ratings unchanged
});

it('shows plain lyrics when there is no lyric check', () => {
  const html = renderToStaticMarkup(<PhraseChips phrases={phrases} song={song} />);
  expect(html).not.toContain('results-lyric');
});
