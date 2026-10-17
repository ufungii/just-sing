import numpy as np
import pytest

from ml.evals.synthetic import detune, example_melody, melody_track, midi_to_hz, render_audio
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


def test_crepe_backend_matches_ground_truth():
    # Runs only where torchcrepe is installed (the GPU / prep environment).
    pytest.importorskip("torchcrepe")
    notes = example_melody()
    ref = melody_track(notes, HOP)
    track = pitch_contour(render_audio(notes), 16_000, backend="crepe")
    assert abs(len(track) - len(ref)) <= 2
    assert pitch_score(track, ref).score > 90
    assert pitch_score(pitch_contour(render_audio(detune(notes, 150)), 16_000, backend="crepe"), ref).score < 75


def test_time_tolerance_forgives_small_lateness_but_not_wrong_notes(ref):
    from ml.scoring.config import PitchConfig

    late = np.concatenate([np.full(5, np.nan), ref])  # 0.1 s late
    strict, tol = PitchConfig(), PitchConfig(time_tolerance_s=0.1)
    assert pitch_score(late, ref, cfg=strict).score < 97
    assert pitch_score(late, ref, cfg=tol).score == pytest.approx(100.0)
    assert pitch_score(ref * 2, ref, cfg=tol).score == 0.0          # wrong register still wrong
    assert pitch_score(np.full_like(ref, np.nan), ref, cfg=tol).score == 0.0


# --- shared extractor: RMS gate, smoothing, manifest form ---
def test_quiet_audio_is_gated_to_silence_even_if_a_pitch_is_present():
    notes = example_melody()
    loud = render_audio(notes)
    assert np.isfinite(pitch_contour(loud, 16_000)).mean() > 0.5
    assert np.isfinite(pitch_contour(loud * 0.005, 16_000)).sum() == 0      # RMS far below the gate
    assert np.isfinite(pitch_contour(loud * 0.005, 16_000, rms_gate=0.0)).mean() > 0.5  # gate is the reason


def test_smoothing_removes_isolated_single_frame_blips():
    from ml.scoring.pitch import _clean

    t = 1.0
    signal = np.full(16_000, 0.3, dtype=np.float32)
    pitch = np.full(51, np.nan)
    pitch[10] = 440.0                                  # a lone detection surrounded by silence
    pitch[20:30] = 220.0                               # a real note
    out = _clean(pitch, signal, rms_gate=0.0, smooth=True)
    assert np.isnan(out[10]) and np.isfinite(out[20:30]).all()
    assert np.isfinite(_clean(pitch, signal, rms_gate=0.0, smooth=False)[10])


def test_reference_contour_is_manifest_ready_and_json_safe():
    import json

    from ml.scoring.pitch import reference_contour

    notes = example_melody()
    ref = reference_contour(render_audio(notes), 16_000, backend="pyin")
    json.dumps(ref, allow_nan=False)                   # raises on NaN/inf
    assert ref["hop_seconds"] == 0.02 and ref["backend"] == "pyin"
    assert len(ref["hz"]) == len(ref["periodicity"]) and ref["settings"]["minimum_rms"] == 0.003
    truth = melody_track(notes, HOP)
    assert pitch_score(to_track(ref["hz"]), truth).score > 85


def test_crepe_chunking_is_seamless_across_the_15_second_boundary():
    pytest.importorskip("torchcrepe")
    notes = example_melody() * 4                       # ~41 s: spans two 15 s chunk boundaries
    # Truth from exact note edges: melody_track rounds each note's length separately, which drifts
    # ~0.1 s against the sample-exact audio over 56 notes and would look like an extractor error.
    edges = np.cumsum([0.0] + [d for _, d in notes])
    truth = np.full(int(round(edges[-1] / HOP)), np.nan)
    for (midi, _), t0, t1 in zip(notes, edges[:-1], edges[1:]):
        if midi is not None:
            truth[int(round(t0 / HOP)):int(round(t1 / HOP))] = midi_to_hz(midi)
    track = pitch_contour(render_audio(notes), 16_000, backend="crepe")
    assert abs(len(track) - len(truth)) <= 2
    assert pitch_score(track, truth).score > 90
    # the frames right at each chunk boundary (15 s and 30 s) must not drop out
    for boundary_s in (15.0, 30.0):
        i = int(boundary_s / HOP)
        window_truth, window_track = truth[i - 10:i + 10], track[i - 10:i + 10]
        sung = np.isfinite(window_truth)
        assert np.isfinite(window_track[sung]).mean() > 0.8
