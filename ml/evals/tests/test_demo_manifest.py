import json

from ml.evals.inspect_reference import inspect_manifest
from ml.evals.make_demo_manifest import OUT, build


def test_demo_manifest_is_clean_and_committed_file_is_current():
    manifest = build()
    findings, stats = inspect_manifest(manifest)
    assert [f.message for f in findings if f.level in ("FAIL", "WARN")] == []
    assert stats["detected_onsets"] == 28
    if OUT.exists():  # the committed fixture must match the generator
        assert json.loads(OUT.read_text(encoding="utf-8")) == json.loads(json.dumps(manifest, ensure_ascii=False))
