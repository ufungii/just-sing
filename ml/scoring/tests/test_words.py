import numpy as np

from ml.evals.make_demo_manifest import build
from ml.scoring.pitch import to_track
from ml.scoring.words import word_feedback

HOP = 0.02


def setup():
    m = build()
    ref = to_track(m["reference"]["hz"])
    return m, ref


def statuses(fb):
    return [w["status"] for line in fb for w in line]


def test_perfect_take_sings_every_word_in_tune():
    m, ref = setup()
    fb = word_feedback(ref, ref, m["lines"])
    graded = [w for line in fb for w in line if w["status"] != "not_graded"]
    assert graded and all(w["status"] == "sung" and w["pitch"] == 100.0 for w in graded)


def test_silence_misses_every_word():
    m, ref = setup()
    fb = word_feedback(np.full_like(ref, np.nan), ref, m["lines"])
    assert set(statuses(fb)) <= {"missed", "not_graded"} and "missed" in statuses(fb)


def test_dropping_one_word_flags_only_that_word():
    m, ref = setup()
    w = m["lines"][0]["words"][1]
    user = ref.copy()
    user[int(round(w["start"] / HOP)):int(round(w["end"] / HOP))] = np.nan
    fb = word_feedback(user, ref, m["lines"])
    assert fb[0][1]["status"] in ("missed", "partly")
    assert fb[0][0]["status"] == "sung" and fb[1][0]["status"] == "sung"


def test_wrong_notes_are_sung_but_out_of_tune():
    m, ref = setup()
    fb = word_feedback(ref * 2 ** (300 / 1200), ref, m["lines"])   # 3 semitones sharp everywhere
    graded = [w for line in fb for w in line if w["status"] != "not_graded"]
    assert all(w["status"] == "sung" for w in graded) and max(w["pitch"] for w in graded) == 0.0


def test_register_and_latency_are_respected():
    m, ref = setup()
    late = np.concatenate([np.full(8, np.nan), ref * 2])           # octave up, 0.16 s device latency
    fb = word_feedback(late, ref, m["lines"], register=12, latency_offset_s=0.16)
    graded = [w for line in fb for w in line if w["status"] != "not_graded"]
    assert all(w["status"] == "sung" and w["pitch"] == 100.0 for w in graded)


def test_excluded_words_are_not_graded():
    m, ref = setup()
    w = m["lines"][0]["words"][0]
    fb = word_feedback(np.full_like(ref, np.nan), ref, m["lines"], excluded=[(w["start"] - 0.05, w["end"] + 0.05)])
    assert fb[0][0]["status"] == "not_graded"


def test_late_entrance_is_reported_without_shifting_away_the_gap():
    lines = [{"words": [{"text": "hello", "start": 0, "end": 1}]}]
    result = word_feedback([None] * 10 + [220] * 40, [220] * 50, lines)[0][0]
    assert result == {"text": "hello", "start": 0, "end": 1, "status": "sung",
                      "coverage": 0.8, "pitch": 80.0, "onset_delay_s": 0.2, "late": True}
    fixed = word_feedback([None] * 10 + [220] * 50, [220] * 50, lines,
                          latency_offset_s=0.2)[0][0]
    assert fixed["coverage"] == 1 and fixed["late"] is False


def test_one_frame_cannot_fill_neighboring_silence():
    lines = [{"words": [{"text": "hello", "start": 0, "end": 1}]}]
    result = word_feedback([None] * 25 + [220] + [None] * 24, [220] * 50, lines)[0][0]
    assert result["coverage"] == 0.02 and result["status"] == "missed"


def test_reference_invalid_values_and_empty_track_are_not_graded():
    lines = [{"words": [{"text": "hello", "start": 0, "end": 1}]}]
    for ref in ([], [0, -1, None, float("inf"), float("nan")]):
        result = word_feedback([220] * 50, ref, lines)[0][0]
        assert result["status"] == "not_graded"
        assert all(result[key] is None for key in ("pitch", "coverage", "onset_delay_s", "late"))


def test_word_fixture_is_current():
    import json
    from ml.evals.make_word_fixtures import OUT, build_fixture
    assert json.loads(OUT.read_text()) == build_fixture()


def test_invalid_settings_fail_explicitly():
    import pytest
    from ml.scoring.config import WordFeedbackConfig
    for kwargs in ({"hop_seconds": 0}, {"register": 1}, {"latency_offset_s": -0.1},
                   {"cfg": WordFeedbackConfig(sung_coverage=0.1)},
                   {"cfg": WordFeedbackConfig(late_after_s=float("nan"))}):
        with pytest.raises(ValueError):
            word_feedback([220], [220], [], **kwargs)


def test_typescript_handoff_passes_shared_fixtures(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path
    import pytest
    if not shutil.which("node") or not shutil.which("git"):
        pytest.skip("Node 24+ and git required for TypeScript handoff parity")
    root = Path(__file__).resolve().parents[3]
    patch = root / "ml/scoring/ts_word_feedback.patch"
    # Apply in a temporary directory; never edit frontend's working files.
    subprocess.run(["git", "apply", str(patch)], cwd=tmp_path, check=True)
    subprocess.run(["node", str(root / "ml/evals/node/word_feedback_parity.mjs"),
                    str(tmp_path / "web/src/scoring/words.ts"),
                    str(root / "contracts/fixtures/word_feedback.json")], check=True)
