"""Degradation evals for the singing score.

Run from the repo root:  python -m ml.evals.run_evals [--seeds N]

We have no labeled singing data, so we take a melody with known ground truth,
degrade it in controlled ways at increasing severity, push it through the real
path (render audio -> pitch tracker -> score_turn), and check that the score
falls as severity rises. Spearman rho near -1 means the score is monotonic in
severity. Writes ml/evals/results/degradation.md and degradation.json.

This validates that the scorer reacts sensibly to controlled errors on clean
synthetic voices. It does NOT show how scores behave on real singers.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from ml.evals.synthetic import (
    add_noise, delay, detune_random, drop_notes, example_melody,
    example_phrases, melody_track, render_audio, time_stretch,
)
from ml.scoring.config import SCORING_VERSION
from ml.scoring.pitch import HOP_SECONDS, pitch_contour
from ml.scoring.score import score_turn

SR = 16_000
RESULTS = Path(__file__).parent / "results"
NOTES = example_melody()
REF = melody_track(NOTES, HOP_SECONDS)
PHRASES = example_phrases()


def score_audio(audio: np.ndarray, **kw) -> dict:
    user = pitch_contour(audio, SR)
    return score_turn(user, REF, PHRASES, **kw)


# Each axis: name, severity label, list of (severity, make_audio(seed)) pairs.
def axes() -> list[tuple[str, str, list[tuple[float, callable]]]]:
    return [
        ("Detuning (every note off by +/- N cents)", "cents",
         [(c, lambda s, c=c: render_audio(detune_random(NOTES, c, s), seed=s))
          for c in (0, 25, 50, 100, 150, 200, 300)]),
        ("Skipped notes (fraction replaced by rests)", "fraction",
         [(f, lambda s, f=f: render_audio(drop_notes(NOTES, f, s), seed=s))
          for f in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)]),
        ("Background noise (white, lower SNR = worse)", "-SNR dB",
         [(-snr, lambda s, snr=snr: add_noise(render_audio(NOTES, seed=s), snr, s))
          for snr in (40, 30, 20, 10, 5, 0, -5)]),
        ("Late entrance, uncalibrated (seconds)", "seconds",
         [(d, lambda s, d=d: delay(render_audio(NOTES, seed=s), SR, d))
          for d in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)]),
        ("Tempo drift (singer slower; 1 - rate)", "1 - rate",
         [(round(1 - r, 2), lambda s, r=r: time_stretch(render_audio(NOTES, seed=s), r))
          for r in (1.0, 0.95, 0.9, 0.8, 0.7, 0.6)]),
    ]


def run_axis(levels, seeds: int) -> dict:
    rows, sev_all, total_all = [], [], []
    for severity, make in levels:
        scores = [score_audio(make(s)) for s in range(seeds)]
        t = [r["total"] for r in scores]
        rows.append({
            "severity": severity,
            "total": float(np.mean(t)), "total_sd": float(np.std(t)),
            "pitch": float(np.mean([r["pitch"] for r in scores])),
            "timing": float(np.mean([r["timing"] for r in scores])),
        })
        sev_all += [severity] * seeds
        total_all += t
    rho = spearmanr(sev_all, total_all).statistic
    return {"rows": rows, "spearman": None if np.isnan(rho) else float(rho)}


def sanity_checks() -> list[tuple[str, float, str]]:
    clean = render_audio(NOTES)
    rng = np.random.default_rng(0)
    return [
        ("Reference-like take (through tracker)", score_audio(clean)["total"], ">= 90"),
        ("Same take, octave up, +12 register chosen",
         score_audio(render_audio([(m + 12 if m else m, d) for m, d in NOTES]), register=12)["total"], ">= 90"),
        ("Same take, octave up, register NOT chosen",
         score_audio(render_audio([(m + 12 if m else m, d) for m, d in NOTES]))["total"], "<= 30"),
        ("Silence", score_audio(np.zeros(len(clean), np.float32))["total"], "== 0"),
        ("Noise only (no voice)", score_audio((rng.standard_normal(len(clean)) * 0.1).astype(np.float32))["total"], "<= 10"),
        ("Identical input scored twice, equal?",
         float(score_audio(clean) == score_audio(clean)), "== 1"),
    ]


def to_markdown(results: dict, checks, seeds: int) -> str:
    out = [
        "# Singing score: degradation evals",
        "",
        f"Scoring version `{SCORING_VERSION}`. Synthetic voice-like melody (9.5 s, 14 notes, 3 phrases), "
        f"rendered to audio, tracked with pyin, scored with `score_turn`. {seeds} seeds per level.",
        "Totals are 0-100. **Limits:** clean synthetic voices only; says nothing yet about real singers.",
        "",
        "## Sanity checks",
        "",
        "| Check | Score | Expected |",
        "|---|---|---|",
    ]
    out += [f"| {n} | {v:.1f} | {e} |" for n, v, e in checks]
    for name, data in results.items():
        rho = data["spearman"]
        out += ["", f"## {name}", "",
                f"Spearman rho (severity vs total): **{rho:.3f}**" if rho is not None else "Spearman rho: n/a",
                "", "| Severity | Total (mean +/- sd) | Pitch | Timing |", "|---|---|---|---|"]
        out += [f"| {r['severity']} | {r['total']:.1f} +/- {r['total_sd']:.1f} | {r['pitch']:.1f} | {r['timing']:.1f} |"
                for r in data["rows"]]
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=3)
    args = parser.parse_args()

    results = {}
    for name, _, levels in axes():
        print("running:", name, flush=True)
        results[name] = run_axis(levels, args.seeds)
        print(f"  spearman = {results[name]['spearman']}", flush=True)
    checks = sanity_checks()

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "degradation.md").write_text(to_markdown(results, checks, args.seeds))
    (RESULTS / "degradation.json").write_text(json.dumps(
        {"scoring_version": SCORING_VERSION, "seeds": args.seeds, "axes": results,
         "checks": [{"name": n, "score": v, "expected": e} for n, v, e in checks]}, indent=2))
    print("wrote", RESULTS / "degradation.md")


if __name__ == "__main__":
    main()
