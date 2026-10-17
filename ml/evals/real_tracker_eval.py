"""Browser-style tracker vs CREPE reference, on a REAL vocal stem.

Run from the repo root with the GPU env:
  ml/pronunciation/.venv/bin/python -m ml.evals.real_tracker_eval ml/data/<song>/vocals.mp3 --start 75 --end 105 --label clip-b

The live game scores the player's browser track (Pitchy, McLeod Pitch Method)
against an offline reference. On real singing the two trackers disagree, which
costs a good singer points they did nothing to lose. This measures:
  1. the MPM clarity threshold: how many frames it voices, how accurate and how
     octave-prone they are, and what a near-perfect take scores;
  2. whether the reference should come from the same tracker family as the live
     one (CREPE reference vs MPM reference), with bad takes to check separation;
  3. whether cleaning the live track (gap filling, octave correction) helps.
A "near-perfect take" here is the same stem plus mild noise, so tracker errors are
more correlated than they would be for a different human performance: treat the
same-tracker numbers as an upper bound. Writes ml/evals/results/real_tracker_<label>.md
(aggregated numbers only).
"""
import argparse
from pathlib import Path

import librosa
import numpy as np

from ml.evals.mpm import mpm_track
from ml.evals.real_audio_eval import chunk_shift
from ml.evals.rough_reference import rough_phrases
from ml.evals.synthetic import add_noise, delay
from ml.evals.track_cleanup import fill_gaps, fix_octaves
from ml.scoring.pitch import HOP_SECONDS, pitch_contour
from ml.scoring.score import score_turn

SR = 16_000
RESULTS = Path(__file__).parent / "results"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("vocals")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()

    y, _ = librosa.load(args.vocals, sr=SR, mono=True, offset=args.start,
                        duration=None if args.end is None else args.end - args.start)
    crepe_ref = pitch_contour(y, SR, "crepe")
    phrases = rough_phrases(crepe_ref, HOP_SECONDS, len(y) / SR)
    ref_voiced = np.isfinite(crepe_ref)
    score = lambda track, ref: score_turn(track, ref, phrases)["total"]

    md = [f"# Browser-style tracker vs CREPE reference, real voice ({args.label})", "",
          f"A real {len(y) / SR:.0f} s vocal clip (local only). CREPE reference voiced {ref_voiced.mean():.0%} of frames. "
          "MPM = our emulation of Pitchy's McLeod Pitch Method. Totals 0-100.",
          "**Limits:** one singer; the 'near-perfect take' is the same stem with mild noise, so same-tracker numbers are an "
          "upper bound; phrases are rough; the stem may contain backing vocals.", "",
          "## 1. MPM clarity threshold (live tracker vs CREPE reference)", "",
          "| Clarity | Frames voiced | Within 1 semitone (of frames both voiced) | About an octave off | Near-perfect take total |",
          "|---|---|---|---|---|"]
    near = add_noise(y, 30, 1)
    for clarity in (0.9, 0.8, 0.7, 0.6, 0.5):
        t = mpm_track(y, SR, clarity)
        n = min(len(t), len(crepe_ref))
        both = np.isfinite(t[:n]) & ref_voiced[:n]
        cents = 1200 * np.log2(t[:n][both] / crepe_ref[:n][both])
        md.append(f"| {clarity} | {np.isfinite(t).mean():.0%} | {(np.abs(cents) <= 100).mean():.0%} | "
                  f"{(np.abs(np.abs(cents) - 1200) < 150).mean():.0%} | {score(mpm_track(near, SR, clarity), crepe_ref):.1f} |")

    takes = {"near-perfect (30 dB noise)": near, "near-perfect (20 dB noise)": add_noise(y, 20, 2),
             "detuned 200 cents": chunk_shift(y, 200, 0), "late 0.3 s": delay(y, SR, 0.3),
             "noise only": (np.random.default_rng(0).standard_normal(len(y)) * 0.05).astype(np.float32),
             "silence": np.zeros(len(y), np.float32)}
    md += ["", "## 2. Reference from CREPE vs from the same tracker family as the live one", "",
           "| Live tracker / reference | " + " | ".join(takes) + " |", "|---|" + "---|" * len(takes)]
    for clarity in (0.6, 0.7, 0.8):
        live = {k: mpm_track(a, SR, clarity) for k, a in takes.items()}
        for name, ref in ((f"MPM {clarity} vs CREPE reference", crepe_ref),
                          (f"MPM {clarity} vs MPM {clarity} reference", mpm_track(y, SR, clarity))):
            md.append(f"| {name} | " + " | ".join(f"{score(live[k], ref):.1f}" for k in takes) + " |")

    md += ["", "## 3. Cleaning the live track (MPM clarity 0.7, CREPE reference)", "",
           "| Cleanup | Near-perfect (30 dB) | Near-perfect (20 dB) | Detuned 200 cents | Late 0.3 s |", "|---|---|---|---|---|"]
    keys = ["near-perfect (30 dB noise)", "near-perfect (20 dB noise)", "detuned 200 cents", "late 0.3 s"]
    live = {k: mpm_track(takes[k], SR, 0.7) for k in keys}
    for name, fn in (("none", lambda t: t), ("fill gaps <= 0.1 s", lambda t: fill_gaps(t, 0.1)),
                     ("fill gaps <= 0.2 s", lambda t: fill_gaps(t, 0.2)), ("octave correction", fix_octaves),
                     ("octave + gaps 0.1 s", lambda t: fill_gaps(fix_octaves(t), 0.1))):
        md.append(f"| {name} | " + " | ".join(f"{score(fn(live[k]), crepe_ref):.1f}" for k in keys) + " |")
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"real_tracker_{args.label}.md"
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print("wrote", out)


if __name__ == "__main__":
    main()
