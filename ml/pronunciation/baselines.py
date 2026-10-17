"""Two local, free pronunciation baselines for SPOKEN Korean phrases.

Both return the practice-result shape in contracts/practice.example.json with
word-level scores in 0-1. They are automated checks, not validated by a fluent
reviewer, and report words only (no phoneme diagnosis).

  A  "whisper-jamo": transcribe with faster-whisper (no lyric prompt, or it
     would echo the answer), then compare jamo with the expected text.
  B  "wav2vec2-ctc": force-align the expected text to a Korean wav2vec2 CTC
     model and take each syllable's posterior probability.

Heavy imports and model loads are lazy so importing this module is cheap.
"""
from functools import lru_cache

import numpy as np

from .ctc import forced_align
from .text import is_syllable, score_words, split_words

SR = 16_000
CTC_MODEL = "kresnik/wav2vec2-large-xlsr-korean"  # Apache-2.0
WHISPER_MODEL = "small"


def _device() -> str:
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_audio(audio, sr: int | None = None) -> np.ndarray:
    """Path or array -> mono float32 at 16 kHz."""
    import librosa

    if isinstance(audio, (str, bytes)) or hasattr(audio, "__fspath__"):
        y, _ = librosa.load(audio, sr=SR, mono=True)
        return y
    y = np.asarray(audio, dtype=np.float32)
    if sr and sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    return y


def _result(provider: str, status: str, words=None, overall=None, **debug) -> dict:
    return {"provider": provider, "status": status, "overall": overall,
            "words": words or [], "debug": debug}


# --------------------------------------------------------------------------- #
# Baseline A
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _whisper():
    from faster_whisper import WhisperModel
    dev = _device()
    return WhisperModel(WHISPER_MODEL, device=dev, compute_type="float16" if dev == "cuda" else "int8")


def transcribe(y: np.ndarray) -> str:
    """Free transcription of 16 kHz audio. No initial_prompt on purpose: a prompt
    containing the answer makes Whisper echo it back regardless of what was said."""
    segments, _ = _whisper().transcribe(
        y, language="ko", beam_size=5, condition_on_previous_text=False,
    )
    return "".join(s.text for s in segments).strip()


def assess_a(audio, expected: str, sr: int | None = None) -> dict:
    return score_a(transcribe(load_audio(audio, sr)), expected)


def score_a(heard: str, expected: str) -> dict:
    """Score an existing transcript (so one transcription can be checked against many texts)."""
    if not heard:
        return _result("whisper-jamo", "error", reason="no_speech_detected")
    overall, words = score_words(expected, heard)
    return _result("whisper-jamo", "ok", [{"text": w.text, "score": round(w.score, 3)} for w in words],
                   round(overall, 3), heard=heard)


# --------------------------------------------------------------------------- #
# Baseline B
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _ctc():
    from transformers import AutoProcessor, Wav2Vec2ForCTC
    proc = AutoProcessor.from_pretrained(CTC_MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(CTC_MODEL).to(_device()).eval()
    return proc, model


def posteriors(y: np.ndarray) -> tuple[np.ndarray, str]:
    """Per-frame log-probabilities (T, C) and the model's own greedy transcript."""
    import torch

    proc, model = _ctc()
    inputs = proc(y, sampling_rate=SR, return_tensors="pt")
    with torch.no_grad():
        logits = model(inputs.input_values.to(model.device)).logits[0]
    log_probs = torch.log_softmax(logits.float(), dim=-1).cpu().numpy()
    return log_probs, proc.decode(log_probs.argmax(-1))


def assess_b(audio, expected: str, sr: int | None = None) -> dict:
    y = load_audio(audio, sr)
    if len(y) < SR * 0.2:
        return _result("wav2vec2-ctc", "error", reason="audio_too_short")
    log_probs, heard = posteriors(y)
    return score_b(log_probs, heard, expected)


def score_b(log_probs: np.ndarray, heard: str, expected: str) -> dict:
    """Force-align `expected` to existing posteriors (reusable across many texts)."""
    proc, _ = _ctc()
    blank = proc.tokenizer.pad_token_id
    vocab = proc.tokenizer.get_vocab()

    # One target per Hangul syllable the model knows; unknown syllables are not scored.
    words = split_words(expected)
    targets, owner = [], []
    for wi, w in enumerate(words):
        for ch in w:
            if is_syllable(ch) and ch in vocab:
                targets.append(vocab[ch])
                owner.append(wi)
    if not targets:
        return _result("wav2vec2-ctc", "error", reason="no_scoreable_syllables")

    frames = forced_align(log_probs, targets, blank)
    if frames is None:
        return _result("wav2vec2-ctc", "error", reason="audio_too_short_for_text", heard=heard)

    post = np.exp(log_probs)
    tok_scores = [float(np.mean([post[t, tid] for t in fr])) for tid, fr in zip(targets, frames)]
    per_word = [[] for _ in words]
    for wi, sc in zip(owner, tok_scores):
        per_word[wi].append(sc)

    out = [{"text": w, "score": round(float(np.mean(s)), 3) if s else None}
           for w, s in zip(words, per_word)]
    scored = [x for x in tok_scores]
    return _result("wav2vec2-ctc", "ok", out, round(float(np.mean(scored)), 3), heard=heard)
