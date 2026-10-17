"""Assemble contract-shaped local song manifests from cached preparation outputs.

No audio inference runs here. Review state lives in song.review.json so song.json
keeps the shared contract shape without implying automatic timings were reviewed.
"""

import argparse
import hashlib
import json
from math import isfinite, log2
from pathlib import Path
from statistics import median
from .text import korean_practice_text, apply_cached_translations
from ml.scoring.live import score_phrase

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = "ml.pipeline.manifest"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def display_notes(reference, duration):
    """Draft note regions; pitch stays in Hz, quantization only finds boundaries."""
    if reference.get("notes"):
        return reference["notes"]
    hop, excluded = reference["hop_seconds"], reference.get("excluded", [])
    notes, values, first, previous = [], [], 0, None
    def finish(end):
        start, end = first * hop, min(duration, end * hop)
        if values and end - start >= 0.08 - 1e-9:
            notes.append({"start": round(start, 6), "end": min(duration, round(end, 6)), "hz": median(values)})
    for i, hz in enumerate([*reference["hz"], None]):
        t = i * hop
        valid = hz is not None and t < duration and not any(r["start"] <= t < r["end"] for r in excluded)
        note = round(69 + 12 * log2(hz / 440)) if valid else None
        if note != previous:
            finish(i)
            first, values, previous = i, [], note
        if valid:
            values.append(hz)
    return notes


def build_manifest(folder):
    folder = folder.resolve()
    metadata = read(folder / "preparation.json")
    reviewed_path = folder / "lyrics.reviewed.json"
    lyrics_reviewed = reviewed_path.is_file()
    track = read(reviewed_path if lyrics_reviewed else folder / "alignment/lyrics.aligned.json")
    apply_cached_translations(track["lines"], folder / "translations.json")
    reference = read(folder / "reference.pitch.json")
    duration = metadata.get("duration", metadata.get("duration_seconds"))
    if not isinstance(duration, (int, float)) or not isfinite(duration) or duration <= 0:
        raise ValueError("Invalid song duration")
    audio, hashes = {}, {}
    for role in ("vocals", "instrumental"):
        relative = metadata.get("playback_audio", {}).get(role) or metadata["audio"][role]
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise ValueError("Selected audio must exist inside the song directory")
        audio[role], hashes[role] = path.relative_to(folder).as_posix(), digest(path)
        expected = metadata.get("audio_checks", {}).get(role, {}).get("sha256")
        if expected and expected != hashes[role]:
            raise ValueError("Selected audio changed after preparation")
    if lyrics_reviewed:
        if (track.get("reviewed") is not True or track.get("status") != "ready"
                or track.get("id") != metadata["id"] or track.get("version") != metadata.get("version", 1)
                or track.get("audio_sha256") != hashes["instrumental"]):
            raise ValueError("Reviewed lyrics do not match the selected clip/version")
    elif track.get("source_audio_sha256") != hashes["vocals"]:
        raise ValueError("Lyrics belong to different vocal audio")
    if reference.get("source_audio_sha256") != hashes["vocals"]:
        raise ValueError("Lyrics/reference belong to different vocal audio")
    if track.get("instrumental_sha256", hashes["instrumental"]) != hashes["instrumental"]:
        raise ValueError("Lyric timeline belongs to different backing audio")
    if any(abs(data["duration"] - duration) > 0.001 for data in (track, reference)):
        raise ValueError("Cached analysis and selected clip durations differ")
    lines, previous = [], 0
    partial_lines = set(track.get("partial_line_indices", []))
    for line_index, item in enumerate(track["lines"]):
        if not previous <= item["start"] < item["end"] <= duration or not item["text"].strip():
            raise ValueError("Invalid or overlapping lyric lines")
        previous = item["end"]
        word_end = item["start"]
        for word in item.get("words", []):
            if not word_end <= word["start"] < word["end"] <= item["end"] or not word["text"].strip():
                raise ValueError("Invalid or overlapping lyric words")
            word_end = word["end"]
        lines.append({"start": item["start"], "end": item["end"], "text": item["text"],
                      "romanized": item.get("romanized", ""), "translation": item.get("translation", ""),
                      "practice_text": "" if line_index in partial_lines else korean_practice_text(item["text"]), "words": item.get("words", [])})
    if not lines:
        raise ValueError("No aligned lyric lines")
    hop, hz = reference["hop_seconds"], reference["hz"]
    if (not isinstance(hop, (int, float)) or not isfinite(hop) or hop <= 0
            or abs(len(hz) * hop - duration) > 2 * hop
            or any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v <= 0) for v in hz)):
        raise ValueError("Invalid reference pitch grid")
    excluded = []
    for region in reference.get("excluded", []):
        if not 0 <= region["start"] < region["end"] <= duration:
            raise ValueError("Invalid excluded region")
        excluded.append({**region, "reason": region.get("reason", "Fixed lyric-free region; listening review pending")})
    provenance = metadata.get("provenance", {})
    source_hash = provenance.get("source_audio_sha256") or next(
        (item["sha256"] for item in provenance.get("inputs", []) if Path(item["filename"]).suffix.lower() in {".mp3", ".wav", ".flac", ".m4a"}), None)
    start = provenance.get("clip_start_seconds", 0)
    phrases, dropped = [], []
    for i, line in enumerate(lines):
        seconds = score_phrase(reference, [], line["start"], line["end"])["scoreable_seconds"]
        if i in partial_lines or seconds < 0.5 - 1e-9:
            dropped.append({"id": f"p{i+1}", "line_index": i, "scoreable_seconds": seconds,
                            "reason": "partial clip boundary" if i in partial_lines else "under_0.5_seconds_scoreable"})
        else:
            phrases.append({"id": f"p{i+1}", "line_index": i, "start": line["start"], "end": line["end"]})
    manifest = {"id": metadata["id"], "version": metadata.get("version", 1),
                "title": metadata["title"], "artist": metadata["artist"], "language": metadata.get("language", "ko"),
                "duration": duration,
                "provenance": {"source_url": provenance.get("source_url") or metadata.get("source_url", ""),
                               "source_version": f"sha256:{source_hash}" if source_hash else "local-preparation",
                               "crop_start": start, "crop_end": start + duration},
                "audio": audio, "lines": lines,
                "phrases": phrases,
                "reference": {"hop_seconds": hop, "hz": hz, "notes": display_notes(reference, duration), "excluded": excluded}}
    review = {"generated_by": GENERATOR, "status": "draft", "reviewed": False,
              "lyrics_reviewed": lyrics_reviewed, "phrases_reviewed": False, "reference_reviewed": reference.get("reviewed") is True,
              "audio_sha256": hashes,
              "dropped_phrases": dropped,
              "minimum_scoreable_seconds": 0.5,
              "translations_reviewed": False,
              "partial_line_indices": sorted(partial_lines),
              "notes": "Automatic lyric/word timing, line-based phrases and display notes need listening review. Verify held-note ends, harmonies and octave errors before judging singers."}
    return manifest, review


def write_manifest(folder):
    folder = Path(folder)
    destination, review_path = folder / "song.json", folder / "song.review.json"
    if destination.exists():
        existing = read(review_path) if review_path.exists() else {}
        if (existing.get("generated_by") != GENERATOR or existing.get("reviewed") is not False
                or existing.get("manifest_sha256") != digest(destination)):
            raise ValueError("Preserve the existing reviewed or manually edited manifest")
    manifest, review = build_manifest(folder)
    content = json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    review["manifest_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    # Publish review state first so the API cannot treat this draft as reviewed.
    for path, text in [(review_path, json.dumps(review, indent=2) + "\n"), (destination, content)]:
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "ml/data")
    args = parser.parse_args()
    data = args.data_dir.resolve()
    folders = sorted(p for p in data.iterdir() if p.is_dir() and (p / "preparation.json").is_file()) if args.all else [data / args.id]
    for folder in folders:
        if not folder.resolve().is_relative_to(data):
            parser.error("Song folder must stay inside the data directory")
        manifest = write_manifest(folder)
        print(f"{manifest['id']}: song.json ({len(manifest['lines'])} lines, {len(manifest['reference']['notes'])} draft notes)")


if __name__ == "__main__":
    main()
