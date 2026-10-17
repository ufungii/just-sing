import numpy as np

from ml.evals.check_recording import SR, analyze, verdict
from ml.evals.synthetic import example_melody, render_audio


def voice(seconds=8):
    y = np.tile(render_audio(example_melody()), 2)[: int(seconds * SR)]
    return (y / np.abs(y).max() * 0.5).astype(np.float32)


def noise(level, n, seed=0):
    return (np.random.default_rng(seed).standard_normal(n) * level).astype(np.float32)


def test_clean_recording_is_ok():
    assert verdict(analyze(voice() + noise(0.001, len(voice()))))[0] == "OK"


def test_too_quiet_noisy_clipped_and_empty_are_rejected():
    y = voice()
    assert verdict(analyze(y * 0.01))[0] == "RE-RECORD"                      # far too quiet
    assert verdict(analyze(np.clip(y * 6, -1, 1)))[0] == "RE-RECORD"          # clipped
    assert verdict(analyze(y + noise(0.25, len(y))))[0] == "RE-RECORD"        # voice buried in noise
    assert verdict(analyze(noise(0.0005, 8 * SR)))[0] == "RE-RECORD"          # nothing there


def test_moderately_noisy_room_is_usable_with_a_note():
    y = voice()
    status, msgs = verdict(analyze(y + noise(0.04, len(y))))
    assert status == "OK" and any("noisy room" in m for m in msgs)
