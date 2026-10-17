"""Prepare a new local song: selected stems, supplied lyrics, alignment and pitch.

Existing song folders are never overwritten. A failed run is cleaned up before
it can appear in the catalog. Run with the pipeline Python environment.
"""

import argparse
import json
import os
from math import isfinite
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from .audio import decoded_frames
from .common import DATA, ROOT, digest


def command(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def export_mp3(source, destination):
    import imageio_ffmpeg
    if source.suffix.lower() == ".mp3":
        shutil.copyfile(source, destination)
    else:
        command(imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-n", "-i", source,
                "-vn", "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "320k", destination)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--id", required=True)
    result.add_argument("--title", required=True)
    result.add_argument("--artist", required=True)
    result.add_argument("--lyrics", type=Path, required=True, help="UTF-8 text, one lyric line per line")
    result.add_argument("--clip", type=Path, help="Source with lead vocals; separates two stem estimates")
    result.add_argument("--vocals", type=Path, help="Reuse a selected vocal stem instead of separation")
    result.add_argument("--instrumental", type=Path, help="Reuse a selected instrumental, without mastering again")
    result.add_argument("--source-url", default="")
    result.add_argument("--start", type=float, default=0)
    result.add_argument("--duration", type=float)
    result.add_argument("--data-dir", type=Path, help="Output catalog root (defaults to ml/data)")
    result.add_argument("--separation-python", type=Path, help="Python interpreter with Demucs installed")
    result.add_argument("--language", choices=("ko", "en"), default="ko")
    return result


def validate_inputs(args):
    """Check source selection and protect existing preparations before processing."""
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", args.id):
        raise ValueError("Use a song ID containing letters, digits, underscores or hyphens")
    selected = bool(args.vocals and args.instrumental)
    if (bool(args.vocals) != bool(args.instrumental) or bool(args.clip) == selected):
        raise ValueError("Supply either --clip or both --vocals and --instrumental")
    if not isfinite(args.start) or args.start < 0 or (args.duration is not None and (not isfinite(args.duration) or args.duration <= 0)):
        raise ValueError("Crop start must be nonnegative and duration must be positive")
    if selected and (args.start or args.duration is not None):
        raise ValueError("Crop only a --clip; selected stems must already share the intended timeline")
    inputs = [args.lyrics, *([args.vocals, args.instrumental] if selected else [args.clip])]
    for path in inputs:
        if not path.is_file():
            raise ValueError(f"Input file does not exist: {path}")
    if not args.lyrics.read_text(encoding="utf-8-sig").strip():
        raise ValueError("Supplied lyric text is empty")
    destination = (args.data_dir or DATA).resolve() / args.id
    if destination.exists():
        raise ValueError("Song ID already exists; choose a new ID to preserve audio and hand corrections")
    configured = args.separation_python or os.getenv("JUST_SING_SEPARATION_PYTHON")
    candidates = [ROOT / "ml/pipeline/separation/.venv/bin/python",
                  ROOT / "ml/pipeline/separation/.venv/Scripts/python.exe"]
    separation_python = Path(configured).expanduser().absolute() if configured else next(
        (path for path in candidates if path.is_file()), candidates[-1])
    if not selected and not separation_python.is_file():
        raise ValueError("Install the separate Demucs environment first (see ml/pipeline/README.md)")
    return inputs, destination, separation_python

def select_stems(args, workspace, separation_python):
    """Reuse selected stems or apply the baseline-vocal/residual-backing recipe."""
    processing = {}
    if args.vocals and args.instrumental:
        vocal_input, backing_input = args.vocals, args.instrumental
    else:
        # Keep the original vocal estimate, while using the preferred
        # fine-tuned residual + mastering recipe for the backing.
        recipes = [
            ("baseline", "htdemucs", 0.25, "predicted"),
            ("backing", "04573f0d", 0.5, "residual"),
        ]
        for name, model, overlap, method in recipes:
            parameters = [separation_python, "-m", "ml.pipeline.separate", "--input", args.clip,
                          "--output", workspace / name, "--model", model, "--overlap", overlap,
                          "--instrumental-method", method, "--start", args.start]
            if args.duration is not None:
                parameters += ["--duration", args.duration]
            command(*parameters)
            processing[name] = json.loads((workspace / name / "separation.json").read_text())
        vocal_input = workspace / "baseline/stems/htdemucs/vocals.wav"
        from .enhance import enhance
        mastered = workspace / "mastered"
        mastered.mkdir()
        processing["mastering"] = enhance(workspace / "backing/stems/04573f0d/instrumental-residual.wav",
                                           mastered, -16, 25)
        backing_input = mastered / processing["mastering"]["mp3"]
    return vocal_input, backing_input, processing


def prepare(args):
    inputs, destination, separation_python = validate_inputs(args)
    data = destination.parent
    work_root = (data / ".preparing").resolve()
    if not work_root.is_relative_to(data):
        raise ValueError("Preparation directory must stay inside the output catalog")
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{args.id}-", dir=work_root) as temporary:
        workspace = Path(temporary).resolve()
        if not workspace.is_relative_to(work_root):
            raise ValueError("Invalid temporary workspace")
        output = workspace / args.id
        output.mkdir()
        print("JUST_SING_STAGE:separating", flush=True)
        vocal_input, backing_input, processing = select_stems(args, workspace, separation_python)
        print("JUST_SING_STAGE:encoding", flush=True)
        for role, source in [("vocals", vocal_input), ("instrumental", backing_input)]:
            export_mp3(source, output / f"{role}.mp3")
        counts = {role: decoded_frames(output / f"{role}.mp3") for role in ("vocals", "instrumental")}
        if not counts["vocals"] or counts["vocals"] != counts["instrumental"]:
            raise ValueError("Selected stems have different decoded lengths; align/crop them before preparation")
        duration = counts["vocals"] / 44100
        shutil.copyfile(args.lyrics, output / "lyrics.supplied.txt")
        print("JUST_SING_STAGE:aligning", flush=True)
        command(sys.executable, "-m", "ml.pipeline.align_lyrics", "--audio", output / "vocals.mp3",
                "--instrumental", output / "instrumental.mp3", "--lyrics", output / "lyrics.supplied.txt",
                "--output", output / "alignment")
        print("JUST_SING_STAGE:pitch", flush=True)
        command(sys.executable, "-m", "ml.pipeline.reference", "--audio", output / "vocals.mp3",
                "--output", output / "reference.pitch.json")
        metadata = {"id": args.id, "version": 1, "title": args.title, "artist": args.artist,
                    "language": args.language, "duration_seconds": duration,
                    "audio": {role: f"{role}.mp3" for role in counts},
                    "provenance": {"source_url": args.source_url, "clip_start_seconds": args.start,
                                   "requested_duration_seconds": args.duration,
                                   "inputs": [{"filename": path.name, "sha256": digest(path)} for path in inputs]},
                    "audio_checks": {role: {"sha256": digest(output / f"{role}.mp3"),
                                             "decoded_frames_44100_stereo": count} for role, count in counts.items()},
                    "processing": processing,
                    "review_status": {"lyrics": "supplied_text_automatic_alignment_needs_listening_review",
                                      "reference_pitch": "unreviewed", "separation": "needs_listening_review"}}
        (output / "preparation.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        print("JUST_SING_STAGE:manifest", flush=True)
        from .manifest import write_manifest
        write_manifest(output)
        # Publish only after both offline jobs succeed. No overwrite of existing releases.
        if destination.exists():
            raise ValueError("Song ID already exists; choose a new ID")
        output.rename(destination)
    return destination


def main():
    cli = parser()
    try:
        output = prepare(cli.parse_args())
    except ValueError as error:
        cli.error(str(error))
    print(f"Prepared local draft: {output}")
    print(f"Preview: http://127.0.0.1:8000/live/?song={output.name}")


if __name__ == "__main__":
    main()
