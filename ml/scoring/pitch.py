"""Pitch extraction and pitch scoring.

Conventions (see CLAUDE.md):
  * Pitch tracks are Hz at a fixed hop (default 0.02 s), starting at clip time 0.
  * Unvoiced frames are NaN in memory and `null` in JSON.
  * Cents are only ever an *error* measure: 1200 * log2(user_hz / target_hz).

Scoring rules implemented here:
  * Register (-12 / 0 / +12 semitones) shifts the target for the whole turn.
    There is deliberately no per-frame octave forgiveness and no per-performance
    "key shift" removal: both would reward a broken melody.
  * Only frames where the reference is voiced and not excluded are scoreable.
    Rests and excluded regions never enter the denominator.
  * Missing/unvoiced user frames on a scoreable frame earn zero credit but stay
    in the denominator, so silence cannot inflate a score.
"""
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .config import PitchConfig

HOP_SECONDS = 0.02
EXTRACTION_SR = 16_000
FMIN_HZ = 65.0
FMAX_HZ = 1000.0


# --------------------------------------------------------------------------- #
# Track helpers
# --------------------------------------------------------------------------- #
def to_track(hz: Sequence[float | None]) -> np.ndarray:
    """Convert a JSON-style list (None = unvoiced) to a float array (NaN = unvoiced)."""
    arr = np.array([np.nan if v is None else v for v in hz], dtype=float)
    arr[~np.isfinite(arr) | (arr <= 0)] = np.nan
    return arr


def track_to_json(track: np.ndarray) -> list[float | None]:
    """Inverse of to_track, for writing manifests."""
    return [None if not np.isfinite(v) else round(float(v), 2) for v in track]


def apply_latency(
    user_hz: np.ndarray, latency_offset_s: float, hop_seconds: float = HOP_SECONDS
) -> np.ndarray:
    """Undo the fixed device delay: move the user's track earlier by the offset.

    The offset is measured once in the setup step, never fitted per performance.
    Genuine lateness beyond it is preserved and penalized by the timing score.
    """
    n = int(round(latency_offset_s / hop_seconds))
    user_hz = np.asarray(user_hz, dtype=float)
    if n <= 0:
        return user_hz
    return np.concatenate([user_hz[n:], np.full(n, np.nan)])


def cents_error(user_hz: np.ndarray, target_hz: np.ndarray) -> np.ndarray:
    """Signed pitch error in cents; positive means the user is sharp."""
    return 1200.0 * np.log2(user_hz / target_hz)


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
PERIODICITY_THRESHOLD = 0.5   # tracker confidence below this is unvoiced
RMS_GATE = 0.003              # window RMS below this is silence, even if the tracker returns a pitch
CREPE_CHUNK_FRAMES = 750      # 15 s of frames per CREPE call (bounds memory), with 100 ms of context


def _extract(signal: np.ndarray, backend: str, device: str | None, progress) -> tuple[np.ndarray, np.ndarray]:
    """The one extraction path: raw pitch (Hz, NaN = unvoiced) and confidence per 20 ms frame.

    Shared by the offline reference (reference_contour) and the evals (pitch_contour), so both
    use identical settings. 16 kHz mono in. Heavy imports stay inside the branches.
    """
    import librosa
    from scipy.ndimage import median_filter

    hop = int(round(HOP_SECONDS * EXTRACTION_SR))
    if backend == "pyin":
        pitch, voiced, prob = librosa.pyin(signal, fmin=FMIN_HZ, fmax=FMAX_HZ, sr=EXTRACTION_SR,
                                           frame_length=2048, hop_length=hop)
        confidence = np.nan_to_num(np.asarray(prob, dtype=np.float32), nan=0.0)
        # pyin makes its own voiced/unvoiced decision; an extra confidence cut only drops good frames.
        pitch = np.where(np.asarray(voiced), pitch, np.nan)
        return np.asarray(pitch, dtype=np.float64), confidence

    if backend == "crepe":
        import torch
        import torchcrepe

        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        n_frames = len(signal) // hop + 1
        pitch = np.full(n_frames, np.nan, dtype=np.float32)
        confidence = np.zeros(n_frames, dtype=np.float32)
        for first in range(0, n_frames, CREPE_CHUNK_FRAMES):
            last = min(n_frames, first + CREPE_CHUNK_FRAMES)
            left_frame = max(0, first - 5)
            lo, hi = left_frame * hop, min(len(signal), (last + 5) * hop)
            with torch.inference_mode():
                hz, periodicity = torchcrepe.predict(
                    torch.from_numpy(signal[lo:hi].copy()).unsqueeze(0), EXTRACTION_SR, hop, FMIN_HZ, FMAX_HZ,
                    model="full", batch_size=256, device=device, return_periodicity=True)
            offset = first - left_frame
            count = min(last - first, hz.shape[1] - offset)
            pitch[first:first + count] = hz[0, offset:offset + count].cpu().numpy()
            confidence[first:first + count] = periodicity[0, offset:offset + count].cpu().numpy()
            if progress:
                progress(min(len(signal) / EXTRACTION_SR, last * HOP_SECONDS))
        confidence = median_filter(confidence, size=3, mode="nearest")
        pitch = np.where(confidence >= PERIODICITY_THRESHOLD, pitch, np.nan)
        return pitch.astype(np.float64), confidence

    raise ValueError(f"unknown pitch backend: {backend!r}")


def _clean(pitch: np.ndarray, signal: np.ndarray, rms_gate: float, smooth: bool) -> np.ndarray:
    """Drop frames that are silent, out of range, or isolated blips; returns Hz with NaN = unvoiced."""
    from scipy.ndimage import median_filter

    hop = int(round(HOP_SECONDS * EXTRACTION_SR))
    squares = np.concatenate([[0.0], np.cumsum(np.pad(signal, (512, 512)).astype(np.float64) ** 2)])
    starts = np.arange(len(pitch)) * hop
    ends = np.minimum(starts + 1024, len(squares) - 1)
    rms = np.sqrt((squares[ends] - squares[np.minimum(starts, len(squares) - 1)]) / 1024.0)
    valid = np.isfinite(pitch) & (rms >= rms_gate) & (pitch >= FMIN_HZ) & (pitch <= FMAX_HZ)
    values = np.where(valid, pitch, 0.0)
    if smooth:  # a 3-frame median also removes single-frame detections surrounded by silence
        values = median_filter(values, size=3, mode="nearest")
    return np.where(values > 0, values, np.nan)


def _prepare(audio: np.ndarray, sr: int) -> np.ndarray:
    signal = np.asarray(audio, dtype=np.float32)
    if signal.ndim != 1 or not len(signal) or not np.isfinite(signal).all():
        raise ValueError("expected finite, nonempty mono audio")
    if sr != EXTRACTION_SR:
        import librosa
        signal = librosa.resample(signal, orig_sr=sr, target_sr=EXTRACTION_SR)
    return signal


def pitch_contour(
    audio: np.ndarray,
    sr: int,
    backend: str = "pyin",
    hop_seconds: float = HOP_SECONDS,
    *,
    rms_gate: float = RMS_GATE,
    smooth: bool = True,
    device: str | None = None,
    progress=None,
) -> np.ndarray:
    """Hz contour (NaN = unvoiced) from mono audio at a 20 ms hop.

    The one shared extractor: the offline pipeline builds the reference with it
    (backend="crepe", via reference_contour) and the evals extract degraded audio with
    it (default "pyin", CPU only). `hop_seconds` must be the scoring hop.
    """
    if abs(hop_seconds - HOP_SECONDS) > 1e-9:
        raise ValueError("the scoring hop is fixed at 0.02 s")
    signal = _prepare(audio, sr)
    pitch, _ = _extract(signal, backend, device, progress)
    return _clean(pitch, signal, rms_gate, smooth)


def reference_contour(
    audio: np.ndarray,
    sample_rate: int = EXTRACTION_SR,
    *,
    backend: str = "crepe",
    progress=None,
    rms_gate: float = RMS_GATE,
    smooth: bool = True,
    device: str | None = None,
) -> dict:
    """The reference in manifest form: {hop_seconds, hz (null = unvoiced), periodicity, backend, settings}.

    Same extraction as pitch_contour, plus the per-frame confidence and the settings used, so a
    manifest records exactly how its contour was made. JSON-safe (no NaN).
    """
    signal = _prepare(audio, sample_rate)
    pitch, confidence = _extract(signal, backend, device, progress)
    hz = _clean(pitch, signal, rms_gate, smooth)
    return {
        "hop_seconds": HOP_SECONDS,
        "hz": [float(v) if np.isfinite(v) else None for v in hz],
        "periodicity": [float(v) if np.isfinite(v) else 0.0 for v in confidence],
        "backend": backend,
        "settings": {"sample_rate_hz": EXTRACTION_SR, "fmin": FMIN_HZ, "fmax": FMAX_HZ,
                     "periodicity_threshold": PERIODICITY_THRESHOLD, "minimum_rms": rms_gate,
                     "median_smoothing": smooth},
    }

# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PitchResult:
    """Pitch result for a span of frames. Sums are kept so spans can be combined
    with duration weighting (see combine)."""

    credit_sum: float        # total credit earned over scoreable frames
    scoreable_frames: int    # frames in the denominator
    voiced_frames: int       # scoreable frames where the user was also voiced

    @property
    def score(self) -> float:
        """0-100. Zero when there is nothing scoreable."""
        if self.scoreable_frames == 0:
            return 0.0
        return 100.0 * self.credit_sum / self.scoreable_frames

    @property
    def coverage(self) -> float:
        """Share of scoreable frames the user was voiced for (0-1)."""
        if self.scoreable_frames == 0:
            return 0.0
        return self.voiced_frames / self.scoreable_frames


def combine(results: Iterable[PitchResult]) -> PitchResult:
    """Aggregate spans weighted by scoreable duration (rests earn no points)."""
    results = list(results)
    return PitchResult(
        credit_sum=sum(r.credit_sum for r in results),
        scoreable_frames=sum(r.scoreable_frames for r in results),
        voiced_frames=sum(r.voiced_frames for r in results),
    )


def scoreable_mask(
    ref_hz: np.ndarray,
    hop_seconds: float = HOP_SECONDS,
    excluded: Sequence[tuple[float, float]] = (),
) -> np.ndarray:
    """Frames that count: reference voiced and outside every excluded region."""
    mask = np.isfinite(ref_hz)
    for start, end in excluded:
        lo = max(0, int(round(start / hop_seconds)))
        hi = max(0, int(round(end / hop_seconds)))
        mask[lo:hi] = False
    return mask


def _frame_credit(err_cents: np.ndarray, cfg: PitchConfig) -> np.ndarray:
    """Soft per-frame credit in [0, 1]: full inside the tolerance, linear to zero."""
    span = cfg.zero_credit_cents - cfg.full_credit_cents
    return np.clip((cfg.zero_credit_cents - np.abs(err_cents)) / span, 0.0, 1.0)


def _align_length(user_hz: np.ndarray, n: int) -> np.ndarray:
    """Pad with unvoiced or truncate so the user track matches the reference."""
    out = np.full(n, np.nan)
    m = min(n, len(user_hz))
    out[:m] = user_hz[:m]
    return out


def pitch_score(
    user_hz: np.ndarray,
    ref_hz: np.ndarray,
    *,
    hop_seconds: float = HOP_SECONDS,
    register: int = 0,
    excluded: Sequence[tuple[float, float]] = (),
    frames: slice | None = None,
    cfg: PitchConfig | None = None,
) -> PitchResult:
    """Score a user pitch track against the reference.

    register: semitones the target is shifted for the whole turn (-12, 0, +12).
    excluded: (start, end) seconds removed from scoring, identical for everyone.
    frames:   restrict to a slice of frames (used for per-phrase scores).
    """
    cfg = cfg or PitchConfig()
    ref_hz = np.asarray(ref_hz, dtype=float)
    user = _align_length(np.asarray(user_hz, dtype=float), len(ref_hz))
    user = np.where(np.isfinite(user) & (user > 0), user, np.nan)

    mask = scoreable_mask(ref_hz, hop_seconds, excluded)
    target = ref_hz * 2.0 ** (register / 12.0)

    if frames is not None:
        keep = np.zeros_like(mask)
        keep[frames] = True
        mask &= keep

    # Each reference frame takes the best credit among user frames within the time
    # tolerance (k = 0 means strictly the same frame).
    k = int(round(cfg.time_tolerance_s / hop_seconds))
    credit = np.zeros(len(ref_hz))
    user_voiced = np.zeros(len(ref_hz), dtype=bool)
    for off in range(-k, k + 1):
        shifted = np.full(len(user), np.nan)
        if off >= 0:
            shifted[: len(user) - off] = user[off:]
        else:
            shifted[-off:] = user[: len(user) + off]
        ok = mask & np.isfinite(shifted)
        c = np.zeros(len(ref_hz))
        c[ok] = _frame_credit(cents_error(shifted[ok], target[ok]), cfg)
        credit = np.maximum(credit, c)
        user_voiced |= np.isfinite(shifted)
    both = mask & user_voiced

    return PitchResult(
        credit_sum=float(credit[mask].sum()),
        scoreable_frames=int(mask.sum()),
        voiced_frames=int(both.sum()),
    )


def phrase_pitch_scores(
    user_hz: np.ndarray,
    ref_hz: np.ndarray,
    phrases: Sequence[tuple[float, float]],
    **kwargs,
) -> list[PitchResult]:
    """Per-phrase results for (start, end) second spans. Use combine() for the total."""
    hop = kwargs.get("hop_seconds", HOP_SECONDS)
    return [
        pitch_score(
            user_hz, ref_hz,
            frames=slice(int(round(s / hop)), int(round(e / hop))),
            **kwargs,
        )
        for s, e in phrases
    ]
