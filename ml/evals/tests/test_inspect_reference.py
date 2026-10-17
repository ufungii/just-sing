import copy

import numpy as np
import pytest

from ml.evals.inspect_reference import inspect_manifest
from ml.evals.synthetic import example_melody, example_phrases, melody_track
from ml.scoring.pitch import track_to_json

HOP = 0.02


def good_manifest():
    notes, t, out = example_melody(), 0.0, []
    for midi, dur in notes:
        if midi is not None:
            out.append({"start": round(t, 3), "end": round(t + dur, 3), "hz": round(440 * 2 ** ((midi - 69) / 12), 2)})
        t += dur
    ref = melody_track(notes, HOP)
    return {
        "duration": len(ref) * HOP, "title": "synthetic",
        "phrases": [{"id": i, "start": s, "end": e} for i, s, e in example_phrases()],
        "reference": {"hop_seconds": HOP, "hz": track_to_json(ref), "notes": out, "excluded": []},
    }


def levels(m):
    return [x.level for x in inspect_manifest(m)[0]]


def messages(m, level):
    return [x.message for x in inspect_manifest(m)[0] if x.level == level]


def test_clean_manifest_has_no_failures_or_warnings():
    assert "FAIL" not in levels(good_manifest()) and "WARN" not in levels(good_manifest())


def test_wrong_frame_count_fails():
    m = good_manifest()
    m["reference"]["hz"] = m["reference"]["hz"][:200]
    assert any("duration" in x for x in messages(m, "FAIL"))


def test_missing_fields_fail_without_crashing():
    assert levels({"reference": {}}) == ["FAIL"]


def test_bad_phrases_fail():
    m = good_manifest()
    m["phrases"].append({"id": "p1", "start": 1.0, "end": 2.0})  # duplicate id and overlap
    m["phrases"].append({"id": "x", "start": 5.0, "end": 99.0})  # beyond the clip
    fails = messages(m, "FAIL")
    assert any("duplicate" in x for x in fails) and any("overlaps" in x for x in fails)
    assert any("out of range" in x for x in fails)


def test_octave_jump_is_flagged_unless_excluded():
    m = good_manifest()
    hz = m["reference"]["hz"]
    for i in range(100, 110):   # a short stretch an octave up
        hz[i] = hz[i] * 2
    assert any("octave" in x for x in messages(m, "WARN"))
    m["reference"]["excluded"] = [{"start": 1.9, "end": 2.3, "reason": "harmony"}]
    assert not any("octave" in x for x in messages(m, "WARN"))


def test_heavy_exclusion_warns():
    m = good_manifest()
    m["reference"]["excluded"] = [{"start": 0.0, "end": 6.0, "reason": "backing vocals"}]
    assert any("excluded" in x for x in messages(m, "WARN"))


def test_fully_excluded_fails():
    m = good_manifest()
    m["reference"]["excluded"] = [{"start": 0.0, "end": m["duration"], "reason": "all"}]
    assert any("nothing is scoreable" in x for x in messages(m, "FAIL"))


def test_tiny_notes_warn_about_timing():
    m = good_manifest()
    m["reference"]["notes"].append({"start": 9.0, "end": 9.05, "hz": 440.0})
    assert any("shorter than" in x for x in messages(m, "WARN"))


def test_note_that_disagrees_with_contour_warns():
    m = good_manifest()
    m["reference"]["notes"][0]["hz"] *= 1.5
    assert any("differ from the contour" in x for x in messages(m, "WARN"))
