"""Does a player's sung line sound closest to the RIGHT line of the original singer? (No text recognition.)

Run from the repo root with the speech environment:
  ml/pronunciation/.venv/bin/python -m ml.evals.player_vs_singer take.wav ml/data/<song>/song.json ml/data/<song>/vocals.mp3

The take is lined up with the song from its melody (align_take.py). Then every lyric line the player
sang is compared (features + DTW, as in sung_similarity.py) with every line of the original vocal stem.
A method that "knows the words" should find the player's line closest to the original singer's SAME
line. Because the player and the original are different voices, a method cannot win by recognising the
singer. Controls, since the right line also has the same tune and length as the player's line:
  * all lines;
  * length-matched: only other lines within 20% of the same duration;
  * tune-and-length-matched: additionally a similar melody (key-independent pitch-contour DTW).
Lines whose lyric repeats elsewhere count as correct for all their occurrences. Reported: AUC (right
line vs other lines) and top-1 (is the nearest original line the right one). Writes
ml/evals/results/player_vs_singer.md (numbers only).
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import librosa
import numpy as np
from scipy.stats import mannwhitneyu

from ml.evals.align_take import align
from ml.evals.sung_similarity import HOP, SR, W2V, cmvn, dtw_cost, melody_cost
from ml.scoring.pitch import pitch_contour, to_track

RESULTS = Path(__file__).parent / "results"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("take")
    ap.add_argument("manifest")
    ap.add_argument("vocals")
    ap.add_argument("--label", default="player take")
    args = ap.parse_args()
    m = json.load(open(args.manifest, encoding="utf-8"))
    ref_audio, _ = librosa.load(args.vocals, sr=SR, mono=True)
    take, _ = librosa.load(args.take, sr=SR, mono=True)
    ref_hz = to_track(m["reference"]["hz"])
    hop = m["reference"]["hop_seconds"]
    take_hz = pitch_contour(take, SR, backend="crepe")
    a = align(take_hz, ref_hz, hop)
    lead = a["lead_in_s"]
    norm = lambda t: re.sub(r"[\s\W_]+", "", t.lower())

    lines = []
    for ln in m["lines"]:
        s, e = ln["start"], ln["end"]
        if e - s < 0.8 or not norm(ln["text"]):
            continue
        ps, pe = int((s + lead) * SR), int((e + lead) * SR)
        if ps < 0 or pe > len(take):
            continue  # the recording does not cover this line
        lines.append({"text": norm(ln["text"]), "dur": e - s, "ref": ref_audio[int(s * SR):int(e * SR)],
                      "player": take[ps:pe], "hz": ref_hz[int(round(s / hop)):int(round(e / hop))],
                      "player_hz": take_hz[int(round((s + lead) / hop)):int(round((e + lead) / hop))]})
    n = len(lines)
    w2v = W2V()
    feats = defaultdict(lambda: {"ref": [], "player": []})
    for ln in lines:
        for side in ("ref", "player"):
            for name, f in w2v.features(ln[side], [6, 12]).items():
                if "posteriorgram" not in name:
                    feats[name][side].append(cmvn(f))
            feats["MFCC (acoustic baseline)"][side].append(cmvn(librosa.feature.mfcc(y=ln[side], sr=SR, n_mfcc=20, hop_length=HOP).T))

    same = np.array([[lines[i]["text"] == lines[j]["text"] for j in range(n)] for i in range(n)])
    dur = np.array([ln["dur"] for ln in lines])
    len_ok = np.abs(dur[:, None] - dur[None, :]) <= 0.2 * dur[:, None]
    mel = np.array([[melody_cost(lines[i]["hz"], lines[j]["hz"]) for j in range(n)] for i in range(n)])
    pos_mel = mel[same & ~np.eye(n, dtype=bool)]
    pos_mel = pos_mel[np.isfinite(pos_mel)]
    mel_thr = float(np.percentile(pos_mel, 75)) if len(pos_mel) else float(np.nanpercentile(mel[np.isfinite(mel)], 25))
    controls = {"all lines": np.ones((n, n), bool), "length-matched": len_ok, "tune-and-length-matched": len_ok & (mel <= mel_thr)}

    def score(costs: np.ndarray, allowed: np.ndarray) -> tuple[float, float, int]:
        pos, neg, hits, q = [], [], 0, 0
        for i in range(n):
            cand = allowed[i] | same[i]
            if not (cand & ~same[i]).any():
                continue
            pos += list(-costs[i][same[i]]); neg += list(-costs[i][cand & ~same[i]])
            j = int(np.argmin(np.where(cand, costs[i], np.inf)))
            hits += int(same[i, j]); q += 1
        auc = mannwhitneyu(pos, neg).statistic / (len(pos) * len(neg)) if pos and neg else float("nan")
        return auc, hits / max(1, q), q

    results = {}
    for name, fs in feats.items():
        costs = np.array([[dtw_cost(fs["player"][i], fs["ref"][j]) for j in range(n)] for i in range(n)])
        results[name] = {c: score(costs, allowed) for c, allowed in controls.items()}
        print(name, {c: f"AUC {v[0]:.2f} top-1 {v[1]:.0%} ({v[2]} lines)" for c, v in results[name].items()}, flush=True)
    # Baseline: the PLAYER's melody vs each original line's melody (key-independent), i.e. "just the tune".
    pmel = np.array([[melody_cost(lines[i]["player_hz"], lines[j]["hz"]) for j in range(n)] for i in range(n)])
    results["player's melody alone (no words)"] = {c: score(np.where(np.isfinite(pmel), pmel, 1e9), allowed) for c, allowed in controls.items()}

    chance = {c: np.mean([1 / max(1, (allowed[i] | same[i]).sum()) * same[i].sum() for i in range(n)]) for c, allowed in controls.items()}
    md = [f"# Player vs original singer: {args.label}", "",
          f"{n} lyric lines the recording covers, lined up by melody (register {a['register']:+d}, agreement {a['agreement']:.2f} vs "
          f"{a['runner_up_agreement']:.2f}). Each player line is compared with every original-singer line; the right line should be nearest. "
          "Different voices, so recognising the singer cannot help.", "",
          "| Features | " + " | ".join(f"{c}: AUC / top-1" for c in controls) + " |", "|---|" + "---|" * len(controls)]
    for name, r in results.items():
        md.append(f"| {name} | " + " | ".join(f"{v[0]:.2f} / {v[1]:.0%}" for v in r.values()) + " |")
    md += ["", "Chance top-1 (one right line among the allowed candidates): " + ", ".join(f"{c} ~{v:.0%}" for c, v in chance.items()) + ".",
           "**Limits:** one singer, one song, a phone recording, an unreviewed reference. The right line always shares the "
           "player's tune and length; the matched controls reduce that advantage but cannot remove it completely."]
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"player_vs_singer_{re.sub(r'[^a-z0-9]+', '-', args.label.lower()).strip('-')}.md"
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md[6:]))
    print("wrote", out)


if __name__ == "__main__":
    main()
