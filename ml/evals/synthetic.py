"""Synthetic melodies for tests and evals.

We have no labeled singing data, so we build melodies with known ground truth
and degrade them in controlled ways. A "melody" is a list of (midi, seconds)
notes; midi=None is a rest.
"""
import numpy as np

Note = tuple[float | None, float]


def midi_to_hz(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69.0) / 12.0)


def example_melody() -> list[Note]:
    """~9 s phrase in a comfortable singing range, with rests between phrases."""
    return [
        (64, 0.5), (67, 0.5), (69, 0.75), (67, 0.5), (64, 0.75),
        (None, 0.5),
        (62, 0.5), (65, 0.5), (67, 0.75), (65, 0.5), (62, 0.75),
        (None, 0.5),
        (60, 0.5), (64, 0.5), (67, 1.0), (72, 1.25),
    ]


def melody_track(notes: list[Note], hop_seconds: float = 0.02) -> np.ndarray:
    """Ground-truth Hz track (NaN for rests) at the scoring hop."""
    parts = []
    for midi, dur in notes:
        n = int(round(dur / hop_seconds))
        parts.append(np.full(n, np.nan if midi is None else midi_to_hz(midi)))
    return np.concatenate(parts)


def detune(notes: list[Note], cents: float, every: int = 2) -> list[Note]:
    """Local degradation: shift every `every`-th note by `cents` (sign alternates).

    A *global* shift is just a register/key change, so it is not a severity axis.
    """
    out = []
    for i, (midi, dur) in enumerate(notes):
        if midi is not None and i % every == 0:
            midi += (cents / 100.0) * (1 if (i // every) % 2 == 0 else -1)
        out.append((midi, dur))
    return out


def render_audio(
    notes: list[Note], sr: int = 16_000, vibrato_cents: float = 20.0, seed: int = 0
) -> np.ndarray:
    """Voice-like audio: a few harmonics with light vibrato, silence on rests."""
    rng = np.random.default_rng(seed)
    chunks = []
    for midi, dur in notes:
        n = int(round(dur * sr))
        if midi is None:
            chunks.append(np.zeros(n))
            continue
        t = np.arange(n) / sr
        vib = vibrato_cents * np.sin(2 * np.pi * 5.5 * t + rng.uniform(0, 2 * np.pi))
        f = midi_to_hz(midi) * 2.0 ** (vib / 1200.0)
        phase = 2 * np.pi * np.cumsum(f) / sr
        wave = sum(np.sin(k * phase) / k for k in range(1, 6))
        fade = np.minimum(1.0, np.minimum(t, t[::-1]) / 0.02)  # avoid clicks
        chunks.append(0.3 * wave * fade)
    return np.concatenate(chunks).astype(np.float32)


# --------------------------------------------------------------------------- #
# Eval helpers: phrases and controlled degradations (all seeded, deterministic)
# --------------------------------------------------------------------------- #
def example_phrases() -> list[tuple[str, float, float]]:
    """(id, start_s, end_s) phrase boundaries matching example_melody()."""
    return [("p1", 0.0, 3.2), ("p2", 3.2, 6.0), ("p3", 6.0, 9.5)]


def detune_random(notes: list[Note], cents: float, seed: int = 0) -> list[Note]:
    """Shift EVERY note by +/- `cents` (random sign). Local error, not a key change."""
    rng = np.random.default_rng(seed)
    return [
        (m if m is None else m + rng.choice([-1.0, 1.0]) * cents / 100.0, d)
        for m, d in notes
    ]


def drop_notes(notes: list[Note], fraction: float, seed: int = 0) -> list[Note]:
    """Replace a random `fraction` of the sung notes with rests (the singer skipped them)."""
    rng = np.random.default_rng(seed)
    sung = [i for i, (m, _) in enumerate(notes) if m is not None]
    k = int(round(fraction * len(sung)))
    gone = set(rng.choice(sung, size=k, replace=False).tolist()) if k else set()
    return [(None if i in gone else m, d) for i, (m, d) in enumerate(notes)]


def add_noise(audio: np.ndarray, snr_db: float, seed: int = 0) -> np.ndarray:
    """Add white noise at a signal-to-noise ratio in dB."""
    rng = np.random.default_rng(seed)
    power = float(np.mean(audio**2)) or 1e-12
    noise = rng.standard_normal(len(audio)) * np.sqrt(power / 10 ** (snr_db / 10))
    return (audio + noise).astype(np.float32)


def delay(audio: np.ndarray, sr: int, seconds: float) -> np.ndarray:
    """Start `seconds` late (singer entered late)."""
    return np.concatenate([np.zeros(int(round(seconds * sr)), np.float32), audio])


def time_stretch(audio: np.ndarray, rate: float) -> np.ndarray:
    """rate < 1 is slower (singer drags), > 1 is faster."""
    import librosa

    return librosa.effects.time_stretch(audio, rate=rate)
