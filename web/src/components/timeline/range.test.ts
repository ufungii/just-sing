import { describe, expect, it } from 'vitest';
import { boundaries, includedPhrases, normalizeRange, snapBoundary } from './range';

const phrases = [
  { id: 'a', start: 1, end: 4 },
  { id: 'b', start: 5, end: 9 },
  { id: 'c', start: 8, end: 12 },
  { id: 'd', start: 14, end: 19 },
];

describe('phrase selection', () => {
  it('keeps only whole phrases, using the same 50ms edge slack as the API', () => {
    expect(includedPhrases(phrases, { start: 4.97, end: 12.02 }).map((p) => p.id)).toEqual(['b', 'c']);
    expect(includedPhrases(phrases, { start: 5.1, end: 11.9 })).toEqual([]);
    expect(includedPhrases(phrases, null)).toBe(phrases);
  });
  it('never offers a handle position that leaves no entire phrase, including overlaps and gaps', () => {
    expect(boundaries(phrases, { start: 5, end: 9 }, 'start')).toEqual([1, 5]);
    expect(boundaries(phrases, { start: 8, end: 19 }, 'end')).toEqual([12, 19]);
    expect(snapBoundary([1, 5, 8], 6.2)).toBe(5);
  });
  it('normalizes both ends even when only one handle was moved, and resets all phrases to full clip', () => {
    expect(normalizeRange(phrases, { start: 5, end: 20 })).toEqual({ start: 5, end: 19 });
    expect(normalizeRange(phrases, { start: 0, end: 9 })).toEqual({ start: 1, end: 9 });
    expect(normalizeRange(phrases, { start: 0, end: 20 })).toBeNull();
    expect(normalizeRange(phrases, null)).toBeNull();
  });
});
