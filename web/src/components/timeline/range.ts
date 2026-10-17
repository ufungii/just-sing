import type { Phrase, TimeRange } from '../../lib/types';

export const RANGE_EPS = 0.05;
export const includedPhrases = <T extends Pick<Phrase, 'start' | 'end'>>(phrases: T[], range?: TimeRange | null): T[] =>
  range ? phrases.filter((p) => p.start >= range.start - RANGE_EPS && p.end <= range.end + RANGE_EPS) : phrases;

/** Commit whole-phrase edges, matching the API's persisted section and full-clip reset. */
export function normalizeRange(phrases: Pick<Phrase, 'start' | 'end'>[], range: TimeRange | null): TimeRange | null {
  const selected = includedPhrases(phrases, range);
  return selected.length && selected.length < phrases.length
    ? { start: Math.min(...selected.map((p) => p.start)), end: Math.max(...selected.map((p) => p.end)) }
    : null;
}

/** Only offer boundaries that leave at least one entire phrase inside the selection. */
export function boundaries(phrases: Pick<Phrase, 'start' | 'end'>[], range: TimeRange, edge: 'start' | 'end'): number[] {
  return [...new Set(phrases.filter((p) => edge === 'start' ? p.end <= range.end + RANGE_EPS : p.start >= range.start - RANGE_EPS)
    .map((p) => p[edge]))].sort((a, b) => a - b);
}

export function snapBoundary(values: number[], time: number): number {
  return values.reduce((best, v) => Math.abs(v - time) < Math.abs(best - time) ? v : best, values[0]);
}

export const rangeLabel = (range: TimeRange) => `${range.start.toFixed(1)}–${range.end.toFixed(1)} s`;
