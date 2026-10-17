import { expect, test } from 'vitest';
import { practicePhrases } from './practicePhrases';
import type { Song } from './types';

test('filters English/display-only exercises without changing singing phrases', () => {
  const song = {lines:[{practice_text:''},{practice_text:'안녕'},{practice_text:' '}],
    phrases:[{id:'english',line_index:0},{id:'korean',line_index:1},{id:'blank',line_index:2}]} as Song;
  expect(practicePhrases(song).map((p) => p.id)).toEqual(['korean']);
  expect(song.phrases).toHaveLength(3);
});
