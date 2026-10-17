"""Score real player recordings against their songs: the first human-singing evidence.

Run from the repo root with the speech environment (needs CREPE, and Node + Pitchy for the
browser-tracker rows; see pitchy_node.py):
  ml/pronunciation/.venv/bin/python -m ml.evals.real_takes_eval "Label=take.wav=song.json" [...]

Each recording is first lined up with its song from the melody (align_take.py: offset + register,
with a confidence check), then scored on the overlapping part of the song with three pitch trackers:
CREPE (offline quality), the real Pitchy at the app's current settings, and the real Pitchy at the
proposed settings. A deliberately misaligned copy (7 s off) is scored as a sanity check: a real score
must drop when the singing no longer lines up. Caveat: aligning by melody also absorbs any consistent
lateness, so timing here is slightly generous (in the app the offset comes from the latency check).
Writes ml/evals/results/real_takes.md (numbers only; recordings stay local).
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import librosa

from ml.evals.align_take import align
from ml.evals.crop_manifest import crop_manifest
from ml.evals.pitchy_node import pitchy_track
from ml.scoring.pitch import pitch_contour, to_track
from ml.scoring.score import score_turn

SR = 16_000
RESULTS = Path(__file__).parent / "results"
TRACKERS = {
    "CREPE": lambda y: pitch_contour(y, SR, backend="crepe"),
    "Pitchy, app today (clarity 0.85, RMS 0.01)": lambda y: pitchy_track(y, SR, sample_rate=48_000, window=2048, clarity=0.85, gate=0.01),
    "Pitchy, proposed (clarity 0.65, RMS 0.005)": lambda y: pitchy_track(y, SR, sample_rate=48_000, window=2048, clarity=0.65, gate=0.005),
}


def run_one(label: str, take: str, manifest: str) -> list[str]:
    m = json.load(open(manifest, encoding="utf-8"))
    y, _ = librosa.load(take, sr=SR, mono=True)
    a = align(pitch_contour(y, SR, backend="crepe"), to_track(m["reference"]["hz"]), m["reference"]["hop_seconds"])
    conf = "confident" if a["agreement"] >= 0.3 and a["margin"] >= 0.1 else ("weak" if a["margin"] >= 0.05 else "ambiguous")
    lead = a["lead_in_s"]
    s0, s1 = max(0.0, -lead), min(m["duration"], len(y) / SR - lead)
    clip, _ = crop_manifest(m, round(s0, 2), round(s1, 2))
    seg = y[int((s0 + lead) * SR):int((s1 + lead) * SR)]
    ref = to_track(clip["reference"]["hz"])
    phrases = [(p["id"], p["start"], p["end"]) for p in clip["phrases"]]
    onsets = [n["start"] for n in clip["reference"]["notes"]] or None
    rows = [f"### {label}", "",
            f"Lined up {conf}ly: register {a['register']:+d}, melody agreement {a['agreement']:.2f} "
            f"(next best offset {a['runner_up_agreement']:.2f}). Scored {s1 - s0:.0f} s of the song, {len(phrases)} phrases.", "",
            "| Tracker | Total | Pitch | Timing | Phrase ratings |", "|---|---|---|---|---|"]
    for name, track in TRACKERS.items():
        r = score_turn(track(seg), ref, phrases, ref_onsets=onsets, register=a["register"])
        ratings = ", ".join(f"{k} {v}" for k, v in Counter(p["rating"] for p in r["phrases"]).most_common())
        rows.append(f"| {name} | {r['total']:.1f} | {r['pitch']:.1f} | {r['timing']:.1f} | {ratings} |")
    bad = y[int((s0 + lead + 7) * SR):int((s1 + lead + 7) * SR)]
    rb = score_turn(TRACKERS["CREPE"](bad), ref, phrases, ref_onsets=onsets, register=a["register"])
    rows += ["", f"Sanity check: the same take misaligned by 7 s scores **{rb['total']:.1f}** (CREPE).", ""]
    print("\n".join(rows), flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("takes", nargs="+", help='"Label=path/to/take.wav=path/to/song.json"')
    args = ap.parse_args()
    md = ["# Real player takes", "",
          "Amateur recordings of people singing along, lined up with each song by melody and scored with the "
          "reference engine (scoring version 0.2.0). References are unreviewed pipeline drafts. Few takes: these are "
          "first observations for calibration, not validation.", ""]
    for spec in args.takes:
        label, take, manifest = spec.split("=")
        md += run_one(label, take, manifest)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "real_takes.md").write_text("\n".join(md) + "\n")
    print("wrote", RESULTS / "real_takes.md")


if __name__ == "__main__":
    main()
