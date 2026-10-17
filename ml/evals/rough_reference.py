"""Turn a vocals stem into a rough manifest and a first real-reference score check.

Run from the repo root (CREPE needs the GPU env; --backend pyin works anywhere):
  ml/pronunciation/.venv/bin/python -m ml.evals.rough_reference path/to/vocals.wav --id russian-roulette

Meant for the moment ML A has a Demucs vocals stem but no finished song.json:
  1. extracts the reference pitch with the shared pitch_contour();
  2. proposes rough phrases from voiced stretches (no lyrics needed);
  3. writes ml/data/<id>/song.rough.json (gitignored) and a contour plot;
  4. runs the manifest inspector;
  5. checks the scorer on this REAL contour: self-score, deliberate lateness, and
     detuning of every other detected note, and reports whether scores fall in order.
The rough phrases are a stand-in: ML A's hand-checked phrases replace them.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from ml.evals.inspect_reference import inspect_manifest, plot
from ml.scoring.pitch import HOP_SECONDS, pitch_contour, track_to_json
from ml.scoring.score import score_turn
from ml.scoring.timing import onset_times

DATA = Path(__file__).resolve().parents[1] / "data"


def rough_phrases(hz: np.ndarray, hop: float, duration: float, min_gap_s: float = 0.35,
                  min_len_s: float = 0.3) -> list[tuple[str, float, float]]:
    """Voiced stretches separated by >= min_gap_s of silence become phrases,
    clamped to the audio duration (the contour can run one frame past it)."""
    voiced = np.isfinite(hz)
    gap = int(round(min_gap_s / hop))
    spans, start, last = [], None, None
    for i, v in enumerate(voiced):
        if v:
            if start is None:
                start = i
            elif i - last > gap:
                spans.append((start, last))
                start = i
            last = i
    if start is not None:
        spans.append((start, last))
    spans = [(a, b) for a, b in spans if (b - a + 1) * hop >= min_len_s]
    out, prev_end = [], 0.0
    for k, (a, b) in enumerate(spans):
        s = max(prev_end, a * hop - 0.05)
        e = min(duration, (b + 1) * hop + 0.10)
        out.append((f"p{k + 1}", round(s, 2), round(e, 2)))
        prev_end = e
    return out


def detune_alternate_notes(hz: np.ndarray, onsets: np.ndarray, hop: float, cents: float) -> np.ndarray:
    """Shift every other detected note (onset to next onset) by +cents: a local error."""
    out = hz.copy()
    bounds = [int(round(t / hop)) for t in onsets] + [len(hz)]
    for k in range(0, len(bounds) - 1, 2):
        out[bounds[k]:bounds[k + 1]] *= 2 ** (cents / 1200)
    return out


def late(hz: np.ndarray, seconds: float, hop: float) -> np.ndarray:
    return np.concatenate([np.full(int(round(seconds / hop)), np.nan), hz])


def main() -> None:
    import librosa

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("vocals")
    ap.add_argument("--id", required=True)
    ap.add_argument("--backend", default="crepe", choices=["crepe", "pyin"])
    ap.add_argument("--start", type=float, default=0.0, help="crop start in the stem, seconds")
    ap.add_argument("--end", type=float, default=None, help="crop end in the stem, seconds")
    ap.add_argument("--min-gap", type=float, default=0.35, help="silence (s) that splits phrases")
    args = ap.parse_args()

    y, sr = librosa.load(args.vocals, sr=None, mono=True, offset=args.start,
                         duration=None if args.end is None else args.end - args.start)
    duration = len(y) / sr
    print(f"loaded {args.vocals} [{args.start:.1f}s-{args.start + duration:.1f}s]: {duration:.2f} s at {sr} Hz; extracting pitch with {args.backend}...", flush=True)
    hz = pitch_contour(y, sr, backend=args.backend)
    phrases = rough_phrases(hz, HOP_SECONDS, duration, args.min_gap)

    manifest = {
        "id": args.id, "version": 0, "title": f"{args.id} (rough)", "language": "ko",
        "duration": round(duration, 3),
        "provenance": {"source_url": "", "crop_start": args.start,
                       "crop_end": args.start + duration},
        "audio": {"instrumental": "", "vocals": str(args.vocals)},
        "lines": [],
        "phrases": [{"id": p, "line_index": None, "start": s, "end": e} for p, s, e in phrases],
        "reference": {"hop_seconds": HOP_SECONDS, "hz": track_to_json(hz), "notes": [], "excluded": []},
    }
    out_dir = DATA / args.id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "song.rough.json").write_text(json.dumps(manifest, ensure_ascii=False))
    try:
        plot(manifest, str(out_dir / "contour.png"))
    except ImportError:
        print("(matplotlib not installed: skipping contour.png)")

    print("\n== inspector")
    findings, stats = inspect_manifest(manifest)
    for level in ("FAIL", "WARN", "INFO"):
        for f in findings:
            if f.level == level:
                print(f"[{level}] {f.message}")

    print(f"\n== scorer on the real contour ({len(phrases)} rough phrases)")
    ons = onset_times(hz, HOP_SECONDS)
    rows = [("self (should be 100)", hz)]
    rows += [(f"late {s} s", late(hz, s, HOP_SECONDS)) for s in (0.1, 0.2, 0.3)]
    rows += [(f"every other note +{c} cents", detune_alternate_notes(hz, ons, HOP_SECONDS, c)) for c in (50, 100, 200)]
    rows += [("silence", np.full_like(hz, np.nan))]
    lines = ["| Take | Total | Pitch | Timing |", "|---|---|---|---|"]
    for name, user in rows:
        r = score_turn(user, hz, phrases)
        print(f"  {name:28s} total={r['total']:5.1f}  pitch={r['pitch']:5.1f}  timing={r['timing']:5.1f}")
        lines.append(f"| {name} | {r['total']:.1f} | {r['pitch']:.1f} | {r['timing']:.1f} |")
    late_scores = [score_turn(late(hz, s, HOP_SECONDS), hz, phrases)["total"] for s in (0, 0.1, 0.2, 0.3)]
    det_scores = [score_turn(detune_alternate_notes(hz, ons, HOP_SECONDS, c), hz, phrases)["total"] for c in (0, 50, 100, 200)]
    ok = late_scores == sorted(late_scores, reverse=True) and det_scores == sorted(det_scores, reverse=True)
    print(f"\nscores fall in order with lateness and detuning: {'yes' if ok else 'NO, investigate'}")
    (out_dir / "rough_report.md").write_text(
        f"# {args.id}: rough reference check\n\nbackend {args.backend}, {duration:.1f} s, {len(phrases)} rough phrases, "
        f"{stats.get('detected_onsets', 0)} detected note starts, voiced {stats.get('voiced_share', 0):.0%}.\n\n"
        + "\n".join(lines) + "\n")
    print(f"wrote {out_dir}/song.rough.json, contour.png, rough_report.md (all gitignored)")


if __name__ == "__main__":
    main()
