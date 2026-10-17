"""Word-window singing activity and pitch, never lexical recognition or a turn score.

Input must be confidence/RMS-gated Hz tracks on the same clip-relative grid.
A detected pitch cannot establish which word the player actually said.
"""
from typing import Sequence

import numpy as np

from . import pitch as pitch_mod
from .config import PitchConfig, WordFeedbackConfig

WORD_FEEDBACK_VERSION = "1.0.0"


def word_feedback(
    user_hz: np.ndarray,
    ref_hz: np.ndarray,
    lines: Sequence[dict],
    *,
    hop_seconds: float = pitch_mod.HOP_SECONDS,
    register: int = 0,
    excluded: Sequence[tuple[float, float]] = (),
    latency_offset_s: float = 0.0,
    pitch_cfg: PitchConfig | None = None,
    cfg: WordFeedbackConfig | None = None,
) -> list[list[dict]]:
    """Return one row per line, one result per word, preserving manifest order.

    Coverage and pitch use only the word's scoreable frames, with no time search.
    `onset_delay_s` measures the first detected voice relative to the first
    scoreable frame; it cannot detect a consonant/word onset during continuous
    singing. `late` is independent of the coverage status, and null if no voice.
    No reference frames means `not_graded`, with all measurements null.
    """
    cfg, pitch_cfg = cfg or WordFeedbackConfig(), pitch_cfg or PitchConfig()
    if not np.isfinite(hop_seconds) or hop_seconds <= 0:
        raise ValueError("hop_seconds must be finite and positive")
    if register not in (-12, 0, 12):
        raise ValueError("register must be -12, 0, or 12")
    if not np.isfinite(latency_offset_s) or latency_offset_s < 0:
        raise ValueError("latency_offset_s must be finite and nonnegative")
    if not 0 <= cfg.partly_coverage <= cfg.sung_coverage <= 1:
        raise ValueError("coverage thresholds must satisfy 0 <= partly <= sung <= 1")
    if not np.isfinite(cfg.late_after_s) or cfg.late_after_s < 0:
        raise ValueError("late_after_s must be finite and nonnegative")
    if not 0 <= pitch_cfg.full_credit_cents < pitch_cfg.zero_credit_cents < float("inf"):
        raise ValueError("pitch thresholds must be finite with 0 <= full < zero")
    ref = pitch_mod.to_track(ref_hz)
    user = pitch_mod.to_track(user_hz)
    user = pitch_mod.apply_latency(user, latency_offset_s, hop_seconds)
    user = pitch_mod._align_length(user, len(ref))
    mask = pitch_mod.scoreable_mask(ref, hop_seconds, excluded)
    voiced = np.isfinite(user)
    credit = np.zeros(len(ref))
    both = mask & voiced
    target = ref * 2.0 ** (register / 12.0)
    credit[both] = pitch_mod._frame_credit(
        pitch_mod.cents_error(user[both], target[both]), pitch_cfg)

    out = []
    for line in lines:
        row = []
        for word in line.get("words", []):
            start, end = word["start"], word["end"]
            if not np.isfinite(start) or not np.isfinite(end) or end < start:
                raise ValueError("word boundaries must be finite with start <= end")
            lo = max(0, int(round(start / hop_seconds)))
            hi = min(len(ref), int(round(end / hop_seconds)))
            frames = np.arange(lo, max(lo, hi))
            frames = frames[mask[frames]]
            result = {"text": word["text"], "start": start, "end": end,
                      "status": "not_graded", "coverage": None, "pitch": None,
                      "onset_delay_s": None, "late": None}
            if len(frames):
                sung = frames[voiced[frames]]
                coverage = len(sung) / len(frames)
                result.update(
                    status=("sung" if coverage >= cfg.sung_coverage else
                            "partly" if coverage >= cfg.partly_coverage else "missed"),
                    coverage=round(coverage, 3),
                    pitch=round(float(100 * credit[frames].mean()), 1),
                )
                if len(sung):
                    delay = (int(sung[0]) - int(frames[0])) * hop_seconds
                    result.update(onset_delay_s=round(delay, 3),
                                  late=bool(delay > cfg.late_after_s + 1e-12))
            row.append(result)
        out.append(row)
    return out
