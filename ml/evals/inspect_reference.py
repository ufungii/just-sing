"""Sanity-check a prepared song manifest (song.json) before it is used for scoring.

Run from the repo root:
  python -m ml.evals.inspect_reference path/to/song.json [--plot contour.png]

ML A can run this before handing a manifest over; ML B uses it to see whether a
real reference is trustworthy. It checks structure (FAIL), then looks for things
that quietly hurt scoring (WARN): suspected octave jumps in the contour, too much
excluded audio, notes too short for the timing detector, phrases with nothing to
grade. It cannot tell whether the contour is the RIGHT singer's melody; that still
needs listening. Exit code is 1 if any FAIL.
"""
import argparse
import json
import sys
from dataclasses import dataclass

import numpy as np

from ml.scoring.pitch import FMAX_HZ, FMIN_HZ, scoreable_mask, to_track
from ml.scoring.timing import onset_times
from ml.scoring.config import TimingConfig

OCTAVE_SUSPECT_CENTS = 1000      # one-frame jump this large is almost never singing
MAX_EXCLUDED_SHARE = 1 / 3       # rule of thumb, not a measured threshold
MIN_PHRASE_SCOREABLE_S = 0.2
NOTE_MATCH_WINDOW_S = 0.1
_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass(frozen=True)
class Finding:
    level: str  # FAIL | WARN | INFO
    message: str


def _midi(hz: float) -> float:
    return 69.0 + 12.0 * np.log2(hz / 440.0)


def _name(midi: float) -> str:
    m = int(round(midi))
    return f"{_NAMES[m % 12]}{m // 12 - 1}"


def _span_ok(start, end, duration) -> bool:
    return (isinstance(start, (int, float)) and isinstance(end, (int, float))
            and 0 <= start < end <= duration + 1e-6)


def inspect_manifest(m: dict) -> tuple[list[Finding], dict]:
    """Return (findings, stats). Never raises on a malformed manifest; reports FAIL instead."""
    f: list[Finding] = []
    stats: dict = {}

    def add(level, msg):
        f.append(Finding(level, msg))

    ref = m.get("reference") or {}
    if "hz" not in ref or "hop_seconds" not in ref or "duration" not in m:
        add("FAIL", "manifest needs `duration`, `reference.hop_seconds`, and `reference.hz`")
        return f, stats

    hop, duration = float(ref["hop_seconds"]), float(m["duration"])
    hz = to_track(ref["hz"])
    n = len(hz)
    voiced = np.isfinite(hz)
    stats.update(frames=n, hop_seconds=hop, duration=duration)

    # ---- structure -------------------------------------------------------- #
    if abs(n * hop - duration) > 0.1:
        add("FAIL", f"contour covers {n * hop:.2f} s ({n} frames x {hop} s) but duration is {duration:.2f} s")
    if n == 0 or not voiced.any():
        add("FAIL", "reference contour has no voiced frames")
        return f, stats

    excluded, phrases = ref.get("excluded", []), m.get("phrases", [])
    ex_spans = []
    for e in excluded:
        if _span_ok(e.get("start"), e.get("end"), duration):
            ex_spans.append((e["start"], e["end"]))
        else:
            add("FAIL", f"excluded region out of range or malformed: {e}")
    if not phrases:
        add("FAIL", "no phrases: nothing can be rated")

    ids, prev_end, valid_phrases = set(), -1.0, []
    for p in sorted((p for p in phrases if isinstance(p, dict)), key=lambda p: p.get("start", 0)):
        if not _span_ok(p.get("start"), p.get("end"), duration):
            add("FAIL", f"phrase {p.get('id')} out of range or malformed: {p}")
            continue
        if p.get("id") in ids:
            add("FAIL", f"duplicate phrase id {p.get('id')!r}")
        ids.add(p.get("id"))
        if p["start"] < prev_end - 1e-6:
            add("FAIL", f"phrase {p['id']} overlaps the previous phrase")
        prev_end = p["end"]
        valid_phrases.append(p)

    for i, line in enumerate(m.get("lines", [])):
        if not _span_ok(line.get("start"), line.get("end"), duration):
            add("WARN", f"line {i} timing out of range or malformed")

    # ---- contour quality -------------------------------------------------- #
    out_of_range = int(((hz[voiced] < FMIN_HZ) | (hz[voiced] > FMAX_HZ)).sum())
    if out_of_range:
        add("WARN", f"{out_of_range} voiced frames outside {FMIN_HZ:.0f}-{FMAX_HZ:.0f} Hz (tracker glitches?)")

    share = float(voiced.mean())
    stats["voiced_share"] = share
    add("INFO", f"voiced share {share:.0%} of the clip")
    if share < 0.2:
        add("WARN", "mostly unvoiced: is this the vocal stem, and is the tracker threshold too strict?")

    midi = _midi(hz[voiced])
    lo, hi = np.percentile(midi, [5, 95])
    stats["span_semitones"] = float(hi - lo)
    add("INFO", f"pitch range (5th-95th pct) {_name(lo)} to {_name(hi)}, {hi - lo:.1f} semitones")
    if hi - lo > 24:
        add("WARN", "range over two octaves: one register choice cannot fit it, and it may hide octave errors")

    jump_t = []
    for i in np.flatnonzero(voiced[1:] & voiced[:-1]) + 1:
        if abs(1200 * np.log2(hz[i] / hz[i - 1])) >= OCTAVE_SUSPECT_CENTS and not any(
                lo_ <= i * hop < hi_ for lo_, hi_ in ex_spans):
            jump_t.append(i * hop)
    stats["octave_suspects"] = len(jump_t)
    if jump_t:
        shown = ", ".join(f"{t:.2f}s" for t in jump_t[:8])
        add("WARN", f"{len(jump_t)} suspected octave/tracker jumps (>= {OCTAVE_SUSPECT_CENTS} cents in one frame) "
                    f"at {shown}{' ...' if len(jump_t) > 8 else ''}: listen there, then fix or exclude")

    # ---- exclusions and phrases ------------------------------------------- #
    mask = scoreable_mask(hz, hop, ex_spans)
    ex_share = 1 - mask.sum() / voiced.sum()
    stats["excluded_share_of_voiced"] = float(ex_share)
    add("INFO", f"{mask.sum() * hop:.1f} s of the reference is scoreable; {ex_share:.0%} of voiced audio excluded")
    if mask.sum() == 0:
        add("FAIL", "everything is excluded or unvoiced: nothing is scoreable")
    elif ex_share > MAX_EXCLUDED_SHARE:
        add("WARN", f"more than a third of the voiced audio is excluded; consider a cleaner clip")

    for p in valid_phrases:
        s = int(mask[int(round(p["start"] / hop)):int(round(p["end"] / hop))].sum()) * hop
        if s == 0:
            add("WARN", f"phrase {p['id']} has nothing scoreable (all rest or excluded): it can never earn a rating")
        elif s < MIN_PHRASE_SCOREABLE_S:
            add("WARN", f"phrase {p['id']} has only {s:.2f} s scoreable")
    covered = sum(
        int(mask[int(round(p["start"] / hop)):int(round(p["end"] / hop))].sum()) for p in valid_phrases)
    if mask.sum() and covered < 0.9 * mask.sum():
        add("WARN", f"phrases cover only {covered / mask.sum():.0%} of the scoreable audio; the rest earns no points")

    # ---- note starts (timing) --------------------------------------------- #
    cfg = TimingConfig()
    ons = onset_times(hz, hop, cfg)
    stats["detected_onsets"] = len(ons)
    gaps = np.diff(ons)
    add("INFO", f"timing detector finds {len(ons)} note starts"
                + (f"; shortest gap {gaps.min():.2f} s" if len(gaps) else ""))

    notes = ref.get("notes", [])
    if notes:
        need = cfg.stable_frames * hop
        short = [nt for nt in notes if nt["end"] - nt["start"] < need]
        if short:
            add("WARN", f"{len(short)} notes shorter than {need:.2f} s: the timing detector cannot see them")
        starts = [nt["start"] for nt in notes]
        hit = [bool(len(ons)) and np.abs(ons - s).min() <= NOTE_MATCH_WINDOW_S for s in starts]
        stats["notes_with_detected_onset"] = sum(hit) / len(notes)
        add("INFO", f"{sum(hit)}/{len(notes)} listed notes have a detected note start within {NOTE_MATCH_WINDOW_S:.1f} s")
        if sum(hit) / len(notes) < 0.8:
            miss = ", ".join(f"{s:.2f}s" for s, h in zip(starts, hit) if not h)[:120]
            add("WARN", f"timing will not match many listed notes (e.g. {miss}): notes are legato/repeated "
                        "or the contour disagrees with them")
        bad = 0
        for nt in notes:
            seg = hz[int(round(nt["start"] / hop)):int(round(nt["end"] / hop))]
            seg = seg[np.isfinite(seg)]
            if len(seg) >= 3 and "hz" in nt and abs(1200 * np.log2(np.median(seg) / nt["hz"])) > 100:
                bad += 1
        if bad:
            add("WARN", f"{bad} listed notes differ from the contour by over 100 cents")
    else:
        add("INFO", "no reference.notes; the scorer will derive note starts from the contour")
    return f, stats


def plot(m: dict, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ref = m["reference"]
    hop, hz = ref["hop_seconds"], to_track(ref["hz"])
    t = np.arange(len(hz)) * hop
    fig, ax = plt.subplots(figsize=(12, 4))
    for p in m.get("phrases", []):
        ax.axvspan(p["start"], p["end"], color="#4c78a8", alpha=0.10)
        ax.text(p["start"], 0.98, str(p.get("id", "")), transform=ax.get_xaxis_transform(), va="top", fontsize=8)
    for e in ref.get("excluded", []):
        ax.axvspan(e["start"], e["end"], color="#e45756", alpha=0.30)
    ax.plot(t, np.where(np.isfinite(hz), _midi(np.where(np.isfinite(hz), hz, 440.0)), np.nan), ".", ms=2, color="k")
    for o in onset_times(hz, hop):
        ax.axvline(o, color="#54a24b", lw=0.6, alpha=0.7)
    ax.set_xlabel("seconds from clip start")
    ax.set_ylabel("MIDI note (60 = middle C)")
    ax.set_title(f"{m.get('title', 'reference')}: blue = phrases, red = excluded, green = detected note starts")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("manifest")
    parser.add_argument("--plot", help="write a contour PNG here (needs matplotlib)")
    args = parser.parse_args()

    manifest = json.load(open(args.manifest, encoding="utf-8"))
    findings, _ = inspect_manifest(manifest)
    for level in ("FAIL", "WARN", "INFO"):
        for item in (x for x in findings if x.level == level):
            print(f"[{level}] {item.message}")
    n_fail = sum(x.level == "FAIL" for x in findings)
    n_warn = sum(x.level == "WARN" for x in findings)
    print(f"\n{n_fail} failure(s), {n_warn} warning(s)")
    if args.plot:
        plot(manifest, args.plot)
        print("plot written to", args.plot)
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
