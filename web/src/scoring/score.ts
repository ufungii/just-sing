/**
 * Live phrase scoring: pure, deterministic functions over a target track and a user pitch track.
 *
 * Port of the Python reference engine (ml/scoring/score.py, pitch.py, timing.py), written from
 * ml/scoring/SPEC.md. `npm test` (src/scoring/fixtures.test.ts) runs it against the shared fixtures in
 * contracts/fixtures. Never change the math here without changing Python and the fixtures together.
 *
 * Inputs are on the hop grid in clip time: userHz[k] is the user's pitch at k * hop seconds, with the
 * single device latency already removed (the PitchTracker does it while capturing; `applyLatency` is the
 * same shift for offline use and the fixtures). Nothing here fits a per-take offset, and there is no DTW.
 */
import type { Phrase, PhraseScore, Rating } from '../lib/types';
import { SCORING_CONFIG, type ScoringConfig } from './config';
import type { TargetTrack } from './reference';
import { centsBetween, roundHalfEven } from './units';

export { centsBetween };

type Track = (number | null | undefined)[];

/** Voiced = finite and > 0; null, undefined, NaN and <= 0 all mean unvoiced (SPEC section 1). */
export const isVoiced = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v) && v > 0;

const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));
/** Output rounding, half-even like Python's round() in ml/scoring/score.py (1.25 -> 1.2, not 1.3). */
export function round(x: number, dp: number): number {
  // Python rounds the exact binary value. Multiplying first can create a fake .5 (0.15 * 10 = 1.5), so only a
  // dyadic x (a multiple of 2^-(dp+1), where x * 10^dp is exact) can be a real tie, and gets half-even; any
  // other x is rounded by toFixed, which rounds the exact value.
  return Number.isInteger(x * 2 ** (dp + 1)) ? roundHalfEven(x * 10 ** dp) / 10 ** dp : Number(x.toFixed(dp));
}

/** Soft pitch credit in [0, 1] for one frame. */
export function pitchCredit(cents: number, cfg: ScoringConfig = SCORING_CONFIG): number {
  return clamp((cfg.pitchZeroCents - Math.abs(cents)) / (cfg.pitchZeroCents - cfg.pitchFullCents), 0, 1);
}

/** Soft timing credit in [0, 1] for one matched onset. */
export function timingCredit(errorSeconds: number, cfg: ScoringConfig = SCORING_CONFIG): number {
  return clamp((cfg.timingZeroSeconds - Math.abs(errorSeconds)) / (cfg.timingZeroSeconds - cfg.timingFullSeconds), 0, 1);
}

/** Frame range [from, to) covered by a phrase, on the hop grid. */
export function phraseFrames(phrase: { start: number; end: number }, hop: number): [number, number] {
  return [roundHalfEven(phrase.start / hop), roundHalfEven(phrase.end / hop)];
}

/** Undo the fixed device delay: drop the first round(offset / hop) frames, pad the end unvoiced (SPEC 3.1). */
export function applyLatency(userHz: Track, latencySeconds: number, hop: number): Track {
  const n = roundHalfEven(latencySeconds / hop);
  return n > 0 ? [...userHz.slice(n), ...new Array<null>(n).fill(null)] : userHz;
}

/** Median; for an even count the mean of the two middle values (SPEC section 5). */
function median(values: number[]): number {
  const s = [...values].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/**
 * Times (s) where a new stable note or voiced stretch begins: `stableFrames` consecutive voiced frames
 * within `stableCents` of their median, starting a new stable run, at least `minOnsetGapSeconds` apart.
 */
export function onsetTimes(track: Track, hop: number, cfg: ScoringConfig = SCORING_CONFIG): number[] {
  const n = track.length;
  const L = cfg.stableFrames;
  const stable = new Array<boolean>(n).fill(false);
  for (let i = 0; i + L <= n; i++) {
    const w: number[] = [];
    for (let j = i; j < i + L; j++) {
      const v = track[j];
      if (!isVoiced(v)) break;
      w.push(v);
    }
    if (w.length < L) continue;
    const med = median(w);
    stable[i] = w.every((v) => Math.abs(1200 * Math.log2(v / med)) <= cfg.stableCents);
  }
  const gap = roundHalfEven(cfg.minOnsetGapSeconds / hop);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    if (stable[i] && (i === 0 || !stable[i - 1]) && (!out.length || i - out[out.length - 1] >= gap)) out.push(i);
  }
  return out.map((i) => i * hop);
}

/** Mean timing credit of reference onsets, each matched greedily to the nearest unused user onset in the window. */
function matchOnsets(ref: number[], user: number[], cfg: ScoringConfig): number {
  const used = new Array<boolean>(user.length).fill(false);
  let sum = 0;
  for (const r of ref) {
    let best = -1;
    for (let j = 0; j < user.length; j++) {
      if (!used[j] && (best < 0 || Math.abs(user[j] - r) < Math.abs(user[best] - r))) best = j;
    }
    if (best < 0 || Math.abs(user[best] - r) > cfg.matchWindowSeconds) continue; // missed entrance: 0 credit, still counted
    used[best] = true;
    sum += timingCredit(user[best] - r, cfg);
  }
  return sum / ref.length;
}

export function rate(score: number, coverage: number, cfg: ScoringConfig = SCORING_CONFIG): Rating {
  if (coverage < cfg.minCoverage) return 'miss';
  if (score >= cfg.perfect) return 'perfect';
  if (score >= cfg.great) return 'great';
  if (score >= cfg.okay) return 'okay';
  return 'bad';
}

/** Scoreable reference frames per phrase id: the weight of that phrase in the totals. */
export function phraseWeights(phrases: { id: string; start: number; end: number }[], target: TargetTrack): Map<string, number> {
  return new Map(
    phrases.map((p) => {
      const [from, to] = phraseFrames(p, target.hop);
      let n = 0;
      for (let k = Math.max(0, from); k < Math.min(to, target.hz.length); k++) if (isVoiced(target.hz[k]) && !target.excluded[k]) n++;
      return [p.id, n];
    }),
  );
}

/** The last clip time (s) whose user frames a phrase's score depends on; rate the phrase only after this. */
export const phraseSettlesAt = (phrase: { end: number }, cfg: ScoringConfig = SCORING_CONFIG) =>
  phrase.end + cfg.matchWindowSeconds + cfg.stableFrames * cfg.hopSeconds + cfg.timeToleranceS;

/** Score one phrase of a turn (SPEC sections 4-7). pitch/timing/score 1 dp, coverage 3 dp; timing is null with no onset in the phrase. */
export function scorePhraseSpan(
  id: string,
  start: number,
  end: number,
  target: TargetTrack,
  userHz: Track,
  cfg: ScoringConfig = SCORING_CONFIG,
): PhraseScore & { weight: number } {
  const { hop } = target;
  const n = target.hz.length;
  const [from, to] = phraseFrames({ start, end }, hop);
  const k = roundHalfEven(cfg.timeToleranceS / hop);

  // The phrase's scoreable frames: rests and exclusions are not in the denominator.
  const frames: number[] = [];
  for (let i = Math.max(0, from); i < Math.min(to, n); i++) if (isVoiced(target.hz[i]) && !target.excluded[i]) frames.push(i);
  const scoreable = frames.length;

  // ONE shift of the user's track within +/- timeToleranceS for the whole phrase (SPEC section 4): the shift with
  // the most pitch credit; ties keep the smallest |shift|, then the negative one. A consistent small lateness is
  // forgiven (timing still scores it) but jitter cannot pick the luckiest frame at every position. The track is
  // read up to k frames beyond the reference length so a shift can reach the tail of a late take.
  const shifts: number[] = [];
  for (let off = -k; off <= k; off++) shifts.push(off);
  shifts.sort((x, y) => Math.abs(x) - Math.abs(y) || x - y);
  let credit = 0;
  let voiced = 0;
  let bestTotal = -1;
  for (const off of shifts) {
    let total = 0;
    let seen = 0;
    for (const i of frames) {
      const j = i + off;
      const u = j >= 0 && j < n + k ? userHz[j] : null;
      if (!isVoiced(u)) continue;
      seen++;
      total += pitchCredit(centsBetween(u, target.hz[i] as number), cfg);
    }
    if (total > bestTotal) { bestTotal = total; credit = total; voiced = seen; }
  }
  const pitch = scoreable ? (100 * credit) / scoreable : 0;
  const coverage = scoreable ? voiced / scoreable : 0;

  const refOnsets = target.onsets.filter((t) => t >= start && t < end).sort((a, b) => a - b);
  const timing = refOnsets.length ? 100 * matchOnsets(refOnsets, onsetTimes(userHz, hop, cfg), cfg) : null;

  const score = timing === null ? pitch : cfg.pitchWeight * pitch + cfg.timingWeight * timing;
  return {
    phrase_id: id,
    pitch: round(pitch, 1),
    timing: timing === null ? null : round(timing, 1),
    score: round(score, 1),
    coverage: round(coverage, 3),
    rating: rate(score, coverage, cfg), // from the unrounded values
    weight: scoreable,
  };
}

/** Score one manifest phrase for the live game. */
export function scorePhrase(phrase: Phrase, target: TargetTrack, userHz: Track, cfg: ScoringConfig = SCORING_CONFIG): PhraseScore {
  const { weight: _weight, ...result } = scorePhraseSpan(phrase.id, phrase.start, phrase.end, target, userHz, cfg);
  return result;
}

/**
 * Totals as ml/scoring/score.py aggregate(): the mean of the rounded phrase values weighted by scoreable
 * reference frames (rests earn nothing); phrases with null timing are left out of the timing mean. With
 * only some phrases (a running score mid-song) the mean is over those phrases.
 */
export function aggregate(phrases: PhraseScore[], weights: Map<string, number>) {
  const mean = (get: (p: PhraseScore) => number | null) => {
    let sum = 0;
    let w = 0;
    for (const p of phrases) {
      const v = get(p);
      const weight = weights.get(p.phrase_id) ?? 0;
      if (v === null || weight <= 0) continue;
      sum += v * weight;
      w += weight;
    }
    return w ? round(sum / w, 1) : 0;
  };
  return { total: mean((p) => p.score), pitch: mean((p) => p.pitch), timing: mean((p) => p.timing) };
}

/** Phrase score for display; the engine already computed it. */
export const phraseTotal = (p: PhraseScore) => p.score;

/**
 * Lyric score 0-100 from the lyric check's per-line statuses, weighted by each line's scoreable frames
 * (ml/scoring/score.py pronunciation_score). Null when nothing was checked: the caller keeps the
 * pitch/timing total, because an unavailable check is never a low score.
 */
export function pronunciationScore(statuses: Map<number, string>, weights: Map<number, number>, cfg: ScoringConfig = SCORING_CONFIG): number | null {
  let sum = 0;
  let w = 0;
  for (const [line, status] of statuses) {
    const weight = weights.get(line) ?? 0;
    if (!Object.hasOwn(cfg.lyricCredit, status) || !(weight > 0)) continue; // unknown status or NaN/zero weight: skipped, as in Python
    const credit = cfg.lyricCredit[status];
    sum += credit * weight;
    w += weight;
  }
  return w ? round(sum / w, 1) : null;
}

/** Final turn total with the lyric score blended in and the humming guard applied (score.py apply_pronunciation). */
export function totalWithPronunciation(
  t: { total: number; pitch: number; timing: number },
  pronunciation: number | null,
  opts: { hasTiming?: boolean } = {},
  cfg: ScoringConfig = SCORING_CONFIG,
): number {
  if (pronunciation === null) return t.total;
  if (!Number.isFinite(pronunciation) || pronunciation < 0 || pronunciation > 100) throw new RangeError('pronunciation must be a finite number in [0, 100]');
  const timing = opts.hasTiming === false ? t.pitch : t.timing; // no onsets anywhere: pitch stands in for timing
  const blend = cfg.totalPitchWeight * t.pitch + cfg.totalTimingWeight * timing + cfg.totalPronunciationWeight * pronunciation;
  // Same operation order as Python (apply_pronunciation) so the two agree to the last bit.
  return round(blend * (cfg.pronunciationFloor + ((1 - cfg.pronunciationFloor) * pronunciation) / 100), 1);
}
