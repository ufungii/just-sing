"""The committed fixtures must match the Python engine (they are the contract the
TypeScript port is tested against), so stale fixtures fail CI."""
import json
from pathlib import Path

import pytest

from dataclasses import replace

from ml.scoring.config import PitchConfig
from ml.scoring.pitch import to_track
from ml.scoring.score import score_turn
from ml.scoring.timing import onset_times

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"


def _load(name):
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"{name} not generated; run python -m ml.evals.make_fixtures")
    return json.loads(path.read_text())


def test_score_fixtures_match_engine():
    data = _load("score_cases.json")
    for case in data["cases"]:
        i = case["input"]
        got = score_turn(
            to_track(i["user_hz"]), to_track(i["ref_hz"]),
            [tuple(p) for p in i["phrases"]],
            hop_seconds=i["hop_seconds"], ref_onsets=i["ref_onsets"],
            register=i["register"], latency_offset_s=i["latency_offset_s"],
            excluded=[tuple(e) for e in i["excluded"]],
            pitch_cfg=replace(PitchConfig(), time_tolerance_s=i["time_tolerance_s"]),
        )
        assert got == case["expected"], case["name"]


def test_onset_fixtures_match_engine():
    data = _load("onset_cases.json")
    for case in data["cases"]:
        got = [round(float(t), 3) for t in onset_times(to_track(case["input"]["hz"]), case["input"]["hop_seconds"])]
        assert got == case["expected_onsets"], case["name"]
