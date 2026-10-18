import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import type { MatchView, Score, Song } from '../../lib/types';
import { MatchBoard } from './BattleTurn';

const score = (total: number, lyrics: Score['lyrics']) => ({ total, pitch: total, timing: total, phrases: [], lyrics } as unknown as Score);
const match = (a: Score['lyrics'], b: Score['lyrics']) => ({ id: 'match', state: 'finished', winner_slot: 0,
  players: [{ slot: 0, display_name: 'Alice' }, { slot: 1, display_name: 'Bo' }],
  attempts: [{ slot: 0, state: 'accepted', score: score(80, a) }, { slot: 1, state: 'accepted', score: score(60, b) }],
} as MatchView);

it('renders separate lyric bars per singer without changing either total or winner', () => {
  const html = renderToStaticMarkup(<MatchBoard song={null} match={match(
    { status: 'ok', lines: [{ line_index: 0, status: 'match' }, { line_index: 2, status: 'unclear' }] },
    { status: 'ok', lines: [{ line_index: 1, status: 'match' }] },
  )} />);
  expect(html.match(/aria-label="LYRICS"/g)).toHaveLength(2);
  expect(html).toContain('1 of 2 sung lines');
  expect(html).toContain('1 of 1 sung lines');
  expect(html).toContain('Pronunciation: MIXED');
  expect(html).toContain('Pronunciation: CLEAR');
  expect(html).toContain('Total score 80 out of 100');
  expect(html).toContain('Total score 60 out of 100');
  expect(html).toContain('Alice WINS!');
});

it('keeps each bar visible while checking or when lyrics could not be checked', () => {
  const html = renderToStaticMarkup(<MatchBoard song={null} match={match({ status: 'pending', lines: [] }, null)} />);
  expect(html.match(/aria-label="LYRICS"/g)).toHaveLength(2);
  expect(html).toContain('Checking this singer');
  expect(html).toContain('Lyrics not checked');
});

it('weights pronunciation by only each singer’s saved phrases', () => {
  const song = { duration: 4,
    reference: { hop_seconds: 0.02, hz: Array(200).fill(220), notes: [], excluded: [] },
    lines: [0, 1, 2].map((i) => ({ text: `line ${i}`, romanized: '', practice_text: '' })),
    phrases: [{ id: 'a', start: 0, end: 1, line_index: 0 },
      { id: 'b', start: 1, end: 3, line_index: 1 }, { id: 'c', start: 3, end: 4, line_index: 2 }],
  } as unknown as Song;
  const view = match({ status: 'ok', lines: [{ line_index: 0, status: 'match' }, { line_index: 1, status: 'unclear' }] },
    { status: 'ok', lines: [{ line_index: 2, status: 'match' }] });
  for (const [slot, ids] of [['a', 'b'], ['c']].entries()) {
    view.attempts[slot].score!.register = 0;
    view.attempts[slot].score!.phrases = ids.map((phrase_id) => ({ phrase_id, pitch: 80, timing: 80, score: 80, coverage: 1, rating: 'great' }));
  }
  const html = renderToStaticMarkup(<MatchBoard match={view} song={song} />);
  expect(html).toContain('aria-label="LYRICS" aria-valuemin="0" aria-valuemax="100" aria-valuenow="33"');
  expect(html).toContain('Pronunciation: UNCLEAR');
  expect(html).toContain('Pronunciation: CLEAR');
  expect(html).toContain('Total score 80 out of 100');
});
