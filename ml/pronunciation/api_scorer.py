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
    last_overall: float | None = None  # read by the API right after assess(); it runs one at a time

    def warmup(self) -> None:
        """Load the CTC model now (about 30 s) so the first user request is not the slow one."""
        baselines._ctc()

    def assess(self, wav: Path, expected_text: str) -> list[dict]:
        self.last_overall = None
        result = baselines.assess(str(wav), expected_text)
        if result["status"] != "ok":
            raise RuntimeError(result["debug"].get("reason", "assessment_failed"))
        # Words the model cannot score (e.g. English letters) are omitted, never faked.
        words = [{"text": w["text"], "score": float(w["score"])} for w in result["words"]
                 if w["score"] is not None]
        if not words:
            raise RuntimeError("no_scoreable_words")
        self.last_overall = result["overall"]
        return words
