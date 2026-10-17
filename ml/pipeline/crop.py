"""Create a separate short demo with matching cropped audio and rebased timing."""

import argparse
import copy
import json
from math import isfinite
from pathlib import Path
import subprocess
import tempfile

from .audio import decoded_frames
from .common import ROOT, digest, read
from .manifest import write_manifest


def rebase_lines(track, start, end):
    lines, partial, source_indices = [], [], []
    for index, original in enumerate(track["lines"]):
        if original["end"] <= start or original["start"] >= end:
            continue
        line = copy.deepcopy(original)
        clipped = original["start"] < start or original["end"] > end
        indices = [i for i, word in enumerate(original.get("words", [])) if word["end"] > start and word["start"] < end]
        line["words"] = [{**original["words"][i], "start": round(max(start, original["words"][i]["start"]) - start, 6),
                          "end": round(min(end, original["words"][i]["end"]) - start, 6)} for i in indices]
        line["start"], line["end"] = round(max(start, original["start"]) - start, 6), round(min(end, original["end"]) - start, 6)
        if clipped:
            partial.append(len(lines))
            if indices:
                line["text"] = " ".join(word["text"] for word in line["words"])
                romanized = original.get("romanized", "").split()
                line["romanized"] = " ".join(romanized[i] for i in indices) if len(romanized) == len(original["words"]) else ""
            line["practice_text"] = ""
        lines.append(line)
        source_indices.append(index)
    sections = sorted({0, *(i for i, source in enumerate(source_indices) if source in track.get("section_starts", []))}) if lines else []
    return lines, partial, sections


def crop_song(song_id, destination_id, start, duration, data_dir=ROOT / "ml/data"):
    import imageio_ffmpeg
    import soundfile as sf
    data_dir = Path(data_dir).resolve()
    source, destination = (data_dir / song_id).resolve(), (data_dir / destination_id).resolve()
    if (source.parent != data_dir or destination.parent != data_dir or destination.exists()
            or not isfinite(start) or not isfinite(duration) or start < 0 or duration <= 0):
        raise ValueError("Use a new song ID and finite positive crop bounds inside the data directory")
    metadata, track, reference = read(source / "preparation.json"), read(source / "alignment/lyrics.aligned.json"), read(source / "reference.pitch.json")
    end = start + duration
    if end > metadata.get("duration", metadata.get("duration_seconds")):
        raise ValueError("Crop exceeds the prepared song")
    hop = reference["hop_seconds"]
    if abs(start / hop - round(start / hop)) > 1e-6 or abs(duration / hop - round(duration / hop)) > 1e-6:
        raise ValueError("Choose crop bounds on the reference pitch grid")
    work = (data_dir / ".preparing").resolve()
    if not work.is_relative_to(data_dir):
        raise ValueError("Crop workspace must be inside ml/data")
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{destination_id}-", dir=work) as temporary:
        workspace = Path(temporary).resolve()
        if not workspace.is_relative_to(work):
            raise ValueError("Invalid crop workspace")
        output = workspace / destination_id
        (output / "alignment").mkdir(parents=True)
        checks, frames = {}, round(duration * 44100)
        for role in ("vocals", "instrumental"):
            relative = metadata.get("playback_audio", {}).get(role) or metadata["audio"][role]
            original = (source / relative).resolve()
            if not original.is_relative_to(source) or sf.info(original).samplerate != 44100:
                raise ValueError("Crop expects selected 44.1 kHz audio inside the song directory")
            target = output / f"{role}.mp3"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-n", "-i", str(original),
                            "-af", f"atrim=start_sample={round(start*44100)}:end_sample={round(end*44100)},asetpts=PTS-STARTPTS",
                            "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "320k", str(target)], check=True)
            if decoded_frames(target) != frames:
                raise ValueError("Cropped MP3 does not have the exact requested frame count")
            checks[role] = {"sha256": digest(target), "decoded_frames_44100_stereo": frames}
        lines, partial, sections = rebase_lines(track, start, end)
        if not lines:
            raise ValueError("No lyrics intersect the crop")
        aligned = {"status": "alignment_draft", "reviewed": False, "duration": duration,
                   "source_audio_sha256": checks["vocals"]["sha256"], "instrumental_sha256": checks["instrumental"]["sha256"],
                   "lines": lines, "partial_line_indices": partial, "section_starts": sections,
                   "notes": "Times rebased from the parent draft. Boundary fragments are display-only, excluded from practice and grading. Their translations retain parent-line context."}
        (output / "alignment/lyrics.aligned.json").write_text(json.dumps(aligned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        first, count = round(start / hop), round(duration / hop)
        cropped_reference = {**reference, "duration": duration, "source_audio_sha256": checks["vocals"]["sha256"],
                             "hz": reference["hz"][first:first+count]}
        if "periodicity" in reference:
            cropped_reference["periodicity"] = reference["periodicity"][first:first+count]
        for name in ("notes", "excluded"):
            cropped_reference[name] = [{**region, "start": round(max(start, region["start"]) - start, 6),
                                        "end": round(min(end, region["end"]) - start, 6)} for region in reference.get(name, [])
                                       if region["end"] > start and region["start"] < end]
        (output / "reference.pitch.json").write_text(json.dumps(cropped_reference, indent=2) + "\n", encoding="utf-8")
        parent_start = metadata.get("provenance", {}).get("clip_start_seconds", 0)
        prepared = {**metadata, "id": destination_id, "version": 1, "title": metadata["title"] + f" ({duration:g}s demo)",
                    "duration_seconds": duration, "audio": {role: f"{role}.mp3" for role in checks},
                    "playback_audio": {role: f"{role}.mp3" for role in checks}, "audio_checks": checks,
                    "provenance": {**metadata.get("provenance", {}), "clip_start_seconds": parent_start + start,
                                   "clip_source_id": song_id, "clip_source_version": metadata.get("version", 1),
                                   "requested_duration_seconds": duration},
                    "review_status": {**metadata.get("review_status", {}), "crop": "exact_frame_count_verified_listening_review_pending"}}
        prepared.pop("duration", None)
        (output / "preparation.json").write_text(json.dumps(prepared, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "lyrics.supplied.txt").write_text("\n".join(line["text"] for line in lines) + "\n", encoding="utf-8")
        manifest = write_manifest(output)
        review_path = output / "song.review.json"
        review = read(review_path)
        review["partial_line_indices"] = partial
        review["notes"] += " Boundary translations retain parent-line context. Backing/harmony annotations still require review."
        review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        output.rename(destination)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--song", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--duration", type=float, default=30)
    args = parser.parse_args()
    result = crop_song(args.song, args.id, args.start, args.duration)
    print(f"{result['id']}: {result['duration']}s, {len(result['lines'])} display lines, {len(result['phrases'])} scoreable phrases")


if __name__ == "__main__":
    main()
