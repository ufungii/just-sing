"""Generate shared scoring fixtures for the TypeScript port.

Run from the repo root:  python -m ml.evals.make_fixtures

Writes contracts/fixtures/score_cases.json and onset_cases.json. Each case has
the inputs the browser would have (Hz tracks with null = unvoiced, phrases,
register, latency offset) and the output the Python reference engine produces.
The TS scorer must reproduce `expected` within `tolerance`. Tracks are rounded
to 2 decimals BEFORE the expected values are computed, so both sides score the
exact same numbers.
"""
import json
from pathlib import Path

import numpy as np

from ml.evals.synthetic import detune, example_melody, example_phrases, melody_track
from ml.scoring.pitch import HOP_SECONDS, to_track, track_to_json
from ml.scoring.score import score_turn
from ml.scoring.timing import onset_times

OUT = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
TOLERANCE = 0.1  # scores are rounded to 1 decimal


def _shift(track: np.ndarray, seconds: float) -> np.ndarray:
    n = int(round(seconds / HOP_SECONDS))
    return np.concatenate([np.full(n, np.nan), track])[: len(track)]


def build_cases() -> list[dict]:
    notes = example_melody()
    ref = melody_track(notes, HOP_SECONDS)
    unsung_first = ref.copy()
    unsung_first[: int(3.2 / HOP_SECONDS)] = np.nan
    garbage = ref.copy()
    garbage[50:100] = 900.0

    # name, description, user track, register, latency, excluded
    specs = [
        ("perfect", "user equals reference", ref, 0, 0.0, []),
        ("silence", "nothing sung", np.full_like(ref, np.nan), 0, 0.0, []),
        ("octave_up_register_selected", "sung an octave up, +12 chosen", ref * 2, 12, 0.0, []),
        ("octave_up_wrong_register", "sung an octave up, register left at 0", ref * 2, 0, 0.0, []),
        ("late_calibrated", "0.16 s device latency, calibrated out", _shift(ref, 0.16), 0, 0.16, []),
        ("late_uncalibrated", "0.3 s late, no calibration", _shift(ref, 0.3), 0, 0.0, []),
        ("first_phrase_unsung", "first phrase skipped", unsung_first, 0, 0.0, []),
        ("detuned_100_cents", "every other note 100 cents off", melody_track(detune(notes, 100), HOP_SECONDS), 0, 0.0, []),
        ("excluded_region", "garbage inside an excluded region does not count", garbage, 0, 0.0, [[1.0, 2.0]]),
    ]

    ref_json = track_to_json(ref)
    ref_rounded = to_track(ref_json)
    ref_onsets = [round(float(t), 3) for t in onset_times(ref_rounded, HOP_SECONDS)]
    phrases = [list(p) for p in example_phrases()]

    cases = []
    for name, desc, user, register, latency, excluded in specs:
        user_json = track_to_json(user)
        expected = score_turn(
            to_track(user_json), ref_rounded, [tuple(p) for p in phrases],
            hop_seconds=HOP_SECONDS, ref_onsets=ref_onsets, register=register,
            excluded=[tuple(e) for e in excluded], latency_offset_s=latency,
        )
        cases.append({
            "name": name,
            "description": desc,
            "input": {
                "hop_seconds": HOP_SECONDS,
                "ref_hz": ref_json,
                "user_hz": user_json,
                "ref_onsets": ref_onsets,
                "phrases": phrases,
                "register": register,
                "latency_offset_s": latency,
                "excluded": excluded,
            },
            "expected": expected,
        })
    return cases


def build_onset_cases() -> list[dict]:
    notes = example_melody()
    ref = melody_track(notes, HOP_SECONDS)
    noise = np.random.default_rng(0).uniform(65, 1000, size=len(ref))
    out = []
    for name, track in [("reference", ref), ("delayed_0.3s", _shift(ref, 0.3)), ("noise", noise)]:
        hz = track_to_json(track)
        out.append({
            "name": name,
            "input": {"hop_seconds": HOP_SECONDS, "hz": hz},
            "expected_onsets": [round(float(t), 3) for t in onset_times(to_track(hz), HOP_SECONDS)],
        })
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    score = {"tolerance": TOLERANCE, "cases": build_cases()}
    onset = {"tolerance_s": 0.001, "cases": build_onset_cases()}
    (OUT / "score_cases.json").write_text(json.dumps(score, separators=(",", ":")))
    (OUT / "onset_cases.json").write_text(json.dumps(onset, separators=(",", ":")))
    for c in score["cases"]:
        e = c["expected"]
        print(f"{c['name']:30s} total={e['total']:5.1f} pitch={e['pitch']:5.1f} timing={e['timing']:5.1f}")


if __name__ == "__main__":
    main()
