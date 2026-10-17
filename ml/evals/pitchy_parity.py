"""Does our Python MPM emulation match the REAL Pitchy? (Node, same audio, same settings.)

Run from the repo root (needs Node + PITCHY_PATH or `npm i pitchy`; see pitchy_node.py):
  PITCHY_PATH=/path/to/pitchy.mjs python -m ml.evals.pitchy_parity ml/data/apr_demos

Every tracker number in the evals comes from ml/evals/mpm.py, an emulation of the algorithm
the browser runs. This checks it against pitchy itself on each `<clip>/vocals.mp3` +
`<clip>/song.json` under the folder, and reports voicing agreement, pitch agreement, and the
perfect-take score (the clip's own vocal scored against its manifest) under both trackers.
Writes ml/evals/results/pitchy_parity.md (aggregated numbers only).
"""
import argparse
import json
from pathlib import Path

import librosa
import numpy as np

from ml.evals.mpm import mpm_track
from ml.evals.pitchy_node import pitchy_track
from ml.scoring.pitch import to_track
from ml.scoring.score import score_turn

RESULTS = Path(__file__).parent / "results"
CONFIGS = [  # (label, sample_rate, window, clarity, gate)
    ("live demo setting: 48 kHz, 4096, clarity 0.8, gate 0.008", 48_000, 4096, 0.8, 0.008),
    ("48 kHz, 4096, clarity 0.65, gate 0.005", 48_000, 4096, 0.65, 0.005),
    ("16 kHz, 2048, clarity 0.8, gate 0.001", 16_000, 2048, 0.8, 0.001),
]


def browser_smooth(track: np.ndarray) -> np.ndarray:
    """Python twin of smoothFrame() in web/src/audio/pitchTracker.ts: octave-glitch fix, then a 5-frame
    median over voiced frames; unvoiced stays unvoiced. Keep the two in step."""
    n, out = len(track), np.full(len(track), np.nan)
    fixed = track.copy()
    for j in range(1, n - 1):
        v, a, b = track[j], track[j - 1], track[j + 1]
        if np.isfinite([v, a, b]).all() and abs(1200 * np.log2(a / b)) < 100 and all(
                abs(abs(1200 * np.log2(v / x)) - 1200) < 150 for x in (a, b)):
            fixed[j] = np.sqrt(a * b)
    for i in np.flatnonzero(np.isfinite(track)):
        w = fixed[max(0, i - 2): i + 3]
        w = np.sort(w[np.isfinite(w)])
        out[i] = w[len(w) // 2] if len(w) % 2 else np.sqrt(w[len(w) // 2 - 1] * w[len(w) // 2])
    return out


def agreement(a: np.ndarray, b: np.ndarray) -> dict:
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    va, vb = np.isfinite(a), np.isfinite(b)
    both = va & vb
    cents = 1200 * np.log2(a[both] / b[both])
    return {"voiced_real": float(va.mean()), "voiced_emulated": float(vb.mean()),
            "voicing_agreement": float(both.sum() / max(1, (va | vb).sum())),
            "within_semitone": float((np.abs(cents) <= 100).mean()) if len(cents) else 0.0}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", help="folder of clip subfolders, each with vocals.mp3 and song.json")
    args = ap.parse_args()
    clips = sorted(p.parent for p in Path(args.folder).glob("*/song.json") if (p.parent / "vocals.mp3").exists())
    md = ["# Emulation vs the real Pitchy", "",
          "Same audio, same settings: `ml/evals/mpm.py` (our emulation) vs pitchy@4.1.0 run in Node "
          "(`ml/evals/node/pitchy_track.mjs`). 'Perfect take' = the clip's own vocal scored against its manifest "
          "reference (CREPE-made), so it measures tracker disagreement, not singing.", "",
          "| Clip | Setting | Voiced (real / emulated) | Voicing agreement | Pitch within 1 semitone | Perfect take: real / emulated | Real, browser-smoothed |",
          "|---|---|---|---|---|---|---|"]
    for k, clip in enumerate(clips, 1):
        m = json.loads((clip / "song.json").read_text(encoding="utf-8"))
        ref = to_track(m["reference"]["hz"])
        phrases = [(p["id"], p["start"], p["end"]) for p in m["phrases"]]
        onsets = [n["start"] for n in m["reference"].get("notes", [])] or None
        y, sr = librosa.load(clip / "vocals.mp3", sr=48_000, mono=True)
        for label, rate, window, clarity, gate in CONFIGS:
            real = pitchy_track(y, sr, sample_rate=rate, window=window, clarity=clarity, gate=gate)
            emu = mpm_track(y, sr, clarity_threshold=clarity, frame_length=window,
                            silence_gate_rms=gate, analysis_sr=rate)
            a = agreement(real, emu)
            s_real = score_turn(real, ref, phrases, ref_onsets=onsets)["total"]
            s_emu = score_turn(emu, ref, phrases, ref_onsets=onsets)["total"]
            s_smooth = score_turn(browser_smooth(real), ref, phrases, ref_onsets=onsets)["total"]
            row = (f"| Clip {k} | {label} | {a['voiced_real']:.0%} / {a['voiced_emulated']:.0%} | "
                   f"{a['voicing_agreement']:.0%} | {a['within_semitone']:.0%} | {s_real:.1f} / {s_emu:.1f} | {s_smooth:.1f} |")
            md.append(row)
            print(row, flush=True)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "pitchy_parity.md").write_text("\n".join(md) + "\n")
    print("wrote", RESULTS / "pitchy_parity.md")


if __name__ == "__main__":
    main()
