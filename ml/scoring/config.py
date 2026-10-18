"""Scoring configuration.

Every threshold lives here, not in the scoring code, so it can be tuned against
the synthetic evals and real recordings (see CLAUDE.md). These are starting
defaults, not validated values. Bump SCORING_VERSION when any of them change so
saved results are never silently reinterpreted.
"""
from dataclasses import dataclass

SCORING_VERSION = "0.4.0"


@dataclass(frozen=True)
class PitchConfig:
    # Frames within this many cents of the target earn full credit.
    full_credit_cents: float = 50.0
    # Credit falls linearly to zero at this error. A soft ramp (not a hard
    # pass/fail) keeps the score smooth, which matters for monotonicity evals.
    zero_credit_cents: float = 200.0
    # Pitch may match the target up to this many seconds early or late without
    # losing pitch credit (lateness is then penalized by timing only). 0 = strict,
    # the current default. See ml/evals/results/tolerance.md before changing it.
    time_tolerance_s: float = 0.1


@dataclass(frozen=True)
class TimingConfig:
    # Entrance within this many seconds of the reference earns full credit.
    full_credit_s: float = 0.10
    # Credit falls linearly to zero at this offset.
    zero_credit_s: float = 0.40
    # A reference onset can only match a user onset inside this window.
    match_window_s: float = 0.50
    # A user onset needs this many consecutive voiced frames within
    # `stable_cents` of their median. Rejects tracker noise, which would
    # otherwise create fake onsets and earn timing points.
    stable_frames: int = 4
    stable_cents: float = 60.0
    # Onsets closer than this are merged (keeps the first).
    min_onset_gap_s: float = 0.12


@dataclass(frozen=True)
class ScoreConfig:
    pitch_weight: float = 0.8
    timing_weight: float = 0.2
    # Phrase rating bands on the 0-100 phrase score, set in 0.3.0 from real takes through the
    # live tracker (ml/evals/band_calibration.py): the original singer's typical phrase is ~78-80,
    # a decent amateur's ~60-64, a semitone off ~45-50, two semitones off ~20-25. One singer and
    # two songs: a starting point, not validated cutoffs.
    perfect: float = 80.0
    great: float = 65.0
    okay: float = 40.0
    # Below this share of scoreable frames sung, a phrase is a Miss. Miss is
    # reserved for insufficient coverage, never for a mic failure.
    min_coverage: float = 0.25


@dataclass(frozen=True)
class PronunciationConfig:
    """How the lyric check (sung words vs the original singer's, per line) enters the turn total.

    Starting defaults, not validated: nobody fluent in Korean has reviewed them, and the lyric check
    was never measured on sung audio. Phrase scores and ratings are unaffected; only the turn total changes.
    """
    pitch_weight: float = 0.7
    timing_weight: float = 0.1
    pronunciation_weight: float = 0.2
    # Humming guard: the blended total is multiplied by floor + (1 - floor) * pronunciation / 100,
    # so a hummer who nails pitch and timing (blend ~80) ends near 80 * floor, while perfect lyrics
    # leave the guard at 1.0. Without it the 20% weight alone would let humming win.
    floor: float = 0.5
    # Per-line credit for each lyric-check status. "not_covered" lines are left out of the mean.
    # "unclear" gets no credit on purpose: humming is graded unclear (a hum sounds like its own hum),
    # not not_sung, so partial credit there would pay for humming. Real singing was "match" on 89-96%
    # of lines in ml/pronunciation/LYRIC_MATCH.md (one singer), so the cost to honest singers is small.
    status_credit: tuple[tuple[str, float], ...] = (("match", 100.0), ("unclear", 0.0), ("not_sung", 0.0))


@dataclass(frozen=True)
class WordFeedbackConfig:
    """Display-only defaults, pending calibration on real player recordings."""
    sung_coverage: float = 0.5
    partly_coverage: float = 0.2
    # First detected voiced frame more than this after the first scoreable frame.
    late_after_s: float = 0.12
