"""Generate the additive, display-only word contract: python -m ml.evals.make_word_fixtures."""
from dataclasses import asdict
import json
from pathlib import Path

from ml.scoring.config import PitchConfig, WordFeedbackConfig
from ml.scoring.words import WORD_FEEDBACK_VERSION, word_feedback

OUT = Path(__file__).resolve().parents[2] / "contracts/fixtures/word_feedback.json"


def build_fixture():
    # Short tracks keep these fixtures readable and easy to port independently.
    words = [{"text": text, "start": i * 0.4, "end": (i + 1) * 0.4}
             for i, text in enumerate(["one", "two", "three"])]
    lines = [{"words": words[:2]}, {"words": words[2:]}, {"words": []}]
    ref = [220.0] * 60
    specs = [
        ("perfect", ref, {}),
        ("silence", [None] * 60, {}),
        ("middle_word_dropped", ref[:20] + [None] * 20 + ref[40:], {}),
        ("late_middle_word", ref[:20] + [None] * 8 + ref[28:], {}),
        ("late_threshold_equal", [None] * 6 + ref[6:], {}),
        ("sung_threshold_equal", ref[:10] + [None] * 10 + ref[20:], {}),
        ("partly_threshold_equal", ref[:4] + [None] * 16 + ref[20:], {}),
        ("below_partly_threshold", ref[:3] + [None] * 17 + ref[20:], {}),
        ("soft_pitch_credit", [round(220 * 2 ** (100 / 1200), 2)] * 60, {}),
        ("wrong_notes_still_sung", [440.0] * 60, {}),
        ("correct_register", [440.0] * 60, {"register": 12}),
        ("lower_register", [110.0] * 60, {"register": -12}),
        ("device_latency", [None] * 8 + ref, {"latency_offset_s": 0.16}),
        ("late_tail_not_credited_to_word", [None] * 20 + ref, {}),
        ("short_recording", ref[:20], {}),
        ("empty_recording", [], {}),
        ("excluded_middle_word", ref, {"excluded": [[0.4, 0.8]]}),
        ("reference_rests", ref, {"ref_hz": [None] * 20 + ref[20:]}),
        ("invalid_hz_unvoiced", [0, -1, None] * 20, {"ref_hz": [0, -1, None] * 20}),
        ("invalid_player_hz", [0, -1, None] * 20, {}),
        ("half_even_and_clipping", ref, {"lines": [{"words": [
            {"text": "clipped", "start": -0.2, "end": 0.05},
            {"text": "tie", "start": 0.05, "end": 0.09},
            {"text": "empty", "start": 0.2, "end": 0.2},
            {"text": "past_end", "start": 2, "end": 3}]}]}),
    ]
    cases = []
    for name, user, overrides in specs:
        inputs = dict(user_hz=user, ref_hz=ref, lines=lines, hop_seconds=0.02,
                      register=0, excluded=[], latency_offset_s=0.0)
        inputs.update(overrides)
        cases.append({"name": name, "input": inputs, "expected": word_feedback(**inputs)})
    return {"word_feedback_version": WORD_FEEDBACK_VERSION,
            "config": asdict(WordFeedbackConfig()),
            "pitch_config": {key: value for key, value in asdict(PitchConfig()).items()
                             if key != "time_tolerance_s"},
            "tolerance": 0.001, "cases": cases}


def main():
    OUT.write_text(json.dumps(build_fixture(), ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {OUT}: {len(build_fixture()['cases'])} cases")


if __name__ == "__main__":
    main()
