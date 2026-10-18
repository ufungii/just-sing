import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import type { Line } from '../../lib/types';
import { Lyrics, type LineVerdicts } from './Lyrics';

const line = (text: string, start: number, end: number) => ({ text, start, end, romanized: '', translation: '', practice_text: text, words: [] }) as Line;
const lines = [line('사랑을 했다', 0, 2), line('우리가 만나', 3, 5), line('그거면 됐다', 6, 8)];
const render = (t: number, verdicts?: LineVerdicts) =>
  renderToStaticMarkup(<Lyrics lines={lines} t={t} showRoman={false} showTrans={false} verdicts={verdicts} />);

it('highlights the line just sung as soon as its lyric check arrives', () => {
  const matched = render(3.5, new Map([[lines[0], 'match']]));
  expect(matched).toContain('sing-lyrics__last is-match');
  expect(matched).toContain('LYRICS ✓');
  expect(matched).toContain('우리가 만나'); // the current line still plays below it
  const unclear = render(5.5, new Map([[lines[0], 'match'], [lines[1], 'unclear']]));
  expect(unclear).toContain('sing-lyrics__last is-unclear'); // now the second line is the one just sung
  expect(unclear).toContain('words?');
});

it('shows nothing extra before any line is sung or without a lyric check', () => {
  expect(render(1)).not.toContain('sing-lyrics__last');
  expect(render(3.5)).not.toContain('sing-lyrics__last');
  expect(render(3.5, new Map())).not.toContain('sing-lyrics__last');
  expect(render(3.5, new Map())).not.toMatch(/checking/i);
});
