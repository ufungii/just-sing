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
def pitch_contour(
    audio: np.ndarray,
    sr: int,
    backend: str = "pyin",
    hop_seconds: float = HOP_SECONDS,
) -> np.ndarray:
    """Extract a Hz contour (NaN = unvoiced) from mono audio.

    One shared function: the offline pipeline uses it for the reference
    (backend="crepe") and the evals use it on degraded audio (default "pyin",
    CPU-only). Heavy imports are lazy so this module stays importable without
    PyTorch.
    """
    import librosa  # lazy: only needed when extracting from audio

    audio = np.asarray(audio, dtype=np.float32)
    if sr != EXTRACTION_SR:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=EXTRACTION_SR)
    hop = int(round(hop_seconds * EXTRACTION_SR))

    if backend == "pyin":
        f0, _, _ = librosa.pyin(
            audio, fmin=FMIN_HZ, fmax=FMAX_HZ, sr=EXTRACTION_SR,
            frame_length=2048, hop_length=hop,
        )
        return np.where(np.isfinite(f0) & (f0 > 0), f0, np.nan)

    if backend == "crepe":
        # Verified with torchcrepe 0.0.24 on CUDA against synthetic ground truth
        # (median error ~8 cents, see test_crepe_backend_matches_ground_truth).
        import torch
        import torchcrepe

        x = torch.from_numpy(audio)[None]
        pitch, periodicity = torchcrepe.predict(
            x, EXTRACTION_SR, hop, FMIN_HZ, FMAX_HZ, model="full",
            batch_size=512, device="cuda" if torch.cuda.is_available() else "cpu",
            return_periodicity=True,
        )
        periodicity = torchcrepe.filter.median(periodicity, 3)
        pitch = torchcrepe.threshold.At(0.5)(pitch, periodicity)  # unvoiced -> NaN
        pitch = torchcrepe.filter.mean(pitch, 3)
        return pitch.squeeze(0).cpu().numpy()

    raise ValueError(f"unknown pitch backend: {backend!r}")


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
