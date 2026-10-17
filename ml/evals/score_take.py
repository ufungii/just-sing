"""Score a recorded take against a clip manifest. One command, per-phrase breakdown.

Run from the repo root:
  python -m ml.evals.score_take take.wav clip.json
  ml/pronunciation/.venv/bin/python -m ml.evals.score_take take.wav clip.json --tracker crepe
  python -m ml.evals.score_take take.wav clip.json --ref-audio vocals.clip.mp3   # reference from the SAME tracker

The take can be any audio file (wav, mp3, ...): a real recording, or a test clip.
The tracker defaults to MPM, our emulation of the browser's Pitchy, because that
is what the live game uses. By default the reference is the manifest's own
`reference.hz`; --ref-audio re-extracts it from the clip's vocal audio with the
SAME tracker, which is how to test the "same tracker for reference and player"
option (see ml/README.md). Prints voiced shares so a silent or mis-leveled take is
obvious instead of looking like bad singing.
"""
import argparse
import json
import sys

import librosa
import numpy as np

from ml.evals.mpm import mpm_track
from ml.scoring.config import PitchConfig
from ml.scoring.pitch import HOP_SECONDS, pitch_contour, scoreable_mask, to_track
from ml.scoring.score import phrase_weights, score_turn
from ml.scoring.timing import onset_times
from ml.scoring.words import WORD_FEEDBACK_VERSION, word_feedback

SR = 16_000


def track_audio(y: np.ndarray, tracker: str, clarity: float, window: int = 2048, gate: float = 1e-3) -> np.ndarray:
    if tracker == "mpm":
        return mpm_track(y, SR, clarity_threshold=clarity, frame_length=window, silence_gate_rms=gate)
    return pitch_contour(y, SR, backend=tracker)


def score_take(take, manifest: dict, *, tracker="mpm", clarity=0.65, register=0, latency_s=0.0,
               tolerance_s=0.0, ref_audio=None, take_start=0.0, take_end=None, window=2048, gate=1e-3) -> dict:
    """Returns score, diagnostics, and display-only word_feedback. `take` is a path or a float array at 16 kHz."""
    if isinstance(take, np.ndarray):
        y = take
    else:
        y, _ = librosa.load(take, sr=SR, mono=True, offset=take_start,
                            duration=None if take_end is None else take_end - take_start)
    ref_info = manifest["reference"]
    hop = ref_info["hop_seconds"]
    if ref_audio is not None:
        ry, _ = librosa.load(ref_audio, sr=SR, mono=True)
        ref = track_audio(ry, tracker, clarity, window, gate)
        source = f"re-extracted with {tracker}"
    else:
        ref, source = to_track(ref_info["hz"]), "manifest reference.hz"
    user = track_audio(y, tracker, clarity, window, gate)

    phrases = [(p["id"], p["start"], p["end"]) for p in manifest["phrases"]]
    excluded = [(e["start"], e["end"]) for e in ref_info.get("excluded", [])]
    notes = ref_info.get("notes") or []
    # Note starts come from the manifest's notes, unless the reference was re-extracted: then they
    # must come from that same contour, or the two would disagree about where notes begin.
    onsets = [n["start"] for n in notes] if notes and ref_audio is None else None
    cfg = PitchConfig(time_tolerance_s=tolerance_s)
    result = score_turn(user, ref, phrases, hop_seconds=hop, ref_onsets=onsets, register=register,
                        excluded=excluded, latency_offset_s=latency_s, pitch_cfg=cfg)
    weights = phrase_weights(ref, phrases, hop_seconds=hop, excluded=excluded)
    scoreable = scoreable_mask(ref, hop, excluded)
    n = min(len(user), len(ref))
    diag = {
        "take_seconds": round(len(y) / SR, 2), "clip_seconds": manifest["duration"], "reference": source,
        "tracker": tracker if tracker != "mpm" else f"mpm (clarity {clarity})",
        "take_voiced_share": float(np.isfinite(user).mean()),
        "reference_voiced_share": float(np.isfinite(ref).mean()),
        "take_voiced_where_reference_scoreable": float(np.isfinite(user[:n])[scoreable[:n]].mean()) if scoreable[:n].any() else 0.0,
        "phrase_seconds": [round(w * hop, 2) for w in weights],
        "median_note_offset_s": None,
    }
    deltas = []
    ref_on = np.array(onsets if onsets is not None else onset_times(ref, hop))
    user_on = onset_times(user, hop) - latency_s
    for r in ref_on:
        if len(user_on) and np.abs(user_on - r).min() <= 0.5:
            deltas.append(float(user_on[np.abs(user_on - r).argmin()] - r))
    if deltas:
        diag["median_note_offset_s"] = round(float(np.median(deltas)), 3)
    return {"score": result, "diagnostics": diag,
            "word_feedback_version": WORD_FEEDBACK_VERSION,
            "word_feedback": word_feedback(user, ref, manifest.get("lines", []),
                                           hop_seconds=hop, register=register,
                                           excluded=excluded, latency_offset_s=latency_s,
                                           pitch_cfg=cfg)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("take")
    ap.add_argument("manifest")
    ap.add_argument("--tracker", default="mpm", choices=["mpm", "crepe", "pyin"])
    ap.add_argument("--clarity", type=float, default=0.65, help="MPM clarity threshold (0.6-0.7 on real voices)")
    ap.add_argument("--window", type=int, default=2048, help="MPM window in samples (the live demo uses 4096)")
    ap.add_argument("--gate", type=float, default=1e-3, help="silence gate, window RMS (the live demo uses 0.008)")
    ap.add_argument("--register", type=int, default=0, choices=[-12, 0, 12])
    ap.add_argument("--latency", type=float, default=0.0, help="device latency in seconds, calibrated once")
    ap.add_argument("--tolerance", type=float, default=0.0, help="pitch time tolerance in seconds (0 = strict)")
    ap.add_argument("--ref-audio", help="clip vocals audio: re-extract the reference with the same tracker")
    ap.add_argument("--take-start", type=float, default=0.0, help="read the take from this second of the file")
    ap.add_argument("--take-end", type=float, default=None)
    args = ap.parse_args()
    manifest = json.load(open(args.manifest, encoding="utf-8"))
    out = score_take(args.take, manifest, tracker=args.tracker, clarity=args.clarity, register=args.register,
                     latency_s=args.latency, tolerance_s=args.tolerance, ref_audio=args.ref_audio,
                     take_start=args.take_start, take_end=args.take_end, window=args.window, gate=args.gate)
    d, s = out["diagnostics"], out["score"]
    print(f"take {d['take_seconds']} s vs clip {d['clip_seconds']} s | tracker {d['tracker']} | reference: {d['reference']}")
    print(f"voiced: take {d['take_voiced_share']:.0%}, reference {d['reference_voiced_share']:.0%}; "
          f"take voiced where the reference is scoreable: {d['take_voiced_where_reference_scoreable']:.0%}")
    if d["take_voiced_where_reference_scoreable"] < 0.25:
        print("WARNING: almost nothing detected where you should be singing. Check the mic, the level, or the take offset "
              "before reading the score as bad singing.")
    if d["median_note_offset_s"] is not None:
        print(f"typical note start: {d['median_note_offset_s']:+.2f} s ({'late' if d['median_note_offset_s'] > 0 else 'early'}; "
              "consider --latency if the whole take is shifted)")
    print(f"\n{'phrase':8s}{'singing s':>10s}{'pitch':>8s}{'timing':>8s}{'score':>8s}  rating")
    for p, secs in zip(s["phrases"], d["phrase_seconds"]):
        t = "-" if p["timing"] is None else f"{p['timing']:.0f}"
        print(f"{p['phrase_id']:8s}{secs:10.1f}{p['pitch']:8.0f}{t:>8s}{p['score']:8.0f}  {p['rating']}")
    print(f"\nTOTAL {s['total']:.1f}   (pitch {s['pitch']:.1f}, timing {s['timing']:.1f}, register {s['register']})")
    print("\nWORD ACTIVITY (detected singing, not word recognition; provisional):")
    for line in out["word_feedback"]:
        for word in line:
            suffix = " / late detected start" if word["late"] else ""
            coverage = "-" if word["coverage"] is None else f"{word['coverage']:.0%}"
            print(f"  {word['text']}: {word['status']} / coverage {coverage}{suffix}")
    sys.exit(0)


if __name__ == "__main__":
    main()
