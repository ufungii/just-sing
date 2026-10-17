import numpy as np
import pytest

from ml.evals.synthetic import detune, example_melody, melody_track, render_audio
from ml.scoring.pitch import (
    combine,
    phrase_pitch_scores,
    pitch_contour,
    pitch_score,
    to_track,
    track_to_json,
)

HOP = 0.02


@pytest.fixture
def ref():
    return melody_track(example_melody(), HOP)


def test_self_score_is_perfect(ref):
    r = pitch_score(ref, ref)
    assert r.score == pytest.approx(100.0)
    assert r.coverage == 1.0


def test_deterministic(ref):
    assert pitch_score(ref * 1.01, ref) == pitch_score(ref * 1.01, ref)


def test_silence_scores_zero(ref):
    r = pitch_score(np.full_like(ref, np.nan), ref)
    assert r.score == 0.0
    assert r.coverage == 0.0


def test_missing_frames_stay_in_denominator(ref):
    half = ref.copy()
    half[len(half) // 2:] = np.nan
    assert 30 < pitch_score(half, ref).score < 70  # not ~100


def test_noise_scores_low(ref):
    rng = np.random.default_rng(0)
    noise = rng.uniform(65, 1000, size=len(ref))
    assert pitch_score(noise, ref).score < 30


def test_register_octave_is_comparable_when_selected(ref):
    up = ref * 2.0
    assert pitch_score(up, ref, register=12).score == pytest.approx(100.0)
    down = ref / 2.0
    assert pitch_score(down, ref, register=-12).score == pytest.approx(100.0)


def test_wrong_register_is_not_forgiven(ref):
    assert pitch_score(ref * 2.0, ref, register=0).score == 0.0


def test_rests_do_not_enter_denominator(ref):
    r = pitch_score(ref, ref)
    assert r.scoreable_frames == int(np.isfinite(ref).sum())
    # singing during a rest neither helps nor hurts
    noisy_rests = np.where(np.isfinite(ref), ref, 300.0)
    assert pitch_score(noisy_rests, ref).score == pytest.approx(100.0)


def test_excluded_regions_are_removed(ref):
    garbage = ref.copy()
    garbage[50:100] = 900.0  # 1.0 s - 2.0 s sung wrong
    assert pitch_score(garbage, ref).score < 100
    r = pitch_score(garbage, ref, excluded=[(1.0, 2.0)])
    assert r.score == pytest.approx(100.0)


def test_score_decreases_with_local_detune_severity():
    notes = example_melody()
    ref = melody_track(notes, HOP)
    scores = [
        pitch_score(melody_track(detune(notes, c), HOP), ref).score
        for c in (0, 25, 50, 100, 150, 250, 400)
    ]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > 99 and scores[-1] < 60


def test_length_mismatch_is_handled(ref):
    short = ref[: len(ref) // 2]
    assert 30 < pitch_score(short, ref).score < 70
    assert pitch_score(np.concatenate([ref, ref]), ref).score == pytest.approx(100.0)


def test_phrase_scores_aggregate_to_whole(ref):
    n = len(ref) * HOP
    phrases = [(0.0, n / 2), (n / 2, n)]
    parts = phrase_pitch_scores(ref, ref, phrases)
    assert combine(parts).score == pytest.approx(pitch_score(ref, ref).score)
    bad = ref.copy()
    bad[: len(bad) // 2] = np.nan
    first, second = phrase_pitch_scores(bad, ref, phrases)
    assert first.score < 5 and second.score == pytest.approx(100.0)


def test_json_round_trip():
    track = to_track([None, 392.0, 440.5])
    assert np.isnan(track[0])
    assert track_to_json(track) == [None, 392.0, 440.5]


def test_pyin_extraction_matches_ground_truth_and_ranks_detuning():
    pytest.importorskip("librosa")
    notes = example_melody()
    ref = melody_track(notes, HOP)

    clean = pitch_contour(render_audio(notes), 16_000)
    off = pitch_contour(render_audio(detune(notes, 150)), 16_000)

    good = pitch_score(clean, ref).score
    bad = pitch_score(off, ref).score
    assert good > 85, f"clean extraction scored only {good:.1f}"
    assert bad < good - 15, f"detuned take not clearly worse: {bad:.1f} vs {good:.1f}"
