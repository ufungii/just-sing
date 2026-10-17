import numpy as np
import pytest

from ml.evals.synthetic import example_melody, melody_track
from ml.scoring.score import score_turn

HOP = 0.02
PHRASES = [("p1", 0.0, 3.2), ("p2", 3.2, 6.0), ("p3", 6.0, 9.5)]


@pytest.fixture
def ref():
    return melody_track(example_melody(), HOP)


def run(user, ref, **kw):
    return score_turn(user, ref, PHRASES, **kw)


def test_perfect_take(ref):
    r = run(ref, ref)
    assert r["total"] == r["pitch"] == r["timing"] == 100.0
    assert [p["rating"] for p in r["phrases"]] == ["Perfect!"] * 3


def test_silence_scores_zero_overall(ref):
    r = run(np.full_like(ref, np.nan), ref)
    assert r["total"] == 0.0
    assert all(p["rating"] == "Miss" for p in r["phrases"])


def test_wrong_register_is_bad_not_miss(ref):
    r = run(ref * 2.0, ref)  # sung an octave up but register left at original
    assert r["pitch"] == 0.0 and r["timing"] == 100.0
    assert r["total"] == pytest.approx(20.0)
    assert all(p["rating"] == "Bad" for p in r["phrases"])


def test_selected_register_scores_like_original(ref):
    assert run(ref * 2.0, ref, register=12)["total"] == run(ref, ref)["total"]


def test_total_agrees_with_phrase_scores(ref):
    user = ref.copy()
    user[: int(3.2 / HOP)] = np.nan  # first phrase unsung
    r = run(user, ref)
    # frame-weighted mean of the displayed phrase scores
    w = np.array([int(np.isfinite(ref[int(s / HOP):int(e / HOP)]).sum()) for _, s, e in PHRASES])
    s = np.array([p["score"] for p in r["phrases"]])
    assert r["total"] == pytest.approx(float((s * w).sum() / w.sum()), abs=0.1)
    assert r["phrases"][0]["rating"] == "Miss"
    assert r["phrases"][1]["rating"] == "Perfect!"


def test_deterministic(ref):
    assert run(ref * 1.02, ref) == run(ref * 1.02, ref)


def _late(track, seconds):
    n = int(round(seconds / HOP))
    return np.concatenate([np.full(n, np.nan), track])[: len(track)]


def test_calibrated_device_latency_costs_nothing_on_pitch_or_timing(ref):
    r = run(_late(ref, 0.16), ref, latency_offset_s=0.16)
    assert r["pitch"] == r["timing"] == r["total"] == 100.0


def test_uncalibrated_lateness_is_penalized(ref):
    assert run(_late(ref, 0.3), ref)["total"] < 60


def test_garbage_in_excluded_region_does_not_cost_timing(ref):
    garbage = ref.copy()
    garbage[50:100] = 900.0  # 1.0 s - 2.0 s
    r = run(garbage, ref, excluded=[(1.0, 2.0)])
    assert r["pitch"] == r["timing"] == r["total"] == 100.0
