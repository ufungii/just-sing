"""What does a pitch time tolerance change? Data for an open scoring decision.

Run from the repo root:  python -m ml.evals.tolerance_eval

With strict frame-by-frame pitch scoring (time_tolerance_s = 0), a singer who is
late on every note loses pitch credit AND timing credit, so lateness is counted
twice. A tolerance lets pitch match within +/- t seconds; lateness is then scored
by timing alone. This runs the same takes at several tolerances. Track-level
(no audio), deterministic. Writes ml/evals/results/tolerance.md.
"""
from dataclasses import replace
from pathlib import Path

import numpy as np

from ml.evals.synthetic import detune_random, drop_notes, example_melody, example_phrases, melody_track
from ml.scoring.config import PitchConfig
from ml.scoring.pitch import HOP_SECONDS
from ml.scoring.score import score_turn

NOTES = example_melody()
REF = melody_track(NOTES, HOP_SECONDS)


def late(track, s):
    return np.concatenate([np.full(int(round(s / HOP_SECONDS)), np.nan), track])


TAKES = {
    "perfect": REF,
    "late 0.05 s": late(REF, 0.05),
    "late 0.1 s": late(REF, 0.1),
    "late 0.2 s": late(REF, 0.2),
    "late 0.3 s": late(REF, 0.3),
    "detuned 100 cents": melody_track(detune_random(NOTES, 100, 0), HOP_SECONDS),
    "detuned 200 cents": melody_track(detune_random(NOTES, 200, 0), HOP_SECONDS),
    "half the notes skipped": melody_track(drop_notes(NOTES, 0.5, 0), HOP_SECONDS),
}


def main() -> None:
    tols = (0.0, 0.05, 0.1, 0.15)
    md = ["# Pitch time tolerance: what it changes", "",
          "Total score (pitch / timing in brackets) for the same takes at different `PitchConfig.time_tolerance_s`. "
          "0 is the current default. Track-level synthetic takes.", "",
          "| Take | " + " | ".join(f"tolerance {t} s" for t in tols) + " |",
          "|---|" + "---|" * len(tols)]
    for name, user in TAKES.items():
        cells = []
        for t in tols:
            r = score_turn(user, REF, example_phrases(), pitch_cfg=replace(PitchConfig(), time_tolerance_s=t))
            cells.append(f"{r['total']:.1f} ({r['pitch']:.0f} / {r['timing']:.0f})")
        md.append(f"| {name} | " + " | ".join(cells) + " |")
        print(name, cells)
    md += ["", "Reading: a tolerance should raise late takes' **pitch** (lateness then shows only in timing) "
           "while leaving detuned and skipped takes about where they were. If it also lifts wrong notes, it is too wide."]
    out = Path(__file__).parent / "results" / "tolerance.md"
    out.write_text("\n".join(md) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
