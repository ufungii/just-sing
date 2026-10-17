import numpy as np

from ml.evals.make_demo_manifest import OFFSETS, build
from ml.evals.score_take import SR, score_take
from ml.evals.synthetic import example_melody, render_audio


def demo_take(offset_error_s=0.0):
    """The demo clip's melody sung at its scheduled times (optionally all late)."""
    m = example_melody()
    one = render_audio(m, sr=SR)
    out = np.zeros(int(30.0 * SR), np.float32)
    for off in OFFSETS:
        a = int((off + offset_error_s) * SR)
        out[a:a + len(one)] = one[:len(out) - a]
    return out


def test_a_good_take_scores_high_and_silence_scores_zero():
    manifest = build()
    good = score_take(demo_take(), manifest, tracker="pyin")["score"]
    assert good["total"] > 85 and all(p["rating"] in ("perfect", "great") for p in good["phrases"])
    quiet = score_take(np.zeros(30 * SR, np.float32), manifest, tracker="mpm")
    assert quiet["score"]["total"] == 0.0
    assert quiet["diagnostics"]["take_voiced_where_reference_scoreable"] == 0.0


def test_lateness_is_reported_and_calibration_removes_it():
    manifest = build()
    late = score_take(demo_take(0.2), manifest, tracker="pyin")
    assert late["score"]["total"] < 80
    assert 0.1 < late["diagnostics"]["median_note_offset_s"] < 0.3
    fixed = score_take(demo_take(0.2), manifest, tracker="pyin", latency_s=0.2)
    assert fixed["score"]["total"] > 85


def test_word_feedback_uses_raw_track_and_does_not_change_the_score(monkeypatch):
    from ml.evals import score_take as module
    from ml.scoring.pitch import to_track
    from ml.scoring.words import word_feedback

    manifest = build()
    ref = to_track(manifest["reference"]["hz"])
    user = np.concatenate([np.full(8, np.nan), ref * 2])
    monkeypatch.setattr(module, "track_audio", lambda *args: user)
    out = module.score_take(np.zeros(10), manifest, register=12, latency_s=0.16)
    assert out["word_feedback_version"] == "1.0.0"
    assert out["word_feedback"] == word_feedback(user, ref, manifest["lines"],
                                                register=12, latency_offset_s=0.16)
    graded = [word for line in out["word_feedback"] for word in line
              if word["status"] != "not_graded"]
    assert graded and all(word["coverage"] == 1 and word["pitch"] == 100
                          and word["late"] is False for word in graded)
    without_lines = module.score_take(np.zeros(10), {**manifest, "lines": []},
                                     register=12, latency_s=0.16)
    assert out["score"] == without_lines["score"]
    assert without_lines["word_feedback"] == []
