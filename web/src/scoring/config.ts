/**
 * Every threshold the live scorer uses, in one place (CLAUDE.md: "thresholds live in config, not code").
 *
 * The scoring values below mirror ml/scoring/config.py (SCORING_VERSION 0.1.0) and ml/scoring/SPEC.md.
 * `npm test` runs this port against contracts/fixtures; never change the math or these numbers in only
 * one language.
 */

/** Must match ml/scoring/config.py SCORING_VERSION, which the server stores with every result. */
export const SCORING_VERSION = '0.1.0';

export const SCORING_CONFIG = {
  // ---------- live pitch capture (what counts as a voiced user frame) ----------
  /** Analysis hop in seconds; equals reference.hop_seconds for every manifest so far. */
  hopSeconds: 0.02,
  /** Pitchy window length in samples (about 43 ms at 48 kHz: enough for 2+ periods of 65 Hz). */
  windowSamples: 2048,
  /** Frames below this Pitchy clarity are unvoiced (null). Keeps mic hiss from earning points. */
  minClarity: 0.85,
  /** Frames quieter than this RMS (linear, full scale 1.0) are unvoiced, whatever the tracker says. */
  minRms: 0.01,
  /** Same frequency limits as pitch_contour() in ml/scoring/pitch.py. */
  fminHz: 65,
  fmaxHz: 1000,

  // ---------- pitch ----------
  /** Full credit within this many cents of the target. */
  pitchFullCents: 50,
  /** Credit falls linearly to zero at this many cents. */
  pitchZeroCents: 200,
  /** Pitch may match the target this many seconds early/late (0 = strict). Implemented, off by default. */
  timeToleranceS: 0,

  // ---------- timing ----------
  /** Entrance within this many seconds of a reference note start earns full credit. */
  timingFullSeconds: 0.1,
  /** ...falling linearly to zero credit at this offset (s). */
  timingZeroSeconds: 0.4,
  /** A reference onset can only match a user onset within this window (s). */
  matchWindowSeconds: 0.5,
  /** A user onset needs this many consecutive voiced frames within `stableCents` of their median. */
  stableFrames: 4,
  stableCents: 60,
  /** Onsets closer than this are merged (keeps the first). */
  minOnsetGapSeconds: 0.12,

  // ---------- phrase score and rating ----------
  pitchWeight: 0.8,
  timingWeight: 0.2,
  perfect: 90,
  great: 75,
  okay: 50,
  /** Below this share of scoreable frames sung, a phrase is a miss (never for a mic failure). */
  minCoverage: 0.25,

  // ---------- display only ----------
  /** Notes are derived from the contour (when the manifest has none) as runs within this many cents. */
  noteChangeCents: 80,
} as const;

export type ScoringConfig = typeof SCORING_CONFIG;
