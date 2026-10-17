"""Post-processing for the LIVE (browser) pitch track, before scoring.

The browser tracker is less sure than the offline reference tracker: on real
singing it drops frames (breathy or fast notes) and sometimes jumps an octave.
These two steps repair that using only the player's own track (no reference
involved), so they cannot "forgive" a wrong note:

  fill_gaps     short unvoiced runs between two voiced frames of similar pitch
                are filled by interpolation. Never creates sound from silence.
  fix_octaves   a voiced frame whose pitch is ~one octave from the recent
                median is moved back an octave (continuity, not target matching).
"""
import numpy as np

HOP = 0.02


def fill_gaps(track: np.ndarray, max_gap_s: float = 0.1, max_cents: float = 200.0) -> np.ndarray:
    out, n, i = track.copy(), len(track), 0
    max_gap = int(round(max_gap_s / HOP))
    while i < n:
        if np.isfinite(out[i]) or i == 0 or not np.isfinite(out[i - 1]):
            i += 1
            continue
        j = i
        while j < n and not np.isfinite(out[j]):
            j += 1
        if j < n and (j - i) <= max_gap and abs(1200 * np.log2(out[j] / out[i - 1])) <= max_cents:
            out[i:j] = np.exp(np.linspace(np.log(out[i - 1]), np.log(out[j]), j - i + 2)[1:-1])
        i = j
    return out


def fix_octaves(track: np.ndarray, window: int = 7, tolerance_cents: float = 150.0) -> np.ndarray:
    """Move a frame by an octave if that brings it within tolerance of the median of the
    previous `window` voiced frames (seen within the last 0.4 s)."""
    out, recent = track.copy(), []
    for i, v in enumerate(out):
        if not np.isfinite(v):
            continue
        if recent:
            med = np.median(recent)
            for factor in (0.5, 2.0):
                if abs(1200 * np.log2(v * factor / med)) <= tolerance_cents < abs(1200 * np.log2(v / med)):
                    v = out[i] = v * factor
                    break
        recent.append(v)
        recent = recent[-window:]
    return out
