/**
 * Every threshold the live scorer uses, in one place (CLAUDE.md: "thresholds live in config, not code").
 *
 * PROVISIONAL: these are the starting defaults written in CLAUDE.md, not calibrated values. The Python
 * reference engine (ml/scoring) and the shared fixtures (contracts/fixtures) do not exist yet; when they
 * land, copy their config here and make this port pass the same fixtures. Never change the math or these
 * numbers in only one language.
 */

/** Must match api/play.py SCORING_VERSION, which the server stores with every result. */
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
  pitchZeroCents: 175,

  // ---------- timing ----------
  /** A target onset is a phrase entrance or a note change. Matched user onsets within this get full credit (s). */
  timingFullSeconds: 0.1,
  /** ...falling linearly to zero credit at this error (s). */
  timingZeroSeconds: 0.35,
  /** Only user onsets within this distance of a target onset can match it (s). */
  onsetSearchSeconds: 0.5,
  /** A pitch jump bigger than this between frames starts a new user onset (cents). */
  onsetJumpCents: 80,
  /** A user onset only counts if the voice then holds for this many frames (filters blips). */
  onsetMinFrames: 3,
  /** When notes are derived from the hz contour, a change bigger than this starts a new note (cents). */
  noteChangeCents: 80,

  // ---------- phrase rating ----------
  /** Below this coverage (share of scoreable frames the user voiced) a phrase is a MISS. */
  missCoverage: 0.25,
  /** Rating bands on the phrase score (0-100), checked top down; anything lower is BAD. */
  bands: [
    { rating: 'perfect', min: 90 },
    { rating: 'great', min: 75 },
    { rating: 'okay', min: 50 },
  ] as const,

  // ---------- totals ----------
  /** 80% pitch / 20% timing: the CLAUDE.md default (not a validated weighting), same as api/play.py. */
  pitchWeight: 0.8,
} as const;

export type ScoringConfig = typeof SCORING_CONFIG;
