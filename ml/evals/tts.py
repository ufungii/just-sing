"""Local Korean text-to-speech for generating eval audio.

Uses facebook/mms-tts-kor (CC-BY-NC-4.0): only for generating test speech on our
machines, never shipped in the app. Output is cached under the gitignored ml/data/
keyed by the text, and seeded so reruns produce identical audio.
"""
import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

CACHE = Path(__file__).resolve().parents[1] / "data" / "tts_cache"
MODEL = "facebook/mms-tts-kor"


@lru_cache(maxsize=1)
def _model():
    import torch
    from transformers import AutoTokenizer, VitsModel

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    return AutoTokenizer.from_pretrained(MODEL), VitsModel.from_pretrained(MODEL).to(dev).eval()


def speak(text: str, variant: int = 0) -> tuple[np.ndarray, int]:
    """16 kHz mono float32 speech for `text` (cached). Different `variant`s are
    different random renditions of the same text by the same voice."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{text}|{variant}".encode("utf-8") if variant else text.encode("utf-8")).hexdigest()[:16]
    path = CACHE / f"{key}.wav"
    if not path.exists():
        import torch

        tok, model = _model()
        torch.manual_seed(int(key[:8], 16) % (2**31))  # VITS is stochastic
        ids = tok(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            wav = model(**ids).waveform[0].cpu().numpy()
        sf.write(path, wav, model.config.sampling_rate)
    wav, sr = sf.read(path, dtype="float32")
    return wav, sr
