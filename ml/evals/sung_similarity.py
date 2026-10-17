"""Can we tell WHICH WORDS were sung by comparing two singers' audio directly? (No text recognition.)

Run from the repo root with the speech environment:
  ml/pronunciation/.venv/bin/python -m ml.evals.sung_similarity

The idea behind "compare your singing to the original singer": turn each sung line into a sequence
of speech-model features, align two lines with DTW (dynamic time warping), and use the alignment
cost as "how alike do these sound". DTW is used on purpose here: it absorbs tempo differences so only
the CONTENT is compared (timing is scored separately by the singing score).

Test set without any new recordings: K-pop choruses repeat, so the full Russian Roulette vocal stem
contains the same lyric line sung several times, sometimes by different members. Pairs with the same
text should be MORE alike than pairs with different text. Reported per feature type:
  * AUC: same-text pairs vs different-text pairs (0.5 = chance, 1.0 = perfect);
  * top-1: for each repeated line, is its nearest other line one with the same text?
Baselines: line length alone, and MFCC (plain acoustic features). Writes
ml/evals/results/sung_similarity.md (numbers only, no audio or lyrics).
"""
import argparse
import collections
import json
import re
from pathlib import Path

import librosa
import numpy as np
from scipy.stats import mannwhitneyu

SR, HOP = 16_000, 320
RESULTS = Path(__file__).parent / "results"
MODEL = "kresnik/wav2vec2-large-xlsr-korean"


def cmvn(x: np.ndarray) -> np.ndarray:
    """Per-line mean/variance normalisation: removes a constant voice/channel offset."""
    return (x - x.mean(0)) / (x.std(0) + 1e-6)


def dtw_cost(a: np.ndarray, b: np.ndarray) -> float:
    """Mean cosine distance along the best DTW alignment of two feature sequences (T, D)."""
    an = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    bn = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    cost = 1.0 - an @ bn.T
    D, wp = librosa.sequence.dtw(C=cost)
    return float(D[-1, -1] / len(wp))


class W2V:
    def __init__(self):
        import torch
        from transformers import AutoProcessor, Wav2Vec2ForCTC
        self.torch = torch
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.proc = AutoProcessor.from_pretrained(MODEL)
        self.model = Wav2Vec2ForCTC.from_pretrained(MODEL).to(self.dev).eval()

    def features(self, y: np.ndarray, layers: list[int]) -> dict:
        inp = self.proc(y, sampling_rate=SR, return_tensors="pt").input_values.to(self.dev)
        with self.torch.no_grad():
            out = self.model(inp, output_hidden_states=True)
        feats = {f"wav2vec2 layer {l}": out.hidden_states[l][0].float().cpu().numpy() for l in layers}
        feats["wav2vec2 posteriorgram"] = self.torch.log_softmax(out.logits[0].float(), -1).cpu().numpy()
        return feats


def load_lines(manifest: Path, vocals: Path, min_len: float = 0.8):
    """(audio, normalised lyric, reference Hz slice) per line long enough to compare."""
    m = json.loads(manifest.read_text(encoding="utf-8"))
    y, _ = librosa.load(vocals, sr=SR, mono=True)
    hop = m["reference"]["hop_seconds"]
    hz = np.array([np.nan if v is None else v for v in m["reference"]["hz"]], dtype=float)
    norm = lambda t: re.sub(r"[\s\W_]+", "", t.lower())
    out = []
    for line in m["lines"]:
        t = norm(line["text"])
        if t and line["end"] - line["start"] >= min_len:
            out.append((y[int(line["start"] * SR):int(line["end"] * SR)], t,
                        hz[int(round(line["start"] / hop)):int(round(line["end"] / hop))]))
    return out


def melody_cost(a: np.ndarray, b: np.ndarray) -> float:
    """Key-independent melody distance: each voiced contour in cents relative to its own median,
    aligned by DTW; mean absolute difference in semitones. inf if either line is mostly unvoiced."""
    def contour(h):
        h = h[np.isfinite(h)]
        return None if len(h) < 10 else (1200 * np.log2(h / np.median(h)) / 100)[:, None]
    ca, cb = contour(a), contour(b)
    if ca is None or cb is None:
        return np.inf
    D, wp = librosa.sequence.dtw(C=np.abs(ca - cb.T))
    return float(D[-1, -1] / len(wp))


def evaluate(costs: np.ndarray, labels: list[str], keep: np.ndarray | None = None) -> dict:
    """keep: optional (n, n) bool mask of the pairs to evaluate (e.g. melody-matched pairs only)."""
    n = len(labels)
    same = np.array([[labels[i] == labels[j] for j in range(n)] for i in range(n)])
    iu = np.triu_indices(n, 1)
    k_mask = np.ones(len(iu[0]), bool) if keep is None else keep[iu]
    pos, neg = -costs[iu][same[iu] & k_mask], -costs[iu][~same[iu] & k_mask]
    auc = mannwhitneyu(pos, neg).statistic / (len(pos) * len(neg))
    counts = collections.Counter(labels)
    hits, chance, k = 0, 0.0, 0
    for i in range(n):
        if counts[labels[i]] < 2:
            continue
        c = costs[i].copy(); c[i] = np.inf
        hits += int(labels[int(np.argmin(c))] == labels[i]); chance += (counts[labels[i]] - 1) / (n - 1); k += 1
    return {"auc": float(auc), "top1": hits / k, "top1_chance": chance / k, "queries": k,
            "pos_pairs": int(len(pos)), "neg_pairs": int(len(neg))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default="ml/data/received/song_a.json")
    ap.add_argument("--vocals", default="ml/data/russian-roulette/vocals.mp3")
    ap.add_argument("--layers", default="6,12,18,24")
    args = ap.parse_args()
    lines = load_lines(Path(args.manifest), Path(args.vocals))
    labels = [t for _, t, _ in lines]
    layers = [int(x) for x in args.layers.split(",")]
    w2v = W2V()
    feats = collections.defaultdict(list)
    for y, _, _ in lines:
        for name, f in w2v.features(y, layers).items():
            feats[name].append(cmvn(f))
        feats["MFCC (acoustic baseline)"].append(cmvn(librosa.feature.mfcc(y=y, sr=SR, n_mfcc=20, hop_length=HOP).T))
    n = len(lines)
    results = {}
    lengths = np.array([len(y) / SR for y, _, _ in lines])
    mel = np.full((n, n), np.inf)
    for i in range(n):
        for j in range(i + 1, n):
            mel[i, j] = mel[j, i] = melody_cost(lines[i][2], lines[j][2])
    same_lyric = np.array([[labels[i] == labels[j] for j in range(n)] for i in range(n)])
    iu = np.triu_indices(n, 1)
    pos_mel = mel[iu][same_lyric[iu] & np.isfinite(mel[iu])]
    threshold = float(np.percentile(pos_mel, 75))   # "as similar a tune as most same-lyric repeats"
    melody_matched = mel <= threshold
    matched_results = {}
    length_costs = np.abs(lengths[:, None] - lengths[None, :])
    results["line length only (trivial baseline)"] = evaluate(length_costs, labels)
    matched_results["line length only (trivial baseline)"] = evaluate(length_costs, labels, melody_matched)
    matched_results["melody itself (pitch-contour DTW)"] = evaluate(np.where(np.isfinite(mel), mel, 1e9), labels, melody_matched)
    for name, fs in feats.items():
        costs = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                costs[i, j] = costs[j, i] = dtw_cost(fs[i], fs[j])
        results[name] = evaluate(costs, labels)
        matched_results[name] = evaluate(costs, labels, melody_matched)
        print(f"{name:34s} all pairs AUC {results[name]['auc']:.3f} | SAME-TUNE pairs only AUC {matched_results[name]['auc']:.3f}", flush=True)
    r0 = next(iter(results.values()))
    md = ["# Comparing two singers' audio directly: does it know which words were sung?", "",
          f"Test set: {n} lyric lines from one full K-pop vocal stem (Demucs output, local only). "
          f"{r0['queries']} lines have the same lyric sung elsewhere in the song (often by another member), giving "
          f"{r0['pos_pairs']} same-lyric pairs vs {r0['neg_pairs']} different-lyric pairs. No repeat is a copy-pasted recording "
          "(waveform correlation of repeats: median 0.04). Each line is turned into features and compared by DTW.", "",
          "| Features | Same vs different lyric (AUC, 0.5 = chance) | Nearest line has the same lyric (top-1) |", "|---|---|---|"]
    for name, r in results.items():
        md.append(f"| {name} | {r['auc']:.3f} | {r['top1']:.0%} (chance {r['top1_chance']:.0%}) |")
    mr = next(iter(matched_results.values()))
    md += ["", "## The control that matters: same tune, different words", "",
           f"In the game the player always sings the same tune as the reference, so the real question is whether a method can "
           f"tell the words apart **when the melody is the same**. Here only pairs whose melodies are as similar as most same-lyric "
           f"repeats are kept (key-independent pitch-contour DTW at or below the 75th percentile of same-lyric pairs): "
           f"{mr['pos_pairs']} same-lyric vs {mr['neg_pairs']} different-lyric pairs.", "",
           "| Features | Same vs different lyric, same-tune pairs only (AUC) |", "|---|---|"]
    for name, r in matched_results.items():
        md.append(f"| {name} | {r['auc']:.3f} |")
    md += ["", "**Limits:** one song, professional singers, stems from Demucs; repeated chorus lines are the easiest case "
           "(often sung in the same melody). This tests whether the features carry lyric content across different "
           "takes, not whether they can grade a learner's pronunciation. Real player takes are the next test."]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "sung_similarity.md").write_text("\n".join(md) + "\n")
    print("wrote", RESULTS / "sung_similarity.md")


if __name__ == "__main__":
    main()
