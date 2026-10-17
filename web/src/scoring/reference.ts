/**
 * Turns a song manifest into what the scorer and the pitch lane need: a per-frame target track (Hz,
 * shifted by the chosen register), per-frame exclusion flags, display notes, and target onsets.
 * Pure functions: same manifest + register -> same output.
 */
import type { Note, Register, Song } from '../lib/types';
import { SCORING_CONFIG, type ScoringConfig } from './config';
import { onsetTimes } from './score';
import { centsBetween, roundHalfEven } from './units';

export interface TargetTrack {
  hop: number;
  /** Target Hz per frame (frame k covers time k * hop), already register-shifted; null = reference rest. */
  hz: (number | null)[];
  /** True where the frame lies in a reviewed `excluded` region (never scored, for every player). */
  excluded: boolean[];
  /** Where the target came from: the reviewed contour, or the notes when the contour is missing. */
  source: 'hz' | 'notes';
  /** Reference note starts (s), outside excluded regions. Register does not change timing. */
  onsets: number[];
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

export function buildTargetTrack(song: Song, register: Register, cfg: ScoringConfig = SCORING_CONFIG): TargetTrack {
  const ratio = registerRatio(register);
  const hop = song.reference.hop_seconds || SCORING_CONFIG.hopSeconds;
  const useHz = hasFullContour(song);
  const frames = useHz ? song.reference.hz.length : Math.ceil(song.duration / hop);

  const hz: (number | null)[] = new Array(frames);
  const excluded: boolean[] = new Array<boolean>(frames).fill(false);
  for (let k = 0; k < frames; k++) {
    const raw = useHz ? song.reference.hz[k] : noteAt(song.reference.notes, k * hop);
    hz[k] = raw === null || raw === undefined ? null : raw * ratio;
  }
  // Excluded regions cover frames [round(start / hop), round(end / hop)) (SPEC section 4).
  for (const e of song.reference.excluded) {
    for (let k = Math.max(0, roundHalfEven(e.start / hop)); k < Math.min(frames, roundHalfEven(e.end / hop)); k++) excluded[k] = true;
  }
  // Note starts: the reviewed notes when the manifest has them, else detected on the contour.
  const starts = song.reference.notes.length ? song.reference.notes.map((n) => n.start) : onsetTimes(hz, hop, cfg);
  const onsets = starts.filter((t) => !song.reference.excluded.some((e) => t >= e.start && t < e.end));
  return { hop, hz, excluded, source: useHz ? 'hz' : 'notes', onsets };
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
