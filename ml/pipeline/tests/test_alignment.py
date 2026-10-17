"""Timing anchor regression checks, independent of installed model weights."""

import hashlib
import unittest

from ..align_lyrics import anchor_windows, lyric_sections, lrc_track


class AnchorTests(unittest.TestCase):
    def test_lrc_export_preserves_blank_music_break_cues(self):
        output = lrc_track([{"start": 1, "end": 3, "text": "first"},
                            {"start": 8, "end": 9, "text": "second"}], 12)
        self.assertIn("[00:01.00]first\n[00:03.00]\n[00:08.00]second\n[00:09.00]\n", output)

    def test_blank_lines_preserve_sections_without_becoming_timing_gaps(self):
        lines, sections = lyric_sections("\ufeff\r\n intro \r\nsecond\r\n\r\n\r\n chorus \r\n\r\n")
        self.assertEqual(lines, ["intro", "second", "chorus"])
        self.assertEqual(sections, [0, 2])

    def corrections(self, texts, starts):
        return {"source_audio_sha256": "audio", "lyric_lines_sha256": hashlib.sha256("\n".join(texts).encode()).hexdigest(),
                "line_starts": starts, "section_starts": [0]}

    def test_entrances_bound_each_line_including_instrumental_gaps(self):
        texts = ["intro", "verse", "chorus"]
        data = self.corrections(texts, [0.55, 14.37, 43.97])
        self.assertEqual(anchor_windows(data, texts, 50, "audio"), [(0.55, 14.37), (14.37, 43.97), (43.97, 50)])

    def test_float_arithmetic_cannot_put_words_outside_line_end(self):
        texts = ["first", "second"]
        data = self.corrections(texts, [0.5, 120 + 36.58])
        self.assertEqual(anchor_windows(data, texts, 160, "audio")[0][1], 156.58)

    def test_single_line_clip_is_valid(self):
        self.assertEqual(anchor_windows(self.corrections(["one"], [0.5]), ["one"], 2, "audio"), [(0.5, 2)])

    def test_outro_does_not_extend_the_last_lyric_to_the_recording_end(self):
        data = self.corrections(["one"], [1])
        data["last_line_end"] = 4
        self.assertEqual(anchor_windows(data, ["one"], 10, "audio"), [(1, 4)])
        for end in (0, 1, 11, float("nan")):
            data["last_line_end"] = end
            with self.assertRaises(ValueError):
                anchor_windows(data, ["one"], 10, "audio")

    def test_explicit_ends_preserve_instrumental_breaks(self):
        data = self.corrections(["first", "second"], [1, 8])
        data["line_ends"] = [3, 9]
        self.assertEqual(anchor_windows(data, ["first", "second"], 10, "audio"), [(1, 3), (8, 9)])
        for ends in ([1, 9], [8.1, 9], [3], [3, 11], [3, float("nan")]):
            data["line_ends"] = ends
            with self.assertRaises(ValueError):
                anchor_windows(data, ["first", "second"], 10, "audio")

    def test_changed_audio_or_lyrics_cannot_reuse_anchors(self):
        data = self.corrections(["first", "second"], [0.5, 2])
        with self.assertRaisesRegex(ValueError, "different vocal audio"):
            anchor_windows(data, ["first", "second"], 3, "other")
        with self.assertRaisesRegex(ValueError, "different lyric lines"):
            anchor_windows(data, ["changed", "second"], 3, "audio")

    def test_invalid_or_out_of_order_anchors_and_sections_are_rejected(self):
        texts = ["first", "second"]
        for starts in ([2, 1], [1, 1], [0.5, 3], [float("nan"), 2], [0.5], [False, 2]):
            with self.subTest(starts=starts), self.assertRaises(ValueError):
                anchor_windows(self.corrections(texts, starts), texts, 3, "audio")
        data = self.corrections(texts, [0.5, 2])
        data["section_starts"] = [1, 0]
        with self.assertRaises(ValueError):
            anchor_windows(data, texts, 3, "audio")


if __name__ == "__main__":
    unittest.main()
