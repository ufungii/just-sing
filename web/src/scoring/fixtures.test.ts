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
import type { TargetTrack } from './reference';
import { roundHalfEven } from './units';
import { aggregate, applyLatency, isVoiced, onsetTimes, scorePhraseSpan } from './score';

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
        register: number; latency_offset_s: number; excluded: [number, number][];
      };
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
      const results = inp.phrases.map(([id, s, e]) => scorePhraseSpan(id, s, e, target, user));
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
