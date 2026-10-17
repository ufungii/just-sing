"""A Python stand-in for the browser's pitch tracker.

The live game tracks the player's pitch in the browser with Pitchy, which
implements the McLeod Pitch Method (MPM): a normalized square difference function
(NSDF), "key maxima" after each positive zero crossing, the first key maximum
above a cutoff (0.9 x the highest), and parabolic interpolation. Its peak height
is the "clarity". This module reimplements that algorithm so the evals can ask:
does a browser-style tracker agree with the CREPE reference? It is an emulation of
the algorithm, not Pitchy's exact code, so small numeric differences are expected.
"""
import numpy as np

from ml.scoring.pitch import EXTRACTION_SR, FMAX_HZ, FMIN_HZ, HOP_SECONDS

KEY_MAX_CUTOFF = 0.9


def _nsdf(frame: np.ndarray) -> np.ndarray:
    n = len(frame)
    spec = np.fft.rfft(frame, 2 * n)
    acf = np.fft.irfft(spec * np.conj(spec))[:n]
    sq = frame ** 2
    m = 2 * np.sum(sq) - np.concatenate([[0.0], np.cumsum(sq)[:-1]]) - np.concatenate(
        [[0.0], np.cumsum(sq[::-1])[:-1]])
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(m > 0, 2 * acf / m, 0.0)
    return out


def _pitch(frame: np.ndarray, sr: int) -> tuple[float, float]:
    """(hz, clarity) for one frame; (nan, 0) if no peak."""
    nsdf = _nsdf(frame - frame.mean())
    min_lag, max_lag = int(sr / FMAX_HZ), min(len(nsdf) - 2, int(sr / FMIN_HZ))
    peaks, i = [], 1
    # skip the initial positive lobe, then collect the max of each positive lobe
    while i < len(nsdf) and nsdf[i] > 0:
        i += 1
    while i < max_lag:
        while i < max_lag and nsdf[i] <= 0:
            i += 1
        best = i
        while i < max_lag and nsdf[i] > 0:
            if nsdf[i] > nsdf[best]:
                best = i
            i += 1
        if best < max_lag and nsdf[best] > 0:
            peaks.append(best)
    peaks = [p for p in peaks if p >= min_lag]
    if not peaks:
        return np.nan, 0.0
    top = max(nsdf[p] for p in peaks)
    lag = next(p for p in peaks if nsdf[p] >= KEY_MAX_CUTOFF * top)
    a, b, c = nsdf[lag - 1], nsdf[lag], nsdf[lag + 1]
    denom = a - 2 * b + c
    shift = 0.5 * (a - c) / denom if denom != 0 else 0.0
    return sr / (lag + shift), float(b - 0.25 * (a - c) * shift)


def mpm_track(
    audio: np.ndarray, sr: int, clarity_threshold: float = 0.9,
    frame_length: int = 2048, hop_seconds: float = HOP_SECONDS, silence_gate_rms: float = 1e-3,
) -> np.ndarray:
    """Hz track (NaN = unvoiced) on the scoring hop, frames centered like librosa."""
    import librosa

    y = np.asarray(audio, dtype=np.float64)
    if sr != EXTRACTION_SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=EXTRACTION_SR)
    hop = int(round(hop_seconds * EXTRACTION_SR))
    pad = np.pad(y, frame_length // 2)
    out = np.full(1 + len(y) // hop, np.nan)
    for k in range(len(out)):
        frame = pad[k * hop: k * hop + frame_length]
        if len(frame) < frame_length or np.sqrt(np.mean(frame ** 2)) < silence_gate_rms:  # silence gate
            continue
        hz, clarity = _pitch(frame, EXTRACTION_SR)
        if clarity >= clarity_threshold and FMIN_HZ <= hz <= FMAX_HZ:
            out[k] = hz
    return out
