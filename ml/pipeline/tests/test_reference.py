"""Check the pipeline boundary without loading or reimplementing ML B's model."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from .. import reference


class SharedReferenceTests(unittest.TestCase):
    def test_cli_uses_shared_reference_adapter_and_preserves_payload(self):
        root = Path(__file__).resolve().parents[3] / "ml/data/test-runs"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="shared-reference-", dir=root) as tmp:
            audio_path, output = Path(tmp) / "input.mp3", Path(tmp) / "reference.json"
            audio_path.write_bytes(b"fixture audio fingerprint")
            samples = [0.0] * 320
            payload = {"hop_seconds": 0.02, "hz": [220.0, None],
                       "periodicity": [0.8, 0.0], "backend": "crepe", "settings": {"shared": True}}
            shared = Mock(return_value=payload)
            decoded = Mock()
            decoded.numpy.return_value = samples
            with patch.dict(sys.modules, {"ml.scoring.pitch": SimpleNamespace(reference_contour=shared)}), \
                 patch.object(reference, "decode_audio", return_value=decoded), \
                 patch.object(sys, "argv", ["reference", "--audio", str(audio_path), "--output", str(output)]), \
                 patch("builtins.print"):
                reference.main()
            shared.assert_called_once()
            self.assertIs(shared.call_args.args[0], samples)
            self.assertTrue(callable(shared.call_args.kwargs["progress"]))
            result = json.loads(output.read_text(encoding="utf-8"))
            for key, value in payload.items():
                self.assertEqual(result[key], value)
            self.assertFalse(result["reviewed"])
            self.assertEqual(result["source_audio_sha256"], hashlib.sha256(audio_path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
