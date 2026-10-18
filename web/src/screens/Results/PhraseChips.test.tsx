import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import type { PhraseScore, Song } from '../../lib/types';
import { PhraseChips, ScoreSummary, pronunciationVerdict } from './PhraseChips';

const song = {
  lines: [
    { text: '첫 줄', romanized: 'cheot jul', practice_text: '첫 줄' },
    { text: '둘째 줄', romanized: 'duljjae jul', practice_text: '둘째 줄' },
    { text: 'baby 셋째', romanized: 'baby setjjae', practice_text: 'baby 셋째' }, // mixed: no spoken practice
  ],
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

it('offers spoken practice only on unclear lines that can be practised', () => {
  const noop = () => {};
  const lyrics = new Map([[0, 'match'], [1, 'unclear'], [2, 'unclear']] as const);
  const html = renderToStaticMarkup(<PhraseChips phrases={phrases} song={song} lyrics={new Map(lyrics)} onPractice={noop} />);
  expect(html.match(/class="results-say"/g)).toHaveLength(1); // line 1 only: line 0 matched, line 2 mixes English
  expect(renderToStaticMarkup(<PhraseChips phrases={phrases} song={song} lyrics={new Map(lyrics)} />)).not.toContain('results-say');
});

it('shows a LYRICS bar beside pitch and timing, or a dash when lyrics were not checked', () => {
  const html = renderToStaticMarkup(<ScoreSummary total={61} pitch={64} timing={50} lyrics={{ matched: 9, graded: 12, score: 78.4 }} />);
  expect(html).toContain('LYRICS');
  expect(html).toContain('78'); // the pronunciation score on the bar
  expect(html).toContain('Pronunciation: MIXED');
  expect(html).toContain('9 of 12 sung lines sounded like the original');
  expect(html).toContain('Total score 61 out of 100');
  expect(renderToStaticMarkup(<ScoreSummary total={61} pitch={64} timing={50} />)).not.toContain('LYRICS');
  expect(renderToStaticMarkup(<ScoreSummary total={61} pitch={64} timing={50} lyrics="unavailable" />)).toContain('Lyrics not checked');
});

it('puts the pronunciation score into plain words', () => {
  expect([95, 80, 79.9, 50, 49.9, 0].map(pronunciationVerdict)).toEqual(['CLEAR', 'CLEAR', 'MIXED', 'MIXED', 'UNCLEAR', 'UNCLEAR']);
  const unclear = renderToStaticMarkup(<ScoreSummary total={40} pitch={60} timing={50} lyrics={{ matched: 1, graded: 6, score: 12 }} />);
  expect(unclear).toContain('Pronunciation: UNCLEAR');
});
