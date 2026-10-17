"""Scoring configuration.

Every threshold lives here, not in the scoring code, so it can be tuned against
the synthetic evals and real recordings (see CLAUDE.md). These are starting
defaults, not validated values. Bump SCORING_VERSION when any of them change so
saved results are never silently reinterpreted.
"""
from dataclasses import dataclass

SCORING_VERSION = "0.1.0"


@dataclass(frozen=True)
class PitchConfig:
    # Frames within this many cents of the target earn full credit.
    full_credit_cents: float = 50.0
    # Credit falls linearly to zero at this error. A soft ramp (not a hard
    # pass/fail) keeps the score smooth, which matters for monotonicity evals.
    zero_credit_cents: float = 200.0


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
    # Phrase rating bands on the 0-100 phrase score. Placeholders to calibrate
    # against recordings; they are not established accuracy cutoffs.
    perfect: float = 90.0
    great: float = 75.0
    okay: float = 50.0
    # Below this share of scoreable frames sung, a phrase is a Miss. Miss is
    # reserved for insufficient coverage, never for a mic failure.
    min_coverage: float = 0.25
