/** Output rounding must be half-even like Python's round() in ml/scoring/score.py (not in the shared fixtures yet). */
import { describe, expect, it } from 'vitest';
import { round } from './score';

describe('round matches Python round() on exact halves', () => {
  it.each([
    [1.25, 1, 1.2],
    [1.35, 1, 1.4],
    [0.5, 0, 0],
    [2.5, 0, 2],
    [1 / 16, 3, 0.062],
    [3 / 16, 3, 0.188],
    [-1.25, 1, -1.2],
  ])('round(%f, %i) = %f', (x, dp, want) => {
    expect(round(x, dp)).toBe(want);
  });
});
