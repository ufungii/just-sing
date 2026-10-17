"""Adapter that plugs ml.pronunciation into the API's practice endpoint.

api/practice.py expects an object with a `provider` string and
`assess(wav_path, expected_text) -> [{"text": str, "score": 0-100}]` that RAISES on
failure (the API then reports status "error"; it never invents a score). This
wraps `baselines.assess`, which returns a status dict instead.

Wiring (in the API's startup, not at import, so the API stays importable
without PyTorch):

    from ml.pronunciation.api_scorer import PronunciationScorer
    import api.practice
    api.practice.scorer = PronunciationScorer()
"""
from pathlib import Path

from . import baselines


class PronunciationScorer:
    provider = "wav2vec2-ctc"

    def assess(self, wav: Path, expected_text: str) -> list[dict]:
        result = baselines.assess(str(wav), expected_text)
        if result["status"] != "ok":
            raise RuntimeError(result["debug"].get("reason", "assessment_failed"))
        # Words the model cannot score (e.g. English letters) are omitted, never faked.
        words = [{"text": w["text"], "score": float(w["score"])} for w in result["words"]
                 if w["score"] is not None]
        if not words:
            raise RuntimeError("no_scoreable_words")
        return words
