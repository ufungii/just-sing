"""The Node Pitchy runner and the emulation agree on a clean tone and a melody.
Skipped unless Node and a Pitchy build (PITCHY_PATH) are available."""
import os
import shutil

import numpy as np
import pytest

from ml.evals.mpm import mpm_track
from ml.evals.synthetic import example_melody, render_audio


def _available():
    from ml.evals.pitchy_node import VENDORED
    return shutil.which("node") and (os.environ.get("PITCHY_PATH") or VENDORED.exists())


pytestmark = pytest.mark.skipif(not _available(), reason="needs node and PITCHY_PATH")


def test_real_pitchy_finds_a_tone_with_center_aligned_frames():
    from ml.evals.pitchy_node import pitchy_track
    t = np.arange(16_000) / 16_000
    track = pitchy_track((0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 16_000)
    assert len(track) == 51                                  # 1 s at 20 ms, frame 0 at t = 0
    assert np.nanmedian(track) == pytest.approx(220, abs=0.5)


def test_emulation_matches_real_pitchy_on_a_melody():
    from ml.evals.pitchy_node import pitchy_track
    y = render_audio(example_melody())
    real = pitchy_track(y, 16_000, sample_rate=48_000, window=4096, clarity=0.8, gate=0.008)
    emu = mpm_track(y, 16_000, clarity_threshold=0.8, frame_length=4096, silence_gate_rms=0.008, analysis_sr=48_000)
    n = min(len(real), len(emu))
    both = np.isfinite(real[:n]) & np.isfinite(emu[:n])
    assert both.sum() / max(1, (np.isfinite(real[:n]) | np.isfinite(emu[:n])).sum()) > 0.9
    assert np.median(np.abs(1200 * np.log2(real[:n][both] / emu[:n][both]))) < 10
