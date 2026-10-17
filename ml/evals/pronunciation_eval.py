"""Pronunciation baseline evals (Baseline A: whisper+jamo, Baseline B: wav2vec2 CTC).

Run from the repo root with the pronunciation env:
  ml/pronunciation/.venv/bin/python -m ml.evals.pronunciation_eval

Test speech is synthesized locally with facebook/mms-tts-kor (CC-BY-NC-4.0, used
only to generate eval audio, never shipped). We have no fluent reviewer, so this
measures whether each scorer separates the RIGHT text from WRONG text for the
same audio, and whether it points at the substituted word. It does not measure
accent or phoneme quality, and TTS is clean single-speaker speech.

  * Separation (AUC): audio of phrase i scored against its own text (matched)
    vs against the other phrases' texts (mismatched). 1.0 = perfect, 0.5 = chance.
  * Word localization: swap one word of the expected text for a different word;
    does the swapped word get the lowest score? (top-1 hit rate; chance ~1/n words)
  * Robustness: repeat separation under noise and speed changes.
"""
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.stats import mannwhitneyu

from ml.evals.synthetic import add_noise
from ml.pronunciation import baselines as pb

PHRASES = [
    "안녕하세요 만나서 반갑습니다", "오늘 날씨가 정말 좋아요", "나는 너를 사랑해",
    "우리 함께 노래해요", "보고 싶어요 매일 매일", "사랑이 뭐길래 이렇게 아파",
    "별이 빛나는 밤에", "내 마음을 받아줘요", "다시 한번 말해줘요",
    "너무너무 행복해요", "나와 함께 춤을 춰요", "영원히 널 기억할게",
]
DATA = Path(__file__).resolve().parents[1] / "data" / "pron_eval"
RESULTS = Path(__file__).parent / "results"
SR = 16_000


def synthesize() -> list[np.ndarray]:
    """TTS each phrase once (cached on disk under the gitignored ml/data/)."""
    DATA.mkdir(parents=True, exist_ok=True)
    out = []
    todo = [i for i in range(len(PHRASES)) if not (DATA / f"{i}.wav").exists()]
    if todo:
        import torch
        from transformers import AutoTokenizer, VitsModel
        tok = AutoTokenizer.from_pretrained("facebook/mms-tts-kor")
        model = VitsModel.from_pretrained("facebook/mms-tts-kor").to(pb._device()).eval()
        for i in todo:
            torch.manual_seed(i)  # VITS is stochastic; fix it so the eval is reproducible
            ids = tok(PHRASES[i], return_tensors="pt").to(model.device)
            with torch.no_grad():
                wav = model(**ids).waveform[0].cpu().numpy()
            sf.write(DATA / f"{i}.wav", wav, model.config.sampling_rate)
        del model
    for i in range(len(PHRASES)):
        out.append(pb.load_audio(DATA / f"{i}.wav"))
    return out


def auc(pos: list[float], neg: list[float]) -> float:
    return float(mannwhitneyu(pos, neg).statistic / (len(pos) * len(neg)))


def cache_models_output(audios):
    """One model pass per audio: Whisper transcript and wav2vec2 log-probs."""
    return [{"heard": pb.transcribe(y), "post": pb.posteriors(y)} for y in audios]


def overall(res: dict) -> float:
    return res["overall"] / 100 if res["status"] == "ok" and res["overall"] is not None else 0.0


def evaluate_condition(audios) -> dict:
    cache = cache_models_output(audios)
    scorers = {
        "A": lambda c, text: pb.score_a(c["heard"], text),
        "B": lambda c, text: pb.score_b(c["post"][0], c["post"][1], text),
    }
    res = {}
    for name, fn in scorers.items():
        matched = [overall(fn(c, PHRASES[i])) for i, c in enumerate(cache)]
        mismatched = [overall(fn(c, PHRASES[j])) for i, c in enumerate(cache)
                      for j in range(len(PHRASES)) if j != i]
        res[name] = {"auc": auc(matched, mismatched),
                     "matched_mean": float(np.mean(matched)),
                     "mismatched_mean": float(np.mean(mismatched))}
    res["heard_A"] = [c["heard"] for c in cache]
    res["heard_B"] = [c["post"][1] for c in cache]
    return res, cache


def word_localization(cache) -> dict:
    """Swap word k of each phrase for a word from another phrase; is it the lowest-scored?"""
    pool = [w for p in PHRASES for w in p.split()]
    hits = {"A": 0, "B": 0}
    chance, total = 0.0, 0
    for i, c in enumerate(cache):
        words = PHRASES[i].split()
        for k in range(len(words)):
            repl = next(w for w in pool[(i * 7 + k * 3) % len(pool):] + pool
                        if w not in PHRASES[i].split())
            text = " ".join(words[:k] + [repl] + words[k + 1:])
            for name, res in (("A", pb.score_a(c["heard"], text)),
                              ("B", pb.score_b(c["post"][0], c["post"][1], text))):
                scores = [w["score"] if w["score"] is not None else 1.0 for w in res["words"]]
                hits[name] += int(res["status"] == "ok" and int(np.argmin(scores)) == k)
            chance += 1 / len(words)
            total += 1
    return {"cases": total, "chance": chance / total,
            "A": hits["A"] / total, "B": hits["B"] / total}


def main() -> None:
    clean = synthesize()
    conditions = {"clean": clean}
    for snr in (20, 10, 5, 0):
        conditions[f"noise {snr} dB SNR"] = [add_noise(y, snr, i) for i, y in enumerate(clean)]
    import librosa
    for rate in (0.8, 1.25):
        conditions[f"speed x{rate}"] = [librosa.effects.time_stretch(y, rate=rate) for y in clean]

    table, clean_cache = {}, None
    for name, audios in conditions.items():
        print("condition:", name, flush=True)
        res, cache = evaluate_condition(audios)
        table[name] = res
        if name == "clean":
            clean_cache = cache
        print(f"  AUC  A={res['A']['auc']:.3f}  B={res['B']['auc']:.3f}", flush=True)

    loc = word_localization(clean_cache)
    print("word localization:", loc)

    md = ["# Pronunciation baselines: evals", "",
          f"{len(PHRASES)} Korean phrases synthesized with MMS-TTS (clean, single speaker). "
          "A = faster-whisper small + jamo comparison. B = kresnik wav2vec2 CTC forced alignment.",
          "**Limits:** TTS speech, no human speakers, no fluent reviewer. This shows each scorer can tell "
          "right text from wrong text and find a swapped word; it does not validate accent or phoneme quality.", "",
          "## Right text vs wrong text (AUC; 0.5 = chance, 1.0 = perfect)", "",
          "| Condition | A auc | B auc | A matched / mismatched | B matched / mismatched |", "|---|---|---|---|---|"]
    for name, r in table.items():
        md.append(f"| {name} | {r['A']['auc']:.3f} | {r['B']['auc']:.3f} | "
                  f"{r['A']['matched_mean']:.2f} / {r['A']['mismatched_mean']:.2f} | "
                  f"{r['B']['matched_mean']:.2f} / {r['B']['mismatched_mean']:.2f} |")
    md += ["", "## Does the scorer flag the swapped word? (clean audio)", "",
           f"{loc['cases']} cases (one word of the expected text replaced). Top-1 hit rate; random guessing would be about {loc['chance']:.2f}.", "",
           "| A | B |", "|---|---|", f"| {loc['A']:.2f} | {loc['B']:.2f} |", "",
           "## What each model heard (clean)", "", "| Expected | A (whisper) | B (wav2vec2 greedy) |", "|---|---|---|"]
    for p, a, b in zip(PHRASES, table["clean"]["heard_A"], table["clean"]["heard_B"]):
        md.append(f"| {p} | {a} | {b} |")

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "pronunciation.md").write_text("\n".join(md) + "\n")
    (RESULTS / "pronunciation.json").write_text(json.dumps(
        {"conditions": table, "word_localization": loc}, ensure_ascii=False, indent=2))
    print("wrote", RESULTS / "pronunciation.md")


if __name__ == "__main__":
    main()
