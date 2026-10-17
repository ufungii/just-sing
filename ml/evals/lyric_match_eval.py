"""Evaluate the SHIPPED lyric-match scorer (ml/pronunciation/lyric_match.py) on a real take, with controls
built from the same take (no re-recording):
  take          the player's recording at the offset found by melody alignment (align_take.py)
  original      the original vocal stem scored against itself (upper bound / sanity)
  aah           the player's own pitch and loudness resynthesised as a wordless "aah" (same tune, no words)
  misaligned    the real take read 6 s off (right voice and tune style, wrong lines)
  quiet         low-level noise the length of the take
A useful scorer gives many matches on take/original and few on aah/misaligned/quiet.

  ml/pronunciation/.venv/bin/python -m ml.evals.lyric_match_eval take.wav ml/data/<song>/song.json ml/data/<song>/vocals.mp3 --label <name>
Writes ml/evals/results/lyric_match_<label>.md (numbers only, no lyrics).
"""
import argparse
import json
import time
from pathlib import Path

import librosa
import numpy as np

from ml.evals.align_take import align
from ml.pronunciation.lyric_match import SR, hum, lyric_match, reference_fingerprints
from ml.scoring.pitch import pitch_contour, to_track

RESULTS = Path(__file__).parent / "results"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("take"); ap.add_argument("manifest"); ap.add_argument("vocals")
    ap.add_argument("--label", default="take")
    args = ap.parse_args()
    m = json.load(open(args.manifest, encoding="utf-8"))
    vocals, _ = librosa.load(args.vocals, sr=SR, mono=True)
    take, _ = librosa.load(args.take, sr=SR, mono=True)

    t0 = time.perf_counter()
    fp = reference_fingerprints(vocals, SR, m)
    t_fp = time.perf_counter() - t0
    take_hz = pitch_contour(take, SR, backend="crepe")
    a = align(take_hz, to_track(m["reference"]["hz"]), m["reference"]["hop_seconds"])
    lead = a["lead_in_s"]
    rms = librosa.feature.rms(y=take, frame_length=640, hop_length=320)[0]
    conditions = {
        "take": (take, lead),
        "original": (vocals, 0.0),
        "aah": (hum(take_hz, rms, len(take)), lead),
        "misaligned": (take, lead + 6.0),
        "quiet": (0.002 * np.random.default_rng(0).standard_normal(len(take)).astype(np.float32), lead),
    }
    rows, timing = [], {}
    for name, (y, off) in conditions.items():
        t0 = time.perf_counter()
        r = lyric_match(y, SR, fp, offset_s=off)
        timing[name] = time.perf_counter() - t0
        s = r["summary"]
        gains = [x["gain"] for x in r["lines"] if x["gain"] is not None]
        rows.append(f"| {name} | {s['graded']} | {s['match']} | {s['match'] / max(1, s['graded']):.0%} | "
                    f"{f'{np.median(gains):+.3f}' if gains else 'n/a'} | {s['not_sung']} | {s['not_covered']} |")
        print(rows[-1], flush=True)
    text = "\n".join([
        f"# Lyric match (shipped scorer): {args.label}", "",
        f"Lines fingerprinted: {len(fp['lines'])} (lines >= 0.8 s with text). Take offset from melody alignment: "
        f"{lead:.2f} s, register {a['register']:+d}, margin {a['margin']:.2f}.", "",
        "| condition | graded | match | match rate | median gain over own hum | not sung | not covered |",
        "|---|---|---|---|---|---|---|", *rows, "",
        f"Time: fingerprints {t_fp:.1f} s for {len(vocals) / SR:.0f} s of vocals; scoring the take {timing['take']:.1f} s "
        f"for {len(take) / SR:.0f} s of audio (device as run; the first call includes model loading).", "",
        "gain = how much closer (cosine distance) the line is to the original than a wordless hum of the same melody; "
        "'match' means gain >= 0.06 and closer than >= 80% of the song's other lines. The 0.06 margin was picked on "
        "these takes, so this table is not an independent test of it. Controls are built from the same take, so they are cleaner than real "
        "mistakes; this is evidence, not validation.",
    ])
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"lyric_match_{args.label}.md"
    out.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
