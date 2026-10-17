import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ..crop import rebase_lines
from ..text import korean_practice_text, apply_cached_translations
from ..manifest import scoreable_seconds


class QualityTests(unittest.TestCase):
    def test_phrase_eligibility_counts_voiced_frames_outside_exclusions(self):
        ref = {"hop_seconds": 0.02, "hz": [220, None, 220, 220, 220],
               "excluded": [{"start": 0.04, "end": 0.06}]}
        self.assertAlmostEqual(scoreable_seconds(ref, 0, 0.1), 0.06)
        self.assertAlmostEqual(scoreable_seconds(ref, 0.001, 0.08), 0.02)
        self.assertEqual(scoreable_seconds(ref, 0.02, 0.06), 0)

    def test_practice_requires_whole_line_korean_without_latin(self):
        self.assertEqual(korean_practice_text("그림자조차 길을 잃게 해"), "그림자조차 길을 잃게 해")
        self.assertEqual(korean_practice_text("Key는 내가 쥘게"), "")
        self.assertEqual(korean_practice_text("나의 마음은 so sweet 너의 손길로"), "")
        self.assertEqual(korean_practice_text("안녕!"), "안녕!")
        self.assertEqual(korean_practice_text("123 ♪"), "")
        self.assertEqual(korean_practice_text("La-la-la (넌 이미)"), "")
        self.assertEqual(korean_practice_text("Just English words"), "")

    def test_translation_cache_binds_text_and_preserves_manual_edits(self):
        root = Path(__file__).resolve().parents[3] / "ml/data/test-runs"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="text-quality-", dir=root) as temporary:
            path = Path(temporary) / "translations.json"
            lines = [{"text": "source", "translation": ""}]
            path.write_text(json.dumps({"lyric_lines_sha256": hashlib.sha256(b"source").hexdigest(),
                                        "lines": [{"line_index": 0, "text": "source", "translation": "draft"}]}))
            apply_cached_translations(lines, path)
            self.assertEqual(lines[0]["translation"], "draft")
            lines[0]["translation"] = "manual correction"
            apply_cached_translations(lines, path)
            self.assertEqual(lines[0]["translation"], "manual correction")
            with self.assertRaises(ValueError):
                apply_cached_translations([{"text": "different"}], path)

    def test_crop_rebases_words_and_marks_boundary_fragments(self):
        track = {"section_starts": [0, 1], "lines": [
            {"start": 44, "end": 47, "text": "first second", "romanized": "one two", "translation": "context",
             "words": [{"text": "first", "start": 44.2, "end": 44.8}, {"text": "second", "start": 45.1, "end": 46.5}]},
            {"start": 73, "end": 77, "text": "third fourth", "romanized": "three four", "translation": "context",
             "words": [{"text": "third", "start": 73.1, "end": 74.8}, {"text": "fourth", "start": 76, "end": 76.5}]}]}
        lines, partial, sections = rebase_lines(track, 45, 75)
        self.assertEqual(partial, [0, 1])
        self.assertEqual(sections, [0, 1])
        self.assertEqual(lines[0]["text"], "second")
        self.assertEqual(lines[0]["romanized"], "two")
        self.assertEqual(lines[0]["words"][0]["start"], 0.1)
        self.assertEqual(lines[1]["end"], 30)
        self.assertTrue(all(line["practice_text"] == "" for line in lines))


if __name__ == "__main__":
    unittest.main()
