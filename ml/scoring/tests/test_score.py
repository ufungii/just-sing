import numpy as np
import pytest

from ml.evals.synthetic import example_melody, melody_track
from ml.scoring.score import score_turn

HOP = 0.02
PHRASES = [("p1", 0.0, 3.2), ("p2", 3.2, 6.0), ("p3", 6.0, 10.25)]


@pytest.fixture
def ref():
    return melody_track(example_melody(), HOP)


def run(user, ref, **kw):
    return score_turn(user, ref, PHRASES, **kw)


def test_perfect_take(ref):
    r = run(ref, ref)
    assert r["total"] == r["pitch"] == r["timing"] == 100.0
    assert [p["rating"] for p in r["phrases"]] == ["perfect"] * 3


def test_silence_scores_zero_overall(ref):
    r = run(np.full_like(ref, np.nan), ref)
    assert r["total"] == 0.0
    assert all(p["rating"] == "miss" for p in r["phrases"])


def test_wrong_register_is_bad_not_miss(ref):
    r = run(ref * 2.0, ref)  # sung an octave up but register left at original
    assert r["pitch"] == 0.0 and r["timing"] == 100.0
    assert r["total"] == pytest.approx(20.0)
    assert all(p["rating"] == "bad" for p in r["phrases"])


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
    assert r["phrases"][0]["rating"] == "miss"
    assert r["phrases"][1]["rating"] == "perfect"


def test_deterministic(ref):
    assert run(ref * 1.02, ref) == run(ref * 1.02, ref)


def _late(track, seconds):
    n = int(round(seconds / HOP))
    # a real recording keeps running past the clip end, so do not truncate the delayed track
    return np.concatenate([np.full(n, np.nan), track])


def test_calibrated_device_latency_costs_nothing_on_pitch_or_timing(ref):
    r = run(_late(ref, 0.16), ref, latency_offset_s=0.16)
    assert r["pitch"] == r["timing"] == r["total"] == 100.0


def test_uncalibrated_lateness_is_penalized(ref):
    assert run(_late(ref, 0.3), ref)["total"] < 70   # inside tolerance only for the first 0.1 s of lateness


def test_garbage_in_excluded_region_does_not_cost_timing(ref):
    garbage = ref.copy()
    garbage[50:100] = 900.0  # 1.0 s - 2.0 s
    r = run(garbage, ref, excluded=[(1.0, 2.0)])
    assert r["pitch"] == r["timing"] == r["total"] == 100.0


# --- finalize_turn: what the API calls on browser-submitted phrase results ---
from ml.scoring.score import finalize_turn, phrase_weights  # noqa: E402

IDS = [p[0] for p in PHRASES]


def _submit(result):
    """What a browser would send: only the measured fields, no score/rating."""
    return [{k: p[k] for k in ("phrase_id", "pitch", "timing", "coverage")} for p in result["phrases"]]


def test_finalize_matches_score_turn(ref):
    user = ref.copy()
    user[: int(3.2 / HOP)] = np.nan
    full = run(user, ref)
    weights = phrase_weights(ref, PHRASES)
    again = finalize_turn(_submit(full), weights, expected_phrase_ids=IDS)
    assert again == full


def test_finalize_ignores_client_supplied_score_and_rating(ref):
    sub = _submit(run(ref, ref))
    for p in sub:
        p["score"], p["rating"] = 100, "perfect"
    sub[0]["pitch"] = 0.0  # but the measured fields say otherwise
    out = finalize_turn(sub, phrase_weights(ref, PHRASES), expected_phrase_ids=IDS)
    assert out["phrases"][0]["score"] < 100 and out["total"] < 100


@pytest.mark.parametrize("mutate", [
    lambda s: s.pop(),                                         # missing phrase
    lambda s: s.append(dict(s[0])),                            # duplicate phrase
    lambda s: s[0].update(phrase_id="nope"),                   # unknown phrase
    lambda s: s[0].update(pitch=101),                          # out of range
    lambda s: s[0].update(pitch=float("nan")),                 # non-finite
    lambda s: s[0].update(coverage=-0.1),
    lambda s: s[0].update(timing="90"),                        # wrong type
])
def test_finalize_rejects_bad_input(ref, mutate):
    sub = _submit(run(ref, ref))
    mutate(sub)
    with pytest.raises(ValueError):
        finalize_turn(sub, phrase_weights(ref, PHRASES), expected_phrase_ids=IDS)


def test_finalize_rejects_bad_register(ref):
    with pytest.raises(ValueError):
        finalize_turn(_submit(run(ref, ref)), phrase_weights(ref, PHRASES),
                      expected_phrase_ids=IDS, register=7)


def test_finalize_allows_null_timing(ref):
    sub = _submit(run(ref, ref))
    sub[0]["timing"] = None
    out = finalize_turn(sub, phrase_weights(ref, PHRASES), expected_phrase_ids=IDS)
    assert out["phrases"][0]["timing"] is None and out["phrases"][0]["score"] == 100.0


def test_finalize_rejects_a_clip_with_nothing_scoreable(ref):
    sub = _submit(run(ref, ref))
    with pytest.raises(ValueError, match="no scoreable"):
        finalize_turn(sub, [0, 0, 0], expected_phrase_ids=IDS)
