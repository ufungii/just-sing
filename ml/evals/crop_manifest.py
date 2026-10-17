"""Crop a full-song manifest to a short clip, re-based to start at 0.

Run from the repo root:
  python -m ml.evals.crop_manifest song.json --start 45 --end 75 --out clip.json [--id my-clip]

The app plays ~30 s clips, but the pipeline can produce a whole-song manifest.
This keeps only lines fully inside the window (a half-cut lyric line makes a bad
phrase), re-bases every time to the clip start, slices the reference contour,
clips excluded regions, and records the source crop in `provenance` so the clip
can be traced back. It prints the ffmpeg commands to cut the audio from the same
timeline; vocals and instrumental must be cut with identical times.
"""
import argparse
import copy
import json

EPS = 1e-6


def crop_manifest(m: dict, start: float, end: float, new_id: str | None = None) -> tuple[dict, dict]:
    ref = m["reference"]
    hop = ref["hop_seconds"]
    i0, i1 = int(round(start / hop)), int(round(end / hop))
    out = copy.deepcopy(m)

    keep = [i for i, l in enumerate(m["lines"]) if l["start"] >= start - EPS and l["end"] <= end + EPS]
    remap = {old: new for new, old in enumerate(keep)}
    shift = lambda t: round(t - start, 3)

    out["lines"] = [
        {**m["lines"][i], "start": shift(m["lines"][i]["start"]), "end": shift(m["lines"][i]["end"]),
         "words": [{**w, "start": shift(w["start"]), "end": shift(w["end"])} for w in m["lines"][i].get("words", [])]}
        for i in keep]

    phrases, clamped = [], 0
    for p in m["phrases"]:
        if p.get("line_index") in remap and p["end"] > start and p["start"] < end:
            s, e = max(p["start"], start), min(p["end"], end)
            clamped += (s != p["start"]) or (e != p["end"])
            phrases.append({**p, "line_index": remap[p["line_index"]], "start": shift(s), "end": shift(e)})
    out["phrases"] = [{**p, "id": f"p{k + 1}"} for k, p in enumerate(phrases)]  # contiguous ids

    out["reference"] = {
        **ref, "hz": ref["hz"][i0:i1],
        "notes": [{**n, "start": shift(n["start"]), "end": shift(n["end"])} for n in ref.get("notes", [])
                  if n["start"] >= start - EPS and n["end"] <= end + EPS],
        "excluded": [{**e, "start": shift(max(e["start"], start)), "end": shift(min(e["end"], end))}
                     for e in ref.get("excluded", []) if e["end"] > start and e["start"] < end],
    }
    old_crop = (m.get("provenance") or {}).get("crop_start", 0) or 0
    out["provenance"] = {**(m.get("provenance") or {}), "crop_start": round(old_crop + start, 3),
                         "crop_end": round(old_crop + end, 3)}
    out["duration"] = round((i1 - i0) * hop, 3)
    if new_id:
        out["id"] = new_id
    report = {"lines_kept": len(keep), "lines_dropped": len(m["lines"]) - len(keep),
              "phrases_kept": len(out["phrases"]), "phrases_clamped": clamped}
    return out, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("manifest")
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--id")
    args = ap.parse_args()
    manifest = json.load(open(args.manifest, encoding="utf-8"))
    clip, report = crop_manifest(manifest, args.start, args.end, args.id)
    json.dump(clip, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"wrote {args.out}: {clip['duration']:.1f} s, {report}")
    d = args.end - args.start
    for stem in ("vocals", "instrumental"):
        print(f"ffmpeg -ss {args.start} -t {d} -i {stem}.mp3 -c:a libmp3lame -b:a 192k {stem}.clip.mp3")


if __name__ == "__main__":
    main()
