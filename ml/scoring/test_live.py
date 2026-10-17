import json
from pathlib import Path

import pytest

from ml.scoring.live import DEFAULT_CONFIG, aggregate, score_phrase


FIXTURES = json.loads((Path(__file__).resolve().parents[2] / "contracts/fixtures/live_scoring.json").read_text())


@pytest.mark.parametrize("case", FIXTURES["cases"], ids=lambda case: case["name"])
def test_shared_analytic_score_cases(case):
    assert DEFAULT_CONFIG == FIXTURES["config"]
    result = score_phrase(case["reference"], case["observations"], case["start"], case["end"],
                          register=case["register"], latency_seconds=case["latency_seconds"])
    for key, expected in case["expected"].items():
        if isinstance(expected, (float, int)):
            assert result[key] == pytest.approx(expected, abs=1e-6)
        else:
            assert result[key] == expected
    assert result == score_phrase(case["reference"], case["observations"], case["start"], case["end"],
                                  register=case["register"], latency_seconds=case["latency_seconds"])


def test_aggregation_weights_only_scoreable_reference_duration():
    scores = [{"status": "provisional", "pitch": 100, "timing": 100, "total": 100, "scoreable_seconds": 1},
              {"status": "provisional", "pitch": 0, "timing": 0, "total": 0, "scoreable_seconds": 3},
              {"status": "unavailable", "pitch": None, "timing": None, "total": None, "scoreable_seconds": 0}]
    assert aggregate(scores) == {"status": "provisional", "pitch": 25, "timing": 25, "total": 25}
