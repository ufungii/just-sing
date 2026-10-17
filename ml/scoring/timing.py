"""Timing score: when does the singer enter, compared with the reference?

Design (see CLAUDE.md):
  * Compare the user's onsets with the reference's phrase entrances and note
    changes. This is separate from pitch: a wrong note sung on time still gets
    full timing credit, and the right note sung late does not.
  * One fixed device-latency offset, measured once in the setup step, is
    subtracted from every user onset. It is never fitted per performance;
    that would hide late singing.
  * No dynamic time warping. It would align away the mistakes we measure.
  * An unmatched reference onset earns zero but stays in the denominator.
  * A user onset must be *stable* (several consecutive voiced frames at nearly
    the same pitch). Tracker noise therefore cannot earn timing points.
"""
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .config import TimingConfig
from .pitch import HOP_SECONDS


def onset_times(
    track: np.ndarray,
    hop_seconds: float = HOP_SECONDS,
    cfg: TimingConfig | None = None,
) -> np.ndarray:
    """Seconds at which a new stable note or voiced stretch begins in a Hz track.

    Detects entries after silence and pitch steps of roughly a semitone or more.
    Slow glides land late, and repeated same-pitch notes with no gap produce no
    onset; both are known limits.
    """
    cfg = cfg or TimingConfig()
    track = np.asarray(track, dtype=float)
    n, length = len(track), cfg.stable_frames

    stable = np.zeros(n, dtype=bool)
    for i in range(n - length + 1):
        window = track[i : i + length]
        if np.all(np.isfinite(window)):
            deviation = np.abs(1200.0 * np.log2(window / np.median(window)))
            stable[i] = deviation.max() <= cfg.stable_cents

    min_gap = int(round(cfg.min_onset_gap_s / hop_seconds))
    onsets: list[int] = []
    for i in range(n):
        if stable[i] and (i == 0 or not stable[i - 1]):
            if not onsets or i - onsets[-1] >= min_gap:
                onsets.append(i)
    return np.array(onsets, dtype=float) * hop_seconds


@dataclass(frozen=True)
class TimingResult:
    credit_sum: float
    n_onsets: int                  # reference onsets in the span (the denominator)
    matched: int
    deltas: tuple[float, ...] = () # signed seconds, user minus reference; + is late

    @property
    def score(self) -> float:
        """0-100. Zero when there is nothing to time."""
        return 0.0 if self.n_onsets == 0 else 100.0 * self.credit_sum / self.n_onsets

    @property
    def median_offset_s(self) -> float | None:
        """Typical early (-) or late (+) entrance, for coaching. None if unmatched."""
        return float(np.median(self.deltas)) if self.deltas else None


def combine(results: Iterable[TimingResult]) -> TimingResult:
    results = list(results)
    return TimingResult(
        credit_sum=sum(r.credit_sum for r in results),
        n_onsets=sum(r.n_onsets for r in results),
        matched=sum(r.matched for r in results),
        deltas=tuple(d for r in results for d in r.deltas),
    )


def timing_score(
    user_hz: np.ndarray,
    ref_onsets: Sequence[float],
    *,
    hop_seconds: float = HOP_SECONDS,
    latency_offset_s: float = 0.0,
    span: tuple[float, float] | None = None,
    cfg: TimingConfig | None = None,
) -> TimingResult:
    """Score the user's entrances against reference onset times (seconds).

    latency_offset_s: fixed device delay measured in setup; subtracted from the
                      user's onset times.
    span: (start, end) seconds; only reference onsets inside are scored
          (used for per-phrase scores).
    """
    cfg = cfg or TimingConfig()
    ref = np.asarray(ref_onsets, dtype=float)
    if span is not None:
        ref = ref[(ref >= span[0]) & (ref < span[1])]

    user_track = np.asarray(user_hz, dtype=float)
    user_track = np.where(np.isfinite(user_track) & (user_track > 0), user_track, np.nan)
    user = onset_times(user_track, hop_seconds, cfg) - latency_offset_s

    used = np.zeros(len(user), dtype=bool)
    credit_span = cfg.zero_credit_s - cfg.full_credit_s
    credit_sum, deltas = 0.0, []

    for t_ref in ref:
        gaps = np.abs(user - t_ref)
        gaps[used] = np.inf
        if len(gaps) == 0 or gaps.min() > cfg.match_window_s:
            continue  # missed entrance: zero credit, still counted
        j = int(gaps.argmin())
        used[j] = True
        delta = float(user[j] - t_ref)
        deltas.append(delta)
        credit_sum += float(np.clip((cfg.zero_credit_s - abs(delta)) / credit_span, 0.0, 1.0))

    return TimingResult(credit_sum, len(ref), len(deltas), tuple(deltas))
