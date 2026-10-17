import numpy as np
import pytest

from ml.evals.synthetic import example_melody, melody_track, render_audio
from ml.scoring.pitch import pitch_contour
from ml.scoring.timing import combine, onset_times, timing_score

HOP = 0.02


def shift(track, seconds):
    """Delay a track by `seconds` (pad the front with unvoiced frames)."""
    n = int(round(seconds / HOP))
    return np.concatenate([np.full(n, np.nan), track])[: len(track)]


@pytest.fixture
def ref():
    return melody_track(example_melody(), HOP)


@pytest.fixture
def onsets(ref):
    return onset_times(ref, HOP)


def test_onsets_found_at_note_starts(onsets):
    # 3 phrases of 5, 5 and 4 notes separated by rests -> 14 notes
    assert len(onsets) == 14
    assert onsets[0] == 0.0
    assert onsets[1] == pytest.approx(0.5)


def test_self_timing_is_perfect(ref, onsets):
    r = timing_score(ref, onsets)
    assert r.score == pytest.approx(100.0)
    assert r.median_offset_s == pytest.approx(0.0)


def test_known_capture_offset_is_corrected(ref, onsets):
    late = shift(ref, 0.16)  # simulated device latency
    assert timing_score(late, onsets, latency_offset_s=0.16).score == pytest.approx(100.0)
    assert timing_score(late, onsets, latency_offset_s=0.0).score < 90


def test_deliberate_lateness_stays_penalized(ref, onsets):
    # device latency 0.1 s is calibrated out; the singer is genuinely another 0.3 s late
    scores = [
        timing_score(shift(ref, 0.1 + extra), onsets, latency_offset_s=0.1).score
        for extra in (0.0, 0.1, 0.2, 0.3, 0.45)
    ]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == pytest.approx(100.0) and scores[-1] == 0.0


def test_early_and_late_have_opposite_signs(ref, onsets):
    assert timing_score(shift(ref, 0.2), onsets).median_offset_s > 0
    early = np.concatenate([ref[10:], np.full(10, np.nan)])  # 0.2 s early
    assert timing_score(early, onsets).median_offset_s < 0


def test_timing_ignores_pitch(ref, onsets):
    wrong_octave = ref * 2.0
    assert timing_score(wrong_octave, onsets).score == pytest.approx(100.0)


def test_silence_scores_zero(ref, onsets):
    assert timing_score(np.full_like(ref, np.nan), onsets).score == 0.0


def test_noise_earns_no_timing_points(ref, onsets):
    rng = np.random.default_rng(0)
    noise = rng.uniform(65, 1000, size=len(ref))
    assert timing_score(noise, onsets).score < 10


def test_humming_one_steady_note_scores_low(ref, onsets):
    hum = np.full_like(ref, 220.0)
    assert timing_score(hum, onsets).score < 20


def test_missed_entrances_stay_in_denominator(ref, onsets):
    half = ref.copy()
    half[len(half) // 2:] = np.nan
    assert 30 < timing_score(half, onsets).score < 70


def test_span_restricts_and_combines(ref, onsets):
    spans = [(0.0, 4.0), (4.0, 20.0)]
    parts = [timing_score(ref, onsets, span=s) for s in spans]
    assert sum(p.n_onsets for p in parts) == len(onsets)
    assert combine(parts).score == pytest.approx(100.0)


def test_pyin_audio_late_take_is_penalized_and_calibration_corrects_it():
    pytest.importorskip("librosa")
    notes = example_melody()
    onsets = onset_times(melody_track(notes, HOP), HOP)

    on_time = pitch_contour(render_audio(notes), 16_000)
    late = pitch_contour(np.concatenate([np.zeros(int(0.3 * 16_000), np.float32), render_audio(notes)]), 16_000)

    good = timing_score(on_time, onsets).score
    bad = timing_score(late, onsets).score
    fixed = timing_score(late, onsets, latency_offset_s=0.3).score
    assert good > 85, good
    assert bad < good - 25, (bad, good)
    assert fixed > 85, fixed
