import numpy as np

from ml.evals.align_take import align
from ml.evals.synthetic import example_melody, melody_track

HOP = 0.02


def song():
    """~41 s melody that never repeats exactly (a repeating song has several equally good offsets,
    which the aligner reports as a small margin, but a test needs one right answer)."""
    m = example_melody()
    up = [(n + 3 if n is not None else None, d) for n, d in m]
    rev = list(reversed(m))
    down = [(n - 2 if n is not None else None, d) for n, d in rev]
    return melody_track(m + up + rev + down, HOP)


def test_finds_lead_in_and_octave():
    ref = song()
    take = np.concatenate([np.full(115, np.nan), ref[:1200] / 2])   # starts 2.3 s in, sung an octave down
    r = align(take, ref)
    assert abs(r["lead_in_s"] - 2.3) <= 0.02 and r["register"] == -12 and r["agreement"] > 0.9


def test_recording_that_starts_after_the_song():
    ref = song()
    take = ref[500:1700].copy()                                    # recording begins at song t = 10 s
    r = align(take, ref)
    assert abs(r["lead_in_s"] + 10.0) <= 0.02 and r["register"] == 0


def test_a_repeating_song_is_reported_as_ambiguous():
    ref = melody_track(example_melody() * 4, HOP)                     # the same 10 s melody four times
    r = align(ref[600:1100].copy(), ref)
    assert r["margin"] < 0.05                                        # another repeat matches just as well


def test_noise_is_reported_as_a_weak_match():
    ref = song()
    noise = np.random.default_rng(0).uniform(100, 600, size=1500)
    r = align(noise, ref)
    assert r["agreement"] < 0.3
