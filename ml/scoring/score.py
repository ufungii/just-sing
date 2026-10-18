"""Assemble pitch + timing into the per-phrase and total score (contracts/score.example.json).

This is the reference implementation. The browser's TypeScript port must produce
the same numbers on the shared fixtures in contracts/fixtures/.

Two entry points:
  * score_turn     raw pitch tracks -> full score (evals, fixtures, offline checks)
  * finalize_turn  the phrase results a browser submitted -> validated, recomputed
                   score (what the API calls; it never sees raw audio)

Aggregation: the total is the mean of the displayed phrase scores weighted by
each phrase's scoreable reference duration, so rests earn no points and the
final result always agrees with the badges the player saw.
"""
import math
from typing import Mapping, Sequence

import numpy as np

from . import pitch as pitch_mod
from .config import SCORING_VERSION, PitchConfig, PronunciationConfig, ScoreConfig, TimingConfig
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


def phrase_entry(
    phrase_id: str, pitch: float, timing: float | None, coverage: float, cfg: ScoreConfig
) -> dict:
    """One phrase's result. A phrase with no onset inside it (timing=None) is scored
    on pitch alone."""
    score = (
        cfg.pitch_weight * pitch + cfg.timing_weight * timing
        if timing is not None else pitch
    )
    return {
        "phrase_id": phrase_id,
        "pitch": round(pitch, 1),
        "timing": None if timing is None else round(timing, 1),
        "score": round(score, 1),
        "coverage": round(coverage, 3),
        "rating": rate(score, coverage, cfg),
    }


def aggregate(entries: Sequence[dict], weights: Sequence[float]) -> dict:
    """Total / pitch / timing as the mean of the phrase values weighted by `weights`
    (scoreable frames). Phrases with timing=None are left out of the timing mean."""
    def weighted(key: str) -> float:
        pairs = [(e[key], w) for e, w in zip(entries, weights) if e[key] is not None and w > 0]
        total_w = sum(w for _, w in pairs)
        return sum(v * w for v, w in pairs) / total_w if total_w else 0.0

    return {
        "total": round(weighted("score"), 1),
        "pitch": round(weighted("pitch"), 1),
        "timing": round(weighted("timing"), 1),
    }


def line_weights(phrases: Sequence[Mapping], weights: Sequence[float]) -> dict[int, float]:
    """Scoreable frames per lyric line: the sum of its phrases' weights (phrases carry `line_index`)."""
    out: dict[int, float] = {}
    for phrase, w in zip(phrases, weights):
        out[phrase["line_index"]] = out.get(phrase["line_index"], 0.0) + w
    return out


def pronunciation_score(
    statuses: Mapping[int, str], weights: Mapping[int, float], cfg: PronunciationConfig | None = None
) -> float | None:
    """0-100 lyric score from the lyric check's per-line statuses, weighted by each line's scoreable frames.

    Returns None when nothing was checked (no line with a known status and weight > 0): the caller then
    keeps the pitch/timing total, because an unavailable check is never a low score."""
    credit = dict((cfg or PronunciationConfig()).status_credit)
    pairs = [(credit[st], weights.get(i, 0.0)) for i, st in statuses.items() if st in credit]
    total_w = sum(w for _, w in pairs if w > 0)
    if not total_w:
        return None
    return round(sum(c * w for c, w in pairs if w > 0) / total_w, 1)


def apply_pronunciation(score: dict, pronunciation: float | None, cfg: PronunciationConfig | None = None) -> dict:
    """Return `score` with `pronunciation` and the final total. `score` is an aggregate()/finalize_turn() dict.

    With a pronunciation value: total = (wp*pitch + wt*timing + wr*pronunciation) * guard, where
    guard = floor + (1 - floor) * pronunciation / 100. Without one (None) the pitch/timing total is kept.
    If no phrase had a scoreable onset (every phrase timing is None) pitch stands in for timing, as the
    per-phrase blend already does. Raises ValueError on a non-finite or out-of-range pronunciation."""
    cfg = cfg or PronunciationConfig()
    pronunciation = _checked(pronunciation, "pronunciation", 0, 100, nullable=True)
    if pronunciation is None:
        return {**score, "pronunciation": None}
    phrases = score.get("phrases")
    has_timing = phrases is None or any(p.get("timing") is not None for p in phrases)
    timing = score["timing"] if has_timing else score["pitch"]
    blend = cfg.pitch_weight * score["pitch"] + cfg.timing_weight * timing + cfg.pronunciation_weight * pronunciation
    guard = cfg.floor + (1 - cfg.floor) * pronunciation / 100
    return {**score, "pronunciation": pronunciation, "total": round(blend * guard, 1)}


def phrase_weights(
    ref_hz: np.ndarray,
    phrases: Sequence[tuple[str, float, float]],
    *,
    hop_seconds: float = pitch_mod.HOP_SECONDS,
    excluded: Sequence[tuple[float, float]] = (),
) -> list[int]:
    """Scoreable reference frames in each phrase. Computed from the manifest alone, so
    the server derives its own weights and never trusts client-supplied ones."""
    mask = pitch_mod.scoreable_mask(np.asarray(ref_hz, dtype=float), hop_seconds, excluded)
    return [
        int(mask[int(round(s / hop_seconds)):int(round(e / hop_seconds))].sum())
        for _, s, e in phrases
    ]


def _checked(value, name: str, lo: float, hi: float, nullable: bool = False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not lo <= value <= hi:
        raise ValueError(f"{name} must be in [{lo}, {hi}]")
    return float(value)


def finalize_turn(
    submitted: Sequence[Mapping],
    weights: Sequence[float],
    *,
    expected_phrase_ids: Sequence[str],
    register: int = 0,
    cfg: ScoreConfig | None = None,
) -> dict:
    """Validate browser-submitted phrase results and recompute everything derived.

    submitted: dicts with phrase_id, pitch (0-100), timing (0-100 or None), coverage (0-1).
               Any `score` / `rating` the client sent is ignored and recomputed here.
    weights:   phrase_weights() from the server's own manifest copy.
    Raises ValueError on unknown/missing/duplicate phrase ids, out-of-range or
    non-finite values, a register that is not -12/0/12, or a clip whose weights are
    all zero (nothing scoreable: a manifest problem, not the player's).

    Pitch and timing arrive rounded to 0.1, so a recomputed phrase score can differ
    from the browser's by at most about 0.1; compare with that tolerance.
    """
    cfg = cfg or ScoreConfig()
    if register not in (-12, 0, 12):
        raise ValueError("register must be -12, 0, or 12")
    if len(weights) != len(expected_phrase_ids):
        raise ValueError("weights and expected_phrase_ids must align")
    ids = [p.get("phrase_id") for p in submitted]
    if sorted(ids, key=str) != sorted(expected_phrase_ids):
        raise ValueError("submitted phrase ids must match the clip's phrases exactly")

    if not any(w > 0 for w in weights):
        # A manifest with nothing scoreable would otherwise zero every player's score silently.
        raise ValueError("this clip has no scoreable reference frames; fix its manifest")

    by_id = {p["phrase_id"]: p for p in submitted}
    entries = [
        phrase_entry(
            pid,
            _checked(by_id[pid].get("pitch"), f"{pid}.pitch", 0, 100),
            _checked(by_id[pid].get("timing"), f"{pid}.timing", 0, 100, nullable=True),
            _checked(by_id[pid].get("coverage"), f"{pid}.coverage", 0, 1),
            cfg,
        )
        for pid in expected_phrase_ids
    ]
    return {"scoring_version": SCORING_VERSION, "register": register,
            **aggregate(entries, weights), "pronunciation": None, "phrases": entries}


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
    """Score a whole turn from raw pitch tracks. phrases are (id, start_s, end_s).
    Returns the score dict without the clip/mode fields, which the caller adds."""
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

    entries, weights = [], []
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
        entries.append(phrase_entry(
            pid, p.score, t.score if t.n_onsets else None, p.coverage, cfg))
        weights.append(p.scoreable_frames)

    return {"scoring_version": SCORING_VERSION, "register": register,
            **aggregate(entries, weights), "pronunciation": None, "phrases": entries}
