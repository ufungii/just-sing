from ml.evals.crop_manifest import crop_manifest
from ml.evals.inspect_reference import inspect_manifest
from ml.evals.make_demo_manifest import build


def test_crop_rebases_and_keeps_only_whole_lines():
    m = build()                                   # 30 s, 6 lines: 2.0-12.25 and 14.0-24.25
    clip, rep = crop_manifest(m, 12.0, 26.0)
    assert clip["duration"] == 14.0 and len(clip["reference"]["hz"]) == 700
    assert rep["lines_kept"] == 3 and rep["lines_dropped"] == 3
    assert [p["id"] for p in clip["phrases"]] == ["p1", "p2", "p3"]
    assert [p["line_index"] for p in clip["phrases"]] == [0, 1, 2]
    assert clip["phrases"][0]["start"] == 2.0     # was 14.0
    assert clip["lines"][0]["words"][0]["start"] >= 2.0
    assert clip["provenance"]["crop_start"] == 12.0 and clip["provenance"]["crop_end"] == 26.0


def test_cropped_clip_passes_the_inspector_and_original_is_untouched():
    m = build()
    before = len(m["lines"])
    clip, _ = crop_manifest(m, 12.0, 26.0, new_id="clip")
    assert clip["id"] == "clip" and len(m["lines"]) == before
    assert [f.message for f in inspect_manifest(clip)[0] if f.level == "FAIL"] == []


def test_excluded_regions_are_clipped_and_rebased():
    m = build()
    m["reference"]["excluded"] = [{"start": 10.0, "end": 16.0, "reason": "x"}, {"start": 28.0, "end": 29.0, "reason": "y"}]
    clip, _ = crop_manifest(m, 12.0, 26.0)
    assert clip["reference"]["excluded"] == [{"start": 0.0, "end": 4.0, "reason": "x"}]
