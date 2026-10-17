"""Where should the Perfect / Great / Okay / Bad cutoffs go? Measured on a real take, no re-recording.

Run from the repo root with the speech environment (needs CREPE, and Node + Pitchy, see pitchy_node.py):
  ml/pronunciation/.venv/bin/python -m ml.evals.band_calibration take.wav ml/data/<song>/song.json \
      --vocals ml/data/<song>/vocals.mp3 --label <name>

The take is lined up with its song by melody (align_take.py), then damaged in known ways built from the
same recording: every phrase pushed off-key by N cents (alternating sharp and flat, so it is not just a
register change), the whole take late by N seconds, a share of phrases silenced, plus noise-only and
silence. With --vocals, the original singer's stem over the same stretch is scored too: the ceiling a
real performance can reach through the tracker. Each version is scored phrase by phrase with the live tracker (the real Pitchy at the proposed
settings) and with CREPE. The phrase-score spread per condition shows which cutoffs separate "sung well"
from "clearly off". It is one singer and one song, so the result is a starting point, not a validation.
Writes ml/evals/results/band_calibration_<label>.md (numbers only).
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import librosa
import numpy as np

from ml.evals.align_take import align
from ml.evals.crop_manifest import crop_manifest
from ml.evals.pitchy_node import pitchy_track
from ml.scoring.config import ScoreConfig
from ml.scoring.pitch import pitch_contour, to_track
from ml.scoring.score import rate, score_turn

SR = 16_000
# Proposed bands for the live path, read off this eval (see the results file for the reasoning).
PROPOSED = ScoreConfig(perfect=80.0, great=65.0, okay=40.0)
RESULTS = Path(__file__).parent / "results"
TRACKERS = {
    "live (Pitchy, clarity 0.65, RMS 0.005)": lambda y: pitchy_track(y, SR, sample_rate=48_000, window=2048, clarity=0.65, gate=0.005),
    "CREPE": lambda y: pitch_contour(y, SR, backend="crepe"),
}


def detune(seg: np.ndarray, phrases, cents: float) -> np.ndarray:
    """Shift each phrase by +cents or -cents, alternating, so the melody itself is wrong."""
    out = seg.copy()
    for k, (_, s, e) in enumerate(phrases):
        a, b = int(s * SR), min(len(seg), int(e * SR))
        if b - a > SR // 10:
            sign = 1 if k % 2 == 0 else -1
            out[a:b] = librosa.effects.pitch_shift(seg[a:b], sr=SR, n_steps=sign * cents / 100)
    return out


def drop(seg: np.ndarray, phrases, share: float, seed: int = 0) -> np.ndarray:
    out = seg.copy()
    rng = np.random.default_rng(seed)
    for _, s, e in rng.permutation(np.array(phrases, dtype=object))[: int(round(share * len(phrases)))]:
        out[int(s * SR):int(e * SR)] = 0
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("take"); ap.add_argument("manifest")
    ap.add_argument("--label", default="take")
    ap.add_argument("--vocals", help="the song's original vocal stem, scored as the ceiling")
    args = ap.parse_args()
    m = json.load(open(args.manifest, encoding="utf-8"))
    y, _ = librosa.load(args.take, sr=SR, mono=True)
    a = align(pitch_contour(y, SR, backend="crepe"), to_track(m["reference"]["hz"]), m["reference"]["hop_seconds"])
    lead = a["lead_in_s"]
    s0, s1 = max(0.0, -lead), min(m["duration"], len(y) / SR - lead)
    clip, _ = crop_manifest(m, round(s0, 2), round(s1, 2))
    seg = y[int((s0 + lead) * SR):int((s1 + lead) * SR)]
    ref = to_track(clip["reference"]["hz"])
    phrases = [(p["id"], p["start"], p["end"]) for p in clip["phrases"]]
    onsets = [n["start"] for n in clip["reference"]["notes"]] or None
    rng = np.random.default_rng(0)
    conditions = {}
    if args.vocals:
        vocals, _ = librosa.load(args.vocals, sr=SR, mono=True)
        # The stem is in the original register; shift the reference with it (register 0).
        conditions["original singer (stem)"] = (vocals[int(s0 * SR):int(s1 * SR)], 0)
    conditions.update({k: (v, a["register"]) for k, v in {
        "real take": seg,
        "off-key 50 cents": detune(seg, phrases, 50),
        "off-key 100 cents": detune(seg, phrases, 100),
        "off-key 200 cents": detune(seg, phrases, 200),
        "off-key 300 cents": detune(seg, phrases, 300),
        "late 0.2 s": np.concatenate([np.zeros(int(0.2 * SR), np.float32), seg])[: len(seg)],
        "late 0.4 s": np.concatenate([np.zeros(int(0.4 * SR), np.float32), seg])[: len(seg)],
        "25% of phrases silent": drop(seg, phrases, 0.25),
        "50% of phrases silent": drop(seg, phrases, 0.50),
        "noise only": (0.02 * rng.standard_normal(len(seg))).astype(np.float32),
        "silence": np.zeros(len(seg), np.float32),
    }.items()})
    cfg = ScoreConfig()
    md = [f"# Rating-band calibration: {args.label}", "",
          f"Take lined up by melody: register {a['register']:+d}, agreement {a['agreement']:.2f} (next best "
          f"{a['runner_up_agreement']:.2f}). {s1 - s0:.0f} s of the song, {len(phrases)} phrases. Current bands: "
          f"perfect >= {cfg.perfect:g}, great >= {cfg.great:g}, okay >= {cfg.okay:g}; miss under "
          f"{cfg.min_coverage:.0%} coverage. Phrase scores below are the 10th / 50th / 90th percentile over phrases "
          "that were not a miss.", ""]
    for tname, track in TRACKERS.items():
        md += [f"## {tname}", "", "| Condition | Total | Phrase p10 / p50 / p90 | Ratings, current bands | Ratings, proposed 80 / 65 / 40 |", "|---|---|---|---|---|"]
        for cname, (audio, register) in conditions.items():
            r = score_turn(track(audio), ref, phrases, ref_onsets=onsets, register=register)
            sc = [p["score"] for p in r["phrases"] if p["rating"] != "miss"]
            q = " / ".join(f"{v:.0f}" for v in np.percentile(sc, [10, 50, 90])) if sc else "n/a"
            ratings = ", ".join(f"{k} {v}" for k, v in Counter(p["rating"] for p in r["phrases"]).most_common())
            proposed = ", ".join(f"{k} {v}" for k, v in Counter(rate(p["score"], p["coverage"], PROPOSED) for p in r["phrases"]).most_common())
            md.append(f"| {cname} | {r['total']:.1f} | {q} | {ratings} | {proposed} |")
            print(tname[:5], md[-1], flush=True)
        md.append("")
    md += ["## Reading it", "",
           "- Through the live tracker the original singer is the realistic ceiling (CREPE scoring the stem is the same "
           "tracker that made the reference, so it is near 100 by construction and says nothing).",
           "- Proposed cutoffs, all on the live path: **perfect >= 80** (about the original singer's typical phrase), "
           "**great >= 65** (about a decent amateur's typical phrase), **okay >= 40** (a phrase a semitone off still "
           "lands here; two semitones off or 0.4 s late falls below). These are choices read off one singer and one song, "
           "not validated thresholds. Changing them is a scoring-version bump: fixtures and the TypeScript port change too.", ""]
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"band_calibration_{args.label}.md"
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
