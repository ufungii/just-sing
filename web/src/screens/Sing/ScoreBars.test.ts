import { describe, expect, it } from 'vitest';
import { barPercent, barTier } from './ScoreBars';

describe('score bar helpers', () => {
  it('maps a running score to a 0-100 fill', () => {
    expect(barPercent(null)).toBe(0);
    expect(barPercent(NaN)).toBe(0);
    expect(barPercent(-5)).toBe(0);
    expect(barPercent(63.4)).toBe(63.4);
    expect(barPercent(140)).toBe(100);
  });
  it('glows above 50 and sparkles above 80', () => {
    expect([0, 50, 50.1, 80, 80.1, 100].map(barTier)).toEqual(['low', 'low', 'mid', 'mid', 'hi', 'hi']);
  });
});
