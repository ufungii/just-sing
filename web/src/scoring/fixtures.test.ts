/**
 * Runs the TypeScript scoring port against the shared fixtures that the Python reference engine
 * generates (contracts/fixtures, `python -m ml.evals.make_fixtures`). A disagreement is a bug in this port.
 *
 * live_scoring.json is NOT tested here: it belongs to the older preview engine in ml/scoring/live.py and
 * web/live (own thresholds, scoring_version baseline-0.1), tested by `node web/live/live_test.js`.
 */
import { describe, expect, it } from 'vitest';
import onsetFixtures from '../../../contracts/fixtures/onset_cases.json';
import scoreFixtures from '../../../contracts/fixtures/score_cases.json';
import pronunciationFixtures from '../../../contracts/fixtures/pronunciation_cases.json';
import type { TargetTrack } from './reference';
import { SCORING_CONFIG } from './config';
import { roundHalfEven } from './units';
import { aggregate, applyLatency, isVoiced, onsetTimes, pronunciationScore, round, scorePhraseSpan, totalWithPronunciation } from './score';

type Hz = (number | null)[];

describe('onsets match onset_cases.json', () => {
  for (const c of onsetFixtures.cases) {
    it(c.name, () => {
      const got = onsetTimes(c.input.hz as Hz, c.input.hop_seconds);
      expect(got).toHaveLength(c.expected_onsets.length);
      got.forEach((t, i) => expect(Math.abs(t - c.expected_onsets[i])).toBeLessThanOrEqual(onsetFixtures.tolerance_s));
    });
  }
});

describe('scores match score_cases.json', () => {
  const tol = scoreFixtures.tolerance;
  for (const c of scoreFixtures.cases) {
    it(c.name, () => {
      const inp = c.input as {
        hop_seconds: number; ref_hz: Hz; user_hz: Hz; ref_onsets: number[]; phrases: [string, number, number][];
        register: number; latency_offset_s: number; excluded: [number, number][]; time_tolerance_s: number;
      };
      // Each fixture case records the pitch time tolerance it was generated with (the default 0.1 s, or 0 for the strict case).
      const cfg = { ...SCORING_CONFIG, timeToleranceS: inp.time_tolerance_s };
      const hop = inp.hop_seconds;
      const ratio = 2 ** (inp.register / 12);
      const excluded = inp.ref_hz.map(() => false);
      for (const [s, e] of inp.excluded) for (let k = Math.max(0, roundHalfEven(s / hop)); k < Math.min(excluded.length, roundHalfEven(e / hop)); k++) excluded[k] = true;
      const target: TargetTrack = {
        hop,
        hz: inp.ref_hz.map((v) => (isVoiced(v) ? v * ratio : null)),
        excluded,
        source: 'hz',
        onsets: inp.ref_onsets.filter((t) => !inp.excluded.some(([s, e]) => t >= s && t < e)),
      };
      const user = applyLatency(inp.user_hz, inp.latency_offset_s, hop);
      const results = inp.phrases.map(([id, s, e]) => scorePhraseSpan(id, s, e, target, user, cfg));
      const weights = new Map(results.map((r) => [r.phrase_id, r.weight]));
      const total = aggregate(results, weights);

      const exp = c.expected;
      for (const key of ['total', 'pitch', 'timing'] as const) expect(Math.abs(total[key] - exp[key]), key).toBeLessThanOrEqual(tol + 1e-9);
      exp.phrases.forEach((e, i) => {
        const g = results[i];
        expect(g.rating).toBe(e.rating);
        for (const key of ['pitch', 'timing', 'score', 'coverage'] as const) {
          if (e[key] === null) expect(g[key]).toBeNull();
          else expect(Math.abs((g[key] as number) - e[key]), `${e.phrase_id}.${key}`).toBeLessThanOrEqual(tol + 1e-9);
        }
      });
    });
  }
});

describe('pronunciation totals match pronunciation_cases.json', () => {
  for (const c of pronunciationFixtures.cases) {
    it(c.name, () => {
      const i = c.input;
      const statuses = new Map(Object.entries(i.line_statuses).map(([k, v]) => [Number(k), v as string]));
      const weights = new Map(Object.entries(i.line_weights).map(([k, v]) => [Number(k), v as number]));
      const pron = pronunciationScore(statuses, weights);
      expect(pron).toBe(c.expected.pronunciation);
      // Same operation order as Python, so the total must match exactly (no tolerance).
      expect(totalWithPronunciation({ ...i, timing: i.timing ?? 0 }, pron, { hasTiming: i.timing !== null })).toBe(c.expected.total);
    });
  }
});

describe('rounding matches Python round(x, 1)', () => {
  it.each([[0.15, 0.1], [0.65, 0.7], [6.8500000000000005, 6.9], [21.95, 21.9], [0.25, 0.2], [0.35, 0.3], [2.5, 2.5]])('%s', (x, want) => {
    expect(round(x, 1)).toBe(want);
  });
});
describe('pronunciationScore edge cases', () => {
  it('skips NaN weights and unknown or inherited status names', () => {
    expect(pronunciationScore(new Map([[1, 'match']]), new Map([[0, NaN], [1, 50]]))).toBe(100);
    expect(pronunciationScore(new Map([[0, 'constructor'], [1, 'match']]), new Map([[0, 50], [1, 50]]))).toBe(100);
  });
  it('rejects an out-of-range value', () => {
    expect(() => totalWithPronunciation({ total: 80, pitch: 80, timing: 80 }, 120)).toThrow(RangeError);
  });
});
