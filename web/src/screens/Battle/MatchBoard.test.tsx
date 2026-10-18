import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import type { MatchView, Score } from '../../lib/types';
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
