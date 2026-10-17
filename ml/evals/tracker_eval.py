"""Tracker agreement eval: does the browser-style tracker agree with the reference?

Run from the repo root with the GPU env (needs torchcrepe):
  ml/pronunciation/.venv/bin/python -m ml.evals.tracker_eval

In the live game the reference contour comes from CREPE (offline) but the
player's pitch comes from Pitchy in the browser (McLeod Pitch Method). If the two
trackers disagree, players lose points for nothing. Here a synthetic singer whose
pitch we know exactly is tracked three ways, and we measure:
  1. each tracker's accuracy against the ground truth;
  2. the live-game pairing: CREPE reference vs MPM player track, compared with
     the same-tracker pairing (CREPE vs CREPE). The gap is the cost of the mismatch;
  3. the effect of MPM's clarity threshold (the frontend's main knob).
Writes ml/evals/results/trackers.md.
"""
import json
from pathlib import Path

import numpy as np

from ml.evals.mpm import mpm_track
from ml.evals.synthetic import (add_noise, delay, detune_random, example_melody,
                                example_phrases, melody_track, render_audio)
from ml.scoring.pitch import HOP_SECONDS, pitch_contour, pitch_score
from ml.scoring.score import score_turn

SR = 16_000
RESULTS = Path(__file__).parent / "results"
NOTES = example_melody()
TRUTH = melody_track(NOTES, HOP_SECONDS)
PHRASES = example_phrases()


def accuracy(track: np.ndarray) -> dict:
    n = min(len(track), len(TRUTH))
    t, g = track[:n], TRUTH[:n]
    both = np.isfinite(t) & np.isfinite(g)
    err = np.abs(1200 * np.log2(t[both] / g[both]))
    return {
        "score_vs_truth": pitch_score(track, TRUTH).score,
        "voicing_recall": float(both.sum() / np.isfinite(g).sum()),
        "false_voicing": float((np.isfinite(t) & ~np.isfinite(g)).sum() / max(1, (~np.isfinite(g)).sum())),
        "median_err_cents": float(np.median(err)) if len(err) else None,
        "gross_err_share": float((err > 100).mean()) if len(err) else None,
    }


def trackers(audio: np.ndarray, clarity: float = 0.9) -> dict:
    return {"pyin": pitch_contour(audio, SR, "pyin"), "crepe": pitch_contour(audio, SR, "crepe"),
            "mpm": mpm_track(audio, SR, clarity_threshold=clarity)}


def main() -> None:
    seeds = range(3)
    takes = {
        "clean": lambda s: render_audio(NOTES, seed=s),
        "noise 20 dB": lambda s: add_noise(render_audio(NOTES, seed=s), 20, s),
        "noise 10 dB": lambda s: add_noise(render_audio(NOTES, seed=s), 10, s),
        "noise 5 dB": lambda s: add_noise(render_audio(NOTES, seed=s), 5, s),
        "detuned 100 cents": lambda s: render_audio(detune_random(NOTES, 100, s), seed=s),
        "late 0.2 s": lambda s: delay(render_audio(NOTES, seed=s), SR, 0.2),
    }
    # The offline reference: CREPE on the clean "original vocals" (seed 100, a different rendition).
    ref = pitch_contour(render_audio(NOTES, seed=100), SR, "crepe")

    acc_rows, pair_rows = {}, {}
    for name, make in takes.items():
        print("take:", name, flush=True)
        acc = {k: [] for k in ("pyin", "crepe", "mpm")}
        pair = {"crepe ref vs crepe player": [], "crepe ref vs mpm player (live game)": [], "truth vs truth-detuned": []}
        for s in seeds:
            audio = make(s)
            tr = trackers(audio)
            for k, v in tr.items():
                acc[k].append(accuracy(v))
            pair["crepe ref vs crepe player"].append(score_turn(tr["crepe"], ref, PHRASES)["total"])
            pair["crepe ref vs mpm player (live game)"].append(score_turn(tr["mpm"], ref, PHRASES)["total"])
        acc_rows[name] = {k: {m: float(np.mean([r[m] for r in v if r[m] is not None])) for m in v[0]}
                          for k, v in acc.items()}
        pair_rows[name] = {k: float(np.mean(v)) for k, v in pair.items() if v}

    clarity_rows = {}
    for clarity in (0.7, 0.8, 0.9, 0.95):
        row = {}
        for name in ("clean", "noise 10 dB"):
            totals = [score_turn(mpm_track(takes[name](s), SR, clarity_threshold=clarity), ref, PHRASES)["total"]
                      for s in seeds]
            row[name] = float(np.mean(totals))
        noise_only = (np.random.default_rng(0).standard_normal(len(render_audio(NOTES))) * 0.05).astype(np.float32)
        row["noise only (no voice)"] = score_turn(mpm_track(noise_only, SR, clarity_threshold=clarity), ref, PHRASES)["total"]
        clarity_rows[clarity] = row
        print("clarity", clarity, row, flush=True)

    md = ["# Pitch trackers: do the browser and the reference agree?", "",
          "Synthetic singer with known pitch (3 seeds per row). Reference = CREPE on a separate clean rendition, "
          "as the offline pipeline would build it. `mpm` is our Python reimplementation of the McLeod Pitch Method "
          "that Pitchy uses in the browser (an emulation, not Pitchy's exact code).",
          "**Limits:** synthetic voices only.", "",
          "## 1. Accuracy against the ground truth", "",
          "| Take | Tracker | Score vs truth | Voicing recall | False voicing | Median error (cents) | Errors > 100 cents |",
          "|---|---|---|---|---|---|---|"]
    for name, row in acc_rows.items():
        for k, a in row.items():
            md.append(f"| {name} | {k} | {a['score_vs_truth']:.1f} | {a['voicing_recall']:.2f} | "
                      f"{a['false_voicing']:.2f} | {a['median_err_cents']:.1f} | {a['gross_err_share']:.3f} |")
    md += ["", "## 2. The live-game pairing (total score)", "",
           "| Take | CREPE ref vs CREPE player | CREPE ref vs MPM player (live game) | Cost of mismatch |",
           "|---|---|---|---|"]
    for name, row in pair_rows.items():
        a, b = row["crepe ref vs crepe player"], row["crepe ref vs mpm player (live game)"]
        md.append(f"| {name} | {a:.1f} | {b:.1f} | {a - b:+.1f} |")
    md += ["", "## 3. MPM clarity threshold (frontend setting), total score", "",
           "| Clarity threshold | Clean take | Take with 10 dB noise | Noise only, no voice |", "|---|---|---|---|"]
    for c, row in clarity_rows.items():
        md.append(f"| {c} | {row['clean']:.1f} | {row['noise 10 dB']:.1f} | {row['noise only (no voice)']:.1f} |")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "trackers.md").write_text("\n".join(md) + "\n")
    (RESULTS / "trackers.json").write_text(json.dumps(
        {"accuracy": acc_rows, "pairing": pair_rows, "clarity": {str(k): v for k, v in clarity_rows.items()}}, indent=2))
    print("wrote", RESULTS / "trackers.md")


if __name__ == "__main__":
    main()
