"""Degradation eval on a REAL vocal stem (no human recordings needed).

Run from the repo root with the GPU env:
  ml/pronunciation/.venv/bin/python -m ml.evals.real_audio_eval ml/data/<song>/vocals.mp3 --start 45 --end 75 --label chorus-a

The synthetic evals use clean computer-made voices. Here the "perfect take" is a
real singer's stem (local only, never committed); we damage it in controlled ways
(local pitch shifts, late entrance, noise, dropped seconds), track it with CREPE
AND with the browser-style MPM tracker, and score it against the clean CREPE
contour. It answers: do scores still fall in order on real, fast, breathy
singing, and what does the browser's tracker cost on a real voice?

Only aggregated numbers are written (ml/evals/results/real_audio_<label>.md): no
audio, no lyrics. Phrases are rough (voiced stretches), so absolute numbers are
indicative; the ORDER of scores is what this checks.
"""
import argparse
from pathlib import Path

import librosa
import numpy as np
from scipy.stats import spearmanr

from ml.evals.mpm import mpm_track
from ml.evals.rough_reference import rough_phrases
from ml.evals.synthetic import add_noise, delay
from ml.scoring.pitch import HOP_SECONDS, pitch_contour
from ml.scoring.score import score_turn

SR = 16_000
RESULTS = Path(__file__).parent / "results"


def chunk_shift(y: np.ndarray, cents: float, seed: int, chunk_s: float = 1.0) -> np.ndarray:
    """Local detune: pitch-shift every other 1 s chunk by +/- cents (random sign)."""
    rng, n, out = np.random.default_rng(seed), int(chunk_s * SR), y.copy()
    for k, a in enumerate(range(0, len(y), n)):
        if k % 2 == 0 and cents:
            seg = y[a:a + n]
            out[a:a + len(seg)] = librosa.effects.pitch_shift(
                seg, sr=SR, n_steps=rng.choice([-1, 1]) * cents / 100.0)[:len(seg)]
    return out


def drop_chunks(y: np.ndarray, fraction: float, seed: int, chunk_s: float = 1.0) -> np.ndarray:
    """Silence a random fraction of the 1 s chunks (the singer skipped them)."""
    rng, n, out = np.random.default_rng(seed), int(chunk_s * SR), y.copy()
    starts = list(range(0, len(y), n))
    for a in rng.choice(starts, size=int(round(fraction * len(starts))), replace=False):
        out[a:a + n] = 0
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("vocals")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--label", required=True, help="short name for the results file (no song title needed)")
    ap.add_argument("--seeds", type=int, default=2)
    args = ap.parse_args()

    y, _ = librosa.load(args.vocals, sr=SR, mono=True, offset=args.start,
                        duration=None if args.end is None else args.end - args.start)
    duration = len(y) / SR
    ref = pitch_contour(y, SR, "crepe")
    phrases = rough_phrases(ref, HOP_SECONDS, duration)
    print(f"{duration:.1f} s clip, reference voiced {np.isfinite(ref).mean():.0%}, {len(phrases)} rough phrases", flush=True)

    def total(audio, tracker):
        track = pitch_contour(audio, SR, "crepe") if tracker == "crepe" else mpm_track(audio, SR, 0.8)
        return score_turn(track, ref, phrases)["total"]

    axes = {
        "Local detuning (every other second shifted +/- N cents)": ("cents", [
            (c, lambda s, c=c: chunk_shift(y, c, s)) for c in (0, 50, 100, 200, 300)]),
        "Late entrance, uncalibrated (seconds)": ("seconds", [
            (d, lambda s, d=d: delay(y, SR, d)) for d in (0.0, 0.1, 0.2, 0.3, 0.4)]),
        "Dropped seconds (fraction silenced)": ("fraction", [
            (f, lambda s, f=f: drop_chunks(y, f, s)) for f in (0.0, 0.1, 0.25, 0.5)]),
        "White noise (-SNR dB, lower SNR = worse)": ("-SNR dB", [
            (-snr, lambda s, snr=snr: add_noise(y, snr, s)) for snr in (30, 20, 10, 5)]),
    }
    md = [f"# Real-voice degradation eval ({args.label})", "",
          f"A real {duration:.0f} s vocal clip (local only, never committed) is damaged at increasing severity, tracked, "
          "and scored against its own clean CREPE contour. Two trackers for the damaged take: **CREPE** and **MPM** "
          "(our emulation of the browser's Pitchy, clarity 0.8). Totals 0-100, "
          f"{args.seeds} seeds per level. Phrases are rough voiced stretches ({len(phrases)}).",
          "**Limits:** one singer, damage is still synthetic, the stem may contain backing vocals, "
          "no human take. Read the ORDER of scores, not the absolute values.", ""]
    for name, (unit, levels) in axes.items():
        print("axis:", name, flush=True)
        md += [f"## {name}", "", f"| {unit} | CREPE total | MPM (browser-style) total |", "|---|---|---|"]
        sev, rows = [], {"crepe": [], "mpm": []}
        for severity, make in levels:
            tot = {t: [total(make(s), t) for s in range(args.seeds)] for t in ("crepe", "mpm")}
            md.append(f"| {severity} | {np.mean(tot['crepe']):.1f} | {np.mean(tot['mpm']):.1f} |")
            for t in tot:
                rows[t] += tot[t]
            sev += [severity] * args.seeds
            print(f"  {severity}: crepe {np.mean(tot['crepe']):.1f}  mpm {np.mean(tot['mpm']):.1f}", flush=True)
        rho = {t: spearmanr(sev, rows[t]).statistic for t in rows}
        md += ["", f"Spearman rho (severity vs total): CREPE **{rho['crepe']:.2f}**, MPM **{rho['mpm']:.2f}**", ""]
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"real_audio_{args.label}.md"
    out.write_text("\n".join(md) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
