"""Small integration checks; offline model inference is replaced by fixture outputs."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import run
from .romanize import romanize_text, romanize_track


class PreparationTests(unittest.TestCase):
    def setUp(self):
        root = (run.ROOT / "ml/data/test-runs").resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="prepare-", dir=root)
        self.root = Path(self.temporary.name).resolve()
        assert self.root.is_relative_to(root)
        self.addCleanup(self.temporary.cleanup)
        self.data = self.root / "data"
        self.data.mkdir()
        self.lyrics = self.root / "lyrics.txt"
        self.lyrics.write_text("Hello world", encoding="utf-8")
        self.vocals = self.root / "selected-vocals.mp3"
        self.backing = self.root / "selected-instrumental.mp3"
        self.vocals.write_bytes(b"selected vocals")
        self.backing.write_bytes(b"selected backing")
        self.args = run.parser().parse_args(["--id", "new-song", "--title", "Test", "--artist", "Test",
                                            "--lyrics", str(self.lyrics), "--vocals", str(self.vocals),
                                            "--instrumental", str(self.backing)])

    def fake_inference(self, *args):
        module = args[2]
        output = Path(args[args.index("--output") + 1])
        if module == "ml.pipeline.align_lyrics":
            output.mkdir()
            (output / "lyrics.aligned.json").write_text(json.dumps({"status": "alignment_draft", "reviewed": False, "lines": []}))
        elif module == "ml.pipeline.reference":
            output.write_text(json.dumps({"status": "unreviewed", "hz": [220]}))
        else:
            self.fail(f"Unexpected job: {module}")

    def test_selected_stems_publish_after_both_jobs_and_keep_only_two_audio_files(self):
        with patch.object(run, "DATA", self.data), patch.object(run, "command", side_effect=self.fake_inference) as jobs, patch.object(run, "decoded_frames", return_value=88200), patch("ml.pipeline.manifest.write_manifest") as manifest:
            folder = run.prepare(self.args)
        manifest.assert_called_once()
        self.assertEqual(jobs.call_count, 2)
        self.assertEqual((folder / "vocals.mp3").read_bytes(), self.vocals.read_bytes())
        self.assertEqual((folder / "instrumental.mp3").read_bytes(), self.backing.read_bytes())
        metadata = json.loads((folder / "preparation.json").read_text())
        self.assertEqual(metadata["duration_seconds"], 2)
        self.assertEqual(metadata["audio"]["vocals"], "vocals.mp3")
        self.assertEqual(len(list(self.data.rglob("*.mp3"))), 2)
        self.assertFalse(any((self.data / ".preparing").iterdir()))

    def test_mismatched_stems_never_reach_catalog(self):
        with patch.object(run, "DATA", self.data), patch.object(run, "decoded_frames", side_effect=[88200, 44100]), patch.object(run, "command") as jobs:
            with self.assertRaisesRegex(ValueError, "different decoded lengths"):
                run.prepare(self.args)
        jobs.assert_not_called()
        self.assertFalse((self.data / self.args.id).exists())
        self.assertFalse(list(self.data.rglob("*.mp3")))

    def test_existing_song_and_hand_corrections_are_preserved(self):
        folder = self.data / self.args.id
        folder.mkdir()
        corrections = folder / "corrections.json"
        corrections.write_text('{"manual": true}')
        with patch.object(run, "DATA", self.data), patch.object(run, "command") as jobs:
            with self.assertRaisesRegex(ValueError, "already exists"):
                run.prepare(self.args)
        jobs.assert_not_called()
        self.assertEqual(corrections.read_text(), '{"manual": true}')

    def test_failed_inference_does_not_publish_partial_song(self):
        with patch.object(run, "DATA", self.data), patch.object(run, "decoded_frames", return_value=88200), patch.object(run, "command", side_effect=RuntimeError("inference failed")):
            with self.assertRaises(RuntimeError):
                run.prepare(self.args)
        self.assertFalse((self.data / self.args.id).exists())
        self.assertFalse(list(self.data.rglob("*.mp3")))

    def test_romanization_preserves_mixed_text_and_timestamps(self):
        self.assertEqual(romanize_text("안녕하세요 Hello!"), "annyeonghaseyo Hello!")
        line = {"text": "안녕하세요 Hello!", "start": 1, "end": 3,
                "words": [{"text": "안녕하세요", "start": 1, "end": 2}]}
        result = romanize_track({"lines": [line]})["lines"][0]
        self.assertEqual(result["words"], line["words"])
        self.assertEqual(result["start"], line["start"])
        self.assertEqual(result["romanized"], "annyeonghaseyo Hello!")
        self.assertNotIn("romanized", line)

    def test_source_recipe_keeps_baseline_vocals_and_masters_only_residual_backing(self):
        self.args.clip = self.vocals
        self.args.vocals = self.args.instrumental = None
        models = []
        def jobs(*args):
            if args[2] != "ml.pipeline.separate":
                return self.fake_inference(*args)
            model = args[args.index("--model") + 1]
            models.append(model)
            output = Path(args[args.index("--output") + 1])
            folder = output / "stems" / model
            folder.mkdir(parents=True)
            # MP3 export is replaced below; these are role-identifying fixtures.
            (folder / "vocals.wav").write_bytes(b"baseline vocal" if model == "htdemucs" else b"alternate vocal")
            (folder / "instrumental-residual.wav").write_bytes(b"residual backing")
            (output / "separation.json").write_text(json.dumps({"model": model}))
        def mastering(source, destination, target, cutoff):
            self.assertEqual(source.read_bytes(), b"residual backing")
            self.assertEqual((target, cutoff), (-16, 25))
            (destination / "master.mp3").write_bytes(b"mastered backing")
            return {"mp3": "master.mp3"}
        import shutil
        with patch.object(run, "DATA", self.data), patch.object(run, "command", side_effect=jobs), patch.object(run, "decoded_frames", return_value=88200), patch.object(run, "export_mp3", side_effect=shutil.copyfile), patch("ml.pipeline.enhance.enhance", side_effect=mastering), patch("ml.pipeline.manifest.write_manifest"):
            folder = run.prepare(self.args)
        self.assertEqual(models, ["htdemucs", "04573f0d"])
        self.assertEqual((folder / "vocals.mp3").read_bytes(), b"baseline vocal")
        self.assertEqual((folder / "instrumental.mp3").read_bytes(), b"mastered backing")
        self.assertFalse(list(self.data.rglob("*.wav")))


if __name__ == "__main__":
    unittest.main()
