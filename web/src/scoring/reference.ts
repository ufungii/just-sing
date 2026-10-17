/**
 * Turns a song manifest into what the scorer and the pitch lane need: a per-frame target track (Hz,
 * shifted by the chosen register), per-frame exclusion flags, display notes, and target onsets.
 * Pure functions: same manifest + register -> same output.
 */
import type { Note, Phrase, Register, Song } from '../lib/types';
import { SCORING_CONFIG, type ScoringConfig } from './config';
import { centsBetween } from './units';

export interface TargetTrack {
  hop: number;
  /** Target Hz per frame (frame k covers time k * hop), already register-shifted; null = reference rest. */
  hz: (number | null)[];
  /** True where the frame lies in a reviewed `excluded` region (never scored, for every player). */
  excluded: boolean[];
  /** Where the target came from: the reviewed contour, or the notes when the contour is missing. */
  source: 'hz' | 'notes';
}

/** Register shift as a frequency ratio: -12 -> 0.5, 0 -> 1, +12 -> 2. Fixed for the whole turn. */
export const registerRatio = (register: Register) => 2 ** (register / 12);

/**
 * The reviewed `reference.hz` contour is the target. It counts as missing when it is empty or stops
 * before the last phrase ends (the synthetic demo ships a 3-frame stub); then the target is drawn from
 * `reference.notes` on the same hop grid.
 */
export function hasFullContour(song: Song): boolean {
  const { hz, hop_seconds } = song.reference;
  const lastEnd = Math.max(0, ...song.phrases.map((p) => p.end));
  return hz.some((h) => h !== null) && hz.length * hop_seconds >= lastEnd - 1e-9;
}

export function buildTargetTrack(song: Song, register: Register): TargetTrack {
  const ratio = registerRatio(register);
  const hop = song.reference.hop_seconds || SCORING_CONFIG.hopSeconds;
  const useHz = hasFullContour(song);
  const frames = useHz ? song.reference.hz.length : Math.ceil(song.duration / hop);

  const hz: (number | null)[] = new Array(frames);
  const excluded: boolean[] = new Array(frames);
  for (let k = 0; k < frames; k++) {
    const t = k * hop;
    const raw = useHz ? song.reference.hz[k] : noteAt(song.reference.notes, t);
    hz[k] = raw === null || raw === undefined ? null : raw * ratio;
    excluded[k] = song.reference.excluded.some((e) => t >= e.start && t < e.end);
  }
  return { hop, hz, excluded, source: useHz ? 'hz' : 'notes' };
}

function noteAt(notes: Note[], t: number): number | null {
  for (const n of notes) if (t >= n.start && t < n.end) return n.hz;
  return null;
}

/**
 * Notes to draw (unshifted Hz). The reviewed `reference.notes` when present; otherwise runs of the
 * contour that stay within `noteChangeCents` of where they started.
 */
export function displayNotes(song: Song, cfg: ScoringConfig = SCORING_CONFIG): Note[] {
  if (song.reference.notes.length) return song.reference.notes;
  const { hz, hop_seconds: hop } = song.reference;
  const notes: Note[] = [];
  let start = -1;
  let sum = 0;
  let count = 0;
  const close = (k: number) => {
    if (start >= 0) notes.push({ start: start * hop, end: k * hop, hz: sum / count });
    start = -1;
    sum = count = 0;
  };
  for (let k = 0; k < hz.length; k++) {
    const h = hz[k];
    if (h === null) {
      close(k);
      continue;
    }
    if (start >= 0 && Math.abs(centsBetween(h, hz[start] as number)) > cfg.noteChangeCents) close(k);
    if (start < 0) start = k;
    sum += h;
    count++;
  }
  close(hz.length);
  return notes;
}

/**
 * Times the singer should come in within a phrase: the phrase entrance plus every note start inside it,
 * skipping anything in an excluded region. Register does not change timing.
 */
export function targetOnsets(song: Song, phrase: Phrase, cfg: ScoringConfig = SCORING_CONFIG): number[] {
  const isExcluded = (t: number) => song.reference.excluded.some((e) => t >= e.start && t < e.end);
  const candidates = [phrase.start, ...displayNotes(song, cfg).map((n) => n.start)]
    .filter((t) => t >= phrase.start && t < phrase.end && !isExcluded(t))
    .sort((a, b) => a - b);
  // A note starting right at the phrase entrance is the same onset, not two.
  const onsets: number[] = [];
  for (const t of candidates) if (!onsets.length || t - onsets[onsets.length - 1] > cfg.timingFullSeconds) onsets.push(t);
  return onsets;
}
