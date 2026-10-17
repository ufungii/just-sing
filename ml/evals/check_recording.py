"""Is this recording usable for calibrating the scorers? Plain-language verdict in a few seconds.

Run from the repo root:  python -m ml.evals.check_recording take.m4a [more files...]

Checks level, clipping, background noise, how much of the file is actually voice, and (with --pitch)
whether a pitch tracker can follow it. A noisy room is fine for testing robustness; what ruins a
recording is: too quiet, clipped (distorted), music or a backing track leaking into the mic, or almost
no voice. The thresholds are practical rules of thumb, not measured limits.
"""
import argparse
import sys

import librosa
import numpy as np

SR = 16_000
FRAME, HOP = 400, 160  # 25 ms frames, 10 ms hop


def db(x: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.maximum(x, 1e-9))


def analyze(y: np.ndarray, with_pitch: bool = False) -> dict:
    frames = librosa.util.frame(np.pad(y, (FRAME // 2, FRAME // 2)), frame_length=FRAME, hop_length=HOP)
    rms_db = db(np.sqrt((frames ** 2).mean(axis=0)))
    floor, loud = float(np.percentile(rms_db, 10)), float(np.percentile(rms_db, 90))
    out = {
        "seconds": len(y) / SR,
        "peak_db": float(db(np.abs(y).max())),
        "clipped_share": float((np.abs(y) >= 0.99).mean()),
        "noise_floor_db": floor, "voice_level_db": loud, "snr_db": loud - floor,
        "active_share": float((rms_db > floor + 10).mean()),
        "voiced_pitch_share": None,
    }
    if with_pitch:
        f0, voiced, _ = librosa.pyin(y, fmin=65, fmax=1000, sr=SR, frame_length=2048, hop_length=320)
        out["voiced_pitch_share"] = float(np.mean(voiced))
    return out


def verdict(a: dict) -> tuple[str, list[str]]:
    problems, notes = [], []
    if a["seconds"] < 2: problems.append("under 2 seconds long")
    if a["peak_db"] < -30: problems.append(f"far too quiet (peak {a['peak_db']:.0f} dBFS): move closer to the mic or raise the input level")
    if a["clipped_share"] > 0.01: problems.append(f"clipped/distorted ({a['clipped_share']:.1%} of samples at full scale): lower the input level or sing further from the mic")
    if a["snr_db"] < 12: problems.append(f"very noisy: voice is only {a['snr_db']:.0f} dB above the background (aim for 20+)")
    if a["active_share"] < 0.10: problems.append("almost no voice found in the file")
    if a["peak_db"] > -3 and not problems: notes.append("peak is close to full scale; a little lower would be safer")
    if 12 <= a["snr_db"] < 20: notes.append(f"noisy room ({a['snr_db']:.0f} dB): usable as a robustness test, not for tuning small thresholds")
    if a["active_share"] > 0.97 and a["seconds"] > 5: notes.append("voice-like sound all the time, with no pauses: if you used speakers, music may be leaking into the mic (use headphones)")
    if a["voiced_pitch_share"] is not None and a["voiced_pitch_share"] < 0.2 and not problems:
        notes.append("the pitch tracker finds very little pitch: fine for speech, a problem for a singing take")
    return ("RE-RECORD" if problems else "OK"), problems + notes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--pitch", action="store_true", help="also check that a pitch tracker can follow it (singing takes)")
    args = ap.parse_args()
    bad = 0
    for path in args.files:
        y, _ = librosa.load(path, sr=SR, mono=True)
        a = analyze(y, args.pitch)
        status, msgs = verdict(a)
        bad += status != "OK"
        print(f"{status:10s} {path}  ({a['seconds']:.1f} s, peak {a['peak_db']:.0f} dBFS, noise floor {a['noise_floor_db']:.0f} dBFS, "
              f"voice {a['snr_db']:.0f} dB above it, voice present {a['active_share']:.0%}"
              + (f", pitch found {a['voiced_pitch_share']:.0%}" if a["voiced_pitch_share"] is not None else "") + ")")
        for m in msgs:
            print("           -", m)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
