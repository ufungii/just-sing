/**
 * Live phrase scoring: pure, deterministic functions over a target track and a user pitch track.
 *
 * PROVISIONAL PORT. CLAUDE.md says the Python engine in ml/scoring is the reference implementation and
 * both languages must pass the shared fixtures in contracts/fixtures. Neither exists yet, so this file
 * implements the written spec directly and is meant to be replaced (or corrected) once they land:
 *
 * - Pitch: for every voiced, non-excluded reference frame, error in cents = 1200 * log2(user / target).
 *   Full credit within `pitchFullCents`, linear to zero at `pitchZeroCents`. Missing / unvoiced user
 *   frames earn 0 but stay in the denominator; rests and excluded frames are not in it. Every frame is
 *   one hop long, so the mean over frames is duration-weighted.
 * - Timing: the singer's voiced onsets are matched one-to-one with target onsets (phrase entrance and
 *   note changes). Credit by absolute error, full within `timingFullSeconds`, zero at
 *   `timingZeroSeconds`; an unmatched target onset earns 0. Silence therefore scores 0 here too.
 *   The single device offset is removed before the user track reaches this file; nothing here fits a
 *   per-take offset, and there is no DTW.
 * - Coverage: share of scoreable frames the user voiced. Below `missCoverage` the phrase is a MISS.
 * - Phrase score = pitchWeight * pitch + (1 - pitchWeight) * timing, rated by the config bands.
 *
 * Inputs are already in clip time on the hop grid: userHz[k] is the user's pitch at k * hop seconds.
 */
import type { Phrase, PhraseScore, Rating, Song } from '../lib/types';
import { SCORING_CONFIG, type ScoringConfig } from './config';
import type { TargetTrack } from './reference';
import { targetOnsets } from './reference';
import { centsBetween } from './units';

export { centsBetween };

/** Soft pitch credit in [0, 1] for one frame. */
export function pitchCredit(cents: number, cfg: ScoringConfig = SCORING_CONFIG): number {
  const e = Math.abs(cents);
  if (e <= cfg.pitchFullCents) return 1;
  if (e >= cfg.pitchZeroCents) return 0;
  return (cfg.pitchZeroCents - e) / (cfg.pitchZeroCents - cfg.pitchFullCents);
}

/** Soft timing credit in [0, 1] for one matched onset. */
export function timingCredit(errorSeconds: number, cfg: ScoringConfig = SCORING_CONFIG): number {
  const e = Math.abs(errorSeconds);
  if (e <= cfg.timingFullSeconds) return 1;
  if (e >= cfg.timingZeroSeconds) return 0;
  return (cfg.timingZeroSeconds - e) / (cfg.timingZeroSeconds - cfg.timingFullSeconds);
}

/** Frame range [from, to) covered by a phrase, on the hop grid. */
export function phraseFrames(phrase: Phrase, hop: number): [number, number] {
  return [Math.round(phrase.start / hop), Math.round(phrase.end / hop)];
}

/**
 * Times where the singer starts a new sung note: voice appears after silence, or the pitch jumps by
 * more than `onsetJumpCents` and is then held. Each onset must be followed by `onsetMinFrames` voiced
 * frames, and onsets are at least that many frames apart, so blips and glides do not spray onsets.
 */
export function userOnsets(userHz: (number | null)[], hop: number, from = 0, to = userHz.length, cfg: ScoringConfig = SCORING_CONFIG): number[] {
  const m = cfg.onsetMinFrames;
  const onsets: number[] = [];
  let last = -Infinity;
  for (let k = Math.max(0, from); k < Math.min(to, userHz.length); k++) {
    const h = userHz[k];
    if (h === null || k - last < m) continue;
    const prev = k > 0 ? userHz[k - 1] : null;
    const isEntry = prev === null || prev === undefined;
    const isJump = !isEntry && Math.abs(centsBetween(h, prev)) > cfg.onsetJumpCents;
    if (!isEntry && !isJump) continue;
    let held = true;
    for (let j = 1; j < m; j++) {
      const next = userHz[k + j];
      if (next === null || next === undefined || Math.abs(centsBetween(next, h)) > cfg.onsetJumpCents) {
        held = false;
        break;
      }
    }
    if (held) {
      onsets.push(k * hop);
      last = k;
    }
  }
  return onsets;
}

/** Mean timing credit of target onsets, each matched to the nearest unused user onset within the search window. */
export function timingScore(targets: number[], user: number[], cfg: ScoringConfig = SCORING_CONFIG): number {
  if (!targets.length) return 0;
  const used = new Set<number>();
  let sum = 0;
  for (const t of targets) {
    let best = -1;
    for (let i = 0; i < user.length; i++) {
      if (used.has(i) || Math.abs(user[i] - t) > cfg.onsetSearchSeconds) continue;
      if (best < 0 || Math.abs(user[i] - t) < Math.abs(user[best] - t)) best = i;
    }
    if (best >= 0) {
      used.add(best);
      sum += timingCredit(user[best] - t, cfg);
    }
  }
  return sum / targets.length;
}

export function rate(score: number, coverage: number, cfg: ScoringConfig = SCORING_CONFIG): Rating {
  if (coverage < cfg.missCoverage) return 'miss';
  for (const band of cfg.bands) if (score >= band.min) return band.rating;
  return 'bad';
}

const round = (x: number, dp: number) => Math.round(x * 10 ** dp) / 10 ** dp;

/** The last clip time (s) whose user frames a phrase's score depends on; rate the phrase only after this. */
export const phraseSettlesAt = (phrase: Phrase, cfg: ScoringConfig = SCORING_CONFIG) => phrase.end + cfg.onsetSearchSeconds;

/** Score one phrase. Pitch and timing are 0-100 (2 dp), coverage 0-1 (4 dp). */
export function scorePhrase(
  song: Song,
  phrase: Phrase,
  target: TargetTrack,
  userHz: (number | null)[],
  cfg: ScoringConfig = SCORING_CONFIG,
): PhraseScore {
  const [from, to] = phraseFrames(phrase, target.hop);
  let scoreable = 0;
  let voiced = 0;
  let credit = 0;
  for (let k = from; k < to; k++) {
    const t = target.hz[k];
    if (t === null || t === undefined || target.excluded[k]) continue; // rests and exclusions: not in the denominator
    scoreable++;
    const u = userHz[k];
    if (u === null || u === undefined) continue; // unvoiced: 0 credit, still counted
    voiced++;
    credit += pitchCredit(centsBetween(u, t), cfg);
  }
  if (scoreable === 0) {
    // A phrase with nothing to sing is a manifest problem; it earns nothing rather than free points.
    console.warn(`[scoring] phrase ${phrase.id} has no scoreable reference frames`);
    return { phrase_id: phrase.id, rating: 'miss', pitch: 0, timing: 0, coverage: 0 };
  }

  const pitch = (100 * credit) / scoreable;
  const coverage = voiced / scoreable;
  const search = Math.round(cfg.onsetSearchSeconds / target.hop);
  const onsets = userOnsets(userHz, target.hop, from - search, to + search, cfg);
  const timing = 100 * timingScore(targetOnsets(song, phrase, cfg), onsets, cfg);
  const score = cfg.pitchWeight * pitch + (1 - cfg.pitchWeight) * timing;

  return { phrase_id: phrase.id, rating: rate(score, coverage, cfg), pitch: round(pitch, 2), timing: round(timing, 2), coverage: round(coverage, 4) };
}

/** Combined phrase score (0-100) from a rounded phrase result, for display. */
export const phraseTotal = (p: PhraseScore, cfg: ScoringConfig = SCORING_CONFIG) => round(cfg.pitchWeight * p.pitch + (1 - cfg.pitchWeight) * p.timing, 2);

/**
 * Totals exactly as api/play.py recomputes them: duration-weighted means of the phrase pitch and timing
 * (rounded to 2 dp), then total = pitchWeight * pitch + (1 - pitchWeight) * timing.
 * With only some phrases (a running score mid-song) the mean is over those phrases.
 */
export function aggregate(song: Song, phrases: PhraseScore[], cfg: ScoringConfig = SCORING_CONFIG) {
  const duration = new Map(song.phrases.map((p) => [p.id, p.end - p.start]));
  const scored = phrases.filter((p) => duration.has(p.phrase_id));
  const time = scored.reduce((s, p) => s + (duration.get(p.phrase_id) as number), 0);
  if (!time) return { total: 0, pitch: 0, timing: 0 };
  const mean = (f: (p: PhraseScore) => number) => scored.reduce((s, p) => s + f(p) * (duration.get(p.phrase_id) as number), 0) / time;
  const pitch = round(mean((p) => p.pitch), 2);
  const timing = round(mean((p) => p.timing), 2);
  return { total: round(cfg.pitchWeight * pitch + (1 - cfg.pitchWeight) * timing, 2), pitch, timing };
}
