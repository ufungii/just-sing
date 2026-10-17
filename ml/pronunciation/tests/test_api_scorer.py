import pytest

pytest.importorskip("rapidfuzz")  # speech env only

from ml.pronunciation import api_scorer  # noqa: E402


def fake(result):
    return lambda audio, expected, sr=None: result


def test_ok_result_becomes_the_apis_word_list(monkeypatch):
    monkeypatch.setattr(api_scorer.baselines, "assess", fake({
        "status": "ok", "overall": 70.0, "debug": {},
        "words": [{"text": "사랑", "score": 80.5}, {"text": "hello", "score": None}]}))
    out = api_scorer.PronunciationScorer().assess("x.wav", "사랑 hello")
    assert out == [{"text": "사랑", "score": 80.5}]  # unscorable word omitted, not faked


def test_error_status_raises_with_the_reason(monkeypatch):
    monkeypatch.setattr(api_scorer.baselines, "assess", fake(
        {"status": "error", "overall": None, "words": [], "debug": {"reason": "audio_too_short"}}))
    with pytest.raises(RuntimeError, match="audio_too_short"):
        api_scorer.PronunciationScorer().assess("x.wav", "사랑")


def test_all_words_unscorable_raises(monkeypatch):
    monkeypatch.setattr(api_scorer.baselines, "assess", fake(
        {"status": "ok", "overall": 0.0, "debug": {}, "words": [{"text": "hi", "score": None}]}))
    with pytest.raises(RuntimeError, match="no_scoreable_words"):
        api_scorer.PronunciationScorer().assess("x.wav", "hi")
