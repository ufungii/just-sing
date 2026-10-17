"""Assemble pitch + timing into the per-phrase and total score (contracts/score.example.json).

This is the reference implementation. The browser's TypeScript port must produce
the same numbers on the shared fixtures in contracts/fixtures/.

Aggregation: the total is the mean of the displayed phrase scores weighted by
each phrase's scoreable reference duration, so rests earn no points and the
final result always agrees with the badges the player saw.
"""
from typing import Sequence

import numpy as np

from . import pitch as pitch_mod
from .config import SCORING_VERSION, PitchConfig, ScoreConfig, TimingConfig
from .timing import onset_times, timing_score


# Lowercase ids per contracts/score.example.json; the UI shows "Perfect!", "Great", ...
def rate(score: float, coverage: float, cfg: ScoreConfig) -> str:
    if coverage < cfg.min_coverage:
        return "miss"
    if score >= cfg.perfect:
        return "perfect"
    if score >= cfg.great:
        return "great"
    if score >= cfg.okay:
        return "okay"
    return "bad"


def score_turn(
    user_hz: np.ndarray,
    ref_hz: np.ndarray,
    phrases: Sequence[tuple[str, float, float]],
    *,
    hop_seconds: float = pitch_mod.HOP_SECONDS,
    ref_onsets: Sequence[float] | None = None,
    register: int = 0,
    excluded: Sequence[tuple[float, float]] = (),
    latency_offset_s: float = 0.0,
    pitch_cfg: PitchConfig | None = None,
    timing_cfg: TimingConfig | None = None,
    cfg: ScoreConfig | None = None,
) -> dict:
    """Score a whole turn. phrases are (id, start_s, end_s). Returns the score dict
    without the clip/mode fields, which the caller adds."""
    cfg = cfg or ScoreConfig()
    ref_hz = np.asarray(ref_hz, dtype=float)
    if ref_onsets is None:
        ref_onsets = onset_times(ref_hz, hop_seconds, timing_cfg)
    # Excluded regions are excluded from timing too, identically for every player.
    ref_onsets = [
        t for t in ref_onsets if not any(lo <= t < hi for lo, hi in excluded)
    ]
    # Correct the device delay ONCE, for both pitch and timing.
    user_hz = pitch_mod.apply_latency(user_hz, latency_offset_s, hop_seconds)

    out, weights = [], []
    for pid, start, end in phrases:
        p = pitch_mod.pitch_score(
            user_hz, ref_hz, hop_seconds=hop_seconds, register=register,
            excluded=excluded, cfg=pitch_cfg,
            frames=slice(int(round(start / hop_seconds)), int(round(end / hop_seconds))),
        )
        t = timing_score(
            user_hz, ref_onsets, hop_seconds=hop_seconds,
            span=(start, end), cfg=timing_cfg,
        )
        # A phrase with no onset inside it (it starts mid-note) is scored on pitch alone.
        timing = t.score if t.n_onsets else None
        score = (
            cfg.pitch_weight * p.score + cfg.timing_weight * timing
            if timing is not None else p.score
        )
        out.append({
            "phrase_id": pid,
            "pitch": round(p.score, 1),
            "timing": None if timing is None else round(timing, 1),
            "score": round(score, 1),
            "coverage": round(p.coverage, 3),
            "rating": rate(score, p.coverage, cfg),
        })
        weights.append(p.scoreable_frames)

    def weighted(key: str) -> float:
        pairs = [(r[key], w) for r, w in zip(out, weights) if r[key] is not None and w > 0]
        total_w = sum(w for _, w in pairs)
        return sum(v * w for v, w in pairs) / total_w if total_w else 0.0

    return {
        "scoring_version": SCORING_VERSION,
        "register": register,
        "total": round(weighted("score"), 1),
        "pitch": round(weighted("pitch"), 1),
        "timing": round(weighted("timing"), 1),
        "phrases": out,
    }
